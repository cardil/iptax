"""Reusable CLI flows for business logic."""

from dataclasses import dataclass
from datetime import date

from rich.console import Console

from iptax.ai.cache import JudgmentCacheManager
from iptax.ai.prompts import build_judgment_prompt
from iptax.ai.provider import AIProvider
from iptax.ai.review import ReviewResult
from iptax.ai.review import review_judgments as run_review_tui
from iptax.cache.history import HistoryManager
from iptax.cache.inflight import InFlightCache
from iptax.config import load_settings as config_load_settings
from iptax.did import fetch_changes as did_fetch_changes
from iptax.models import Change, Decision, InFlightReport, Judgment, Settings
from iptax.timing import resolve_date_ranges
from iptax.workday.client import WorkdayClient
from iptax.workday.models import CalendarEntry
from iptax.workday.validation import validate_workday_coverage

from .elements import (
    count_decisions,
    display_review_results,
    format_decision_summary,
)

# Constants
MAX_MISSING_DAYS_TO_SHOW = 5
MIN_REPORTS_FOR_LAST = 2  # Need at least 2 reports for "last" to differ from "latest"


@dataclass
class DateRangeOverrides:
    """Optional date range overrides for flows."""

    workday_start: date | None = None
    workday_end: date | None = None
    did_start: date | None = None
    did_end: date | None = None


@dataclass
class FlowOptions:
    """Options for flow execution."""

    skip_workday: bool = False
    skip_did: bool = False
    skip_ai: bool = False
    skip_review: bool = False
    force: bool = False


def fetch_changes(
    console: Console,
    settings: Settings,
    start_date: date,
    end_date: date,
) -> list[Change]:
    """Fetch changes from DID.

    Args:
        console: Rich console for output
        settings: Application settings
        start_date: Start date for fetching
        end_date: End date for fetching

    Returns:
        List of changes
    """
    console.print("[cyan]🔍[/cyan] Fetching changes from did...")
    changes = did_fetch_changes(settings, start_date, end_date)
    change_word = "change" if len(changes) == 1 else "changes"
    console.print(f"[green]✓[/green] Found {len(changes)} {change_word}")
    return changes


def load_settings(console: Console) -> Settings:
    """Load settings with console output.

    Args:
        console: Rich console for output

    Returns:
        Loaded settings
    """
    settings = config_load_settings()
    console.print("[cyan]✓[/cyan] Settings loaded")
    return settings


def load_history(console: Console) -> HistoryManager:
    """Load history manager with console output.

    Args:
        console: Rich console for output

    Returns:
        Loaded history manager
    """
    manager = HistoryManager()
    manager.load()
    console.print("[cyan]✓[/cyan] History loaded")
    return manager


async def review(
    console: Console,
    judgments: list[Judgment],
    changes: list[Change],
) -> ReviewResult:
    """Run interactive review of AI judgments with summary.

    Shows pre-review summary, runs TUI, then shows post-review results.

    Args:
        console: Rich console for output
        judgments: List of AI judgments to review
        changes: List of changes for title lookup

    Returns:
        ReviewResult with potentially modified judgments
    """
    # Early return for empty judgments
    if not judgments:
        console.print("\n[yellow]No AI judgments to review.[/yellow]")
        return ReviewResult(judgments=[], accepted=False)

    # Pre-review summary using AI decisions (not final)
    include_count, exclude_count, uncertain_count = count_decisions(
        judgments, use_final=False
    )
    summary = format_decision_summary(include_count, exclude_count, uncertain_count)
    console.print(f"\n[bold]AI analysis:[/] {summary}")

    # Run TUI
    result = await run_review_tui(judgments, changes)

    # Mark all judgments as reviewed by setting user_decision if not set
    if result.accepted:
        for judgment in result.judgments:
            if judgment.user_decision is None:
                judgment.user_decision = judgment.decision

    # Post-review results
    display_review_results(console, result.judgments, changes, accepted=result.accepted)

    return result


async def _fetch_workday_data(
    console: Console,
    report: InFlightReport,
    settings: Settings,
    start_date: date,
    end_date: date,
) -> None:
    """Fetch and validate Workday data, updating report in place.

    Args:
        console: Rich console for output
        report: In-flight report to update
        settings: Application settings
        start_date: Start date for Workday range
        end_date: End date for Workday range
    """
    console.print(f"\n[cyan]📅[/cyan] Fetching Workday: {start_date} to {end_date}")

    client = WorkdayClient(settings.workday, console=console)
    work_hours = await client.fetch_work_hours(start_date, end_date, headless=True)

    # Validate coverage
    calendar_entries = [
        CalendarEntry(
            entry_date=e.entry_date,
            title=e.title,
            entry_type=e.entry_type,
            hours=e.hours,
        )
        for e in work_hours.calendar_entries
    ]
    missing = validate_workday_coverage(calendar_entries, start_date, end_date)

    if missing:
        console.print(
            f"\n[red]⚠ WARNING:[/red] Missing Workday entries for {len(missing)} days!"
        )
        console.print(
            "[yellow]This is a legal compliance issue "
            "(misdemeanor under Polish law)[/yellow]"
        )
        for day in missing[:MAX_MISSING_DAYS_TO_SHOW]:
            console.print(f"  - {day.strftime('%Y-%m-%d (%A)')}")
        if len(missing) > MAX_MISSING_DAYS_TO_SHOW:
            console.print(f"  ... and {len(missing) - MAX_MISSING_DAYS_TO_SHOW} more")
        report.workday_validated = False
    else:
        console.print("[green]✓[/green] All workdays have entries")
        report.workday_validated = True

    # Store Workday data
    report.workday_entries = work_hours.calendar_entries
    report.total_hours = work_hours.total_hours
    report.working_days = work_hours.working_days
    report.absence_days = work_hours.absence_days

    console.print(
        f"[green]✓[/green] Workday: {work_hours.working_days} days, "
        f"{work_hours.total_hours} hours"
    )


async def collect_flow(
    console: Console,
    month: str | None = None,
    options: FlowOptions | None = None,
    overrides: DateRangeOverrides | None = None,
) -> bool:
    """Data collection flow for a monthly report.

    Fetches Did changes and Workday hours, saves to in-flight cache.

    Args:
        console: Rich console for output
        month: Month specification (None|current|last|YYYY-MM)
        options: Flow execution options
        overrides: Optional date range overrides

    Returns:
        True if successful, False on failure
    """
    if options is None:
        options = FlowOptions()
    if overrides is None:
        overrides = DateRangeOverrides()

    # Load settings
    settings = load_settings(console)

    # Resolve date ranges
    ranges = resolve_date_ranges(
        month,
        workday_start=overrides.workday_start,
        workday_end=overrides.workday_end,
        did_start=overrides.did_start,
        did_end=overrides.did_end,
    )

    # Determine month key from workday range
    month_key = ranges.workday_start.strftime("%Y-%m")

    # Check for existing in-flight
    cache = InFlightCache()
    if options.force and cache.exists(month_key):
        console.print(
            f"[yellow]🗑[/yellow] Discarding existing in-flight for {month_key}"
        )
        cache.delete(month_key)
    elif cache.exists(month_key):
        existing_report = cache.load(month_key)
        console.print(f"\n[red]✗[/red] In-flight report already exists for {month_key}")
        if existing_report:
            _display_inflight_summary(console, existing_report)
        console.print("\nUse --force to discard and start fresh")
        return False

    # Create in-flight report
    report = InFlightReport(
        month=month_key,
        workday_start=ranges.workday_start,
        workday_end=ranges.workday_end,
        changes_since=ranges.did_start,
        changes_until=ranges.did_end,
    )

    # Fetch Did changes
    if not options.skip_did:
        console.print(
            f"\n[cyan]📥[/cyan] Fetching Did changes: "
            f"{ranges.did_start} to {ranges.did_end}"
        )
        changes = fetch_changes(console, settings, ranges.did_start, ranges.did_end)
        report.changes = changes
    else:
        console.print("[yellow]⏭[/yellow] Skipping Did collection")

    # Fetch Workday data
    if not options.skip_workday and settings.workday.enabled:
        await _fetch_workday_data(
            console, report, settings, ranges.workday_start, ranges.workday_end
        )
    elif options.skip_workday:
        console.print("[yellow]⏭[/yellow] Skipping Workday collection")
    else:
        console.print("[yellow]⏭[/yellow] Workday disabled in settings")

    # Save to cache
    saved_path = cache.save(report)
    console.print(f"\n[green]✓[/green] Saved to: {saved_path}")

    # Display summary
    _display_inflight_summary(console, report)

    # Next steps
    console.print("\n[bold]Next steps:[/bold]")
    if not options.skip_did and report.changes:
        console.print("  • Run [cyan]iptax review[/cyan] to review AI judgments")
    console.print("  • Run [cyan]iptax report[/cyan] to complete and generate report")

    return True


def _run_ai_filtering(
    console: Console,
    changes: list[Change],
    settings: Settings,
) -> list[Judgment]:
    """Run AI filtering on changes.

    Args:
        console: Rich console for output
        changes: List of changes to filter
        settings: Application settings

    Returns:
        List of AI judgments
    """
    # Load history from AI cache for learning context
    ai_cache = JudgmentCacheManager()
    history = ai_cache.get_history_for_prompt(settings.product.name)
    if history:
        console.print(
            f"[cyan]📚[/cyan] Using {len(history)} cached judgments for context"
        )

    # Build prompt for all changes at once (batch processing)
    prompt = build_judgment_prompt(settings.product.name, changes, history=history)

    # Call AI provider with spinner
    provider = AIProvider(settings.ai)
    with console.status(
        f"[cyan]🤖 Running AI filtering on {len(changes)} changes...[/cyan]",
        spinner="dots",
    ):
        response = provider.judge_changes(prompt)

    # Get AI provider string
    if hasattr(settings.ai, "model"):
        ai_provider_str = f"{settings.ai.provider}/{settings.ai.model}"
    else:
        ai_provider_str = f"{settings.ai.provider}/unknown"

    # Convert AIResponseItems to Judgments with all required fields
    judgments: list[Judgment] = []
    for item in response.judgments:
        # Find corresponding change
        change = next((c for c in changes if c.get_change_id() == item.change_id), None)
        if not change:
            continue  # Skip if change not found

        judgment = Judgment(
            change_id=item.change_id,
            decision=item.decision,
            reasoning=item.reasoning,
            product=settings.product.name,
            url=change.get_url(),
            description=change.title,
            ai_provider=ai_provider_str,
        )
        judgments.append(judgment)

    return judgments


def _display_inflight_summary(console: Console, report: InFlightReport) -> None:
    """Display in-flight report summary with date ranges.

    Args:
        console: Rich console for output
        report: In-flight report to summarize
    """
    console.print("\n[bold]📋 In-Flight Report Summary:[/bold]")
    console.print(f"  [cyan]Report Month:[/cyan] {report.month}")
    console.print(
        f"  [cyan]Workday Range:[/cyan] "
        f"{report.workday_start} to {report.workday_end}"
    )
    console.print(
        f"  [cyan]Changes Range:[/cyan] "
        f"{report.changes_since} to {report.changes_until}"
    )
    console.print(f"  [cyan]Changes Collected:[/cyan] {len(report.changes)}")
    if report.total_hours is not None:
        console.print(
            f"  [cyan]Workday Hours:[/cyan] {report.total_hours} "
            f"({report.working_days} days)"
        )
        if report.workday_validated:
            console.print("  [green]✓ Workday Coverage:[/green] Complete")
        else:
            console.print("  [yellow]⚠ Workday Coverage:[/yellow] INCOMPLETE")
    if report.judgments:
        console.print(f"  [cyan]AI Judgments:[/cyan] {len(report.judgments)}")


def _display_collection_summary(console: Console, report: InFlightReport) -> None:
    """Display data collection summary (used in report flow).

    Args:
        console: Rich console for output
        report: In-flight report to summarize
    """
    console.print("\n[bold]Data Collection:[/bold]")
    console.print(f"  • Did changes: {len(report.changes)}")
    if report.total_hours is not None:
        console.print(f"  • Workday hours: {report.total_hours}")
        console.print(f"  • Working days: {report.working_days}")
        if not report.workday_validated:
            console.print("  [yellow]⚠ Workday validation: INCOMPLETE[/yellow]")


# Month alias sets for _resolve_review_month
_LATEST_ALIASES = {"latest", "current"}
_PREVIOUS_ALIASES = {"last", "previous", "prev"}


def _resolve_review_month(
    month_spec: str | None,
    available_reports: list[str],
) -> str | None:
    """Resolve month specification to a concrete month key.

    Args:
        month_spec: Month specification (None|latest|current|last|previous|prev|YYYY-MM)
        available_reports: List of available month keys

    Returns:
        Resolved month key or None if not found
    """
    if not available_reports:
        return None

    if month_spec is None or month_spec in _LATEST_ALIASES:
        # Return the most recent
        return max(available_reports)

    if month_spec in _PREVIOUS_ALIASES:
        # Return second most recent if available, else most recent
        sorted_reports = sorted(available_reports)
        if len(sorted_reports) >= MIN_REPORTS_FOR_LAST:
            return sorted_reports[-MIN_REPORTS_FOR_LAST]
        return sorted_reports[-1]

    # Assume YYYY-MM format
    if month_spec in available_reports:
        return month_spec

    return None


def _load_report_for_review(
    console: Console,
    cache: InFlightCache,
    month: str | None,
) -> tuple[InFlightReport | None, str | None]:
    """Load and validate report for review.

    Args:
        console: Rich console for output
        cache: In-flight cache manager
        month: Month specification

    Returns:
        Tuple of (report, month_key) or (None, None) on failure
    """
    reports = cache.list_all()

    if not reports:
        console.print("[red]✗[/red] No in-flight reports found")
        console.print("Run [cyan]iptax collect[/cyan] first")
        return None, None

    # Resolve month specification
    month_key = _resolve_review_month(month, reports)

    if month_key is None:
        console.print(f"[red]✗[/red] No in-flight report found for '{month}'")
        console.print("\nAvailable reports:")
        for m in sorted(reports):
            console.print(f"  • {m}")
        return None, None

    report = cache.load(month_key)

    if report is None:
        console.print(f"[red]✗[/red] Failed to load report for {month_key}")
        return None, None

    if not report.changes:
        console.print(f"[cyan]📋[/cyan] Reviewing report for {month_key}")
        _display_inflight_summary(console, report)
        console.print("[red]✗[/red] No changes to review")
        return None, None

    return report, month_key


async def _run_review_process(
    console: Console,
    cache: InFlightCache,
    report: InFlightReport,
    force: bool,
) -> bool:
    """Execute the review process for a loaded report.

    Args:
        console: Rich console for output
        cache: In-flight cache manager
        report: Report to review
        force: Force re-review even if already reviewed

    Returns:
        True if successful
    """
    # Check if already reviewed (ALL judgments have user decisions)
    all_reviewed = report.judgments and all(
        j.user_decision is not None for j in report.judgments
    )
    if all_reviewed and not force:
        console.print("\n[green]✓[/green] This report has already been reviewed.")
        # Show the existing review summary
        display_review_results(console, report.judgments, report.changes, accepted=True)
        console.print("\nUse --force to re-review.")
        return True  # Already reviewed is a success

    # Run AI filtering if needed
    # If --force, clear existing judgments and re-run AI
    if force and report.judgments:
        console.print(
            "[yellow]🗑[/yellow] Clearing existing AI judgments for re-analysis"
        )
        report.judgments = []

    if not report.judgments:
        settings = load_settings(console)

        report.judgments = _run_ai_filtering(console, report.changes, settings)
        cache.save(report)
        console.print("[green]✓[/green] AI filtering complete")

    # Run review TUI
    result = await review(console, report.judgments, report.changes)

    # Always save judgments (even partial reviews when user quits)
    report.judgments = result.judgments
    cache.save(report)

    if result.accepted:
        # Save to AI cache for learning context
        _save_judgments_to_ai_cache(console, result.judgments)
        console.print("\n[green]✓[/green] Review complete and saved")
    else:
        console.print("\n[yellow]⏳[/yellow] Partial review saved")

    return True  # Both accepted and partial reviews are success


async def review_flow(
    console: Console,
    month: str | None = None,
    force: bool = False,
) -> bool:
    """Interactive review flow for in-flight report.

    Loads in-flight data, runs AI filtering if needed, launches TUI.

    Args:
        console: Rich console for output
        month: Month specification (None|latest|last|YYYY-MM)
        force: Force re-review even if already reviewed

    Returns:
        True if successful, False on failure
    """
    cache = InFlightCache()
    report, month_key = _load_report_for_review(console, cache, month)

    if report is None:
        return False

    console.print(f"[cyan]📋[/cyan] Reviewing report for {month_key}")
    _display_inflight_summary(console, report)

    return await _run_review_process(console, cache, report, force)


def _save_judgments_to_ai_cache(console: Console, judgments: list[Judgment]) -> None:
    """Save judgments to AI cache for learning context.

    Args:
        console: Rich console for output
        judgments: List of judgments to save
    """
    ai_cache = JudgmentCacheManager()
    saved_count = 0
    for judgment in judgments:
        # Save each judgment to the AI cache
        ai_cache.add_judgment(judgment)
        saved_count += 1

    console.print(f"[green]✓[/green] Saved {saved_count} judgments to AI cache")


async def report_flow(
    console: Console,
    month: str | None = None,
    options: FlowOptions | None = None,
    overrides: DateRangeOverrides | None = None,
) -> bool:
    """Complete report flow: collect → AI → review → display.

    Args:
        console: Rich console for output
        month: Month specification
        options: Flow execution options
        overrides: Optional date range overrides

    Returns:
        True if successful, False on failure
    """
    if options is None:
        options = FlowOptions()
    if overrides is None:
        overrides = DateRangeOverrides()

    # Resolve month
    ranges = resolve_date_ranges(
        month,
        workday_start=overrides.workday_start,
        workday_end=overrides.workday_end,
        did_start=overrides.did_start,
        did_end=overrides.did_end,
    )
    month_key = ranges.workday_start.strftime("%Y-%m")

    # Check cache
    cache = InFlightCache()

    if options.force and cache.exists(month_key):
        console.print(
            f"[yellow]🗑[/yellow] Discarding existing in-flight for {month_key}"
        )
        cache.delete(month_key)

    # Run collect if no in-flight exists
    if not cache.exists(month_key):
        collect_options = FlowOptions(
            skip_workday=options.skip_workday,
            skip_did=False,
        )
        success = await collect_flow(
            console,
            month=month,
            options=collect_options,
            overrides=overrides,
        )
        if not success:
            return False

    # Load in-flight
    report = cache.load(month_key)
    if report is None:
        console.print(f"[red]✗[/red] Failed to load report for {month_key}")
        return False

    console.print(f"\n[cyan]📊[/cyan] Generating report for {month_key}")

    # Display collected data
    _display_collection_summary(console, report)

    # Run AI if needed and not skipped
    if not options.skip_ai and report.changes and not report.judgments:
        settings = load_settings(console)
        report.judgments = _run_ai_filtering(console, report.changes, settings)
        cache.save(report)

    # Review if needed and not skipped
    if not options.skip_review and report.judgments:
        result = await review(console, report.judgments, report.changes)

        # Always save judgments (even partial reviews)
        report.judgments = result.judgments
        cache.save(report)

        # Save to AI cache if review was accepted
        if result.accepted:
            _save_judgments_to_ai_cache(console, result.judgments)

    # Display final summary
    if report.judgments:
        include_count = sum(
            1 for j in report.judgments if j.final_decision == Decision.INCLUDE
        )
        console.print("\n[bold]Final Report:[/bold]")
        console.print(f"  • Approved changes: {include_count}")

    console.print(f"\n[green]✓[/green] Report ready for {month_key}")
    console.print("[dim]Note: Full report generation coming in next phase[/dim]")

    return True
