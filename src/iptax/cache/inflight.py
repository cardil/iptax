"""In-flight report caching for collecting data across multiple steps.

This module manages temporary storage of report data during the collection
and review process. The cache allows users to:
- Collect data (Did PRs, Workday hours) without immediately running AI/review
- Resume work on a report after interruption
- Review and modify AI judgments before final report generation
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from iptax.models import INFLIGHT_SCHEMA_VERSION, InFlightReport
from iptax.utils.env import get_cache_dir

logger = logging.getLogger(__name__)


# State indicators
STATE_COMPLETE = "✓"
STATE_PENDING = "○"
STATE_INCOMPLETE = "⚠"
STATE_SKIPPED = "-"


@dataclass
class ReportState:
    """State of an in-flight report for display purposes.

    Attributes:
        did: Did collection state
        workday: Workday collection state
        ai: AI filtering state
        reviewed: Review completion state
        status: Human-readable status message
    """

    did: str
    workday: str
    ai: str
    reviewed: str
    status: str

    @classmethod
    def from_report(
        cls, report: InFlightReport, workday_enabled: bool = True
    ) -> "ReportState":
        """Derive state from an InFlightReport.

        Args:
            report: In-flight report to analyze
            workday_enabled: Whether Workday integration is enabled

        Returns:
            ReportState with derived states and status
        """
        # Did collection state
        did = STATE_COMPLETE if report.changes else STATE_PENDING

        # Workday collection state
        if report.total_hours is not None:
            workday = STATE_COMPLETE if report.workday_validated else STATE_INCOMPLETE
        elif workday_enabled:
            workday = STATE_PENDING
        else:
            workday = STATE_SKIPPED

        # AI filtering state
        ai = STATE_COMPLETE if report.judgments else STATE_PENDING

        # Review state
        reviewed = STATE_COMPLETE if report.is_reviewed() else STATE_PENDING

        # Derive overall status
        status = cls._derive_status(did, workday, ai, reviewed)

        return cls(
            did=did,
            workday=workday,
            ai=ai,
            reviewed=reviewed,
            status=status,
        )

    @staticmethod
    def _derive_status(did: str, workday: str, ai: str, reviewed: str) -> str:
        """Derive human-readable status from individual states.

        Args:
            did: Did collection state
            workday: Workday collection state
            ai: AI filtering state
            reviewed: Review completion state

        Returns:
            Human-readable status message
        """
        # Check for incomplete workday first (warning state)
        if workday == STATE_INCOMPLETE:
            return "Workday incomplete"

        # Check if ready for dist
        did_ready = did == STATE_COMPLETE
        # Workday is ready if complete (hours available) or explicitly skipped
        # Accept COMPLETE even if workday is disabled (data from earlier run,
        # or hours manually provided by user)
        workday_ready = workday in (STATE_COMPLETE, STATE_SKIPPED)
        ai_ready = ai == STATE_COMPLETE
        reviewed_ready = reviewed == STATE_COMPLETE

        if did_ready and workday_ready and ai_ready and reviewed_ready:
            return "Ready for dist"

        # Determine what's still needed
        if not did_ready:
            return "Collecting"

        if not workday_ready:
            return "Needs Workday"

        return "Needs AI filtering" if not ai_ready else "Needs review"


class InFlightCache:
    """Manages in-flight report cache storage.

    The cache is stored in ~/.cache/iptax/inflight/ as JSON files,
    one per month being worked on.

    Examples:
        # Use default path
        cache = InFlightCache()
        report = cache.load("2024-11")

        # Use custom path (for testing)
        cache = InFlightCache(cache_dir="/tmp/test-cache")
        cache.save(report)
    """

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        """Initialize cache manager.

        Args:
            cache_dir: Custom cache directory. If None, uses default
                (~/.cache/iptax/inflight or $XDG_CACHE_HOME/iptax/inflight)
        """
        if cache_dir is None:
            cache_dir = self._get_default_cache_dir()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _get_default_cache_dir() -> Path:
        """Get default cache directory for in-flight reports.

        Returns:
            Path to inflight cache directory
        """
        return get_cache_dir() / "inflight"

    @staticmethod
    def _validate_month_format(month: str) -> None:
        """Validate month format to prevent path traversal.

        Args:
            month: Month string to validate

        Raises:
            ValueError: If month format is invalid
        """
        if not re.match(r"^\d{4}-\d{2}$", month):
            raise ValueError(f"Invalid month format: {month}. Expected YYYY-MM.")

    def _get_cache_path(self, month: str) -> Path:
        """Get path to cache file for a month.

        Args:
            month: Month in YYYY-MM format

        Returns:
            Path to the cache file

        Raises:
            ValueError: If month format is invalid (path traversal prevention)
        """
        self._validate_month_format(month)
        return self.cache_dir / f"{month}.json"

    def exists(self, month: str) -> bool:
        """Check if in-flight cache exists for a month with compatible schema.

        Args:
            month: Month in YYYY-MM format

        Returns:
            True if cache exists and has compatible schema version,
            False if missing or has incompatible schema
        """
        cache_path = self._get_cache_path(month)
        if not cache_path.exists():
            return False

        # Check schema version compatibility
        try:
            with cache_path.open("r") as f:
                data = json.load(f)
            schema_version = data.get("schema_version")
        except (json.JSONDecodeError, OSError):
            # Corrupted file or read error - treat as non-existent
            return False
        else:
            return bool(schema_version == INFLIGHT_SCHEMA_VERSION)

    def load(self, month: str) -> InFlightReport | None:
        """Load in-flight report from cache.

        Args:
            month: Month in YYYY-MM format

        Returns:
            InFlightReport if exists and schema version matches, None otherwise
            (also None for corrupted files or incompatible schema versions)
        """
        cache_path = self._get_cache_path(month)
        if not cache_path.exists():
            return None

        try:
            with cache_path.open("r") as f:
                data = json.load(f)

            # Check schema version compatibility
            schema_version = data.get("schema_version")
            if schema_version != INFLIGHT_SCHEMA_VERSION:
                logger.warning(
                    "Incompatible cache schema version in %s: "
                    "expected %s, got %s. Cache will be ignored.",
                    cache_path,
                    INFLIGHT_SCHEMA_VERSION,
                    schema_version,
                )
                return None

            return InFlightReport(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("Corrupted cache file %s: %s", cache_path, e)
            return None

    def save(self, report: InFlightReport) -> Path:
        """Save in-flight report to cache.

        Args:
            report: Report to save

        Returns:
            Path where report was saved
        """
        cache_path = self._get_cache_path(report.month)

        # Set schema version to current before saving
        report.schema_version = INFLIGHT_SCHEMA_VERSION

        with cache_path.open("w") as f:
            json.dump(
                report.model_dump(mode="json"),
                f,
                indent=2,
                default=str,
            )

        # Set secure permissions
        cache_path.chmod(0o600)

        return cache_path

    def delete(self, month: str) -> bool:
        """Delete in-flight cache for a month.

        Args:
            month: Month in YYYY-MM format

        Returns:
            True if cache was deleted, False if it didn't exist
        """
        cache_path = self._get_cache_path(month)
        if cache_path.exists():
            cache_path.unlink()
            return True
        return False

    def list_all(self) -> list[str]:
        """List all months with in-flight cache.

        Returns:
            List of month strings (YYYY-MM format), sorted
        """
        if not self.cache_dir.exists():
            return []

        months = []
        for cache_file in self.cache_dir.glob("*.json"):
            month = cache_file.stem
            # Only include valid YYYY-MM format files
            if re.match(r"^\d{4}-\d{2}$", month):
                months.append(month)

        return sorted(months)

    def clear_all(self) -> int:
        """Clear all in-flight caches.

        Returns:
            Number of caches deleted
        """
        count = 0
        for month in self.list_all():
            if self.delete(month):
                count += 1
        return count


# Convenience functions


def get_inflight_cache() -> InFlightCache:
    """Get an InFlightCache instance using default paths.

    Returns:
        InFlightCache instance with default cache directory
    """
    return InFlightCache()


def get_inflight_cache_dir() -> Path:
    """Get default path for in-flight cache directory.

    Returns:
        Path to the default inflight cache directory
    """
    return InFlightCache._get_default_cache_dir()
