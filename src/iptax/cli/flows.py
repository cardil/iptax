"""Reusable CLI flows for business logic."""

from dataclasses import dataclass
from datetime import date

from rich.console import Console

from iptax.ai.prompts import build_judgment_prompt
from iptax.ai.provider import AIProvider
from iptax.ai.review import ReviewResult
from iptax.ai.review import review_judgments as run_review_tui
from iptax.cache.history import HistoryManager
from iptax.cache.inflight import InFlightCache
from iptax.cli.utils import resolve_date_ranges
from iptax.config import load_settings as config_load_settings
from iptax.did import fetch_changes as did_fetch_changes
from iptax.models import Change, Decision, InFlightReport, Judgment, Settings
from iptax.workday.client import WorkdayClient
from iptax.workday.models import CalendarEntry
from iptax.workday.validation import validate_workday_coverage

from .elements import display_review_results

# Constants
MAX_MISSING_DAYS_TO_SHOW = 5


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
    force_new: bool = False


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


def review(
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

    # Pre-review summary
    include_count = sum(1 for j in judgments if j.decision == Decision.INCLUDE)
    exclude_count = sum(1 for j in judgments if j.decision == Decision.EXCLUDE)
    uncertain_count = sum(1 for j in judgments if j.decision == Decision.UNCERTAIN)

    console.print(
        f"\n[bold]AI Analysis Summary:[/] "
        f"[green]✓INCLUDE: {include_count}[/]  "
        f"[red]✗EXCLUDE: {exclude_count}[/]  "
        f"[yellow]?UNCERTAIN: {uncertain_count}[/]"
    )

    # Run TUI
    result = run_review_tui(judgments, changes)

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
) -> None:
    """Data collection flow for a monthly report.

    Fetches Did changes and Workday hours, saves to in-flight cache.

    Args:
        console: Rich console for output
        month: Month specification (None|current|last|YYYY-MM)
        options: Flow execution options
        overrides: Optional date range overrides
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
    if cache.exists(month_key):
        console.print(
            f"\n[yellow]⚠[/yellow] In-flight report already exists for {month_key}"
        )
        console.print("Use --force-new to discard and start fresh")
        return

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

    # Next steps
    console.print("\n[bold]Next steps:[/bold]")
    if not options.skip_did and report.changes:
        console.print("  • Run [cyan]iptax review[/cyan] to review AI judgments")
    console.print("  • Run [cyan]iptax report[/cyan] to complete and generate report")


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
    console.print(
        f"\n[cyan]🤖[/cyan] Running AI filtering on {len(changes)} changes..."
    )

    # Build prompt for all changes at once (batch processing)
    prompt = build_judgment_prompt(settings.product.name, changes, history=[])

    # Call AI provider
    provider = AIProvider(settings.ai)
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


def _display_collection_summary(console: Console, report: InFlightReport) -> None:
    """Display data collection summary.

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


async def review_flow(console: Console) -> None:
    """Interactive review flow for in-flight report.

    Loads in-flight data, runs AI filtering if needed, launches TUI.

    Args:
        console: Rich console for output
    """
    # Check for in-flight reports
    cache = InFlightCache()
    reports = cache.list_all()

    if not reports:
        console.print("[yellow]No in-flight reports found[/yellow]")
        console.print("Run [cyan]iptax collect[/cyan] first")
        return

    # For now, use the most recent
    month_key = max(reports)
    report = cache.load(month_key)

    if report is None:
        console.print(f"[red]Failed to load report for {month_key}[/red]")
        return

    console.print(f"[cyan]📋[/cyan] Reviewing report for {month_key}")

    # Check if we have changes
    if not report.changes:
        console.print("[yellow]No changes to review[/yellow]")
        return

    # Run AI filtering if not done yet
    if not report.judgments:
        settings = load_settings(console)

        report.judgments = _run_ai_filtering(console, report.changes, settings)
        cache.save(report)
        console.print("[green]✓[/green] AI filtering complete")

    # Run review TUI
    result = review(console, report.judgments, report.changes)

    if result.accepted:
        # Save updated judgments back
        report.judgments = result.judgments
        cache.save(report)
        console.print("\n[green]✓[/green] Review saved")


async def report_flow(
    console: Console,
    month: str | None = None,
    options: FlowOptions | None = None,
    overrides: DateRangeOverrides | None = None,
) -> None:
    """Complete report flow: collect → AI → review → display.

    Args:
        console: Rich console for output
        month: Month specification
        options: Flow execution options
        overrides: Optional date range overrides
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

    if options.force_new and cache.exists(month_key):
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
        await collect_flow(
            console,
            month=month,
            options=collect_options,
            overrides=overrides,
        )

    # Load in-flight
    report = cache.load(month_key)
    if report is None:
        console.print(f"[red]Failed to load report for {month_key}[/red]")
        return

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
        result = review(console, report.judgments, report.changes)

        if result.accepted:
            report.judgments = result.judgments
            cache.save(report)

    # Display final summary
    if report.judgments:
        include_count = sum(
            1 for j in report.judgments if j.final_decision == Decision.INCLUDE
        )
        console.print("\n[bold]Final Report:[/bold]")
        console.print(f"  • Approved changes: {include_count}")

    console.print(f"\n[green]✓[/green] Report ready for {month_key}")
    console.print("[dim]Note: Full report generation coming in next phase[/dim]")
