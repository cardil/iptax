"""Reusable CLI flows for business logic."""

from datetime import date

from rich.console import Console

from iptax.ai.models import Decision, Judgment
from iptax.ai.review import ReviewResult
from iptax.ai.review import review_judgments as run_review_tui
from iptax.config import load_settings as config_load_settings
from iptax.did import fetch_changes as did_fetch_changes
from iptax.history import HistoryManager
from iptax.models import Change, Settings

from .elements import display_review_results


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
