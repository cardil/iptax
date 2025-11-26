"""History tracking for IP tax reports.

This module manages the history of generated reports, tracking cutoff dates
to ensure no changes are duplicated or missed between reports. It provides
date range calculation and handles first-time setup.
"""

import shutil
import tomllib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import NoReturn

import questionary
import tomli_w
from pydantic import ValidationError

from iptax.models import HistoryEntry
from iptax.utils.env import get_cache_dir, get_month_end_date

# Constants
DECEMBER_MONTH = 12


class HistoryError(Exception):
    """Base exception for history-related errors."""

    pass


class HistoryCorruptedError(HistoryError):
    """History file is corrupted and cannot be parsed."""

    pass


class HistoryManager:
    """Manages report history and date range calculations.

    The history file tracks when reports were generated and what cutoff
    dates were used, ensuring no changes are duplicated or missed between
    monthly reports.

    Examples:
        # Use default path
        manager = HistoryManager()
        start, end = manager.get_date_range("2024-11")

        # Use custom path (useful for testing)
        manager = HistoryManager(history_path="/tmp/test-history.toml")
        manager.add_entry("2024-10", date(2024, 10, 25))
    """

    def __init__(self, history_path: Path | str | None = None) -> None:
        """Initialize history manager.

        Args:
            history_path: Path to history.toml. If None, uses default
                location (~/.cache/iptax/history.toml or
                $XDG_CACHE_HOME/iptax/history.toml)
        """
        self.history_path = (
            Path(history_path) if history_path else self._get_default_history_path()
        )
        self._history: dict[str, HistoryEntry] = {}
        self._loaded = False

    @staticmethod
    def _get_default_history_path() -> Path:
        """Get default path for history.toml.

        Respects XDG_CACHE_HOME and HOME environment variables.

        Returns:
            Path to history.toml
        """
        return get_cache_dir() / "history.toml"

    def load(self) -> None:
        """Load history from TOML file.

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
            with self.history_path.open("rb") as f:
                data = tomllib.load(f)

            # Parse each month's entry using Pydantic
            self._history = {}
            for month, entry_data in data.items():
                try:
                    self._history[month] = HistoryEntry(**entry_data)
                except ValidationError as e:
                    raise HistoryCorruptedError(
                        f"Invalid history entry for {month}: {e}"
                    ) from e

            self._loaded = True

        except tomllib.TOMLDecodeError as e:
            raise HistoryCorruptedError(
                f"Cannot parse {self.history_path}: {e}\n\n"
                "The history file has invalid TOML syntax."
            ) from e
        except HistoryCorruptedError:
            raise
        except Exception as e:
            raise HistoryCorruptedError(
                f"Failed to load history from {self.history_path}: {e}"
            ) from e

    def save(self) -> None:
        """Save history to TOML file.

        Creates parent directory if it doesn't exist.
        Sets file permissions to 600 (owner read/write only).

        Raises:
            HistoryError: If save operation fails
        """
        try:
            # Create parent directory if needed
            self.history_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert history to dict for TOML serialization
            data = {}
            for month, entry in self._history.items():
                data[month] = entry.model_dump(mode="python", exclude_none=True)

            # Write to file
            with self.history_path.open("wb") as f:
                tomli_w.dump(data, f)

            # Set secure permissions
            self.history_path.chmod(0o600)

        except Exception as e:
            raise HistoryError(f"Failed to save history: {e}") from e

    def _ensure_loaded(self) -> None:
        """Ensure history is loaded before operations."""
        if not self._loaded:
            self.load()

    def has_entry(self, month: str) -> bool:
        """Check if a report exists for the given month.

        Args:
            month: Month in YYYY-MM format

        Returns:
            True if report entry exists for this month
        """
        self._ensure_loaded()
        return month in self._history

    def get_entry(self, month: str) -> HistoryEntry | None:
        """Get history entry for a specific month.

        Args:
            month: Month in YYYY-MM format

        Returns:
            HistoryEntry if exists, None otherwise
        """
        self._ensure_loaded()
        return self._history.get(month)

    def get_all_entries(self) -> dict[str, HistoryEntry]:
        """Get all history entries.

        Returns:
            Dictionary mapping month (YYYY-MM) to HistoryEntry
        """
        self._ensure_loaded()
        return self._history.copy()

    def get_previous_entry(self, month: str) -> HistoryEntry | None:
        """Get the most recent entry before the given month.

        Args:
            month: Month in YYYY-MM format

        Returns:
            Most recent HistoryEntry before this month, or None if no previous entries
        """
        self._ensure_loaded()

        if not self._history:
            return None

        # Sort months in descending order
        sorted_months = sorted(self._history.keys(), reverse=True)

        # Find first month before the given month
        for prev_month in sorted_months:
            if prev_month < month:
                return self._history[prev_month]

        return None

    def add_entry(
        self,
        month: str,
        cutoff_date: date,
        regenerate: bool = False,
    ) -> None:
        """Add or update a history entry for a month.

        Args:
            month: Month in YYYY-MM format
            cutoff_date: Last cutoff date for this report
            regenerate: If True, updates regenerated_at timestamp

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
        now = datetime.now(UTC)

        if month_key in self._history and regenerate:
            # Update existing entry with regeneration timestamp and cutoff date
            entry = self._history[month_key]
            entry.last_cutoff_date = cutoff_date
            entry.regenerated_at = now
        else:
            # Create new entry
            self._history[month_key] = HistoryEntry(
                last_cutoff_date=cutoff_date,
                generated_at=now,
            )

    def _prompt_first_cutoff(self, default_date: date | None = None) -> date:
        """Prompt user for previous month's cutoff date.

        Args:
            default_date: Default cutoff date to suggest

        Returns:
            User-provided cutoff date
        """
        questionary.print(
            "\nThis is your first report. To calculate the date range,\n"
            "I need to know when your previous report ended.\n",
            style="yellow",
        )

        # Use default date or calculate reasonable default (25th of previous month)
        if default_date is None:
            today = date.today()
            # Get previous month
            if today.month == 1:
                prev_month = 12
                prev_year = today.year - 1
            else:
                prev_month = today.month - 1
                prev_year = today.year

            default_date = date(prev_year, prev_month, 25)

        default_str = default_date.strftime("%Y-%m-%d")

        while True:
            response = questionary.text(
                f"Enter the last cutoff date (YYYY-MM-DD) [{default_str}]:",
                default=default_str,
            ).ask()

            if response is None:  # User cancelled
                raise KeyboardInterrupt("User cancelled operation")

            if not response.strip():
                response = default_str

            try:
                cutoff = datetime.strptime(response.strip(), "%Y-%m-%d").date()
            except ValueError:
                questionary.print(
                    f"Error: Invalid date format '{response}'. Please use YYYY-MM-DD.",
                    style="red",
                )
                continue

            # Validate date is not in the future
            if cutoff > date.today():
                questionary.print(
                    "Error: Cutoff date cannot be in the future.",
                    style="red",
                )
                continue
            return cutoff

    def get_date_range(
        self,
        month: str,
        prompt_first: bool = True,
    ) -> tuple[date, date]:
        """Calculate date range for a report.

        For the first report, prompts user for previous cutoff date.
        For subsequent reports, uses previous report's cutoff + 1 day.

        Args:
            month: Month in YYYY-MM format
            prompt_first: If True, prompts for first cutoff. If False, raises error.

        Returns:
            Tuple of (start_date, end_date)

        Raises:
            HistoryError: If no previous entry and prompt_first is False
            ValueError: If month format is invalid
        """
        self._ensure_loaded()

        # Validate month format
        try:
            month_date = datetime.strptime(month, "%Y-%m")
        except ValueError as e:
            raise ValueError(f"Invalid month format '{month}', expected YYYY-MM") from e

        # Calculate end date (last day of the month)
        end_date = get_month_end_date(month_date.year, month_date.month)

        # Get previous entry to determine start date
        prev_entry = self.get_previous_entry(month)

        if prev_entry is None:
            # First report ever
            if not prompt_first:
                raise HistoryError(
                    "No previous report found and prompting is disabled.\n"
                    "For the first report, you must provide a previous cutoff date."
                )

            # Suggest 25th of the month immediately preceding the target month
            if month_date.month == 1:
                prev_year = month_date.year - 1
                prev_month = DECEMBER_MONTH
            else:
                prev_year = month_date.year
                prev_month = month_date.month - 1
            default_cutoff = date(prev_year, prev_month, 25)

            cutoff = self._prompt_first_cutoff(default_cutoff)
            start_date = cutoff + timedelta(days=1)
        else:
            # Use previous cutoff + 1 day
            start_date = prev_entry.last_cutoff_date + timedelta(days=1)

        return start_date, end_date

    def check_date_range_span(
        self,
        start_date: date,
        end_date: date,
        warn_days: int = 31,
    ) -> bool:
        """Check if date range spans too many days.

        Args:
            start_date: Start of range
            end_date: End of range
            warn_days: Number of days to warn about (default: 31)

        Returns:
            True if range is acceptable, False if user should review
        """
        span_days = (end_date - start_date).days + 1

        if span_days <= warn_days:
            return True

        # Calculate approximate months missed
        months_missed = (span_days // 30) - 1

        questionary.print(
            f"\nWarning: Date range spans {span_days} days "
            f"({start_date} to {end_date})\n",
            style="yellow",
        )

        if months_missed > 0:
            questionary.print(
                f"This likely means you skipped generating reports for approximately "
                f"{months_missed} month(s).\n",
                style="yellow",
            )

        response = questionary.select(
            "What would you like to do?",
            choices=[
                "Continue with this range (may include too many changes)",
                "Adjust start date manually",
                "Quit and generate missing month reports first",
            ],
        ).ask()

        if response is None or "Quit" in response:
            raise KeyboardInterrupt("User cancelled operation")

        return "Adjust" not in response

    def prompt_regenerate(self, month: str) -> bool:
        """Prompt user whether to regenerate existing report.

        Args:
            month: Month in YYYY-MM format

        Returns:
            True if user wants to regenerate, False otherwise

        Raises:
            KeyboardInterrupt: If user cancels
        """
        entry = self.get_entry(month)
        if entry is None:
            return True  # No existing report, proceed

        questionary.print(
            f"\nReport for {month} already exists.\n",
            style="yellow",
        )
        questionary.print(
            f"Generated on: {entry.generated_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Cutoff date: {entry.last_cutoff_date}\n",
            style="fg:gray",
        )

        if entry.regenerated_at:
            regenerated_str = entry.regenerated_at.strftime("%Y-%m-%d %H:%M:%S")
            questionary.print(
                f"Last regenerated: {regenerated_str}\n",
                style="fg:gray",
            )

        response = questionary.select(
            "Do you want to regenerate this report?",
            choices=[
                "Regenerate (overwrites existing files)",
                "Cancel",
            ],
        ).ask()

        if response is None or "Cancel" in response:
            raise KeyboardInterrupt("User cancelled operation")

        return "Regenerate" in response

    def handle_corrupted_file(self) -> NoReturn:
        """Handle corrupted history file by prompting user for action.

        Raises:
            KeyboardInterrupt: If user cancels
            SystemExit: After handling the corruption
        """
        questionary.print(
            f"\nError: Cannot parse {self.history_path}\n",
            style="red",
        )

        response = questionary.select(
            "What would you like to do?",
            choices=[
                "Backup and create new history (safe)",
                "Fix manually (advanced)",
                "Quit",
            ],
        ).ask()

        if response is None or "Quit" in response:
            raise KeyboardInterrupt("User cancelled operation")

        if "Backup" in response:
            # Create backup
            backup_path = self.history_path.with_suffix(".toml.backup")
            shutil.copy2(self.history_path, backup_path)
            questionary.print(
                f"✓ Backed up to {backup_path}",
                style="green",
            )

            # Create new empty history
            self._history = {}
            self._loaded = True
            self.save()
            questionary.print(
                f"✓ Created new history file at {self.history_path}",
                style="green",
            )

            raise SystemExit(0)

        # Fix manually
        questionary.print(
            f"\nPlease fix the TOML syntax in {self.history_path}\n"
            "Then run the command again.\n",
            style="yellow",
        )
        raise SystemExit(1)


# Convenience functions that use default paths


def get_history_manager() -> HistoryManager:
    """Get a history manager using default paths.

    Returns:
        HistoryManager instance with default history path
    """
    return HistoryManager()


def get_history_path() -> Path:
    """Get default path for history.toml.

    Returns:
        Path to the default history file location
    """
    return HistoryManager._get_default_history_path()
