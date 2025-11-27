"""Calendar data generators for Workday mock server."""

from calendar import monthcalendar
from datetime import date, timedelta
from typing import Any


def generate_full_work_week(week_start: date) -> dict[str, list[dict[str, Any]]]:
    """Generate a standard 40-hour work week (8 hours Mon-Fri).

    Args:
        week_start: Monday of the week

    Returns:
        Dictionary mapping date strings to calendar entries
    """
    data = {}
    for day_offset in range(5):  # Monday to Friday
        entry_date = week_start + timedelta(days=day_offset)
        data[entry_date.isoformat()] = [
            {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
        ]
    return data


def generate_partial_week(
    week_start: date, hours_per_day: list[float]
) -> dict[str, list[dict[str, Any]]]:
    """Generate a week with variable hours per day.

    Args:
        week_start: Monday of the week
        hours_per_day: List of hours for each day (Mon-Sun, use 0 for no entry)

    Returns:
        Dictionary mapping date strings to calendar entries
    """
    data = {}
    for day_offset, hours in enumerate(hours_per_day):
        if hours > 0:
            entry_date = week_start + timedelta(days=day_offset)
            data[entry_date.isoformat()] = [
                {
                    "title": "Regular/Time Worked",
                    "type": "Time Tracking",
                    "hours": hours,
                }
            ]
    return data


def generate_week_with_pto(
    week_start: date,
    pto_days: list[int],  # Day offsets (0=Monday, 4=Friday)
    pto_hours: float = 8.0,
) -> dict[str, list[dict[str, Any]]]:
    """Generate a week with PTO on specified days.

    Args:
        week_start: Monday of the week
        pto_days: List of day offsets for PTO (0=Monday, 4=Friday)
        pto_hours: Hours per PTO day (default: 8.0)

    Returns:
        Dictionary mapping date strings to calendar entries
    """
    data = generate_full_work_week(week_start)

    for day_offset in pto_days:
        entry_date = week_start + timedelta(days=day_offset)
        date_str = entry_date.isoformat()
        # Replace work entry with PTO
        data[date_str] = [
            {
                "title": "Paid Time Off in Hours",
                "type": "Time Tracking",
                "hours": pto_hours,
            }
        ]

    return data


def generate_empty_week() -> dict[str, list[dict[str, Any]]]:
    """Generate an empty week (no entries).

    Returns:
        Empty dictionary
    """
    return {}


def generate_month_data(
    year: int, month: int, pattern: str = "full"
) -> dict[str, list[dict[str, Any]]]:
    """Generate calendar data for an entire month.

    Args:
        year: Year (e.g., 2025)
        month: Month (1-12)
        pattern: Data pattern - "full", "partial", "with_pto", or "empty"

    Returns:
        Dictionary mapping date strings to calendar entries

    Patterns:
        - "full": Full 8-hour days Mon-Fri
        - "partial": Mix of full and partial days
        - "with_pto": Include some PTO days
        - "empty": No entries
    """
    data = {}
    weeks = monthcalendar(year, month)

    for week in weeks:
        # Find Monday of the week
        monday_day = week[0]
        if monday_day == 0:
            continue  # Week starts in previous month

        week_start = date(year, month, monday_day)

        if pattern == "full":
            data.update(generate_full_work_week(week_start))
        elif pattern == "partial":
            # Vary hours: 8, 6, 8, 4, 8 hours per day
            data.update(generate_partial_week(week_start, [8, 6, 8, 4, 8]))
        elif pattern == "with_pto":
            # One day of PTO per week (Wednesday)
            data.update(generate_week_with_pto(week_start, [2]))
        elif pattern == "empty":
            pass  # No data

    return data
