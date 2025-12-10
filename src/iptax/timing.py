"""Date range timing logic for IP tax reporting.

This module implements the Polish legal requirements for IP tax reporting dates.

Polish Law Context:

Employee payments must be made before the 10th of the following month.
This creates two reporting windows:

1. Days 1-10 of a month (Finalization Window):
    Report for the PREVIOUS month. Both Workday and Did use the full calendar month.
    Example: Run Dec 5 to Report November (Nov 1-30 for both)

2. Days 11-31 of a month (Active Work Window):
    Report for the CURRENT month.
    Workday: Full calendar month (must fill hours ahead)
    Did: Rolling window from approx 1 month ago to today
    Example: Run Nov 25 to Report November (Workday: Nov 1-30, Did: Oct 25 to Nov 25)

Date Range Skewing:

The Did collector uses skewed dates to avoid missing or duplicating changes:
If history exists: Start from last report date plus 1 day
If no history: Start from approx 25th of the previous month
End date: Today (in rolling mode) or end of month (in finalization mode)
"""

from datetime import date, datetime, timedelta

from iptax.cache.history import HistoryManager
from iptax.models import ReportDateRanges
from iptax.utils.env import get_month_end_date, get_today

PAYMENT_DEADLINE_DAY = 10

DEFAULT_DID_START_DAY = 25

DECEMBER = 12


def resolve_date_ranges(
    month: str | None = None,
    workday_start: date | None = None,
    workday_end: date | None = None,
    did_start: date | None = None,
    did_end: date | None = None,
) -> ReportDateRanges:
    """Resolve month specification to concrete date ranges.

    This is the main entry point for translating user input (month spec)
    into the four dates needed for reporting.

    Month spec can be:
    None: Auto-detect based on Polish legal requirements (days 1-10 = last month)
    current: Force current month
    last: Force previous month
    YYYY-MM: Specific month

    Args:
        month: Month specification
        workday_start: Override Workday start date
        workday_end: Override Workday end date
        did_start: Override Did start date
        did_end: Override Did end date

    Returns:
        ReportDateRanges with resolved dates
    """
    target_month = resolve_month_spec(month)
    default_wd_start, default_wd_end = get_workday_range(target_month)
    default_did_start, default_did_end = get_did_range(target_month)

    wd_start = workday_start if workday_start is not None else default_wd_start
    wd_end = workday_end if workday_end is not None else default_wd_end
    did_start_final = did_start if did_start is not None else default_did_start
    did_end_final = did_end if did_end is not None else default_did_end

    return ReportDateRanges(
        workday_start=wd_start,
        workday_end=wd_end,
        did_start=did_start_final,
        did_end=did_end_final,
    )


def resolve_month_spec(month: str | None) -> str:
    """Resolve month specification to YYYY-MM format.

    Args:
        month: Month spec (None, current, last, or YYYY-MM)

    Returns:
        Month in YYYY-MM format

    Raises:
        ValueError: If month format is invalid
    """
    if month is None:
        return auto_detect_month()

    if month == "current":
        return get_today().strftime("%Y-%m")

    if month == "last":
        today = get_today()
        if today.month == 1:
            return f"{today.year - 1}-12"
        return f"{today.year}-{today.month - 1:02d}"

    try:
        parsed = datetime.strptime(month, "%Y-%m")
        return parsed.strftime("%Y-%m")
    except ValueError as e:
        raise ValueError(
            f"Invalid month format '{month}'. Expected YYYY-MM, 'current', or 'last'"
        ) from e


def auto_detect_month() -> str:
    """Auto-detect reporting month based on Polish legal requirements.

    Polish law requires employee payments before the 10th of next month.
    Days 1-10: Report previous month
    Days 11-31: Report current month

    Returns:
        Month in YYYY-MM format
    """
    today = get_today()

    if today.day <= PAYMENT_DEADLINE_DAY:
        if today.month == 1:
            return f"{today.year - 1}-12"
        return f"{today.year}-{today.month - 1:02d}"

    return today.strftime("%Y-%m")


def get_workday_range(month: str) -> tuple[date, date]:
    """Get Workday date range (full calendar month).

    Workday always uses the full calendar month regardless of when
    the tool is run. Users must fill hours ahead of time.

    Args:
        month: Month in YYYY-MM format

    Returns:
        Tuple of (start_date, end_date) for the full month
    """
    year, month_num = month.split("-")
    start_date = date(int(year), int(month_num), 1)
    end_date = get_month_end_date(int(year), int(month_num))
    return start_date, end_date


def _get_prev_month(year: int, month: int) -> tuple[int, int]:
    """Get previous month's year and month.

    Args:
        year: Target year
        month: Target month (1-12)

    Returns:
        Tuple of (year, month) for previous month
    """
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _get_next_month(year: int, month: int) -> tuple[int, int]:
    """Get next month's year and month.

    Args:
        year: Target year
        month: Target month (1-12)

    Returns:
        Tuple of (year, month) for next month
    """
    if month == DECEMBER:
        return year + 1, 1
    return year, month + 1


def get_did_range(month: str) -> tuple[date, date]:
    """Get Did date range for a specific month.

    The Did range is determined by history to avoid missing or duplicating changes:

    Start date:
    - If previous month has history: prev_month.last_change_date + 1
    - Otherwise: 1st of target month

    End date:
    - If target month has history: target_month.last_change_date
    - Else if next month has history: next_month.first_change_date - 1
    - Otherwise: 25th of target month (or today if current month)

    Examples:
    - 2024-08 with 2024-07 cutoff=23, 2024-08 cutoff=24: Jul 24 to Aug 24
    - 2024-08 with 2024-07 cutoff=23, no 2024-08: Jul 24 to Aug 25
    - 2024-08 with no history: Aug 1 to Aug 31

    Args:
        month: Month in YYYY-MM format (target month for report)

    Returns:
        Tuple of (start_date, end_date)
    """
    today = get_today()

    year, month_num = month.split("-")
    target_year = int(year)
    target_month = int(month_num)

    # Load history
    history = HistoryManager()
    history.load()
    entries = history.get_all_entries()

    # Get previous month key
    prev_year, prev_month = _get_prev_month(target_year, target_month)
    prev_month_key = f"{prev_year}-{prev_month:02d}"

    # Get next month key
    next_year, next_month = _get_next_month(target_year, target_month)
    next_month_key = f"{next_year}-{next_month:02d}"

    # Determine start date
    if prev_month_key in entries:
        # Start from day after previous month's cutoff
        prev_cutoff = entries[prev_month_key].last_change_date
        start_date = prev_cutoff + timedelta(days=1)
    else:
        # No previous history - start at 1st of target month
        start_date = date(target_year, target_month, 1)

    # Determine end date
    if month in entries:
        # Use target month's cutoff
        end_date = entries[month].last_change_date
    elif next_month_key in entries:
        # Use next month's first_change_date - 1
        next_start = entries[next_month_key].first_change_date
        end_date = next_start - timedelta(days=1)
    else:
        # No target or next month history - use 25th or end of month
        target_month_end = get_month_end_date(target_year, target_month)

        # If target month is in the past, use 25th as default end
        if target_month_end < today:
            try:
                end_date = date(target_year, target_month, DEFAULT_DID_START_DAY)
            except ValueError:
                end_date = target_month_end
        else:
            # Current or future month - use today or end of month
            end_date = min(today, target_month_end)

    return start_date, end_date


def is_finalization_window() -> bool:
    """Check if we're in the finalization window (days 1-10).

    Returns:
        True if today is days 1-10, False otherwise
    """
    return get_today().day <= PAYMENT_DEADLINE_DAY
