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

from iptax.cache.history import get_last_report_date
from iptax.models import ReportDateRanges
from iptax.utils.env import get_month_end_date, get_today

PAYMENT_DEADLINE_DAY = 10

DEFAULT_DID_START_DAY = 25


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


def get_did_range(month: str) -> tuple[date, date]:
    """Get Did date range based on Polish legal timing logic.

    The logic differs based on when the tool is run:

    Days 1-10 (finalizing previous month):
    Did uses the same range as Workday (full target month)
    Example: Run Dec 5, Did is Nov 1-30

    Days 11-31 (working on current month):
    Did uses rolling window: (today minus 1 month) to today
    If history exists, starts from last report date plus 1
    Example: Run Nov 25, Did is Oct 25 to Nov 25

    Args:
        month: Month in YYYY-MM format (target month for report)

    Returns:
        Tuple of (start_date, end_date)
    """
    today = get_today()

    year, month_num = month.split("-")
    target_year = int(year)
    target_month = int(month_num)

    if today.day <= PAYMENT_DEADLINE_DAY:
        start_date = date(target_year, target_month, 1)
        end_date = get_month_end_date(target_year, target_month)
        return start_date, end_date

    last_report = get_last_report_date()

    if last_report is not None:
        start_date = last_report + timedelta(days=1)
    else:
        if target_month == 1:
            prev_year = target_year - 1
            prev_month = 12
        else:
            prev_year = target_year
            prev_month = target_month - 1

        try:
            start_date = date(prev_year, prev_month, DEFAULT_DID_START_DAY)
        except ValueError:
            start_date = get_month_end_date(prev_year, prev_month)

    return start_date, today


def is_finalization_window() -> bool:
    """Check if we're in the finalization window (days 1-10).

    Returns:
        True if today is days 1-10, False otherwise
    """
    return get_today().day <= PAYMENT_DEADLINE_DAY
