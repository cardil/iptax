"""Unit tests for history tracking."""

import tomllib
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import tomli_w

from iptax.history import (
    HistoryCorruptedError,
    HistoryError,
    HistoryManager,
    get_history_manager,
    get_history_path,
)
from iptax.models import HistoryEntry


class TestHistoryManager:
    """Test HistoryManager class."""

    def test_init_with_custom_path(self, tmp_path: Path) -> None:
        """Test initialization with custom path."""
        custom_path = tmp_path / "custom_history.toml"
        manager = HistoryManager(history_path=custom_path)

        assert manager.history_path == custom_path
        assert not manager._loaded

    def test_init_with_default_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test initialization with default path."""
        test_home = tmp_path / "test_home"
        monkeypatch.setenv("HOME", str(test_home))
        manager = HistoryManager()

        assert str(manager.history_path).endswith(".cache/iptax/history.toml")

    def test_get_default_history_path_with_xdg(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test default path respects XDG_CACHE_HOME."""
        xdg_cache = tmp_path / "xdg_cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))
        path = HistoryManager._get_default_history_path()

        assert path == xdg_cache / "iptax" / "history.toml"

    def test_get_default_history_path_without_xdg(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test default path without XDG_CACHE_HOME."""
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        test_home = tmp_path / "test_home"
        monkeypatch.setenv("HOME", str(test_home))
        path = HistoryManager._get_default_history_path()

        assert path == test_home / ".cache" / "iptax" / "history.toml"


class TestHistoryLoadSave:
    """Test history file loading and saving."""

    def test_load_empty_history(self, tmp_path: Path) -> None:
        """Test loading when history file doesn't exist."""
        history_path = tmp_path / "history.toml"
        manager = HistoryManager(history_path=history_path)

        manager.load()

        assert manager._loaded
        assert manager._history == {}

    def test_load_valid_history(self, tmp_path: Path) -> None:
        """Test loading valid history file."""
        history_path = tmp_path / "history.toml"

        # Create valid history file
        data = {
            "2024-10": {
                "last_cutoff_date": "2024-10-25",
                "generated_at": "2024-10-26T10:00:00Z",
            },
            "2024-11": {
                "last_cutoff_date": "2024-11-25",
                "generated_at": "2024-11-26T09:00:00Z",
                "regenerated_at": "2024-11-30T14:00:00Z",
            },
        }

        with history_path.open("wb") as f:
            tomli_w.dump(data, f)

        # Load and verify
        manager = HistoryManager(history_path=history_path)
        manager.load()

        assert len(manager._history) == 2
        assert "2024-10" in manager._history
        assert "2024-11" in manager._history

        entry_10 = manager._history["2024-10"]
        assert entry_10.last_cutoff_date == date(2024, 10, 25)
        assert entry_10.regenerated_at is None

        entry_11 = manager._history["2024-11"]
        assert entry_11.last_cutoff_date == date(2024, 11, 25)
        assert entry_11.regenerated_at is not None

    def test_load_corrupted_toml(self, tmp_path: Path) -> None:
        """Test loading corrupted TOML file."""
        history_path = tmp_path / "history.toml"

        # Create invalid TOML
        history_path.write_text("invalid [ toml", encoding="utf-8")

        manager = HistoryManager(history_path=history_path)

        with pytest.raises(HistoryCorruptedError, match="Cannot parse"):
            manager.load()

    def test_load_invalid_entry(self, tmp_path: Path) -> None:
        """Test loading history with invalid entry data."""
        history_path = tmp_path / "history.toml"

        # Create history with invalid date format
        data = {
            "2024-10": {
                "last_cutoff_date": "invalid-date",
                "generated_at": "2024-10-26T10:00:00Z",
            }
        }

        with history_path.open("wb") as f:
            tomli_w.dump(data, f)

        manager = HistoryManager(history_path=history_path)

        with pytest.raises(HistoryCorruptedError, match="Invalid history entry"):
            manager.load()

    def test_save_history(self, tmp_path: Path) -> None:
        """Test saving history to file."""
        history_path = tmp_path / "history.toml"
        manager = HistoryManager(history_path=history_path)

        # Add entries
        manager._loaded = True
        manager.add_entry("2024-10", date(2024, 10, 25))
        manager.add_entry("2024-11", date(2024, 11, 25))

        # Save
        manager.save()

        # Verify file exists and has correct permissions
        assert history_path.exists()
        assert history_path.stat().st_mode & 0o777 == 0o600

        # Verify content
        with history_path.open("rb") as f:
            data = tomllib.load(f)

        assert "2024-10" in data
        assert "2024-11" in data

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Test that save creates parent directory if needed."""
        history_path = tmp_path / "subdir" / "history.toml"
        manager = HistoryManager(history_path=history_path)

        manager._loaded = True
        manager.add_entry("2024-10", date(2024, 10, 25))
        manager.save()

        assert history_path.parent.exists()
        assert history_path.exists()


class TestHistoryEntries:
    """Test history entry operations."""

    def test_has_entry(self, tmp_path: Path) -> None:
        """Test checking if entry exists."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True
        manager._history["2024-10"] = HistoryEntry(
            last_cutoff_date=date(2024, 10, 25),
            generated_at=datetime.now(UTC),
        )

        assert manager.has_entry("2024-10")
        assert not manager.has_entry("2024-11")

    def test_get_entry(self, tmp_path: Path) -> None:
        """Test getting specific entry."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        entry = HistoryEntry(
            last_cutoff_date=date(2024, 10, 25),
            generated_at=datetime.now(UTC),
        )
        manager._history["2024-10"] = entry

        result = manager.get_entry("2024-10")
        assert result == entry

        result = manager.get_entry("2024-11")
        assert result is None

    def test_get_all_entries(self, tmp_path: Path) -> None:
        """Test getting all entries."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        entry1 = HistoryEntry(
            last_cutoff_date=date(2024, 10, 25),
            generated_at=datetime.now(UTC),
        )
        entry2 = HistoryEntry(
            last_cutoff_date=date(2024, 11, 25),
            generated_at=datetime.now(UTC),
        )

        manager._history["2024-10"] = entry1
        manager._history["2024-11"] = entry2

        all_entries = manager.get_all_entries()
        assert len(all_entries) == 2
        assert "2024-10" in all_entries
        assert "2024-11" in all_entries

        # Verify it's a copy
        all_entries["2024-12"] = entry1
        assert "2024-12" not in manager._history

    def test_get_previous_entry(self, tmp_path: Path) -> None:
        """Test getting previous entry."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        manager._history["2024-09"] = HistoryEntry(
            last_cutoff_date=date(2024, 9, 25),
            generated_at=datetime.now(UTC),
        )
        manager._history["2024-10"] = HistoryEntry(
            last_cutoff_date=date(2024, 10, 25),
            generated_at=datetime.now(UTC),
        )

        # Get previous of November (should be October)
        prev = manager.get_previous_entry("2024-11")
        assert prev is not None
        assert prev.last_cutoff_date == date(2024, 10, 25)

        # Get previous of October (should be September)
        prev = manager.get_previous_entry("2024-10")
        assert prev is not None
        assert prev.last_cutoff_date == date(2024, 9, 25)

        # Get previous of September (should be None)
        prev = manager.get_previous_entry("2024-09")
        assert prev is None

    def test_get_previous_entry_empty_history(self, tmp_path: Path) -> None:
        """Test getting previous entry with empty history."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        prev = manager.get_previous_entry("2024-10")
        assert prev is None

    def test_add_entry_new(self, tmp_path: Path) -> None:
        """Test adding new entry."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        manager.add_entry("2024-10", date(2024, 10, 25))

        assert "2024-10" in manager._history
        entry = manager._history["2024-10"]
        assert entry.last_cutoff_date == date(2024, 10, 25)
        assert entry.regenerated_at is None

    def test_add_entry_regenerate(self, tmp_path: Path) -> None:
        """Test regenerating existing entry."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        # Add initial entry
        manager.add_entry("2024-10", date(2024, 10, 25))
        original_generated = manager._history["2024-10"].generated_at

        # Regenerate
        manager.add_entry("2024-10", date(2024, 10, 25), regenerate=True)

        entry = manager._history["2024-10"]
        assert entry.generated_at == original_generated
        assert entry.regenerated_at is not None

    def test_add_entry_invalid_month(self, tmp_path: Path) -> None:
        """Test adding entry with invalid month format."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        with pytest.raises(ValueError, match="Invalid month format"):
            manager.add_entry("2024-13", date(2024, 10, 25))

        with pytest.raises(ValueError, match="Invalid month format"):
            manager.add_entry("invalid", date(2024, 10, 25))


class TestDateRangeCalculation:
    """Test date range calculation logic."""

    def test_get_date_range_with_previous(self, tmp_path: Path) -> None:
        """Test date range calculation with previous report."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        # Add October report
        manager._history["2024-10"] = HistoryEntry(
            last_cutoff_date=date(2024, 10, 25),
            generated_at=datetime.now(UTC),
        )

        # Calculate November range
        start, end = manager.get_date_range("2024-11", prompt_first=False)

        # Start should be October 26 (previous cutoff + 1)
        assert start == date(2024, 10, 26)
        # End should be November 30 (last day of November)
        assert end == date(2024, 11, 30)

    def test_get_date_range_december(self, tmp_path: Path) -> None:
        """Test date range for December (year boundary)."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        manager._history["2024-11"] = HistoryEntry(
            last_cutoff_date=date(2024, 11, 25),
            generated_at=datetime.now(UTC),
        )

        start, end = manager.get_date_range("2024-12", prompt_first=False)

        assert start == date(2024, 11, 26)
        assert end == date(2024, 12, 31)

    def test_get_date_range_first_report_no_prompt(self, tmp_path: Path) -> None:
        """Test first report without prompting raises error."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        with pytest.raises(HistoryError, match="No previous report found"):
            manager.get_date_range("2024-10", prompt_first=False)

    @patch("iptax.history.questionary")
    def test_get_date_range_first_report_with_prompt(
        self, mock_questionary: Mock, tmp_path: Path
    ) -> None:
        """Test first report with user prompt."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        # Mock user input for cutoff date
        mock_text = Mock()
        mock_text.ask.return_value = "2024-09-25"
        mock_questionary.text.return_value = mock_text
        mock_questionary.print = Mock()

        start, end = manager.get_date_range("2024-10", prompt_first=True)

        assert start == date(2024, 9, 26)  # User input + 1
        assert end == date(2024, 10, 31)  # Last day of October

    def test_get_date_range_invalid_month(self, tmp_path: Path) -> None:
        """Test date range with invalid month format."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        with pytest.raises(ValueError, match="Invalid month format"):
            manager.get_date_range("invalid")

    def test_check_date_range_span_normal(self, tmp_path: Path) -> None:
        """Test date range span check for normal range."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")

        start = date(2024, 10, 1)
        end = date(2024, 10, 31)

        result = manager.check_date_range_span(start, end, warn_days=31)
        assert result is True

    @patch("iptax.history.questionary")
    def test_check_date_range_span_too_long_continue(
        self, mock_questionary: Mock, tmp_path: Path
    ) -> None:
        """Test date range span check for multi-month range, user continues."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")

        start = date(2024, 9, 1)
        end = date(2024, 11, 30)

        mock_questionary.print = Mock()
        mock_select = Mock()
        mock_select.ask.return_value = (
            "Continue with this range (may include too many changes)"
        )
        mock_questionary.select.return_value = mock_select

        result = manager.check_date_range_span(start, end, warn_days=31)
        assert result is True

    @patch("iptax.history.questionary")
    def test_check_date_range_span_too_long_adjust(
        self, mock_questionary: Mock, tmp_path: Path
    ) -> None:
        """Test date range span check for multi-month range, user adjusts."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")

        start = date(2024, 9, 1)
        end = date(2024, 11, 30)

        mock_questionary.print = Mock()
        mock_select = Mock()
        mock_select.ask.return_value = "Adjust start date manually"
        mock_questionary.select.return_value = mock_select

        result = manager.check_date_range_span(start, end, warn_days=31)
        assert result is False


class TestRegenerationPrompt:
    """Test regeneration prompt logic."""

    def test_prompt_regenerate_no_existing(self, tmp_path: Path) -> None:
        """Test prompt when no existing report."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        result = manager.prompt_regenerate("2024-10")
        assert result is True

    @patch("iptax.history.questionary")
    def test_prompt_regenerate_existing_yes(
        self, mock_questionary: Mock, tmp_path: Path
    ) -> None:
        """Test prompt with existing report, user says yes."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        manager._history["2024-10"] = HistoryEntry(
            last_cutoff_date=date(2024, 10, 25),
            generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
        )

        mock_questionary.print = Mock()
        mock_select = Mock()
        mock_select.ask.return_value = "Regenerate (overwrites existing files)"
        mock_questionary.select.return_value = mock_select

        result = manager.prompt_regenerate("2024-10")
        assert result is True

    @patch("iptax.history.questionary")
    def test_prompt_regenerate_existing_cancel(
        self, mock_questionary: Mock, tmp_path: Path
    ) -> None:
        """Test prompt with existing report, user cancels."""
        manager = HistoryManager(history_path=tmp_path / "history.toml")
        manager._loaded = True

        manager._history["2024-10"] = HistoryEntry(
            last_cutoff_date=date(2024, 10, 25),
            generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
        )

        mock_questionary.print = Mock()
        mock_select = Mock()
        mock_select.ask.return_value = "Cancel"
        mock_questionary.select.return_value = mock_select

        with pytest.raises(KeyboardInterrupt):
            manager.prompt_regenerate("2024-10")


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_get_history_manager(self) -> None:
        """Test getting default history manager."""
        manager = get_history_manager()
        assert isinstance(manager, HistoryManager)
        assert str(manager.history_path).endswith("history.toml")

    def test_get_history_path(self) -> None:
        """Test getting default history path."""
        path = get_history_path()
        assert isinstance(path, Path)
        assert str(path).endswith("history.toml")
