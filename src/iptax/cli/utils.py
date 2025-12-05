"""CLI utility functions.

For date range timing logic, see iptax.timing module.
"""

from datetime import date, datetime

from iptax.utils.env import get_month_end_date


def parse_month_key(month: str | None) -> str:
    """Parse month string to YYYY-MM format.

    Args:
        month: Month string in YYYY-MM format, or None for current month

    Returns:
        Month in YYYY-MM format

    Raises:
        ValueError: If month format is invalid
    """
    if month is None:
        return datetime.now().strftime("%Y-%m")

    parsed = datetime.strptime(month, "%Y-%m")
    return parsed.strftime("%Y-%m")


def get_date_range(month: str) -> tuple[date, date]:
    """Get date range for a calendar month.

    Args:
        month: Month in YYYY-MM format

    Returns:
        Tuple of (start_date, end_date) for the full month
    """
    year, month_num = month.split("-")
    start_date = date(int(year), int(month_num), 1)
    end_date = get_month_end_date(int(year), int(month_num))
    return start_date, end_date
