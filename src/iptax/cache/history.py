"""History tracking for IP tax reports.

This module manages the history of generated reports, tracking cutoff dates
to ensure no changes are duplicated or missed between reports.

The history file is stored in JSON format at ~/.cache/iptax/history.json
"""

import json
from datetime import date, datetime
from pathlib import Path

from pydantic import ValidationError

from iptax.models import HistoryEntry
from iptax.utils.env import get_cache_dir


class HistoryError(Exception):
    """Base exception for history-related errors."""

    pass


class HistoryCorruptedError(HistoryError):
    """History file is corrupted and cannot be parsed."""

    pass


class HistoryManager:
    """Manages report history.

    The history file tracks when reports were generated and what cutoff
    dates were used, ensuring no changes are duplicated or missed between
    monthly reports.

    Examples:
        # Use default path
        manager = HistoryManager()
        manager.load()
        entries = manager.get_all_entries()

        # Add entry after report completes
        manager.add_entry("2024-10", date(2024, 10, 25))
        manager.save()
    """

    def __init__(self, history_path: Path | str | None = None) -> None:
        """Initialize history manager.

        Args:
            history_path: Path to history.json. If None, uses default
                location (~/.cache/iptax/history.json)
        """
        self.history_path = (
            Path(history_path) if history_path else self._get_default_history_path()
        )
        self._history: dict[str, HistoryEntry] = {}
        self._loaded = False

    @staticmethod
    def _get_default_history_path() -> Path:
        """Get default path for history.json.

        Returns:
            Path to history.json
        """
        return get_cache_dir() / "history.json"

    def load(self) -> None:
        """Load history from JSON file.

        If the file doesn't exist, starts with empty history.
        If the file is corrupted, raises HistoryCorruptedError.

        Raises:
            HistoryCorruptedError: If history file cannot be parsed
        """
        if not self.history_path.exists():
            self._history = {}
            self._loaded = True
            return

        try:
            with self.history_path.open(encoding="utf-8") as f:
                data = json.load(f)

            # Parse each month's entry using Pydantic
            self._history = {}
            for month, entry_data in data.items():
                try:
                    # Handle date string conversion
                    if isinstance(entry_data.get("last_cutoff_date"), str):
                        entry_data["last_cutoff_date"] = date.fromisoformat(
                            entry_data["last_cutoff_date"]
                        )
                    if isinstance(entry_data.get("generated_at"), str):
                        entry_data["generated_at"] = datetime.fromisoformat(
                            entry_data["generated_at"]
                        )
                    if entry_data.get("regenerated_at") and isinstance(
                        entry_data["regenerated_at"], str
                    ):
                        entry_data["regenerated_at"] = datetime.fromisoformat(
                            entry_data["regenerated_at"]
                        )
                    self._history[month] = HistoryEntry(**entry_data)
                except ValidationError as e:
                    raise HistoryCorruptedError(
                        f"Invalid history entry for {month}: {e}"
                    ) from e

            self._loaded = True

        except json.JSONDecodeError as e:
            raise HistoryCorruptedError(
                f"Cannot parse {self.history_path}: {e}\n\n"
                "The history file has invalid JSON syntax."
            ) from e
        except HistoryCorruptedError:
            raise
        except Exception as e:
            raise HistoryCorruptedError(
                f"Failed to load history from {self.history_path}: {e}"
            ) from e

    def save(self) -> None:
        """Save history to JSON file.

        Creates parent directory if it doesn't exist.
        Sets file permissions to 600 (owner read/write only).

        Raises:
            HistoryError: If save operation fails
        """
        try:
            # Create parent directory if needed
            self.history_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert history to dict for JSON serialization
            data = {}
            for month, entry in self._history.items():
                entry_dict = {
                    "last_cutoff_date": entry.last_cutoff_date.isoformat(),
                    "generated_at": entry.generated_at.isoformat(),
                }
                if entry.regenerated_at:
                    entry_dict["regenerated_at"] = entry.regenerated_at.isoformat()
                data[month] = entry_dict

            # Write to file with pretty formatting
            with self.history_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")  # Add trailing newline

            # Set secure permissions
            self.history_path.chmod(0o600)

        except Exception as e:
            raise HistoryError(f"Failed to save history: {e}") from e

    def _ensure_loaded(self) -> None:
        """Ensure history is loaded before operations."""
        if not self._loaded:
            self.load()

    def get_all_entries(self) -> dict[str, HistoryEntry]:
        """Get all history entries.

        Returns:
            Dictionary mapping month (YYYY-MM) to HistoryEntry
        """
        self._ensure_loaded()
        return self._history.copy()

    def add_entry(self, month: str, cutoff_date: date) -> None:
        """Add a history entry for a completed report.

        Args:
            month: Month in YYYY-MM format
            cutoff_date: Last cutoff date for this report

        Raises:
            ValueError: If month format is invalid
        """
        self._ensure_loaded()

        # Validate and normalize month format
        try:
            parsed_month = datetime.strptime(month, "%Y-%m")
        except ValueError as e:
            raise ValueError(f"Invalid month format '{month}', expected YYYY-MM") from e

        # Normalize to YYYY-MM format
        month_key = parsed_month.strftime("%Y-%m")
        now = datetime.now()

        # Check if this is a regeneration
        if month_key in self._history:
            existing = self._history[month_key]
            self._history[month_key] = HistoryEntry(
                last_cutoff_date=cutoff_date,
                generated_at=existing.generated_at,
                regenerated_at=now,
            )
        else:
            self._history[month_key] = HistoryEntry(
                last_cutoff_date=cutoff_date,
                generated_at=now,
            )


# Convenience functions


def get_history_path() -> Path:
    """Get default path for history.json.

    Returns:
        Path to the default history file location
    """
    return HistoryManager._get_default_history_path()


def get_last_report_date() -> date | None:
    """Get the cutoff date from the most recent report.

    Used by timing.py to calculate the Did date range start.

    Returns:
        Date of the last report's cutoff, or None if no reports exist
    """
    manager = HistoryManager()
    manager.load()

    entries = manager.get_all_entries()
    if not entries:
        return None

    # Get the most recent entry
    latest_month = max(entries.keys())
    return entries[latest_month].last_cutoff_date


def save_report_date(report_date: date, month: str) -> None:
    """Save a report date to history after report completes.

    Args:
        report_date: The cutoff date for the report
        month: The month being reported (YYYY-MM format)
    """
    manager = HistoryManager()
    manager.load()
    manager.add_entry(month, report_date)
    manager.save()
