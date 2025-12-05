"""In-flight report caching for collecting data across multiple steps.

This module manages temporary storage of report data during the collection
and review process. The cache allows users to:
- Collect data (Did PRs, Workday hours) without immediately running AI/review
- Resume work on a report after interruption
- Review and modify AI judgments before final report generation
"""

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from iptax.models import InFlightReport
from iptax.utils.env import get_cache_dir

logger = logging.getLogger(__name__)


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

    def _get_cache_path(self, month: str) -> Path:
        """Get path to cache file for a month.

        Args:
            month: Month in YYYY-MM format

        Returns:
            Path to the cache file
        """
        return self.cache_dir / f"{month}.json"

    def exists(self, month: str) -> bool:
        """Check if in-flight cache exists for a month.

        Args:
            month: Month in YYYY-MM format

        Returns:
            True if cache exists
        """
        return self._get_cache_path(month).exists()

    def load(self, month: str) -> InFlightReport | None:
        """Load in-flight report from cache.

        Args:
            month: Month in YYYY-MM format

        Returns:
            InFlightReport if exists, None otherwise (also None for corrupted files)
        """
        cache_path = self._get_cache_path(month)
        if not cache_path.exists():
            return None

        try:
            with cache_path.open("r") as f:
                data = json.load(f)
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
