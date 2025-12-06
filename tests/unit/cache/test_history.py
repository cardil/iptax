"""Tests for history tracking module."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from iptax.cache.history import (
    HistoryCorruptedError,
    HistoryManager,
    get_history_path,
    get_last_report_date,
    save_report_date,
)
from iptax.models import HistoryEntry


class TestHistoryManager:
    """Tests for HistoryManager class."""

    @pytest.mark.unit
    def test_init_with_custom_path(self, tmp_path: Path) -> None:
        """Test initialization with custom path."""
        custom_path = tmp_path / "custom_history.json"
        manager = HistoryManager(history_path=custom_path)
        assert manager.history_path == custom_path

    @pytest.mark.unit
    def test_init_with_default_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test initialization with default path."""
        test_home = tmp_path / "test_home"
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        monkeypatch.setenv("HOME", str(test_home))
        manager = HistoryManager()

        assert str(manager.history_path).endswith(".cache/iptax/history.json")

    @pytest.mark.unit
    def test_get_default_history_path_with_xdg(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test default path respects XDG_CACHE_HOME."""
        xdg_cache = tmp_path / "xdg_cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))
        path = HistoryManager._get_default_history_path()

        assert path == xdg_cache / "iptax" / "history.json"


class TestHistoryLoad:
    """Tests for history loading."""

    @pytest.mark.unit
    def test_load_empty_file_not_exists(self, tmp_path: Path) -> None:
        """Test loading when file doesn't exist."""
        manager = HistoryManager(history_path=tmp_path / "history.json")
        manager.load()

        assert manager._history == {}
        assert manager._loaded is True

    @pytest.mark.unit
    def test_load_valid_json(self, tmp_path: Path) -> None:
        """Test loading valid JSON history."""
        history_file = tmp_path / "history.json"
        data = {
            "2024-10": {
                "last_cutoff_date": "2024-10-25",
                "generated_at": "2024-10-26T10:00:00",
            }
        }
        history_file.write_text(json.dumps(data), encoding="utf-8")

        manager = HistoryManager(history_path=history_file)
        manager.load()

        assert "2024-10" in manager._history
        assert manager._history["2024-10"].last_cutoff_date == date(2024, 10, 25)

    @pytest.mark.unit
    def test_load_with_regenerated_at(self, tmp_path: Path) -> None:
        """Test loading history with regenerated_at field."""
        history_file = tmp_path / "history.json"
        data = {
            "2024-10": {
                "last_cutoff_date": "2024-10-25",
                "generated_at": "2024-10-26T10:00:00",
                "regenerated_at": "2024-10-28T14:00:00",
            }
        }
        history_file.write_text(json.dumps(data), encoding="utf-8")

        manager = HistoryManager(history_path=history_file)
        manager.load()

        assert manager._history["2024-10"].regenerated_at is not None

    @pytest.mark.unit
    def test_load_corrupted_json(self, tmp_path: Path) -> None:
        """Test loading corrupted JSON raises error."""
        history_file = tmp_path / "history.json"
        history_file.write_text("not valid json {{{", encoding="utf-8")

        manager = HistoryManager(history_path=history_file)

        with pytest.raises(HistoryCorruptedError, match="invalid JSON"):
            manager.load()

    @pytest.mark.unit
    def test_load_invalid_entry(self, tmp_path: Path) -> None:
        """Test loading with invalid entry data raises error."""
        history_file = tmp_path / "history.json"
        data = {"2024-10": {"invalid_field": "bad data"}}
        history_file.write_text(json.dumps(data), encoding="utf-8")

        manager = HistoryManager(history_path=history_file)

        with pytest.raises(HistoryCorruptedError, match="Invalid history entry"):
            manager.load()


class TestHistorySave:
    """Tests for history saving."""

    @pytest.mark.unit
    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Test save creates parent directory."""
        history_file = tmp_path / "subdir" / "history.json"
        manager = HistoryManager(history_path=history_file)
        manager._loaded = True
        manager._history = {
            "2024-10": HistoryEntry(
                last_cutoff_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }

        manager.save()

        assert history_file.exists()
        assert history_file.parent.exists()

    @pytest.mark.unit
    def test_save_and_reload(self, tmp_path: Path) -> None:
        """Test save and reload roundtrip."""
        history_file = tmp_path / "history.json"
        manager = HistoryManager(history_path=history_file)
        manager._loaded = True
        manager._history = {
            "2024-10": HistoryEntry(
                last_cutoff_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }

        manager.save()

        # Reload
        manager2 = HistoryManager(history_path=history_file)
        manager2.load()

        assert "2024-10" in manager2._history
        assert manager2._history["2024-10"].last_cutoff_date == date(2024, 10, 25)

    @pytest.mark.unit
    def test_save_sets_permissions(self, tmp_path: Path) -> None:
        """Test save sets file permissions to 600."""
        history_file = tmp_path / "history.json"
        manager = HistoryManager(history_path=history_file)
        manager._loaded = True
        manager._history = {}

        manager.save()

        # Check permissions (600 = owner read/write only)
        mode = history_file.stat().st_mode & 0o777
        assert mode == 0o600


class TestHistoryGetAllEntries:
    """Tests for get_all_entries method."""

    @pytest.mark.unit
    def test_get_all_entries_empty(self, tmp_path: Path) -> None:
        """Test getting entries from empty history."""
        manager = HistoryManager(history_path=tmp_path / "history.json")
        manager._loaded = True
        manager._history = {}

        entries = manager.get_all_entries()

        assert entries == {}

    @pytest.mark.unit
    def test_get_all_entries_returns_copy(self, tmp_path: Path) -> None:
        """Test that get_all_entries returns a copy."""
        manager = HistoryManager(history_path=tmp_path / "history.json")
        manager._loaded = True
        manager._history = {
            "2024-10": HistoryEntry(
                last_cutoff_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }

        entries = manager.get_all_entries()
        entries["2024-11"] = HistoryEntry(
            last_cutoff_date=date(2024, 11, 25),
            generated_at=datetime(2024, 11, 26, 10, 0, 0, tzinfo=UTC),
        )

        # Original should be unchanged
        assert "2024-11" not in manager._history


class TestHistoryAddEntry:
    """Tests for add_entry method."""

    @pytest.mark.unit
    def test_add_entry_new(self, tmp_path: Path) -> None:
        """Test adding a new entry."""
        manager = HistoryManager(history_path=tmp_path / "history.json")
        manager._loaded = True
        manager._history = {}

        manager.add_entry("2024-10", date(2024, 10, 25))

        assert "2024-10" in manager._history
        assert manager._history["2024-10"].last_cutoff_date == date(2024, 10, 25)

    @pytest.mark.unit
    def test_add_entry_overwrites_existing(self, tmp_path: Path) -> None:
        """Test adding entry overwrites existing."""
        manager = HistoryManager(history_path=tmp_path / "history.json")
        manager._loaded = True
        manager._history = {
            "2024-10": HistoryEntry(
                last_cutoff_date=date(2024, 10, 20),
                generated_at=datetime(2024, 10, 21, 10, 0, 0, tzinfo=UTC),
            )
        }

        manager.add_entry("2024-10", date(2024, 10, 25))

        assert manager._history["2024-10"].last_cutoff_date == date(2024, 10, 25)

    @pytest.mark.unit
    def test_add_entry_invalid_month(self, tmp_path: Path) -> None:
        """Test adding entry with invalid month format."""
        manager = HistoryManager(history_path=tmp_path / "history.json")
        manager._loaded = True
        manager._history = {}

        with pytest.raises(ValueError, match="Invalid month format"):
            manager.add_entry("invalid", date(2024, 10, 25))

    @pytest.mark.unit
    def test_add_entry_auto_loads(self, tmp_path: Path) -> None:
        """Test add_entry auto-loads if not loaded."""
        history_file = tmp_path / "history.json"
        manager = HistoryManager(history_path=history_file)
        # Not loaded yet

        manager.add_entry("2024-10", date(2024, 10, 25))

        assert manager._loaded is True


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.unit
    def test_get_history_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test get_history_path returns correct path."""
        xdg_cache = tmp_path / "xdg_cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))

        path = get_history_path()

        assert path == xdg_cache / "iptax" / "history.json"

    @pytest.mark.unit
    def test_get_last_report_date_no_history(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test get_last_report_date with empty history."""
        cache_dir = tmp_path / "cache" / "iptax"
        cache_dir.mkdir(parents=True)
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        result = get_last_report_date()

        assert result is None

    @pytest.mark.unit
    def test_get_last_report_date_with_history(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test get_last_report_date with existing history."""
        cache_dir = tmp_path / "cache" / "iptax"
        cache_dir.mkdir(parents=True)
        history_file = cache_dir / "history.json"

        data = {
            "2024-09": {
                "last_cutoff_date": "2024-09-25",
                "generated_at": "2024-09-26T10:00:00",
            },
            "2024-10": {
                "last_cutoff_date": "2024-10-25",
                "generated_at": "2024-10-26T10:00:00",
            },
        }
        history_file.write_text(json.dumps(data), encoding="utf-8")

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        result = get_last_report_date()

        # Should return the latest (2024-10)
        assert result == date(2024, 10, 25)

    @pytest.mark.unit
    def test_save_report_date(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test save_report_date creates entry."""
        cache_dir = tmp_path / "cache" / "iptax"
        cache_dir.mkdir(parents=True)
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        save_report_date(date(2024, 11, 25), "2024-11")

        # Verify it was saved
        history_file = cache_dir / "history.json"
        assert history_file.exists()

        data = json.loads(history_file.read_text(encoding="utf-8"))
        assert "2024-11" in data
        assert data["2024-11"]["last_cutoff_date"] == "2024-11-25"


class TestEnsureLoaded:
    """Tests for _ensure_loaded method."""

    @pytest.mark.unit
    def test_ensure_loaded_auto_loads(self, tmp_path: Path) -> None:
        """Test _ensure_loaded auto-loads when not loaded."""
        history_file = tmp_path / "history.json"
        data = {
            "2024-10": {
                "last_cutoff_date": "2024-10-25",
                "generated_at": "2024-10-26T10:00:00",
            }
        }
        history_file.write_text(json.dumps(data), encoding="utf-8")

        manager = HistoryManager(history_path=history_file)
        assert manager._loaded is False

        # Call method that uses _ensure_loaded
        entries = manager.get_all_entries()

        assert manager._loaded is True
        assert "2024-10" in entries
