"""Workday data validation functions.

This module provides validation for Workday calendar data to ensure
complete coverage of all workdays in a reporting period. This is critical
for legal compliance - failing to report correct work hours is a misdemeanor
under Polish law.
"""

from datetime import date, timedelta

from iptax.models import WorkdayCalendarEntry

# Weekday constants (Monday=0, Sunday=6)
FRIDAY_WEEKDAY = 4


def get_workdays_in_range(start_date: date, end_date: date) -> list[date]:
    """Get all workdays (Monday-Friday) in a date range.

    Args:
        start_date: Start of range (inclusive)
        end_date: End of range (inclusive)

    Returns:
        List of dates representing all workdays in the range

    Example:
        >>> start = date(2024, 11, 1)
        >>> end = date(2024, 11, 30)
        >>> workdays = get_workdays_in_range(start, end)
        >>> len(workdays)  # November 2024 has ~21 workdays
        21
    """
    workdays = []
    current = start_date
    while current <= end_date:
        # Monday = 0, Sunday = 6
        if current.weekday() <= FRIDAY_WEEKDAY:  # Mon-Fri
            workdays.append(current)
        current += timedelta(days=1)

    return workdays


def validate_workday_coverage(
    entries: list[WorkdayCalendarEntry],
    start_date: date,
    end_date: date,
) -> list[date]:
    """Validate that all workdays in a date range have calendar entries.

    Checks if every workday (Mon-Fri) in the specified range has at least
    one calendar entry. Entries can be:
    - Work hours (Time Tracking type, may be multiple per day)
    - PTO (Time Off type)
    - Holiday (Holiday Calendar Entry Type)

    This is critical for legal compliance - all workdays must be accounted for.

    Args:
        entries: List of calendar entries from Workday
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)

    Returns:
        List of dates that are missing entries. Empty list means complete coverage.

    Example:
        >>> from iptax.models import WorkdayCalendarEntry
        >>> start = date(2024, 11, 1)
        >>> end = date(2024, 11, 30)
        >>> entries = [
        ...     WorkdayCalendarEntry(
        ...         entry_date=date(2024, 11, 1), title="Work",
        ...         entry_type="Time Tracking", hours=8.0
        ...     ),
        ...     WorkdayCalendarEntry(
        ...         entry_date=date(2024, 11, 4), title="Holiday",
        ...         entry_type="Holiday Calendar Entry Type", hours=0.0
        ...     ),
        ... ]
        >>> missing = validate_workday_coverage(entries, start, end)
        >>> if missing:
        ...     print(f"Missing entries for: {missing}")
    """
    # Get all workdays in the range
    workdays = get_workdays_in_range(start_date, end_date)

    # Get set of dates that have entries in the specified range
    # Any entry type counts (work hours, PTO, holiday)
    entry_dates = {
        entry.entry_date
        for entry in entries
        if start_date <= entry.entry_date <= end_date
    }

    # Find workdays without entries
    return [day for day in workdays if day not in entry_dates]
