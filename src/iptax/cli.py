"""Command-line interface for iptax."""

import sys

import click
import yaml

from iptax.config import (
    ConfigError,
    create_default_config,
    get_config_path,
    load_settings,
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
def report(month: str | None, skip_ai: bool, skip_workday: bool, dry_run: bool) -> None:
    """Generate IP tax report for the specified month (default: current month)."""
    click.echo("Report generation not yet implemented")
    click.echo(f"Month: {month or 'current'}")
    click.echo(f"Skip AI: {skip_ai}")
    click.echo(f"Skip Workday: {skip_workday}")
    click.echo(f"Dry run: {dry_run}")


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


def main() -> None:
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
