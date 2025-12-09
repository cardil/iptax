"""Tests for timing module."""

from datetime import date
from unittest.mock import patch

import pytest

from iptax import timing


class TestResolveDateRanges:
    """Tests for resolve_date_ranges function."""

    @pytest.mark.unit
    def test_explicit_month(self):
        """Test resolving with explicit month (YYYY-MM)."""
        ranges = timing.resolve_date_ranges("2024-11")

        assert ranges.workday_start == date(2024, 11, 1)
        assert ranges.workday_end == date(2024, 11, 30)
        assert ranges.did_start <= ranges.did_end

    @pytest.mark.unit
    def test_workday_range_full_month(self):
        """Test that workday range covers full calendar month."""
        ranges = timing.resolve_date_ranges("2024-02")

        assert ranges.workday_start == date(2024, 2, 1)
        assert ranges.workday_end == date(2024, 2, 29)

    @pytest.mark.unit
    def test_with_overrides(self):
        """Test resolving with date overrides."""
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
    def test_partial_overrides(self):
        """Test that partial overrides work."""
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
    """Tests for get_did_range function."""

    @pytest.mark.unit
    def test_days_1_to_10_uses_full_month(self, monkeypatch):
        """Days 1-10: Did uses same range as Workday (full month)."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-05")
        start, end = timing.get_did_range("2024-11")
        assert start == date(2024, 11, 1)
        assert end == date(2024, 11, 30)

    @pytest.mark.unit
    def test_days_11_to_31_uses_rolling_window(self, monkeypatch):
        """Days 11-31: Did uses rolling window ending at today."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-11-25")
        # No history means default to 25th of previous month
        with patch("iptax.timing.get_last_report_date", return_value=None):
            start, end = timing.get_did_range("2024-11")
        assert start == date(2024, 10, 25)
        assert end == date(2024, 11, 25)

    @pytest.mark.unit
    def test_january_previous_month_is_december(self, monkeypatch):
        """January: Previous month default should be December."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-01-15")
        # No history means default to 25th of previous month (December)
        with patch("iptax.timing.get_last_report_date", return_value=None):
            start, end = timing.get_did_range("2024-01")
        assert start == date(2023, 12, 25)
        assert end == date(2024, 1, 15)

    @pytest.mark.unit
    def test_with_history_uses_last_report_date(self, monkeypatch):
        """With history, Did starts from last report date + 1."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-11-25")
        # History exists with last report on Oct 20
        with patch(
            "iptax.timing.get_last_report_date", return_value=date(2024, 10, 20)
        ):
            start, end = timing.get_did_range("2024-11")
        assert start == date(2024, 10, 21)  # Last report + 1 day
        assert end == date(2024, 11, 25)

    @pytest.mark.unit
    def test_days_1_to_10_older_month_uses_history(self, monkeypatch):
        """Days 1-10: Older months should still use history, not full month.

        When today is Dec 5 (finalization window for Nov), but user requests
        Oct report, we should use history-based range, not full Oct month.
        """
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-05")
        # History exists with Sept 25 cutoff
        with patch("iptax.timing.get_last_report_date", return_value=date(2024, 9, 25)):
            start, end = timing.get_did_range("2024-10")
        # Should start from last report + 1, not Oct 1
        assert start == date(2024, 9, 26)  # Last report + 1 day
        assert end == date(2024, 12, 5)  # Today

    @pytest.mark.unit
    def test_days_1_to_10_auto_detect_month_uses_full_range(self, monkeypatch):
        """Days 1-10: Auto-detected month (previous) should use full month.

        When today is Dec 5 and we request Nov (the finalization month),
        we should use full month range for Did.
        """
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-12-05")
        start, end = timing.get_did_range("2024-11")
        # Should use full November, not history
        assert start == date(2024, 11, 1)
        assert end == date(2024, 11, 30)


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
