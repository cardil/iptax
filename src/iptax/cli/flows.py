"""Reusable CLI flows for business logic."""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import questionary
from rich.console import Console
from rich.prompt import Confirm

from iptax.ai.cache import JudgmentCacheManager, get_ai_cache_path
from iptax.ai.prompts import build_judgment_prompt
from iptax.ai.provider import AIProvider
from iptax.ai.review import ReviewResult
from iptax.ai.review import review_judgments as run_review_tui
from iptax.cache.history import HistoryManager, get_history_path, save_report_date
from iptax.cache.inflight import InFlightCache
from iptax.config import load_settings as config_load_settings
from iptax.did import fetch_changes as did_fetch_changes
from iptax.models import (
    AIProviderConfigBase,
    Change,
    Decision,
    DisabledAIConfig,
    Fields,
    InFlightReport,
    Judgment,
    Settings,
)
from iptax.report.compiler import compile_report
from iptax.report.generator import generate_all
from iptax.timing import resolve_date_ranges
from iptax.workday.client import WorkdayClient
from iptax.workday.validation import validate_workday_coverage

from .elements import (
    count_decisions,
    display_review_results,
    format_decision_summary,
)

# Constants
MAX_MISSING_DAYS_TO_SHOW = 5
MIN_REPORTS_FOR_LAST = 2  # Need at least 2 reports for "last" to differ from "latest"


def _get_playwright_command() -> list[str]:
    """Get the command to run playwright.

    Returns:
        Command list to run playwright (either via python -m or direct path).
    """
    # Try to find playwright in PATH first
    playwright_path = shutil.which("playwright")
    if playwright_path:
        return [playwright_path]
    # Fallback to python -m playwright
    return [sys.executable, "-m", "playwright"]


def _is_playwright_firefox_installed() -> bool:
    """Check if Playwright Firefox browser is installed.

    Uses `playwright install --list` to check browser cache.
    The output format lists installed browsers as paths like:
    /home/user/.cache/ms-playwright/firefox-1495

    Returns:
        True if Firefox is installed, False otherwise.
    """
    cmd = [*_get_playwright_command(), "install", "--list"]
    try:
        # S603: Command is built from trusted sources (sys.executable or shutil.which)
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    else:
        # Look for firefox browser path in the output (e.g. "firefox-1495")
        return result.returncode == 0 and "firefox-" in result.stdout


def _install_playwright_firefox(console: Console) -> bool:
    """Install Playwright Firefox browser.

    Args:
        console: Rich console for output

    Returns:
        True if installation succeeded, False otherwise.
    """
    console.print("[cyan]🔧[/cyan] Installing Playwright Firefox browser...")
    cmd = [*_get_playwright_command(), "install", "firefox"]
    try:
        # S603: Command is built from trusted sources (sys.executable or shutil.which)
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        console.print(
            "[red]✗[/red] Playwright not found. Is iptax installed correctly?"
        )
        return False
    else:
        if result.returncode != 0:
            console.print(f"[red]✗[/red] Failed to install browser: {result.stderr}")
            return False
        console.print("[green]✓[/green] Playwright Firefox browser installed")
        return True


def ensure_browser_installed(console: Console) -> bool:
    """Ensure Playwright Firefox is installed, installing if necessary.

    Args:
        console: Rich console for output

    Returns:
        True if browser is available (already installed or successfully installed).
    """
    if _is_playwright_firefox_installed():
        return True
    return _install_playwright_firefox(console)


def init_flow(console: Console) -> bool:
    """Initialize iptax by installing required browser.

    Args:
        console: Rich console for output

    Returns:
        True if initialization succeeded.
    """
    console.print("[cyan]🚀[/cyan] Initializing iptax...")

    if _is_playwright_firefox_installed():
        console.print("[green]✓[/green] Playwright Firefox already installed")
        return True

    return _install_playwright_firefox(console)


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


@dataclass
class OutputOptions:
    """Options for output generation."""

    output_dir: Path | None = None
    output_format: str = "all"


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
    date_range: tuple[date, date] | None = None,
) -> ReviewResult:
    """Run interactive review of AI judgments with summary.

    Shows pre-review summary, runs TUI, then shows post-review results.

    Args:
        console: Rich console for output
        judgments: List of AI judgments to review
        changes: List of changes for title lookup
        date_range: Optional tuple of (start_date, end_date) to display in header

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
    result = await run_review_tui(judgments, changes, date_range)

    # Mark all judgments as reviewed by setting user_decision if not set
    if result.accepted:
        for judgment in result.judgments:
            if judgment.user_decision is None:
                judgment.user_decision = judgment.decision

    # Post-review results
    display_review_results(console, result.judgments, changes, accepted=result.accepted)

    return result


# Minimum hours required for a valid report (before rounding)
MIN_WORK_HOURS = 0.5


async def _fetch_workday_data(
    console: Console,
    report: InFlightReport,
    settings: Settings,
    start_date: date,
    end_date: date,
) -> bool:
    """Fetch and validate Workday data, updating report in place.

    Args:
        console: Rich console for output
        report: In-flight report to update
        settings: Application settings
        start_date: Start date for Workday range
        end_date: End date for Workday range

    Returns:
        True if data was successfully fetched and validated (or user confirmed),
        False if hours are insufficient or coverage is incomplete and user declined.
    """
    console.print(f"\n[cyan]📅[/cyan] Fetching Workday: {start_date} to {end_date}")

    client = WorkdayClient(settings.workday, console=console)
    work_hours = await client.fetch_work_hours(start_date, end_date, headless=True)

    # Validate minimum hours early (before saving)
    if work_hours.total_hours < MIN_WORK_HOURS:
        console.print(
            f"\n[red]✗[/red] Insufficient work hours: {work_hours.total_hours:.1f}h"
        )
        console.print(
            "  At least 1 hour is required after rounding for report generation."
        )
        console.print("  Cannot create a report with 0 hours.")
        return False

    # Store Workday data (validated for minimum hours)
    report.workday_entries = work_hours.calendar_entries
    report.total_hours = work_hours.total_hours
    report.working_days = work_hours.working_days
    report.absence_days = work_hours.absence_days

    # Validate coverage
    missing = validate_workday_coverage(
        work_hours.calendar_entries, start_date, end_date
    )

    if missing:
        console.print(
            f"\n[red]⚠ WARNING:[/red] Missing Workday entries for {len(missing)} days!"
        )
        for day in missing[:MAX_MISSING_DAYS_TO_SHOW]:
            console.print(f"  - {day.strftime('%Y-%m-%d (%A)')}")
        if len(missing) > MAX_MISSING_DAYS_TO_SHOW:
            console.print(f"  ... and {len(missing) - MAX_MISSING_DAYS_TO_SHOW} more")
        report.workday_validated = False

        # Ask user if they want to continue (TTY) or fail (non-TTY/piped)
        if console.is_terminal:
            continue_anyway = Confirm.ask(
                "\n[bold]Continue with incomplete Workday coverage?[/bold]",
                default=False,
            )
            if not continue_anyway:
                console.print("[yellow]⏹[/yellow] Aborted by user")
                return False
            console.print(
                "[yellow]⚠[/yellow] Continuing with incomplete coverage "
                "(user confirmed)"
            )
        else:
            # Non-interactive mode: fail immediately
            console.print(
                "\n[red]✗[/red] Cannot proceed with incomplete Workday coverage "
                "in non-interactive mode"
            )
            return False
    else:
        console.print("[green]✓[/green] All workdays have entries")
        report.workday_validated = True

    return True


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
        workday_success = await _fetch_workday_data(
            console, report, settings, ranges.workday_start, ranges.workday_end
        )
        if not workday_success:
            # User declined or non-interactive mode with incomplete coverage
            # Don't save invalid report
            return False
    elif options.skip_workday:
        console.print("[yellow]⏭[/yellow] Skipping Workday collection")
    else:
        console.print("[yellow]⏭[/yellow] Workday disabled in settings")

    # Save to cache (only if we reach here - workday validated or skipped)
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
    # Get AI-specific settings with type narrowing
    ai_config = settings.ai
    max_learnings = Fields(AIProviderConfigBase).max_learnings.default
    correction_ratio = Fields(AIProviderConfigBase).correction_ratio.default
    hints: list[str] | None = None

    if isinstance(ai_config, AIProviderConfigBase):
        max_learnings = ai_config.max_learnings
        correction_ratio = ai_config.correction_ratio
        hints = ai_config.hints if ai_config.hints else None

    # Load history from AI cache for learning context
    ai_cache = JudgmentCacheManager()
    history = ai_cache.get_history_for_prompt(
        settings.product.name,
        max_entries=max_learnings,
        correction_ratio=correction_ratio,
    )
    if history:
        console.print(
            f"[cyan]📚[/cyan] Using {len(history)} cached judgments for context"
        )

    # Build prompt for all changes at once (batch processing)
    prompt = build_judgment_prompt(
        settings.product.name,
        changes,
        history=history,
        hints=hints,
    )

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
        eff_hrs = int(report.effective_hours) if report.effective_hours else 0
        eff_days = report.effective_days or 0
        console.print(f"  [cyan]Work Time:[/cyan] {eff_days} days, {eff_hrs} hours")
        # Show PTO separately if any
        if report.absence_days and report.absence_days > 0:
            pto_days = report.absence_days
            pto_hrs = int(pto_days * 8)
            console.print(
                f"  [cyan]Paid Time Off:[/cyan] {pto_days} days, {pto_hrs} hours"
            )
            total_days = (report.effective_days or 0) + (report.absence_days or 0)
            total_hrs = int(report.total_hours)
            console.print(
                f"  [cyan]Total Recorded:[/cyan] {total_days} days, {total_hrs} hours"
            )
        if report.workday_validated:
            console.print("  [green]✓ Workday Coverage:[/green] Complete")
        else:
            # Calculate and show missing days
            missing = validate_workday_coverage(
                report.workday_entries, report.workday_start, report.workday_end
            )
            missing_count = len(missing)
            console.print(
                f"  [yellow]⚠ Workday Coverage:[/yellow] INCOMPLETE "
                f"({missing_count} day{'s' if missing_count != 1 else ''} missing)"
            )
            # Show first few missing days
            for day in missing[:MAX_MISSING_DAYS_TO_SHOW]:
                console.print(f"    - {day.strftime('%Y-%m-%d (%A)')}")
            if missing_count > MAX_MISSING_DAYS_TO_SHOW:
                console.print(
                    f"    ... and {missing_count - MAX_MISSING_DAYS_TO_SHOW} more"
                )
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
        # Display hours as integer for cleaner output
        effective_hrs = int(report.effective_hours) if report.effective_hours else 0
        eff_days = report.effective_days or 0
        console.print(f"  • Work time: {eff_days} days, {effective_hrs} hours")
        # Show PTO separately if any
        if report.absence_days and report.absence_days > 0:
            pto_days = report.absence_days
            pto_hrs = int(pto_days * 8)
            console.print(f"  • 🌴 Paid Time Off: {pto_days} days, {pto_hrs} hours")
            total_days = (report.effective_days or 0) + (report.absence_days or 0)
            total_hrs = int(report.total_hours)
            console.print(
                f"  • 📅 Total recorded: {total_days} days, {total_hrs} hours"
            )
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


def _skip_if_already_reviewed(
    console: Console,
    report: InFlightReport,
    force: bool,
    *,
    show_status_message: bool = True,
    show_force_hint: bool = True,
) -> bool | None:
    """Check if review should be skipped for already-reviewed reports.

    Args:
        console: Rich console for output
        report: Report to check
        force: Force re-review even if already reviewed
        show_status_message: Whether to show "This report has already been reviewed."
        show_force_hint: Whether to show "Use --force to re-review."

    Returns:
        True if already reviewed and should skip (caller returns True early),
        None if review should proceed.

    Note:
        The `accepted=True` parameter to `display_review_results` is correct here:
        when `is_reviewed()` returns True, it means the user completed a previous
        review session and accepted the results. The display shows the final
        decisions (which may include EXCLUDE items the user explicitly marked).
    """
    if not report.is_reviewed() or force:
        return None  # Proceed with review

    if show_status_message:
        console.print("\n[green]✓[/green] This report has already been reviewed.")

    # Display existing review results
    display_review_results(console, report.judgments, report.changes, accepted=True)

    if show_force_hint:
        console.print("\nUse --force to re-review.")

    return True


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
    # Check if already reviewed - use helper to reduce duplication
    if (skip_result := _skip_if_already_reviewed(console, report, force)) is not None:
        return skip_result  # Already reviewed is a success

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
    date_range = (report.changes_since, report.changes_until)
    result = await review(console, report.judgments, report.changes, date_range)

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


async def _process_ai_and_review(
    console: Console,
    cache: InFlightCache,
    report: InFlightReport,
    flow_options: FlowOptions,
) -> bool:
    """Process AI filtering and review if needed.

    Args:
        console: Rich console for output
        cache: In-flight cache manager
        report: Report to process
        flow_options: Flow execution options

    Returns:
        True if review accepted or skipped, False if cancelled
    """
    # Run AI if needed and not skipped
    if not flow_options.skip_ai and report.changes and not report.judgments:
        settings = load_settings(console)
        report.judgments = _run_ai_filtering(console, report.changes, settings)
        cache.save(report)

    # Check if already reviewed - skip TUI (no status message/hint in report flow)
    if (
        skip_result := _skip_if_already_reviewed(
            console,
            report,
            flow_options.force,
            show_status_message=False,
            show_force_hint=False,
        )
    ) is not None:
        return skip_result

    # Review if needed and not skipped
    if not flow_options.skip_review and report.judgments:
        date_range = (report.changes_since, report.changes_until)
        result = await review(console, report.judgments, report.changes, date_range)

        # Always save judgments (even partial reviews)
        report.judgments = result.judgments
        cache.save(report)

        # Save to AI cache if review was accepted
        if result.accepted:
            _save_judgments_to_ai_cache(console, result.judgments)
            return True

        return False  # Review not accepted

    return True  # Skipped review or no judgments


async def report_flow(
    console: Console,
    month: str | None = None,
    options: FlowOptions | None = None,
    overrides: DateRangeOverrides | None = None,
    output_options: OutputOptions | None = None,
) -> bool:
    """Complete report flow: collect → AI → review → generate.

    Args:
        console: Rich console for output
        month: Month specification
        options: Flow execution options
        overrides: Optional date range overrides
        output_options: Output generation options

    Returns:
        True if successful, False on failure
    """
    if options is None:
        options = FlowOptions()
    if overrides is None:
        overrides = DateRangeOverrides()
    if output_options is None:
        output_options = OutputOptions()

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

    # Process AI and review
    review_accepted = await _process_ai_and_review(console, cache, report, options)

    # Only finalize if review was accepted (or skipped)
    if not review_accepted:
        console.print("\n[yellow]⏳[/yellow] Review not completed - report not saved")
        console.print("Run [cyan]iptax report[/cyan] again to resume")
        return True  # Partial success - data is saved in cache

    # Display final summary
    if report.judgments:
        include_count = sum(
            1 for j in report.judgments if j.final_decision == Decision.INCLUDE
        )
        console.print("\n[bold]Final Report:[/bold]")
        console.print(f"  • Approved changes: {include_count}")

    # Generate output files
    success = await dist_flow(
        console,
        month=month_key,
        output_options=output_options,
        force=options.force,
    )

    if not success:
        return False

    # Save report to history so next report knows where to start
    save_report_date(report.changes_since, report.changes_until, month_key)
    console.print(
        f"[green]✓[/green] Report saved to history "
        f"({report.changes_since} to {report.changes_until})"
    )

    # Note: We keep in-flight cache so dist can be run again if needed
    # Users can manually clear with: iptax cache clear --month YYYY-MM

    console.print(f"\n[green]✓[/green] Report complete for {month_key}")

    return True


def _validate_dist_readiness(
    report: InFlightReport,
    settings: Settings,
    force: bool,
) -> str | None:
    """Validate that report is ready for distribution.

    Args:
        report: In-flight report to validate
        settings: Application settings
        force: Force flag (confirms manual review when AI disabled)

    Returns:
        Error message if validation fails, None if successful
    """
    if not report.changes:
        return "No changes in report"

    # Check review status - AI is disabled if it's DisabledAIConfig OR provider is None
    ai_enabled = (
        not isinstance(settings.ai, DisabledAIConfig)
        and getattr(settings.ai, "provider", None) is not None
    )

    if ai_enabled:
        # AI enabled: require judgments and all must be reviewed
        if not report.judgments:
            return (
                "AI is enabled but no judgments found. "
                "Run [cyan]iptax review[/cyan] first."
            )

        # Check if all judgments are reviewed
        unreviewed = [j for j in report.judgments if j.user_decision is None]
        if unreviewed:
            return (
                f"{len(unreviewed)} judgment(s) not reviewed. "
                "Run [cyan]iptax review[/cyan] first."
            )
    elif not report.judgments and not force:
        # AI disabled: require manual review confirmation
        return (
            "AI is disabled. Changes require manual review before generation.\n"
            "Review your changes manually, then use --force to confirm and generate."
        )

    # Check for required hours data (only if Workday is enabled)
    if report.total_hours is None and settings.workday.enabled:
        return (
            "Missing work hours data. "
            "Run [cyan]iptax collect[/cyan] to gather Workday data."
        )

    return None


async def dist_flow(
    console: Console,
    month: str | None = None,
    output_options: OutputOptions | None = None,
    force: bool = False,
) -> bool:
    """Generate output files from in-flight report.

    Args:
        console: Rich console for output
        month: Month specification (None|latest|last|YYYY-MM)
        output_options: Output generation options
        force: Overwrite existing files (also confirms manual review when AI disabled)

    Returns:
        True if successful, False on failure
    """
    if output_options is None:
        output_options = OutputOptions()
    # Load settings
    settings = load_settings(console)

    # Load in-flight report
    cache = InFlightCache()
    report, month_key = _load_report_for_review(console, cache, month)

    if report is None:
        return False

    console.print(f"\n[cyan]📊[/cyan] Generating output for {month_key}")
    _display_inflight_summary(console, report)

    # Validate report is ready for dist
    error = _validate_dist_readiness(report, settings, force)
    if error:
        console.print(f"\n[red]✗[/red] {error}")
        return False

    # Compile report
    console.print("\n[cyan]📝[/cyan] Compiling report data...")
    try:
        report_data = compile_report(report, settings)
    except ValueError as e:
        console.print(f"\n[red]✗[/red] Compilation failed: {e}")
        return False

    console.print(
        f"[green]✓[/green] Compiled {len(report_data.changes)} approved changes "
        f"from {len(report_data.repositories)} repositories"
    )

    # Determine output directory
    if output_options.output_dir:
        target_dir = output_options.output_dir
        console.print("[cyan]📁[/cyan] Using custom output directory:")
        console.print(f"  {target_dir}")
    else:
        year = int(report_data.month.split("-")[0])
        target_dir = settings.report.get_output_path(year)
        console.print("[cyan]📁[/cyan] Using configured output directory:")
        console.print(f"  {target_dir}")

    # Generate output files
    fmt = output_options.output_format
    console.print(f"\n[cyan]✍[/cyan] Generating {fmt} files...")

    try:
        generated_files = generate_all(
            report_data, target_dir, force=force, format_type=fmt
        )
        console.print(f"\n[green]✓[/green] Generated {len(generated_files)} file(s):")
        for file_path in generated_files:
            console.print(f"  • {file_path}")
    except FileExistsError as e:
        console.print(f"\n[red]✗[/red] {e}")
        console.print("Use --force to overwrite existing files")
        return False
    except Exception as e:
        console.print(f"\n[red]✗[/red] Generation failed: {e}")
        return False

    console.print(f"\n[green]✓[/green] Output generated for {month_key}")
    return True


# Cache clearing utilities


def confirm_or_force(prompt: str, force: bool) -> bool:
    """Return True if force is set or user confirms the prompt.

    Args:
        prompt: Question to ask the user
        force: If True, skip confirmation and return True

    Returns:
        True if should proceed, False otherwise
    """
    return force or questionary.confirm(prompt, default=False).unsafe_ask()


def clear_ai_cache(force: bool) -> None:
    """Clear AI judgment cache with optional confirmation.

    Args:
        force: If True, skip confirmation prompt
    """
    ai_cache_path = get_ai_cache_path()
    if not ai_cache_path.exists():
        print("No AI cache to clear.")  # noqa: T201  # CLI output
        return
    if confirm_or_force("Clear AI judgment cache?", force):
        ai_cache_path.unlink()
        print("\033[32m✓ Cleared AI judgment cache\033[0m")  # noqa: T201  # CLI output
    else:
        print("AI cache clear cancelled.")  # noqa: T201  # CLI output


def clear_inflight_cache(cache_mgr: InFlightCache, force: bool) -> None:
    """Clear all in-flight reports with optional confirmation.

    Args:
        cache_mgr: InFlightCache instance
        force: If True, skip confirmation prompt
    """
    if confirm_or_force("Clear ALL in-flight reports?", force):
        count = cache_mgr.clear_all()
        print(f"\033[32m✓ Cleared {count} in-flight report(s)\033[0m")  # noqa: T201
    else:
        print("In-flight cache clear cancelled.")  # noqa: T201  # CLI output


def clear_history_cache(force: bool) -> None:
    """Clear report history with optional confirmation.

    Args:
        force: If True, skip confirmation prompt
    """
    history_path = get_history_path()
    if not history_path.exists():
        print("No history to clear.")  # noqa: T201  # CLI output
        return
    if confirm_or_force(
        "Clear report history? This resets Did date range tracking.", force
    ):
        HistoryManager().clear()
        print("\033[32m✓ Cleared report history\033[0m")  # noqa: T201  # CLI output
    else:
        print("History clear cancelled.")  # noqa: T201  # CLI output
