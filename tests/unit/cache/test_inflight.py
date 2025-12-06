"""Unit tests for in-flight report cache."""

from datetime import date
from pathlib import Path

import pytest

from iptax.cache.inflight import InFlightCache
from iptax.models import InFlightReport


class TestInFlightCache:
    """Test InFlightCache class."""

    def test_init_with_custom_path(self, tmp_path: Path) -> None:
        """Test initialization with custom path."""
        custom_path = tmp_path / "custom_cache"
        cache = InFlightCache(cache_dir=custom_path)

        assert cache.cache_dir == custom_path

    def test_exists_no_report(self, tmp_path: Path) -> None:
        """Test exists returns False when no report exists."""
        cache = InFlightCache(cache_dir=tmp_path)

        assert not cache.exists("2024-11")

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Test saving and loading a report."""
        cache = InFlightCache(cache_dir=tmp_path)

        # Create a report
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )

        # Save
        path = cache.save(report)
        assert path.exists()
        assert cache.exists("2024-11")

        # Load
        loaded = cache.load("2024-11")
        assert loaded is not None
        assert loaded.month == "2024-11"
        assert loaded.workday_start == date(2024, 11, 1)
        assert loaded.workday_end == date(2024, 11, 30)
        assert loaded.changes_since == date(2024, 10, 25)
        assert loaded.changes_until == date(2024, 11, 25)

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        """Test loading non-existent report returns None."""
        cache = InFlightCache(cache_dir=tmp_path)

        loaded = cache.load("2024-11")
        assert loaded is None

    def test_delete(self, tmp_path: Path) -> None:
        """Test deleting a report."""
        cache = InFlightCache(cache_dir=tmp_path)

        # Create and save a report
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        cache.save(report)
        assert cache.exists("2024-11")

        # Delete
        result = cache.delete("2024-11")
        assert result is True
        assert not cache.exists("2024-11")

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        """Test deleting non-existent report returns False."""
        cache = InFlightCache(cache_dir=tmp_path)

        result = cache.delete("2024-11")
        assert result is False

    def test_list_all_empty(self, tmp_path: Path) -> None:
        """Test listing reports when cache is empty."""
        cache = InFlightCache(cache_dir=tmp_path)

        reports = cache.list_all()
        assert reports == []

    def test_list_all_multiple(self, tmp_path: Path) -> None:
        """Test listing multiple reports."""
        cache = InFlightCache(cache_dir=tmp_path)

        # Create multiple reports
        for month in ["2024-10", "2024-11", "2024-12"]:
            report = InFlightReport(
                month=month,
                workday_start=date(2024, 11, 1),
                workday_end=date(2024, 11, 30),
                changes_since=date(2024, 10, 25),
                changes_until=date(2024, 11, 25),
            )
            cache.save(report)

        reports = cache.list_all()
        assert len(reports) == 3
        assert set(reports) == {"2024-10", "2024-11", "2024-12"}

    def test_clear_all(self, tmp_path: Path) -> None:
        """Test clearing all reports."""
        cache = InFlightCache(cache_dir=tmp_path)

        # Create multiple reports
        for month in ["2024-10", "2024-11"]:
            report = InFlightReport(
                month=month,
                workday_start=date(2024, 11, 1),
                workday_end=date(2024, 11, 30),
                changes_since=date(2024, 10, 25),
                changes_until=date(2024, 11, 25),
            )
            cache.save(report)

        # Clear all
        count = cache.clear_all()
        assert count == 2
        assert cache.list_all() == []

    def test_clear_all_empty(self, tmp_path: Path) -> None:
        """Test clearing when cache is empty."""
        cache = InFlightCache(cache_dir=tmp_path)

        count = cache.clear_all()
        assert count == 0

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Test that save creates cache directory if needed."""
        cache_dir = tmp_path / "subdir" / "cache"
        cache = InFlightCache(cache_dir=cache_dir)

        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )

        cache.save(report)
        assert cache_dir.exists()

    def test_invalid_month_format_raises_error(self, tmp_path: Path) -> None:
        """Test that invalid month format raises ValueError."""
        cache = InFlightCache(cache_dir=tmp_path)

        with pytest.raises(ValueError, match="Invalid month format"):
            cache.load("../../../tmp/evil")

    def test_path_traversal_attempt_raises_error(self, tmp_path: Path) -> None:
        """Test that path traversal attempts are rejected."""
        cache = InFlightCache(cache_dir=tmp_path)

        with pytest.raises(ValueError, match="Invalid month format"):
            cache.exists("2024-11/../../../etc/passwd")

    def test_list_all_filters_invalid_files(self, tmp_path: Path) -> None:
        """Test that list_all only returns valid YYYY-MM format files."""
        cache = InFlightCache(cache_dir=tmp_path)

        # Create a valid report
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        cache.save(report)

        # Create an invalid file manually
        (tmp_path / "invalid.json").write_text("{}")
        (tmp_path / "not-a-month.json").write_text("{}")

        # Should only return valid month
        reports = cache.list_all()
        assert reports == ["2024-11"]
