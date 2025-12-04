"""Command-line interface for iptax."""

import sys
import time

import click
import questionary
import yaml
from rich.console import Console

from iptax.ai.tui import ai_progress
from iptax.cache.history import (
    HistoryCorruptedError,
    HistoryManager,
    get_history_path,
)
from iptax.cli import elements, flows, mocks, utils
from iptax.config import (
    ConfigError,
    create_default_config,
    get_config_path,
)
from iptax.config import (
    load_settings as config_load_settings,
)
from iptax.did import DidIntegrationError
from iptax.utils.env import get_cache_dir
from iptax.utils.logging import setup_logging
from iptax.workday import WorkdayClient, WorkdayError


def _setup_logging() -> None:
    """Setup logging to user's cache directory.

    Truncates log file on each run to keep it manageable.
    """
    cache_dir = get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_file = cache_dir / "iptax.log"
    setup_logging(log_file)


@click.group()
@click.version_option()
def cli() -> None:
    """IP Tax Reporter - Automated tax report generator for Polish IP tax
    deduction program."""
    pass


@cli.command()
@click.option("--month", help="Month to generate report for (YYYY-MM format)")
@click.option("--skip-ai", is_flag=True, help="Skip AI filtering")
@click.option("--skip-workday", is_flag=True, help="Skip Workday integration")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be generated without creating files",
)
def report(
    month: str | None,
    skip_ai: bool,  # noqa: ARG001 - placeholder for future AI filtering implementation
    skip_workday: bool,  # noqa: ARG001 - placeholder for future Workday integration
    dry_run: bool,
) -> None:
    """Generate IP tax report for the specified month (default: current month)."""
    console = Console()

    try:
        settings = flows.load_settings(console)
        flows.load_history(console)

        # Get month key and date range
        month_key = _parse_month(month)
        start_date, end_date = utils.get_date_range(month_key)

        # Fetch and display changes
        changes = flows.fetch_changes(console, settings, start_date, end_date)
        elements.display_changes(console, changes, start_date, end_date)

        if dry_run:
            console.print("\n[yellow]Dry run - no files created[/yellow]")
        elif changes:
            console.print(
                "\n[yellow]Note: Full report generation not yet implemented[/yellow]"
            )

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
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Report generation cancelled[/yellow]")
        sys.exit(1)


def _parse_month(month: str | None) -> str:
    """Parse month string, exit on error."""
    try:
        return utils.parse_month_key(month)
    except ValueError:
        click.secho(
            f"Error: Invalid month format '{month}', expected YYYY-MM",
            fg="red",
            err=True,
        )
        sys.exit(1)


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
        month_key = _parse_month(month)
        if month_key not in entries:
            click.secho(f"No history entry found for {month_key}", fg="yellow")
            sys.exit(0)
        entries = {month_key: entries[month_key]}

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

        # Get month key and date range
        month_key = _parse_month(month)
        start_date, end_date = utils.get_date_range(month_key)
        console.print(f"[cyan]📅[/cyan] Date range: {start_date} to {end_date}")

        # Create Workday client and fetch hours
        client = WorkdayClient(settings.workday)
        headless = not foreground
        # Auto-detect interactive mode based on whether stdin is a terminal
        interactive = sys.stdin.isatty()

        console.print("[cyan]🔍[/cyan] Fetching work hours...")
        work_hours = client.get_work_hours(
            start_date, end_date, interactive=interactive, headless=headless
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


# TODO(ksuszyns): Remove this command after integrating AI review into report command
@cli.command("ai-test")
@click.option("--mock-count", default=15, help="Number of mock changes to generate")
def ai_test(mock_count: int) -> None:
    """Test AI review UI with mock data (temporary command).

    This command generates mock changes and judgments to test the TUI
    without making real AI calls. It will be removed once integrated
    into the report command.
    """
    console = Console()

    # Generate mock data
    mock_changes = mocks.generate_mock_changes(mock_count)
    mock_judgments = mocks.generate_mock_judgments(mock_changes)

    # Show spinner demo
    with ai_progress(console, "Simulating AI processing..."):
        time.sleep(1)

    # Run review flow
    flows.review(console, mock_judgments, mock_changes)


def main() -> None:
    """Main entry point for the CLI."""
    _setup_logging()
    cli()


if __name__ == "__main__":
    main()
