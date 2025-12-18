"""Command-line interface for iptax."""

import asyncio
import logging
import sys
from collections.abc import Callable
from datetime import date
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

import click
import questionary
import yaml
from rich.console import Console

from iptax.ai.cache import JudgmentCacheManager, get_ai_cache_path
from iptax.cache.history import (
    HistoryCorruptedError,
    HistoryManager,
    get_history_path,
)
from iptax.cache.inflight import InFlightCache, get_inflight_cache_dir
from iptax.cli import elements, flows
from iptax.cli.flows import (
    DateRangeOverrides,
    FlowOptions,
    OutputOptions,
    clear_ai_cache,
    clear_history_cache,
    clear_inflight_cache,
)
from iptax.config import (
    ConfigError,
    create_default_config,
    get_config_path,
)
from iptax.config import (
    load_settings as config_load_settings,
)
from iptax.did import DidIntegrationError
from iptax.models import AICacheStats, HistoryCacheStats, InflightCacheStats
from iptax.timing import resolve_date_ranges
from iptax.utils.env import get_cache_dir
from iptax.utils.logging import setup_logging
from iptax.workday import WorkdayClient, WorkdayError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Month string format constant (YYYY-MM)
MONTH_STRING_LENGTH = 7

# Shared option definitions for reuse across commands
MONTH_OPTION_HELP = "Month to target (None=auto-detect, 'current', 'last', or YYYY-MM)"


def month_option(f: F) -> F:
    """Shared --month option decorator."""
    return click.option("--month", help=MONTH_OPTION_HELP)(f)


def force_option(f: F) -> F:
    """Shared --force option decorator."""
    return click.option(
        "--force", is_flag=True, help="Discard existing in-flight data"
    )(f)


def skip_ai_option(f: F) -> F:
    """Shared --skip-ai option decorator."""
    return click.option("--skip-ai", is_flag=True, help="Skip AI filtering")(f)


def skip_review_option(f: F) -> F:
    """Shared --skip-review option decorator."""
    return click.option("--skip-review", is_flag=True, help="Skip interactive review")(
        f
    )


def skip_workday_option(f: F) -> F:
    """Shared --skip-workday option decorator."""
    return click.option(
        "--skip-workday", is_flag=True, help="Skip Workday integration"
    )(f)


def skip_did_option(f: F) -> F:
    """Shared --skip-did option decorator."""
    return click.option("--skip-did", is_flag=True, help="Skip Did collection")(f)


def output_dir_option(f: F) -> F:
    """Shared --output-dir option decorator."""
    return click.option(
        "--output-dir", type=click.Path(), help="Override output directory"
    )(f)


def output_format_option(f: F) -> F:
    """Shared --format option decorator."""
    return click.option(
        "--format",
        "output_format",
        type=click.Choice(["all", "md", "pdf"], case_sensitive=False),
        default="all",
        help="Output format (default: all)",
    )(f)


def date_override_options(f: F) -> F:
    """Add all date override options."""
    return click.option("--did-end", help="Override Did end date (YYYY-MM-DD)")(
        click.option("--did-start", help="Override Did start date (YYYY-MM-DD)")(
            click.option(
                "--workday-end", help="Override Workday end date (YYYY-MM-DD)"
            )(
                click.option(
                    "--workday-start", help="Override Workday start date (YYYY-MM-DD)"
                )(f)
            )
        )
    )


def _get_log_file() -> Path:
    """Get the path to the log file."""
    return get_cache_dir() / "iptax.log"


def _setup_logging() -> None:
    """Setup logging to user's cache directory.

    Truncates log file on each run to keep it manageable.
    """
    log_file = _get_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    setup_logging(log_file)


def async_command(f: F) -> F:
    """Decorator to run async click commands.

    Wraps an async function to be run with asyncio.run().
    This is a generic decorator for Click commands which can have various signatures.
    """

    @wraps(f)
    def wrapper(*args: object, **kwargs: object) -> object:
        return asyncio.run(f(*args, **kwargs))

    # Generic decorator - can't preserve exact return type
    # without complex generics (type:ignore[return-value])
    return wrapper  # type: ignore[return-value]


def _parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format.

    Raises:
        click.BadParameter: If date format is invalid
    """
    try:
        return date.fromisoformat(date_str)
    except ValueError as e:
        # Re-raise as Click parameter error for better CLI error messages
        raise click.BadParameter(
            f"Invalid date format '{date_str}', expected YYYY-MM-DD"
        ) from e


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option()
@month_option
@skip_ai_option
@skip_review_option
@skip_workday_option
@force_option
def cli(  # noqa: PLR0913  # CLI group needs many options for flexibility
    ctx: click.Context,
    month: str | None,
    skip_ai: bool,
    skip_review: bool,
    skip_workday: bool,
    force: bool,
) -> None:
    """IP Tax Reporter - Automated tax report generator for Polish IP tax
    deduction program."""
    # Store options in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["month"] = month
    ctx.obj["skip_ai"] = skip_ai
    ctx.obj["skip_review"] = skip_review
    ctx.obj["skip_workday"] = skip_workday
    ctx.obj["force"] = force

    # If no subcommand, invoke report with the group options
    if ctx.invoked_subcommand is None:
        ctx.invoke(
            report,
            month=month,
            skip_ai=skip_ai,
            skip_review=skip_review,
            skip_workday=skip_workday,
            force=force,
            workday_start=None,
            workday_end=None,
            did_start=None,
            did_end=None,
        )


@cli.command()
@month_option
@skip_ai_option
@skip_review_option
@skip_workday_option
@force_option
@output_dir_option
@output_format_option
@date_override_options
@async_command
async def report(  # noqa: PLR0913  # CLI commands need many options for flexibility
    # Core parameters
    month: str | None,
    # Skip flags for different steps
    skip_ai: bool,
    skip_review: bool,
    skip_workday: bool,
    force: bool,
    # Output options
    output_dir: str | None,
    output_format: str,
    # Date range overrides (optional advanced usage)
    workday_start: str | None,
    workday_end: str | None,
    did_start: str | None,
    did_end: str | None,
) -> None:
    """Generate IP tax report (default command if no subcommand specified).

    Many parameters needed: core month, skip flags for stages, date overrides.
    """
    console = Console()

    try:
        # Parse date overrides
        overrides = DateRangeOverrides(
            workday_start=_parse_date(workday_start) if workday_start else None,
            workday_end=_parse_date(workday_end) if workday_end else None,
            did_start=_parse_date(did_start) if did_start else None,
            did_end=_parse_date(did_end) if did_end else None,
        )

        # Set up options
        options = FlowOptions(
            skip_workday=skip_workday,
            skip_ai=skip_ai,
            skip_review=skip_review,
            force=force,
        )

        # Create output options
        output_options = OutputOptions(
            output_dir=Path(output_dir) if output_dir else None,
            output_format=output_format,
        )

        # Run report flow
        success = await flows.report_flow(
            console,
            month=month,
            options=options,
            overrides=overrides,
            output_options=output_options,
        )
        if not success:
            sys.exit(1)

    except ConfigError as e:
        click.secho(f"Configuration error: {e}", fg="red", err=True)
        click.echo("\nRun 'iptax config' to configure the application.")
        sys.exit(1)
    except DidIntegrationError as e:
        click.secho(f"Did integration error: {e}", fg="red", err=True)
        click.echo("\nCheck your did configuration and try again.")
        sys.exit(1)
    except HistoryCorruptedError as e:
        click.secho(f"History error: {e}", fg="red", err=True)
        sys.exit(1)
    except WorkdayError as e:
        click.secho(f"Workday error: {e}", fg="red", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Report generation cancelled[/yellow]")
        sys.exit(1)


@cli.command()
@month_option
@skip_did_option
@skip_workday_option
@force_option
@date_override_options
@async_command
async def collect(  # noqa: PLR0913  # CLI commands need many options for flexibility
    # Core parameters
    month: str | None,
    # Skip flags
    skip_did: bool,
    skip_workday: bool,
    force: bool,
    # Date range overrides (optional advanced usage)
    workday_start: str | None,
    workday_end: str | None,
    did_start: str | None,
    did_end: str | None,
) -> None:
    """Collect data for a monthly report.

    Many parameters needed: core month, skip flags, date overrides.
    """
    console = Console()

    try:
        # Parse date overrides
        overrides = DateRangeOverrides(
            workday_start=_parse_date(workday_start) if workday_start else None,
            workday_end=_parse_date(workday_end) if workday_end else None,
            did_start=_parse_date(did_start) if did_start else None,
            did_end=_parse_date(did_end) if did_end else None,
        )

        # Set up options
        options = FlowOptions(
            skip_did=skip_did,
            skip_workday=skip_workday,
            force=force,
        )

        # Run collect flow
        success = await flows.collect_flow(
            console, month=month, options=options, overrides=overrides
        )
        if not success:
            sys.exit(1)

    except ConfigError as e:
        click.secho(f"Configuration error: {e}", fg="red", err=True)
        click.echo("\nRun 'iptax config' to configure the application.")
        sys.exit(1)
    except DidIntegrationError as e:
        click.secho(f"Did integration error: {e}", fg="red", err=True)
        click.echo("\nCheck your did configuration and try again.")
        sys.exit(1)
    except WorkdayError as e:
        click.secho(f"Workday error: {e}", fg="red", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Collection cancelled[/yellow]")
        sys.exit(1)


@cli.command()
@month_option
@force_option
@async_command
async def review(month: str | None, force: bool) -> None:
    """Review AI judgments for in-flight report."""
    console = Console()

    try:
        success = await flows.review_flow(console, month=month, force=force)
        if not success:
            sys.exit(1)

    except ConfigError as e:
        click.secho(f"Configuration error: {e}", fg="red", err=True)
        click.echo("\nRun 'iptax config' to configure the application.")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Review cancelled[/yellow]")
        sys.exit(1)


@cli.command()
@month_option
@output_dir_option
@output_format_option
@force_option
@async_command
async def dist(
    month: str | None,
    output_dir: str | None,
    output_format: str,
    force: bool,
) -> None:
    """Generate output files from in-flight report.

    Creates markdown and PDF files from a previously collected and reviewed report.
    """
    console = Console()

    try:
        # Create output options
        output_options = OutputOptions(
            output_dir=Path(output_dir) if output_dir else None,
            output_format=output_format,
        )

        success = await flows.dist_flow(
            console,
            month=month,
            output_options=output_options,
            force=force,
        )
        if not success:
            sys.exit(1)

    except ConfigError as e:
        click.secho(f"Configuration error: {e}", fg="red", err=True)
        click.echo("\nRun 'iptax config' to configure the application.")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Generation cancelled[/yellow]")
        sys.exit(1)


@cli.group(invoke_without_command=True)
@click.pass_context
def cache(ctx: click.Context) -> None:
    """Manage caches (in-flight reports, AI judgments, history)."""
    # If no subcommand, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cache.command(name="list")
def cache_list() -> None:
    """List all in-flight reports with state info."""
    console = Console()
    cache_mgr = InFlightCache()

    month_keys = cache_mgr.list_all()
    if not month_keys:
        click.echo("No in-flight reports found.")
        return

    # Load reports and check workday setting
    reports_with_months = []
    for month_key in sorted(month_keys):
        inflight_report = cache_mgr.load(month_key)
        if inflight_report:
            reports_with_months.append((month_key, inflight_report))

    # Try to load settings to check if workday is enabled
    workday_enabled = True
    try:
        settings = config_load_settings()
        workday_enabled = settings.workday.enabled
    except ConfigError:
        # If settings can't be loaded, assume workday enabled
        pass

    elements.display_inflight_table(
        console, reports_with_months, workday_enabled=workday_enabled
    )


@cache.command(name="stats")
def cache_stats() -> None:
    """Show AI cache and history statistics."""
    console = Console()

    # Gather all stats
    ai_stats = _gather_ai_cache_stats()
    history_stats = _gather_history_stats()
    inflight_stats = _gather_inflight_stats()

    # Display all stats
    elements.display_cache_stats(console, ai_stats, history_stats, inflight_stats)


def _gather_ai_cache_stats() -> AICacheStats:
    """Gather AI cache statistics.

    Returns:
        AICacheStats with current AI cache state
    """
    cache_mgr = JudgmentCacheManager()
    stats = cache_mgr.stats()

    cache_path = get_ai_cache_path()
    cache_size = cache_path.stat().st_size if cache_path.exists() else 0

    return AICacheStats(
        total_judgments=stats["total_judgments"],
        corrected_count=stats["corrected_count"],
        correct_count=stats["correct_count"],
        correction_rate=stats["correction_rate"],
        products=stats["products"],
        oldest_judgment=stats["oldest_judgment"],
        newest_judgment=stats["newest_judgment"],
        cache_path=cache_path,
        cache_size_bytes=cache_size,
    )


def _gather_history_stats() -> HistoryCacheStats:
    """Gather history statistics.

    Returns:
        HistoryCacheStats with current history state
    """
    manager = HistoryManager()
    manager.load()
    entries = manager.get_all_entries()

    history_path = get_history_path()
    history_size = history_path.stat().st_size if history_path.exists() else 0

    return HistoryCacheStats(
        total_reports=len(entries),
        entries=entries,
        history_path=history_path,
        history_size_bytes=history_size,
    )


def _gather_inflight_stats() -> InflightCacheStats:
    """Gather in-flight cache statistics.

    Returns:
        InflightCacheStats with current in-flight cache state
    """
    cache_mgr = InFlightCache()
    months = cache_mgr.list_all()

    return InflightCacheStats(
        active_reports=len(months),
        months=months,
        cache_dir=get_inflight_cache_dir(),
    )


@cache.command(name="clear")
@click.option("--month", help="Clear specific month (YYYY-MM)")
@click.option("--inflight", "clear_inflight", is_flag=True, help="Clear in-flight only")
@click.option("--ai", "clear_ai", is_flag=True, help="Clear AI cache only")
@click.option("--history", "clear_history", is_flag=True, help="Clear history only")
@click.option("--force", is_flag=True, help="Skip confirmation prompts")
def cache_clear(
    month: str | None,
    clear_inflight: bool,
    clear_ai: bool,
    clear_history: bool,
    force: bool,
) -> None:
    """Clear caches (in-flight, AI, history, or by month).

    By default, clears all caches (AI, in-flight, and history) with confirmation.
    Use flags to clear specific caches only. Use --force to skip confirmations.
    """
    cache_mgr = InFlightCache()

    # If specific month provided, clear that month's data from specified cache(s)
    if month:
        # Determine what to clear - if no flags specified, clear both
        # in-flight and history (for consistency, as month-specific
        # clearing targets related data)
        clear_all = not clear_inflight and not clear_ai and not clear_history

        # Clear in-flight if requested or no specific cache specified
        if clear_inflight or clear_all:
            if cache_mgr.delete(month):
                click.secho(f"✓ Cleared in-flight report for {month}", fg="green")
            else:
                click.secho(f"No in-flight report found for {month}", fg="yellow")

        # Clear history if requested or no specific cache specified
        if clear_history or clear_all:
            history_mgr = HistoryManager()
            history_mgr.load()
            if history_mgr.delete_entry(month):
                click.secho(f"✓ Cleared history entry for {month}", fg="green")
            else:
                click.secho(f"No history entry found for {month}", fg="yellow")

        # AI cache doesn't support per-month clearing
        if clear_ai:
            click.secho(
                "Warning: AI cache cannot be cleared per-month. "
                "Use without --month to clear all.",
                fg="yellow",
            )

        return

    # Determine what to clear - if no flags specified, clear all
    clear_all = not clear_inflight and not clear_ai and not clear_history

    if clear_ai or clear_all:
        clear_ai_cache(force)
    if clear_inflight or clear_all:
        clear_inflight_cache(cache_mgr, force)
    if clear_history or clear_all:
        clear_history_cache(force)


@cache.command(name="path")
@click.option("--ai", "show_ai", is_flag=True, help="Show AI cache path only")
@click.option("--history", "show_history", is_flag=True, help="Show history path only")
@click.option(
    "--inflight", "show_inflight", is_flag=True, help="Show in-flight dir only"
)
def cache_path_cmd(show_ai: bool, show_history: bool, show_inflight: bool) -> None:
    """Show paths to all cache directories.

    Use --ai, --history, or --inflight to get a specific path for piping.
    """
    # If specific path requested, output just that path (no formatting)
    if show_ai:
        click.echo(str(get_ai_cache_path()))
        return
    if show_history:
        click.echo(str(get_history_path()))
        return
    if show_inflight:
        click.echo(str(get_inflight_cache_dir()))
        return

    # Show all paths with formatting
    console = Console()
    elements.display_cache_paths(
        console,
        ai_cache_path=get_ai_cache_path(),
        history_path=get_history_path(),
        inflight_dir=get_inflight_cache_dir(),
    )


@cli.command()
@click.option("--show", is_flag=True, help="Display current configuration")
@click.option("--validate", is_flag=True, help="Validate current configuration")
@click.option("--path", is_flag=True, help="Show path to configuration file")
def config(show: bool, validate: bool, path: bool) -> None:
    """Configure iptax settings interactively."""
    config_path = get_config_path()
    console = Console()

    # Handle --path flag
    if path:
        click.echo(str(config_path))
        return

    # Handle --show flag
    if show:
        try:
            settings = config_load_settings()
            # Pretty-print YAML
            yaml_str = yaml.safe_dump(
                settings.model_dump(),
                default_flow_style=False,
                sort_keys=False,
                indent=2,
                allow_unicode=True,
            )
            click.echo(yaml_str)
        except ConfigError as e:
            click.secho(f"Error: {e}", fg="red", err=True)
            sys.exit(1)
        return

    # Handle --validate flag
    if validate:
        try:
            config_load_settings()
            click.secho("✓ Configuration is valid", fg="green")
            click.echo(f"Configuration file: {config_path}")
        except ConfigError as e:
            click.secho("✗ Configuration is invalid", fg="red", err=True)
            click.secho(f"Error: {e}", fg="red", err=True)
            sys.exit(1)
        return

    # No flags - run interactive configuration wizard
    try:
        # Check if config already exists
        if config_path.exists():
            click.echo(f"Configuration file already exists at: {config_path}")
            overwrite = questionary.confirm(
                "Do you want to overwrite it?",
                default=True,
            ).unsafe_ask()
            if not overwrite:
                click.echo("Configuration not changed.")
                return

        # Run interactive wizard
        create_default_config(interactive=True)
        click.secho("\n✓ Configuration created successfully!", fg="green")

        # Ensure browser is installed (for Workday integration)
        flows.ensure_browser_installed(console)

    except ConfigError as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n\nConfiguration cancelled.")
        sys.exit(1)


@cli.command()
def init() -> None:
    """Initialize iptax by installing required browser.

    Installs Playwright Firefox browser needed for Workday integration.
    This is also run automatically during 'iptax config'.
    """
    console = Console()
    success = flows.init_flow(console)
    if not success:
        sys.exit(1)


@cli.command()
@click.option("--month", help="Show specific month only (YYYY-MM format)")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "yaml"], case_sensitive=False),
    default="table",
    help="Output format (default: table)",
)
@click.option("--path", is_flag=True, help="Show path to history file")
def history(month: str | None, output_format: str, path: bool) -> None:
    """Show report history."""
    history_path = get_history_path()

    # Handle --path flag
    if path:
        click.echo(str(history_path))
        return

    # Load history
    try:
        manager = HistoryManager()
        manager.load()
    except HistoryCorruptedError as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        click.echo("\nRun 'iptax' to fix the corrupted history file.")
        sys.exit(1)

    entries = manager.get_all_entries()

    # Filter by month if specified
    if month:
        # Validate month format (YYYY-MM)
        if not month or len(month) != MONTH_STRING_LENGTH or month[4] != "-":
            click.secho(
                f"Invalid month format '{month}', expected YYYY-MM",
                fg="red",
                err=True,
            )
            sys.exit(1)
        if month not in entries:
            click.secho(f"No history entry found for {month}", fg="yellow")
            sys.exit(0)
        entries = {month: entries[month]}

    # Handle empty history
    if not entries:
        click.secho("No report history found.", fg="yellow")
        click.echo(f"\nHistory file: {history_path}")
        return

    # Output based on format
    console = Console()
    if output_format == "json":
        click.echo(elements.format_history_json(entries))
    elif output_format == "yaml":
        click.echo(elements.format_history_yaml(entries))
    else:  # table
        elements.display_history_table(console, entries)


# TODO(ksuszyns): Remove this command after integrating workday into report command
@cli.command()
@click.option("--month", help="Month to fetch work hours for (YYYY-MM format)")
@click.option(
    "--foreground",
    is_flag=True,
    help="Run browser in foreground (visible) instead of headless",
)
@click.option(
    "--no-kerberos",
    is_flag=True,
    help="Disable Kerberos/SPNEGO authentication (use SSO login form instead)",
)
def workday(month: str | None, foreground: bool, no_kerberos: bool) -> None:
    """Test Workday integration (temporary command).

    This command is for testing the Workday integration.
    It will be removed once integrated into the report command.
    """
    console = Console()

    try:
        settings = flows.load_settings(console)

        # Override auth method if --no-kerberos flag is set
        if no_kerberos:
            settings.workday.auth = "sso"
            console.print("[yellow]⚠[/yellow] Kerberos disabled, using SSO login form")

        # Resolve date range using timing module
        ranges = resolve_date_ranges(month)
        console.print(
            f"[cyan]📅[/cyan] Date range: "
            f"{ranges.workday_start} to {ranges.workday_end}"
        )

        # Create Workday client and fetch hours
        client = WorkdayClient(settings.workday)
        headless = not foreground
        # Auto-detect interactive mode based on whether stdin is a terminal
        interactive = sys.stdin.isatty()

        console.print("[cyan]🔍[/cyan] Fetching work hours...")
        work_hours = client.get_work_hours(
            ranges.workday_start,
            ranges.workday_end,
            interactive=interactive,
            headless=headless,
        )

        # Display results
        console.print("\n[bold green]✓ Work hours retrieved:[/bold green]")
        console.print(f"  Working days: {work_hours.working_days}")
        console.print(f"  Absence days: {work_hours.absence_days}")
        console.print(f"  Total hours: {work_hours.total_hours}")
        console.print(f"  Effective days: {work_hours.effective_days}")
        console.print(f"  Effective hours: {work_hours.effective_hours}")

    except ConfigError as e:
        click.secho(f"Configuration error: {e}", fg="red", err=True)
        click.echo("\nRun 'iptax config' to configure the application.")
        sys.exit(1)
    except WorkdayError as e:
        click.secho(f"Workday error: {e}", fg="red", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Operation cancelled[/yellow]")
        sys.exit(1)


def main() -> None:
    """Main entry point for the CLI.

    Sets up logging and provides a generic catch-all error handler
    for unexpected errors.
    """
    _setup_logging()
    try:
        cli()
    except Exception:
        # Log the full traceback to the log file (details only in log)
        logger.exception("Fatal error occurred")

        # Show user-friendly error message (no exception details)
        click.secho(
            "\nFatal error occurred.",
            fg="red",
            err=True,
        )
        click.secho(
            f"Check logs for details: {_get_log_file()}",
            fg="yellow",
            err=True,
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
