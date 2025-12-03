"""CLI utility functions."""

from datetime import date, datetime

from iptax.utils.env import get_month_end_date


def parse_month_key(month: str | None) -> str:
    """Parse month string to normalized YYYY-MM format.

    Args:
        month: Month string (YYYY-MM) or None for current month

    Returns:
        Normalized month key

    Raises:
        ValueError: If month format is invalid
    """
    if month:
        parsed_month = datetime.strptime(month, "%Y-%m")
        return parsed_month.strftime("%Y-%m")
    return datetime.now().strftime("%Y-%m")


def get_date_range(month_key: str) -> tuple[date, date]:
    """Get start and end date for a month.

    Args:
        month_key: Month in YYYY-MM format

    Returns:
        Tuple of (start_date, end_date)
    """
    year, month_num = month_key.split("-")
    start_date = datetime(int(year), int(month_num), 1).date()
    end_date = get_month_end_date(int(year), int(month_num))
    return start_date, end_date
