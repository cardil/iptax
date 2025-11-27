"""Utility functions for Workday integration."""

from __future__ import annotations

import re
from datetime import date, timedelta

# Weekday constants (Monday = 0, Friday = 4)
FRIDAY = 4


def calculate_working_days(start_date: date, end_date: date) -> int:
    """Calculate the number of working days (Mon-Fri) in a date range.

    Does not account for public holidays.

    Args:
        start_date: Start of the date range (inclusive)
        end_date: End of the date range (inclusive)

    Returns:
        Number of working days (Monday through Friday)
    """
    working_days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() <= FRIDAY:
            working_days += 1
        current = current + timedelta(days=1)
    return working_days


def _is_valid_float(value: str) -> bool:
    """Check if a string is a valid float."""
    try:
        float(value)
    except ValueError:
        return False
    else:
        return True


def _parse_week_range(week_text: str) -> tuple[date, date]:
    """Parse a week range string into start and end dates.

    Handles formats like:
    - "Nov 24 - 30, 2025" (same month)
    - "Dec 30, 2024 - Jan 5, 2025" (different months/years)

    Args:
        week_text: Week range text from Workday

    Returns:
        Tuple of (week_start, week_end) dates
    """
    # Normalize dash characters (en-dash and em-dash to hyphen)
    week_text = week_text.replace("\u2013", "-").replace("\u2014", "-")

    # Pattern for same month: "Nov 24 - 30, 2025"
    same_month_pattern = r"(\w+)\s+(\d+)\s*-\s*(\d+),\s*(\d{4})"
    match = re.match(same_month_pattern, week_text)
    if match:
        month_str, start_day, end_day, year = match.groups()
        month = _month_to_number(month_str)
        return (
            date(int(year), month, int(start_day)),
            date(int(year), month, int(end_day)),
        )

    # Pattern for different months: "Dec 30, 2024 - Jan 5, 2025"
    diff_month_pattern = r"(\w+)\s+(\d+),\s*(\d{4})\s*-\s*(\w+)\s+(\d+),\s*(\d{4})"
    match = re.match(diff_month_pattern, week_text)
    if match:
        start_month_str, start_day, start_year, end_month_str, end_day, end_year = (
            match.groups()
        )
        return (
            date(int(start_year), _month_to_number(start_month_str), int(start_day)),
            date(int(end_year), _month_to_number(end_month_str), int(end_day)),
        )

    # Pattern for different months same year: "Dec 30 - Jan 5, 2025"
    diff_month_same_year_pattern = r"(\w+)\s+(\d+)\s*-\s*(\w+)\s+(\d+),\s*(\d{4})"
    match = re.match(diff_month_same_year_pattern, week_text)
    if match:
        start_month_str, start_day, end_month_str, end_day, year = match.groups()
        start_month = _month_to_number(start_month_str)
        end_month = _month_to_number(end_month_str)
        # Handle year boundary (Dec -> Jan means start is previous year)
        end_year = int(year)
        start_year = end_year if start_month <= end_month else end_year - 1
        return (
            date(start_year, start_month, int(start_day)),
            date(end_year, end_month, int(end_day)),
        )

    raise ValueError(f"Could not parse week range: {week_text}")


def _month_to_number(month_str: str) -> int:
    """Convert month abbreviation to number.

    Args:
        month_str: Month abbreviation (e.g., "Jan", "Feb")

    Returns:
        Month number (1-12)
    """
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    return months[month_str.lower()[:3]]
