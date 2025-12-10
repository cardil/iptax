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

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from iptax.cache.history import HistoryManager
from iptax.models import HistoryEntry, ReportDateRanges
from iptax.utils.env import get_month_end_date, get_today

PAYMENT_DEADLINE_DAY = 10

DEFAULT_DID_START_DAY = 25

MIN_RANGE_DAYS = 15

DECEMBER = 12


class DateRangeError(Exception):
    """Error raised when date range is invalid.

    This includes:
    - Gap detected between target month end and next month start in history
    - Date range too short (less than MIN_RANGE_DAYS days)
    """

    pass


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


@dataclass
class _DidRangeContext:
    """Context for Did date range calculation."""

    prev_entry: HistoryEntry | None
    target_entry: HistoryEntry | None
    next_entry: HistoryEntry | None
    has_relevant_history: bool
    is_past: bool
    prev_year: int
    prev_month: int
    target_year: int
    target_month: int
    target_month_end: date
    today: date


def _calculate_did_start_date(ctx: _DidRangeContext) -> date:
    """Calculate Did start date based on history and context."""
    if ctx.prev_entry:
        return ctx.prev_entry.last_change_date + timedelta(days=1)
    if ctx.has_relevant_history:
        return date(ctx.prev_year, ctx.prev_month, DEFAULT_DID_START_DAY)
    if ctx.is_past:
        return date(ctx.target_year, ctx.target_month, 1)
    return date(ctx.prev_year, ctx.prev_month, DEFAULT_DID_START_DAY)


def _calculate_did_end_date(ctx: _DidRangeContext) -> date:
    """Calculate Did end date based on history and context."""
    if ctx.target_entry:
        return ctx.target_entry.last_change_date
    if ctx.next_entry:
        return ctx.next_entry.first_change_date - timedelta(days=1)
    if ctx.is_past:
        if ctx.has_relevant_history:
            return date(ctx.target_year, ctx.target_month, DEFAULT_DID_START_DAY)
        return ctx.target_month_end
    cutoff_25th = date(ctx.target_year, ctx.target_month, DEFAULT_DID_START_DAY)
    return min(ctx.today, cutoff_25th)


def get_did_range(month: str) -> tuple[date, date]:
    """Get Did date range for a specific month.

    The Did range is determined by history to avoid missing or duplicating changes.
    See _calculate_did_start_date and _calculate_did_end_date for detailed logic.

    Args:
        month: Month in YYYY-MM format (target month for report)

    Returns:
        Tuple of (start_date, end_date)

    Raises:
        DateRangeError: If gap detected in history or range < MIN_RANGE_DAYS days
    """
    today = get_today()

    year, month_num = month.split("-")
    target_year = int(year)
    target_month = int(month_num)

    # Load history
    history = HistoryManager()
    history.load()
    entries = history.get_all_entries()

    # Get adjacent month keys
    prev_year, prev_month = _get_prev_month(target_year, target_month)
    prev_month_key = f"{prev_year}-{prev_month:02d}"

    next_year, next_month = _get_next_month(target_year, target_month)
    next_month_key = f"{next_year}-{next_month:02d}"

    # Get history entries
    prev_entry = entries.get(prev_month_key)
    target_entry = entries.get(month)
    next_entry = entries.get(next_month_key)

    # Only consider history relevant to this target month (prev/target/next)
    has_relevant_history = bool(prev_entry or target_entry or next_entry)

    # Check for gap between target and next
    if target_entry and next_entry:
        expected_next_start = target_entry.last_change_date + timedelta(days=1)
        if expected_next_start != next_entry.first_change_date:
            target_end = target_entry.last_change_date
            next_start = next_entry.first_change_date
            raise DateRangeError(
                f"Gap detected between target month end ({target_end}) "
                f"and next month start ({next_start})"
            )

    # Determine if past month
    target_month_end = get_month_end_date(target_year, target_month)
    is_past = target_month_end < today

    # Calculate dates using context
    ctx = _DidRangeContext(
        prev_entry=prev_entry,
        target_entry=target_entry,
        next_entry=next_entry,
        has_relevant_history=has_relevant_history,
        is_past=is_past,
        prev_year=prev_year,
        prev_month=prev_month,
        target_year=target_year,
        target_month=target_month,
        target_month_end=target_month_end,
        today=today,
    )
    start_date = _calculate_did_start_date(ctx)
    end_date = _calculate_did_end_date(ctx)

    # Validate range
    range_days = (end_date - start_date).days + 1
    if range_days < MIN_RANGE_DAYS:
        raise DateRangeError(
            f"Date range too short ({range_days} days). "
            f"Need at least {MIN_RANGE_DAYS} days for valid report. "
            f"Range: {start_date} to {end_date}"
        )

    return start_date, end_date


def is_finalization_window() -> bool:
    """Check if we're in the finalization window (days 1-10).

    Returns:
        True if today is days 1-10, False otherwise
    """
    return get_today().day <= PAYMENT_DEADLINE_DAY
