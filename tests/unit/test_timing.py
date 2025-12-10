"""Tests for timing module."""

import logging
from datetime import UTC, date, datetime

import pytest

from iptax import timing
from iptax.cache.history import HistoryManager
from iptax.models import HistoryEntry
from iptax.utils.env import cache_dir_for_home

logger = logging.getLogger(__name__)


class TestResolveDateRanges:
    """Tests for resolve_date_ranges function."""

    @pytest.mark.unit
    def test_explicit_month(self, isolated_home):
        """Test resolving with explicit month (YYYY-MM)."""
        logger.debug("Using isolated home: %s", isolated_home)
        ranges = timing.resolve_date_ranges("2024-11")

        assert ranges.workday_start == date(2024, 11, 1)
        assert ranges.workday_end == date(2024, 11, 30)
        assert ranges.did_start <= ranges.did_end

    @pytest.mark.unit
    def test_workday_range_full_month(self, isolated_home):
        """Test that workday range covers full calendar month."""
        logger.debug("Using isolated home: %s", isolated_home)
        ranges = timing.resolve_date_ranges("2024-02")

        assert ranges.workday_start == date(2024, 2, 1)
        assert ranges.workday_end == date(2024, 2, 29)

    @pytest.mark.unit
    def test_with_overrides(self, isolated_home):
        """Test resolving with date overrides."""
        logger.debug("Using isolated home: %s", isolated_home)
        ranges = timing.resolve_date_ranges(
            "2024-11",
            workday_start=date(2024, 11, 5),
            workday_end=date(2024, 11, 25),
            did_start=date(2024, 10, 20),
            did_end=date(2024, 11, 20),
        )

        assert ranges.workday_start == date(2024, 11, 5)
        assert ranges.workday_end == date(2024, 11, 25)
        assert ranges.did_start == date(2024, 10, 20)
        assert ranges.did_end == date(2024, 11, 20)

    @pytest.mark.unit
    def test_partial_overrides(self, isolated_home):
        """Test that partial overrides work."""
        logger.debug("Using isolated home: %s", isolated_home)
        ranges = timing.resolve_date_ranges(
            "2024-11",
            workday_start=date(2024, 11, 5),
        )

        assert ranges.workday_start == date(2024, 11, 5)
        assert ranges.workday_end == date(2024, 11, 30)


class TestResolveMonthSpec:
    """Tests for resolve_month_spec function."""

    @pytest.mark.unit
    def test_explicit_month(self):
        """Test explicit YYYY-MM format."""
        result = timing.resolve_month_spec("2024-11")
        assert result == "2024-11"

    @pytest.mark.unit
    def test_current_keyword(self, monkeypatch):
        """Test 'current' keyword returns current month."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-11-15")
        result = timing.resolve_month_spec("current")
        assert result == "2024-11"

    @pytest.mark.unit
    def test_last_keyword(self, monkeypatch):
        """Test 'last' keyword returns previous month."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-11-15")
        result = timing.resolve_month_spec("last")
        assert result == "2024-10"

    @pytest.mark.unit
    def test_last_keyword_january(self, monkeypatch):
        """Test 'last' keyword in January returns December of previous year."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-01-15")
        result = timing.resolve_month_spec("last")
        assert result == "2023-12"

    @pytest.mark.unit
    def test_invalid_format_raises(self):
        """Test invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid month format"):
            timing.resolve_month_spec("invalid")


class TestAutoDetectMonth:
    """Tests for auto_detect_month function."""

    @pytest.mark.unit
    def test_days_1_to_10_returns_previous_month(self, monkeypatch):
        """Days 1-10 should report previous month."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-05")
        result = timing.auto_detect_month()
        assert result == "2024-11"

    @pytest.mark.unit
    def test_days_11_to_31_returns_current_month(self, monkeypatch):
        """Days 11-31 should report current month."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-11-25")
        result = timing.auto_detect_month()
        assert result == "2024-11"

    @pytest.mark.unit
    def test_january_day_5_returns_december(self, monkeypatch):
        """January days 1-10 should report December of previous year."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-01-05")
        result = timing.auto_detect_month()
        assert result == "2023-12"

    @pytest.mark.unit
    def test_day_10_is_previous_month(self, monkeypatch):
        """Day 10 is the boundary - still previous month."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-10")
        result = timing.auto_detect_month()
        assert result == "2024-11"

    @pytest.mark.unit
    def test_day_11_is_current_month(self, monkeypatch):
        """Day 11 is the boundary - current month."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-11")
        result = timing.auto_detect_month()
        assert result == "2024-12"


class TestGetWorkdayRange:
    """Tests for get_workday_range function."""

    @pytest.mark.unit
    def test_full_month(self):
        """Test workday range is full calendar month."""
        start, end = timing.get_workday_range("2024-11")
        assert start == date(2024, 11, 1)
        assert end == date(2024, 11, 30)

    @pytest.mark.unit
    def test_february_leap_year(self):
        """Test February in leap year."""
        start, end = timing.get_workday_range("2024-02")
        assert start == date(2024, 2, 1)
        assert end == date(2024, 2, 29)


class TestGetDidRange:
    """Tests for get_did_range function.

    The new logic determines dates from history:
    - Start: prev_month.last_change_date + 1 (if exists), else 1st of target
    - End: target.last_change_date (if exists), or next.first_change_date - 1,
        else 25th/today
    """

    @pytest.mark.unit
    def test_no_history_past_month_uses_defaults(self, monkeypatch, isolated_home):
        """No history for past month: start = 1st, end = 25th."""
        logger.debug("Using isolated home: %s", isolated_home)
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-05")
        start, end = timing.get_did_range("2024-11")
        # No history: start = Nov 1, end = Nov 25 (default for past month)
        assert start == date(2024, 11, 1)
        assert end == date(2024, 11, 25)

    @pytest.mark.unit
    def test_no_history_current_month_ends_today(self, monkeypatch, isolated_home):
        """No history for current month: start = 1st, end = today."""
        logger.debug("Using isolated home: %s", isolated_home)
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-11-25")
        start, end = timing.get_did_range("2024-11")
        # No history: start = Nov 1, end = today (Nov 25)
        assert start == date(2024, 11, 1)
        assert end == date(2024, 11, 25)

    @pytest.mark.unit
    def test_january_no_history(self, monkeypatch, isolated_home):
        """January with no history: start = Jan 1, end = today."""
        logger.debug("Using isolated home: %s", isolated_home)
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-01-15")
        start, end = timing.get_did_range("2024-01")
        # No history: start = Jan 1, end = today (Jan 15)
        assert start == date(2024, 1, 1)
        assert end == date(2024, 1, 15)

    @pytest.mark.unit
    def test_with_prev_month_history(self, monkeypatch, isolated_home):
        """With previous month history: start from prev cutoff + 1."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-11-25")

        # Create history for October with last_change_date = Oct 20
        cache_dir = cache_dir_for_home(isolated_home)
        cache_dir.mkdir(parents=True, exist_ok=True)
        history_file = cache_dir / "history.json"

        manager = HistoryManager(history_path=history_file)
        manager._history = {
            "2024-10": HistoryEntry(
                first_change_date=date(2024, 9, 21),
                last_change_date=date(2024, 10, 20),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }
        manager._loaded = True
        manager.save()

        start, end = timing.get_did_range("2024-11")
        assert start == date(2024, 10, 21)  # Last report + 1 day
        assert end == date(2024, 11, 25)  # Today

    @pytest.mark.unit
    def test_with_target_month_history(self, monkeypatch, isolated_home):
        """With target month history: end = target's last_change_date."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-05")

        cache_dir = cache_dir_for_home(isolated_home)
        cache_dir.mkdir(parents=True, exist_ok=True)
        history_file = cache_dir / "history.json"

        manager = HistoryManager(history_path=history_file)
        manager._history = {
            "2024-10": HistoryEntry(
                first_change_date=date(2024, 9, 26),
                last_change_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            ),
            "2024-11": HistoryEntry(
                first_change_date=date(2024, 10, 26),
                last_change_date=date(2024, 11, 24),
                generated_at=datetime(2024, 11, 26, 10, 0, 0, tzinfo=UTC),
            ),
        }
        manager._loaded = True
        manager.save()

        start, end = timing.get_did_range("2024-11")
        assert start == date(2024, 10, 26)  # Oct cutoff + 1
        assert end == date(2024, 11, 24)  # Nov's last_change_date

    @pytest.mark.unit
    def test_with_next_month_history(self, monkeypatch, isolated_home):
        """With next month history but no target: end = next's first - 1."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-05")

        cache_dir = cache_dir_for_home(isolated_home)
        cache_dir.mkdir(parents=True, exist_ok=True)
        history_file = cache_dir / "history.json"

        manager = HistoryManager(history_path=history_file)
        manager._history = {
            "2024-10": HistoryEntry(
                first_change_date=date(2024, 9, 26),
                last_change_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            ),
            # No Nov entry, but Dec exists
            "2024-12": HistoryEntry(
                first_change_date=date(2024, 11, 26),
                last_change_date=date(2024, 12, 4),
                generated_at=datetime(2024, 12, 5, 10, 0, 0, tzinfo=UTC),
            ),
        }
        manager._loaded = True
        manager.save()

        start, end = timing.get_did_range("2024-11")
        assert start == date(2024, 10, 26)  # Oct cutoff + 1
        assert end == date(2024, 11, 25)  # Dec first - 1


class TestIsFinalizationWindow:
    """Tests for is_finalization_window function."""

    @pytest.mark.unit
    def test_day_5_is_finalization(self, monkeypatch):
        """Day 5 is in finalization window."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-05")
        assert timing.is_finalization_window() is True

    @pytest.mark.unit
    def test_day_10_is_finalization(self, monkeypatch):
        """Day 10 is the boundary - still in finalization."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-10")
        assert timing.is_finalization_window() is True

    @pytest.mark.unit
    def test_day_11_is_not_finalization(self, monkeypatch):
        """Day 11 is not in finalization window."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-11")
        assert timing.is_finalization_window() is False
