"""Reusable CLI elements for displaying output."""

import json
from datetime import date, timedelta

import yaml
from rich.console import Console
from rich.table import Table

from iptax.models import Change, Decision, HistoryEntry, Judgment


def count_decisions(
    judgments: list[Judgment],
    *,
    use_final: bool = True,
) -> tuple[int, int, int]:
    """Count judgments by decision type.

    Args:
        judgments: List of judgments to count
        use_final: If True, use final_decision; if False, use decision (AI)

    Returns:
        Tuple of (include_count, exclude_count, uncertain_count)
    """
    if use_final:
        include_count = sum(
            1 for j in judgments if j.final_decision == Decision.INCLUDE
        )
        exclude_count = sum(
            1 for j in judgments if j.final_decision == Decision.EXCLUDE
        )
        uncertain_count = sum(
            1 for j in judgments if j.final_decision == Decision.UNCERTAIN
        )
    else:
        include_count = sum(1 for j in judgments if j.decision == Decision.INCLUDE)
        exclude_count = sum(1 for j in judgments if j.decision == Decision.EXCLUDE)
        uncertain_count = sum(1 for j in judgments if j.decision == Decision.UNCERTAIN)
    return include_count, exclude_count, uncertain_count


def format_decision_summary(
    include_count: int,
    exclude_count: int,
    uncertain_count: int,
    *,
    uncertain_color: str = "yellow",
) -> str:
    """Format decision counts as a Rich-markup summary string.

    Args:
        include_count: Number of INCLUDE decisions
        exclude_count: Number of EXCLUDE decisions
        uncertain_count: Number of UNCERTAIN decisions
        uncertain_color: Color for uncertain count (yellow or orange)

    Returns:
        Rich-formatted summary string with only non-zero counts
    """
    summary_parts = []
    if include_count > 0:
        summary_parts.append(f"[green]INCLUDE(✓): {include_count}[/]")
    if exclude_count > 0:
        summary_parts.append(f"[red]EXCLUDE(✗): {exclude_count}[/]")
    if uncertain_count > 0:
        summary_parts.append(f"[{uncertain_color}]UNCERTAIN(?): {uncertain_count}[/]")
    return "  ".join(summary_parts)


def display_changes(
    console: Console,
    changes: list[Change],
    start_date: date,
    end_date: date,
) -> None:
    """Display fetched changes in the console.

    Args:
        console: Rich console for output
        changes: List of changes to display
        start_date: Start of date range
        end_date: End of date range
    """
    console.print(f"[cyan]📅[/cyan] Date range: {start_date} to {end_date}")
    change_word = "change" if len(changes) == 1 else "changes"
    console.print(f"[green]✓[/green] Found {len(changes)} {change_word}")

    if not changes:
        console.print("[yellow]No changes found for this period[/yellow]")
        return

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


def display_review_results(
    console: Console,
    judgments: list[Judgment],
    changes: list[Change],
    *,
    accepted: bool,
) -> None:
    """Display review results after TUI.

    Args:
        console: Rich console for output
        judgments: Final judgments after review
        changes: Original changes for title lookup
        accepted: Whether user accepted (True) or quit (False)
    """
    if not accepted:
        console.print("\n[yellow]Review cancelled (quit)[/]")
        return

    # Count and format decisions using shared utilities
    include_count, exclude_count, uncertain_count = count_decisions(judgments)
    summary = format_decision_summary(include_count, exclude_count, uncertain_count)

    # Print summary
    console.print(f"\n[bold]Review complete:[/] {summary}")

    # Print approved list with user action indicator
    console.print("\n[bold]Approved changes:[/]")
    change_map = {c.get_change_id(): c for c in changes}

    for j in judgments:
        if j.final_decision != Decision.INCLUDE:
            continue

        change_or_none = change_map.get(j.change_id)
        title = change_or_none.title if change_or_none else j.change_id

        # Indicator for user action
        action_icon = "[cyan]✎[/]" if j.was_corrected else " "
        reason_str = f" [dim]({j.user_reasoning})[/]" if j.user_reasoning else ""

        console.print(f"  {action_icon} [green]✓[/] {title}{reason_str}")


def display_history_table(console: Console, entries: dict[str, HistoryEntry]) -> None:
    """Display history entries as a formatted table.

    Args:
        console: Rich console for output
        entries: Dictionary of month -> HistoryEntry
    """
    table = Table(title="Report History", show_header=True, header_style="bold cyan")
    table.add_column("Month", style="cyan", no_wrap=True)
    table.add_column("Cutoff Date", style="green")
    table.add_column("Generated At", style="blue")
    table.add_column("Regenerated", style="yellow")

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

    if entries:
        latest_month = max(entries.keys())
        latest_entry = entries[latest_month]
        next_start = latest_entry.last_cutoff_date + timedelta(days=1)
        console.print(
            f"\nNext report will start from: [green]{next_start}[/green]",
        )


def format_history_json(entries: dict[str, HistoryEntry]) -> str:
    """Format history entries as JSON.

    Args:
        entries: Dictionary of month -> HistoryEntry

    Returns:
        JSON string
    """
    data = _convert_entries_to_dict(entries)
    return json.dumps(data, indent=2)


def format_history_yaml(entries: dict[str, HistoryEntry]) -> str:
    """Format history entries as YAML.

    Args:
        entries: Dictionary of month -> HistoryEntry

    Returns:
        YAML string
    """
    data = _convert_entries_to_dict(entries)
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)


def _convert_entries_to_dict(entries: dict[str, HistoryEntry]) -> dict:
    """Convert history entries to serializable dictionary."""
    data = {}
    for month, entry in entries.items():
        data[month] = {
            "last_cutoff_date": str(entry.last_cutoff_date),
            "generated_at": entry.generated_at.isoformat(),
            "regenerated_at": (
                entry.regenerated_at.isoformat() if entry.regenerated_at else None
            ),
        }
    return data
