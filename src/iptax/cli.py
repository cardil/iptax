"""Command-line interface for iptax."""

import json
import logging
import sys
from datetime import date, datetime, timedelta

import click
import yaml
from rich.console import Console
from rich.table import Table

from iptax.config import (
    ConfigError,
    create_default_config,
    get_config_path,
    load_settings,
)
from iptax.did import DidIntegrationError, fetch_changes
from iptax.history import HistoryCorruptedError, HistoryManager, get_history_path
from iptax.models import Change, Settings
from iptax.utils.env import get_cache_dir


def _setup_logging() -> None:
    """Setup logging to user's cache directory."""
    cache_dir = get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Setup root logger
    log_file = cache_dir / "iptax.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file),
        ],
    )


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
    skip_ai: bool,  # noqa: ARG001
    skip_workday: bool,  # noqa: ARG001
    dry_run: bool,
) -> None:
    """Generate IP tax report for the specified month (default: current month)."""
    console = Console()

    try:
        settings = load_settings()
        console.print("[cyan]✓[/cyan] Settings loaded")

        manager = HistoryManager()
        manager.load()
        console.print("[cyan]✓[/cyan] History loaded")

        # Get month key and date range
        month_key = _get_month_key(month)
        start_date, end_date = _get_date_range(month_key)
        console.print(f"[cyan]📅[/cyan] Date range: {start_date} to {end_date}")

        # Fetch and display changes
        changes = _fetch_and_display_changes(console, settings, start_date, end_date)

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


def _get_month_key(month: str | None) -> str:
    """Get month key from provided month or current month."""
    if month:
        try:
            parsed_month = datetime.strptime(month, "%Y-%m")
            return parsed_month.strftime("%Y-%m")
        except ValueError:
            click.secho(
                f"Error: Invalid month format '{month}', expected YYYY-MM",
                fg="red",
                err=True,
            )
            sys.exit(1)
    return datetime.now().strftime("%Y-%m")


def _get_date_range(month_key: str) -> tuple[date, date]:
    """Get start and end date for a month."""
    year, month_num = month_key.split("-")
    start_date = datetime(int(year), int(month_num), 1).date()

    # Get last day of month
    december = 12
    if int(month_num) == december:
        end_date = datetime(int(year), december, 31).date()
    else:
        next_month = datetime(int(year), int(month_num) + 1, 1).date()
        end_date = next_month - timedelta(days=1)

    return start_date, end_date


def _fetch_and_display_changes(
    console: Console, settings: Settings, start_date: date, end_date: date
) -> list[Change]:
    """Fetch changes and display them in the console."""
    console.print("[cyan]🔍[/cyan] Fetching changes from did...")
    changes = fetch_changes(settings, start_date, end_date)
    console.print(f"[green]✓[/green] Found {len(changes)} changes")

    if not changes:
        console.print("[yellow]No changes found for this period[/yellow]")
        return changes

    # Display changes
    console.print("\n[bold]Changes:[/bold]")
    for i, change in enumerate(changes, 1):
        console.print(f"\n[cyan]{i}.[/cyan] {change.title}")
        console.print(f"   Repository: {change.repository.get_display_name()}")
        console.print(f"   URL: {change.get_url()}")
        if change.merged_at:
            merged_str = change.merged_at.strftime("%Y-%m-%d %H:%M:%S")
            console.print(f"   Merged: {merged_str}")

    # Display summary
    repositories = {change.repository.get_display_name() for change in changes}
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  Total changes: {len(changes)}")
    console.print(f"  Repositories: {len(repositories)}")

    return changes


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
            settings = load_settings()
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
            load_settings()
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
            if not click.confirm("Do you want to overwrite it?"):
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
        # Normalize month format
        try:
            parsed_month = datetime.strptime(month, "%Y-%m")
            month_key = parsed_month.strftime("%Y-%m")
        except ValueError:
            click.secho(
                f"Error: Invalid month format '{month}', expected YYYY-MM",
                fg="red",
                err=True,
            )
            sys.exit(1)

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
    if output_format == "json":
        _output_json(entries)
    elif output_format == "yaml":
        _output_yaml(entries)
    else:  # table
        _output_table(entries)


def _output_table(entries: dict) -> None:
    """Output history as a formatted table."""
    console = Console()

    # Create table
    table = Table(title="Report History", show_header=True, header_style="bold cyan")
    table.add_column("Month", style="cyan", no_wrap=True)
    table.add_column("Cutoff Date", style="green")
    table.add_column("Generated At", style="blue")
    table.add_column("Regenerated", style="yellow")

    # Sort entries by month
    for month in sorted(entries.keys()):
        entry = entries[month]
        regenerated = (
            entry.regenerated_at.strftime("%Y-%m-%d") if entry.regenerated_at else "-"
        )

        table.add_row(
            month,
            str(entry.last_cutoff_date),
            entry.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            regenerated,
        )

    console.print(table)

    # Show next report info if there are entries
    if entries:
        latest_month = max(entries.keys())
        latest_entry = entries[latest_month]
        next_start = latest_entry.last_cutoff_date + timedelta(days=1)
        console.print(
            f"\nNext report will start from: [green]{next_start}[/green]",
        )


def _output_json(entries: dict) -> None:
    """Output history as JSON."""
    data = {}
    for month, entry in entries.items():
        data[month] = {
            "last_cutoff_date": str(entry.last_cutoff_date),
            "generated_at": entry.generated_at.isoformat(),
            "regenerated_at": (
                entry.regenerated_at.isoformat() if entry.regenerated_at else None
            ),
        }

    click.echo(json.dumps(data, indent=2))


def _output_yaml(entries: dict) -> None:
    """Output history as YAML."""
    data = {}
    for month, entry in entries.items():
        data[month] = {
            "last_cutoff_date": str(entry.last_cutoff_date),
            "generated_at": entry.generated_at.isoformat(),
            "regenerated_at": (
                entry.regenerated_at.isoformat() if entry.regenerated_at else None
            ),
        }

    click.echo(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))


def main() -> None:
    """Main entry point for the CLI."""
    _setup_logging()
    cli()


if __name__ == "__main__":
    main()
