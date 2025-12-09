"""Unit tests for workday validation."""

from datetime import date

from iptax.models import WorkdayCalendarEntry
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

        # November 2024 has 21 workdays (30 days - 5 Saturdays - 4 Sundays)
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
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 4),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 5),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 6),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 7),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 8),
                title="Work",
                entry_type="Time Tracking",
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
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 4),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 5),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 7),
                title="Work",
                entry_type="Time Tracking",
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
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 1),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 4),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
        ]

        missing = validate_workday_coverage(entries, start, end)

        assert len(missing) == 0

    def test_pto_counts_as_coverage(self) -> None:
        """Test that PTO/absence entries count as coverage."""
        start = date(2024, 11, 4)  # Monday
        end = date(2024, 11, 6)  # Wednesday

        # Mix of work, time off, and holiday
        entries = [
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 4),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 5),
                title="Annual Leave",
                entry_type="Time Off",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 6),
                title="Independence Day",
                entry_type="Holiday Calendar Entry Type",
                hours=0.0,
            ),
        ]

        missing = validate_workday_coverage(entries, start, end)

        assert len(missing) == 0

    def test_empty_entries(self) -> None:
        """Test with no entries at all."""
        start = date(2024, 11, 4)  # Monday
        end = date(2024, 11, 8)  # Friday

        entries: list[WorkdayCalendarEntry] = []

        missing = validate_workday_coverage(entries, start, end)

        # All 5 workdays should be missing
        assert len(missing) == 5

    def test_payroll_calendar_marker_not_valid_coverage(self) -> None:
        """Test that payroll calendar markers don't count as valid coverage.

        This is a regression test for a bug where "Time Pay Calendar Event"
        entries (payroll period markers) were incorrectly counted as valid
        workday coverage, causing missing workdays to not be detected.
        """
        start = date(2024, 10, 28)  # Monday
        end = date(2024, 11, 1)  # Friday

        # Have real work entries for Mon-Thu, but Friday only has payroll marker
        entries = [
            WorkdayCalendarEntry(
                entry_date=date(2024, 10, 28),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 10, 29),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 10, 30),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2024, 10, 31),
                title="Work",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            # Friday (Nov 1) only has a payroll marker - should NOT count
            WorkdayCalendarEntry(
                entry_date=date(2024, 11, 1),
                title="Time Period End",
                entry_type="Time Pay Calendar Event",
                hours=0.0,
            ),
        ]

        missing = validate_workday_coverage(entries, start, end)

        # Friday should be reported as missing
        assert len(missing) == 1
        assert date(2024, 11, 1) in missing
