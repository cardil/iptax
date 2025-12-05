"""Unit tests for workday validation."""

from datetime import date

from iptax.workday.models import CalendarEntry
from iptax.workday.validation import get_workdays_in_range, validate_workday_coverage


class TestGetWorkdaysInRange:
    """Test get_workdays_in_range function."""

    def test_single_week(self) -> None:
        """Test getting workdays for a single week."""
        start = date(2024, 11, 4)  # Monday
        end = date(2024, 11, 8)  # Friday

        workdays = get_workdays_in_range(start, end)

        assert len(workdays) == 5
        assert workdays[0] == date(2024, 11, 4)  # Monday
        assert workdays[-1] == date(2024, 11, 8)  # Friday

    def test_includes_weekend(self) -> None:
        """Test that weekends are excluded."""
        start = date(2024, 11, 1)  # Friday
        end = date(2024, 11, 4)  # Monday

        workdays = get_workdays_in_range(start, end)

        # Should have Friday (1st) and Monday (4th), not Sat/Sun
        assert len(workdays) == 2
        assert date(2024, 11, 1) in workdays  # Friday
        assert date(2024, 11, 4) in workdays  # Monday
        assert date(2024, 11, 2) not in workdays  # Saturday
        assert date(2024, 11, 3) not in workdays  # Sunday

    def test_full_month(self) -> None:
        """Test getting workdays for a full month."""
        start = date(2024, 11, 1)
        end = date(2024, 11, 30)

        workdays = get_workdays_in_range(start, end)

        # November 2024 has 21 workdays (30 days - 4 Saturdays - 5 Sundays)
        assert len(workdays) == 21

    def test_single_day(self) -> None:
        """Test with start and end on same day."""
        start = date(2024, 11, 4)  # Monday
        end = date(2024, 11, 4)

        workdays = get_workdays_in_range(start, end)

        assert len(workdays) == 1
        assert workdays[0] == date(2024, 11, 4)

    def test_single_weekend_day(self) -> None:
        """Test with single weekend day."""
        start = date(2024, 11, 2)  # Saturday
        end = date(2024, 11, 2)

        workdays = get_workdays_in_range(start, end)

        assert len(workdays) == 0


class TestValidateWorkdayCoverage:
    """Test validate_workday_coverage function."""

    def test_complete_coverage(self) -> None:
        """Test with complete workday coverage."""
        start = date(2024, 11, 4)  # Monday
        end = date(2024, 11, 8)  # Friday

        # Create entries for all workdays
        entries = [
            CalendarEntry(
                entry_date=date(2024, 11, 4),
                title="Work",
                entry_type="work",
                hours=8.0,
            ),
            CalendarEntry(
                entry_date=date(2024, 11, 5),
                title="Work",
                entry_type="work",
                hours=8.0,
            ),
            CalendarEntry(
                entry_date=date(2024, 11, 6),
                title="Work",
                entry_type="work",
                hours=8.0,
            ),
            CalendarEntry(
                entry_date=date(2024, 11, 7),
                title="Work",
                entry_type="work",
                hours=8.0,
            ),
            CalendarEntry(
                entry_date=date(2024, 11, 8),
                title="Work",
                entry_type="work",
                hours=8.0,
            ),
        ]

        missing = validate_workday_coverage(entries, start, end)

        assert len(missing) == 0

    def test_missing_days(self) -> None:
        """Test with missing workdays."""
        start = date(2024, 11, 4)  # Monday
        end = date(2024, 11, 8)  # Friday

        # Missing Wednesday and Friday
        entries = [
            CalendarEntry(
                entry_date=date(2024, 11, 4),
                title="Work",
                entry_type="work",
                hours=8.0,
            ),
            CalendarEntry(
                entry_date=date(2024, 11, 5),
                title="Work",
                entry_type="work",
                hours=8.0,
            ),
            CalendarEntry(
                entry_date=date(2024, 11, 7),
                title="Work",
                entry_type="work",
                hours=8.0,
            ),
        ]

        missing = validate_workday_coverage(entries, start, end)

        assert len(missing) == 2
        assert date(2024, 11, 6) in missing  # Wednesday
        assert date(2024, 11, 8) in missing  # Friday

    def test_weekend_not_required(self) -> None:
        """Test that weekend days don't need entries."""
        start = date(2024, 11, 1)  # Friday
        end = date(2024, 11, 4)  # Monday

        # Only have Friday and Monday, no Saturday/Sunday
        entries = [
            CalendarEntry(
                entry_date=date(2024, 11, 1),
                title="Work",
                entry_type="work",
                hours=8.0,
            ),
            CalendarEntry(
                entry_date=date(2024, 11, 4),
                title="Work",
                entry_type="work",
                hours=8.0,
            ),
        ]

        missing = validate_workday_coverage(entries, start, end)

        assert len(missing) == 0

    def test_pto_counts_as_coverage(self) -> None:
        """Test that PTO/absence entries count as coverage."""
        start = date(2024, 11, 4)  # Monday
        end = date(2024, 11, 6)  # Wednesday

        # Mix of work and PTO
        entries = [
            CalendarEntry(
                entry_date=date(2024, 11, 4),
                title="Work",
                entry_type="work",
                hours=8.0,
            ),
            CalendarEntry(
                entry_date=date(2024, 11, 5),
                title="Vacation",
                entry_type="pto",
                hours=8.0,
            ),
            CalendarEntry(
                entry_date=date(2024, 11, 6),
                title="Holiday",
                entry_type="holiday",
                hours=0.0,
            ),
        ]

        missing = validate_workday_coverage(entries, start, end)

        assert len(missing) == 0

    def test_empty_entries(self) -> None:
        """Test with no entries at all."""
        start = date(2024, 11, 4)  # Monday
        end = date(2024, 11, 8)  # Friday

        entries = []

        missing = validate_workday_coverage(entries, start, end)

        # All 5 workdays should be missing
        assert len(missing) == 5
