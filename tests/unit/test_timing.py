"""Tests for timing module."""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest

from iptax import timing
from iptax.cache.history import HistoryManager
from iptax.models import HistoryEntry
from iptax.utils.env import cache_dir_for_home

logger = logging.getLogger(__name__)


def _parse_date(s: str, default_year: int = 2024) -> date:
    """Parse human-readable date like 'Nov 25' or 'Nov 25, 2024' to date."""
    from datetime import datetime as dt

    s = s.strip()
    # Try with year first
    for fmt in ("%b %d, %Y", "%b %d %Y", "%B %d, %Y", "%B %d %Y"):
        try:
            return dt.strptime(s, fmt).date()
        except ValueError:
            continue
    # Try without year - append default_year to string to avoid deprecation warning
    for fmt in ("%b %d", "%B %d"):
        try:
            parsed = dt.strptime(f"{s}, {default_year}", f"{fmt}, %Y")
            return parsed.date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s}")


def _parse_target_month(target: str) -> tuple[int, int]:
    """Parse target month like 'Nov 2024' or '2024-11' to (year, month)."""
    from datetime import datetime as dt

    target = target.strip()

    # Try YYYY-MM format first
    if "-" in target and len(target) == 7:
        year, month = target.split("-")
        return int(year), int(month)

    # Try "Nov 2024" format
    for fmt in ("%b %Y", "%B %Y"):
        try:
            parsed = dt.strptime(target, fmt)
        except ValueError:
            continue
        else:
            return parsed.year, parsed.month

    raise ValueError(f"Cannot parse target month: {target}")


def _format_target_month(year: int, month: int) -> str:
    """Format target month as YYYY-MM for API calls."""
    return f"{year}-{month:02d}"


@dataclass
class DidRangeCase:
    """Test case for get_did_range function."""

    name: str
    today: str  # "Nov 25" or "Nov 25, 2024"
    target: str  # "Nov 2024" or "2024-11"
    prev_last: str | None  # "Oct 20" or None
    target_last: str | None  # "Nov 24" or None
    next_first: str | None  # "Dec 1" or None
    exp_start: str | None = None  # "Oct 25" or None (if error)
    exp_end: str | None = None  # "Nov 25" or None (if error)
    error_match: str | None = None  # If set, expect error with this pattern

    def __str__(self) -> str:
        return self.name


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
    def test_none_uses_auto_detect(self, monkeypatch):
        """Test None month spec uses auto_detect_month."""
        monkeypatch.setenv("IPTAX_FAKE_DATE", "2024-11-15")
        result = timing.resolve_month_spec(None)
        assert result == "2024-11"  # Day 15 returns current month

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


DID_RANGE_CASES = [
    # No History Cases
    DidRangeCase(
        name="1: Current, first use",
        today="Nov 25, 2024",
        target="Nov 2024",
        prev_last=None,
        target_last=None,
        next_first=None,
        exp_start="Oct 25",
        exp_end="Nov 25",
    ),
    DidRangeCase(
        name="1.5: Current, past 25th",
        today="Nov 26, 2024",
        target="Nov 2024",
        prev_last=None,
        target_last=None,
        next_first=None,
        exp_start="Oct 25",
        exp_end="Nov 25",
    ),
    DidRangeCase(
        name="2: Current, early",
        today="Nov 10, 2024",
        target="Nov 2024",
        prev_last=None,
        target_last=None,
        next_first=None,
        exp_start="Oct 25",
        exp_end="Nov 10",
    ),
    DidRangeCase(
        name="3: Past (finalization)",
        today="Dec 05, 2024",
        target="Nov 2024",
        prev_last=None,
        target_last=None,
        next_first=None,
        exp_start="Nov 01",
        exp_end="Nov 30",
    ),
    DidRangeCase(
        name="4: Old past",
        today="Dec 10, 2024",
        target="Aug 2024",
        prev_last=None,
        target_last=None,
        next_first=None,
        exp_start="Aug 01",
        exp_end="Aug 31",
    ),
    DidRangeCase(
        name="4.5: Old past, irrelevant history",
        # History exists for 2025 but not 2024 - should still use full month
        today="Dec 10, 2024",
        target="Aug 2024",
        prev_last=None,  # No Jul 2024 history
        target_last=None,  # No Aug 2024 history
        next_first=None,  # No Sep 2024 history
        # Test will add "irrelevant" history for 2025-08 in the setup
        exp_start="Aug 01",
        exp_end="Aug 31",
    ),
    # With Prev History
    DidRangeCase(
        name="5: Current, has prev",
        today="Nov 25, 2024",
        target="Nov 2024",
        prev_last="Oct 20",
        target_last=None,
        next_first=None,
        exp_start="Oct 21",
        exp_end="Nov 25",
    ),
    DidRangeCase(
        name="6: Past, has prev",
        today="Dec 05, 2024",
        target="Nov 2024",
        prev_last="Oct 20",
        target_last=None,
        next_first=None,
        exp_start="Oct 21",
        exp_end="Nov 25",
    ),
    DidRangeCase(
        name="7: Old, has prev",
        today="Dec 10, 2024",
        target="Aug 2024",
        prev_last="Jul 20",
        target_last=None,
        next_first=None,
        exp_start="Jul 21",
        exp_end="Aug 25",
    ),
    # With Target History (re-run)
    DidRangeCase(
        name="8: Re-run current",
        today="Nov 25, 2024",
        target="Nov 2024",
        prev_last="Oct 20",
        target_last="Nov 24",
        next_first=None,
        exp_start="Oct 21",
        exp_end="Nov 24",
    ),
    DidRangeCase(
        name="9: Re-run past",
        today="Dec 05, 2024",
        target="Nov 2024",
        prev_last="Oct 20",
        target_last="Nov 25",
        next_first=None,
        exp_start="Oct 21",
        exp_end="Nov 25",
    ),
    # With Next History (no target)
    DidRangeCase(
        name="10: Old, only next",
        today="Dec 10, 2024",
        target="Aug 2024",
        prev_last=None,
        target_last=None,
        next_first="Aug 23",
        exp_start="Jul 25",
        exp_end="Aug 22",
    ),
    DidRangeCase(
        name="11: Old, prev+next",
        today="Dec 10, 2024",
        target="Aug 2024",
        prev_last="Jul 20",
        target_last=None,
        next_first="Aug 23",
        exp_start="Jul 21",
        exp_end="Aug 22",
    ),
    # With Target + Next History (valid - consecutive dates)
    DidRangeCase(
        name="12: Old, target+next consecutive",
        today="Dec 10, 2024",
        target="Aug 2024",
        prev_last=None,
        target_last="Aug 22",
        next_first="Aug 23",
        exp_start="Jul 25",
        exp_end="Aug 22",
    ),
    DidRangeCase(
        name="13: Old, all history consecutive",
        today="Dec 10, 2024",
        target="Aug 2024",
        prev_last="Jul 20",
        target_last="Aug 22",
        next_first="Aug 23",
        exp_start="Jul 21",
        exp_end="Aug 22",
    ),
    # With Target + Next History (error - gap between target and next)
    DidRangeCase(
        name="14: Old, target+next gap (error)",
        today="Dec 10, 2024",
        target="Aug 2024",
        prev_last=None,
        target_last="Aug 20",
        next_first="Aug 25",
        error_match="Gap",
    ),
    DidRangeCase(
        name="15: Old, all history gap (error)",
        today="Dec 10, 2024",
        target="Aug 2024",
        prev_last="Jul 20",
        target_last="Aug 20",
        next_first="Aug 25",
        error_match="Gap",
    ),
    # Edge Cases
    DidRangeCase(
        name="16: January wrap",
        today="Jan 25, 2024",
        target="Jan 2024",
        prev_last="Dec 20",
        target_last=None,
        next_first=None,
        exp_start="Dec 21",
        exp_end="Jan 25",
    ),
    DidRangeCase(
        name="17: Month end",
        today="Nov 30, 2024",
        target="Nov 2024",
        prev_last="Oct 25",
        target_last=None,
        next_first=None,
        exp_start="Oct 26",
        exp_end="Nov 25",
    ),
    DidRangeCase(
        name="18: Day 1 (error)",
        today="Nov 01, 2024",
        target="Nov 2024",
        prev_last=None,
        target_last=None,
        next_first=None,
        error_match="at least 15 days",
    ),
    DidRangeCase(
        name="19: December target with next",
        today="Jan 10, 2025",
        target="Dec 2024",
        prev_last="Nov 20",
        target_last=None,
        next_first="Dec 23",  # This is Jan 2025 history key
        exp_start="Nov 21",
        exp_end="Dec 22",
    ),
]


def _build_history_entry(last_change: date) -> HistoryEntry:
    """Build a HistoryEntry from last_change_date."""
    return HistoryEntry(
        first_change_date=last_change.replace(day=max(1, last_change.day - 5)),
        last_change_date=last_change,
        generated_at=datetime(
            last_change.year, last_change.month, last_change.day, 10, 0, 0, tzinfo=UTC
        ),
    )


def _build_history_entry_from_first(first_change: date) -> HistoryEntry:
    """Build a HistoryEntry from first_change_date (for next month)."""
    return HistoryEntry(
        first_change_date=first_change,
        last_change_date=first_change.replace(day=min(first_change.day + 5, 28)),
        generated_at=datetime(
            first_change.year,
            first_change.month,
            first_change.day,
            10,
            0,
            0,
            tzinfo=UTC,
        ),
    )


class TestGetDidRange:
    """Parametrized tests for get_did_range with table-driven cases."""

    @pytest.mark.unit
    @pytest.mark.parametrize("case", DID_RANGE_CASES, ids=str)
    def test_did_range(self, case: DidRangeCase, monkeypatch, isolated_home):
        """Test Did date range calculation for various scenarios."""
        logger.debug("Test case: %s, isolated_home: %s", case.name, isolated_home)

        # Parse today and set fake date
        today = _parse_date(case.today)
        monkeypatch.setenv("IPTAX_FAKE_DATE", today.isoformat())

        target_year, target_month = _parse_target_month(case.target)
        target_api_format = _format_target_month(target_year, target_month)
        history: dict[str, HistoryEntry] = {}

        # Build prev month history
        if case.prev_last:
            prev_last_date = _parse_date(case.prev_last, default_year=target_year)
            # Determine correct year for prev month
            if target_month == 1:
                prev_last_date = prev_last_date.replace(year=target_year - 1)
            prev_month_key = f"{prev_last_date.year}-{prev_last_date.month:02d}"
            history[prev_month_key] = _build_history_entry(prev_last_date)

        # Build target month history
        if case.target_last:
            target_last_date = _parse_date(case.target_last, default_year=target_year)
            history[target_api_format] = _build_history_entry(target_last_date)

        # Build next month history
        if case.next_first:
            # Determine correct year and month for next month
            if target_month == 12:
                next_year = target_year + 1
                next_month_num = 1
            else:
                next_year = target_year
                next_month_num = target_month + 1
            # The date from next_first might be in the target month (Did ranges don't
            # align with calendar months), but the history KEY is for the next month
            next_first_date = _parse_date(case.next_first, default_year=next_year)
            # Correct year wrap for dates in December when target is December
            if target_month == 12 and next_first_date.month != 1:
                # Date like "Dec 23" for January target should stay in prev year
                next_first_date = next_first_date.replace(year=target_year)
            next_month_key = f"{next_year}-{next_month_num:02d}"
            history[next_month_key] = _build_history_entry_from_first(next_first_date)

        # Always add irrelevant history entries for 2025 to test isolation
        # This mimics real scenarios where old history exists but shouldn't affect
        # date calculations for older months
        history["2025-08"] = HistoryEntry(
            first_change_date=date(2025, 7, 18),
            last_change_date=date(2025, 9, 22),
            generated_at=datetime(2025, 9, 22, 15, 12, 54, tzinfo=UTC),
        )
        history["2025-09"] = HistoryEntry(
            first_change_date=date(2025, 8, 23),
            last_change_date=date(2025, 9, 25),
            generated_at=datetime(2025, 12, 9, 20, 8, 28, tzinfo=UTC),
        )

        # Save history (always have at least the 2025 entries now)
        cache_dir = cache_dir_for_home(isolated_home)
        cache_dir.mkdir(parents=True, exist_ok=True)
        manager = HistoryManager(history_path=cache_dir / "history.json")
        manager._history = history
        manager._loaded = True
        manager.save()

        # Run and assert
        if case.error_match:
            with pytest.raises(timing.DateRangeError, match=case.error_match):
                timing.get_did_range(target_api_format)
        else:
            # Parse expected dates
            exp_start = _parse_date(case.exp_start, default_year=target_year)
            exp_end = _parse_date(case.exp_end, default_year=target_year)
            # Handle year wrap for start
            if exp_start.month > target_month:
                exp_start = exp_start.replace(year=target_year - 1)

            start, end = timing.get_did_range(target_api_format)
            assert start == exp_start, f"Start: expected {exp_start}, got {start}"
            assert end == exp_end, f"End: expected {exp_end}, got {end}"


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
