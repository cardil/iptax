"""Command-line interface for iptax."""

import asyncio
import sys
from collections.abc import Callable
from datetime import date
from functools import wraps
from typing import Any, TypeVar

import click
import questionary
import yaml
from rich.console import Console

from iptax.cache.history import (
    HistoryCorruptedError,
    HistoryManager,
    get_history_path,
)
from iptax.cache.inflight import InFlightCache
from iptax.cli import elements, flows
from iptax.cli.flows import DateRangeOverrides, FlowOptions
from iptax.config import (
    ConfigError,
    create_default_config,
    get_config_path,
)
from iptax.config import (
    load_settings as config_load_settings,
)
from iptax.did import DidIntegrationError
from iptax.timing import resolve_date_ranges
from iptax.utils.env import get_cache_dir
from iptax.utils.logging import setup_logging
from iptax.workday import WorkdayClient, WorkdayError

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


def _setup_logging() -> None:
    """Setup logging to user's cache directory.

    Truncates log file on each run to keep it manageable.
    """
    cache_dir = get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_file = cache_dir / "iptax.log"
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

        # Run report flow
        success = await flows.report_flow(
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
@click.argument("action", type=click.Choice(["list", "clear"]))
@click.option("--month", help="Month to target (YYYY-MM, for 'clear' only)")
def cache(action: str, month: str | None) -> None:
    """Manage in-flight report cache.

    Actions:
        list  - List all in-flight reports
        clear - Clear in-flight cache (all or specific month)
    """
    cache_mgr = InFlightCache()

    if action == "list":
        reports = cache_mgr.list_all()
        if not reports:
            click.echo("No in-flight reports found.")
        else:
            click.echo("In-flight reports:")
            for month_key in sorted(reports):
                click.echo(f"  • {month_key}")

    elif action == "clear":
        if month:
            if cache_mgr.delete(month):
                click.secho(f"✓ Cleared in-flight report for {month}", fg="green")
            else:
                click.secho(f"No in-flight report found for {month}", fg="yellow")
        else:
            # Clear all
            confirm = questionary.confirm(
                "Clear ALL in-flight reports?",
                default=False,
            ).unsafe_ask()
            if confirm:
                count = cache_mgr.clear_all()
                click.secho(f"✓ Cleared {count} in-flight report(s)", fg="green")
            else:
                click.echo("Cancelled.")


@cli.command()
@click.option("--show", is_flag=True, help="Display current configuration")
@click.option("--validate", is_flag=True, help="Validate current configuration")
@click.option("--path", is_flag=True, help="Show path to configuration file")
def config(show: bool, validate: bool, path: bool) -> None:
    """Configure iptax settings interactively."""
    config_path = get_config_path()

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

    except ConfigError as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n\nConfiguration cancelled.")
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
    """Main entry point for the CLI."""
    _setup_logging()
    cli()


if __name__ == "__main__":
    main()
