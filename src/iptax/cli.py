"""Command-line interface for iptax-reporter."""

import click


@click.group()
@click.version_option()
def cli() -> None:
    """IP Tax Reporter - Automated tax report generator for Polish IP tax deduction program."""
    pass


@cli.command()
@click.option("--month", help="Month to generate report for (YYYY-MM format)")
@click.option("--skip-ai", is_flag=True, help="Skip AI filtering")
@click.option("--skip-workday", is_flag=True, help="Skip Workday integration")
@click.option("--dry-run", is_flag=True, help="Show what would be generated without creating files")
def report(month: str | None, skip_ai: bool, skip_workday: bool, dry_run: bool) -> None:
    """Generate IP tax report for the specified month (default: current month)."""
    click.echo("Report generation not yet implemented")
    click.echo(f"Month: {month or 'current'}")
    click.echo(f"Skip AI: {skip_ai}")
    click.echo(f"Skip Workday: {skip_workday}")
    click.echo(f"Dry run: {dry_run}")


@cli.command()
def config() -> None:
    """Configure iptax settings interactively."""
    click.echo("Configuration wizard not yet implemented")


def main() -> None:
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
