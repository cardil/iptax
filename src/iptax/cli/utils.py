"""CLI utility functions for date range resolution."""

from datetime import date, datetime, timedelta

from iptax.cache.history import get_last_report_date
from iptax.models import ReportDateRanges
from iptax.utils.env import get_month_end_date

# Polish legal requirement: payments due before 10th of next month
PAYMENT_DEADLINE_DAY = 10


def resolve_date_ranges(
    month: str | None,
    workday_start: date | None = None,
    workday_end: date | None = None,
    did_start: date | None = None,
    did_end: date | None = None,
) -> ReportDateRanges:
    """Resolve month specification to concrete date ranges.

    This is the main entry point for translating user input (month spec)
    into the four dates needed for reporting.

    Month spec can be:
    - None: Auto-detect based on Polish legal requirements (days 1-10 = last month)
    - "current": Force current month
    - "last": Force previous month
    - "YYYY-MM": Specific month

    Args:
        month: Month specification
        workday_start: Override Workday start date
        workday_end: Override Workday end date
        did_start: Override Did start date
        did_end: Override Did end date

    Returns:
        ReportDateRanges with resolved dates

    Example:
        # Auto-detect (run on Nov 25)
        >>> ranges = resolve_date_ranges(None)
        >>> ranges.workday_start
        date(2024, 11, 1)

        # Force current month
        >>> ranges = resolve_date_ranges("current")

        # Specific month with Did override
        >>> ranges = resolve_date_ranges("2024-11", did_start=date(2024, 10, 20))
    """
    # Step 1: Determine which month we're reporting for
    target_month = _resolve_month_spec(month)

    # Step 2: Calculate default date ranges
    default_wd_start, default_wd_end = _get_workday_range(target_month)
    default_did_start, default_did_end = _get_did_range(target_month)

    # Step 3: Apply overrides
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


def _resolve_month_spec(month: str | None) -> str:
    """Resolve month specification to YYYY-MM format.

    Args:
        month: Month spec (None|current|last|YYYY-MM)

    Returns:
        Month in YYYY-MM format
    """
    if month is None:
        return _auto_detect_month()

    if month == "current":
        return datetime.now().strftime("%Y-%m")

    if month == "last":
        today = date.today()
        if today.month == 1:
            return f"{today.year - 1}-12"
        return f"{today.year}-{today.month - 1:02d}"

    # Parse as YYYY-MM
    try:
        parsed = datetime.strptime(month, "%Y-%m")
        return parsed.strftime("%Y-%m")
    except ValueError as e:
        raise ValueError(
            f"Invalid month format '{month}'. " "Expected YYYY-MM, 'current', or 'last'"
        ) from e


def _auto_detect_month() -> str:
    """Auto-detect reporting month based on Polish legal requirements.

    Polish law requires employee payments before the 10th of next month.
    - Days 1-10: Report previous month
    - Days 11-31: Report current month

    Returns:
        Month in YYYY-MM format
    """
    today = date.today()

    if today.day <= PAYMENT_DEADLINE_DAY:
        # Report previous month
        if today.month == 1:
            return f"{today.year - 1}-12"
        return f"{today.year}-{today.month - 1:02d}"

    # Report current month
    return today.strftime("%Y-%m")


def _get_workday_range(month: str) -> tuple[date, date]:
    """Get Workday date range (full calendar month).

    Args:
        month: Month in YYYY-MM format

    Returns:
        Tuple of (start_date, end_date) for the full month
    """
    year, month_num = month.split("-")
    start_date = date(int(year), int(month_num), 1)
    end_date = get_month_end_date(int(year), int(month_num))
    return start_date, end_date


def _get_did_range(month: str) -> tuple[date, date]:
    """Get Did date range (skewed based on last report).

    Did range starts from last report date (or ~25th of prev month)
    and goes to today, ensuring no changes are missed or duplicated.

    Args:
        month: Month in YYYY-MM format (used for default calculation)

    Returns:
        Tuple of (start_date, end_date)
    """
    today = date.today()
    last_report = get_last_report_date()

    if last_report is not None:
        # Continue from last report
        start_date = last_report + timedelta(days=1)
    else:
        # No history: default to 25th of month before target month
        year, month_num = month.split("-")
        target_year = int(year)
        target_month = int(month_num)

        if target_month == 1:
            prev_year = target_year - 1
            prev_month = 12
        else:
            prev_year = target_year
            prev_month = target_month - 1

        # Try 25th, fallback to end of month if invalid (e.g., Feb 30)
        try:
            start_date = date(prev_year, prev_month, 25)
        except ValueError:
            start_date = get_month_end_date(prev_year, prev_month)

    return start_date, today
