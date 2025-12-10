"""Reusable CLI elements for displaying output."""

import json
from datetime import date, timedelta
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from iptax.cache.inflight import ReportState
from iptax.models import (
    AICacheStats,
    Change,
    Decision,
    HistoryCacheStats,
    HistoryEntry,
    InflightCacheStats,
    InFlightReport,
    Judgment,
)

# File size constants
BYTES_PER_KB = 1024
BYTES_PER_MB = BYTES_PER_KB * 1024

# Month constants
MONTHS_IN_YEAR = 12


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
            str(entry.last_change_date),
            entry.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            regenerated,
        )

    console.print(table)

    if entries:
        latest_month = max(entries.keys())
        latest_entry = entries[latest_month]
        next_start = latest_entry.last_change_date + timedelta(days=1)
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
            "first_change_date": str(entry.first_change_date),
            "last_change_date": str(entry.last_change_date),
            "generated_at": entry.generated_at.isoformat(),
            "regenerated_at": (
                entry.regenerated_at.isoformat() if entry.regenerated_at else None
            ),
        }
    return data


def display_inflight_table(
    console: Console,
    reports: list[tuple[str, InFlightReport]],
    workday_enabled: bool = True,
) -> None:
    """Display in-flight reports as a formatted table with state columns.

    Args:
        console: Rich console for output
        reports: List of (month, InFlightReport) tuples
        workday_enabled: Whether Workday integration is enabled
    """
    table = Table(
        title="In-flight Reports",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Month", style="cyan", no_wrap=True)
    table.add_column("Created", style="dim")
    table.add_column("Did", justify="center")
    table.add_column("WD", justify="center")
    table.add_column("AI", justify="center")
    table.add_column("Rev", justify="center")
    table.add_column("Status", style="white")

    for month, report in reports:
        state = ReportState.from_report(report, workday_enabled=workday_enabled)

        # Format created date
        created_str = report.created_at.strftime("%b %d")

        # Color the status based on state
        status_style = _get_status_style(state.status)
        status_display = f"[{status_style}]{state.status}[/]"

        table.add_row(
            month,
            created_str,
            _colorize_state(state.did),
            _colorize_state(state.workday),
            _colorize_state(state.ai),
            _colorize_state(state.reviewed),
            status_display,
        )

    console.print(table)

    # Print legend
    console.print("\n[dim]Legend: ✓=complete  ○=pending  ⚠=incomplete  -=skipped[/dim]")


# State colorization mapping
_STATE_COLORS: dict[str, str] = {
    "✓": "[green]✓[/]",
    "○": "[dim]○[/]",
    "⚠": "[yellow]⚠[/]",
    "-": "[dim]-[/]",
}


def _colorize_state(state: str) -> str:
    """Colorize a state indicator.

    Args:
        state: State indicator character

    Returns:
        Rich-formatted state string
    """
    return _STATE_COLORS.get(state, state)


def _get_status_style(status: str) -> str:
    """Get style for a status message.

    Args:
        status: Status message

    Returns:
        Rich style string
    """
    if status == "Ready for dist":
        return "green"
    if status.startswith("Needs") or status == "Workday incomplete":
        return "yellow"
    if status == "Collecting":
        return "dim"
    return "white"


# Cache stats display functions


def display_cache_stats(
    console: Console,
    ai_stats: AICacheStats | None,
    history_stats: HistoryCacheStats | None,
    inflight_stats: InflightCacheStats | None,
) -> None:
    """Display comprehensive cache statistics.

    Args:
        console: Rich console for output
        ai_stats: AI cache statistics or None if unavailable
        history_stats: History statistics or None if unavailable
        inflight_stats: In-flight cache statistics or None if unavailable
    """
    console.print("\n[bold cyan]Cache Statistics[/bold cyan]")
    console.print("━" * 76)

    # AI Judgment Cache Section
    console.print("\n[bold]📊 AI Judgment Cache[/bold]")
    console.print("─" * 76)

    if ai_stats is None:
        console.print("  [dim]AI cache not available[/dim]")
    elif ai_stats.total_judgments == 0:
        console.print("  [dim]No judgments cached yet[/dim]")
        console.print(f"  Cache file:          {ai_stats.cache_path}")
    else:
        _display_ai_stats(console, ai_stats)

    # Report History Section
    console.print("\n[bold]📅 Report History[/bold]")
    console.print("─" * 76)

    if history_stats is None:
        console.print("  [dim]History not available[/dim]")
    elif history_stats.total_reports == 0:
        console.print("  [dim]No reports generated yet[/dim]")
        console.print(f"  History file:        {history_stats.history_path}")
    else:
        _display_history_stats(console, history_stats)

    # In-flight Cache Section
    console.print("\n[bold]📁 In-flight Cache[/bold]")
    console.print("─" * 76)

    if inflight_stats is None:
        console.print("  [dim]In-flight cache not available[/dim]")
    else:
        _display_inflight_stats(console, inflight_stats)


def _display_ai_stats(console: Console, stats: AICacheStats) -> None:
    """Display AI cache statistics."""
    correction_pct = stats.correction_rate * 100
    correct_pct = 100 - correction_pct

    console.print(f"  Total judgments:      {stats.total_judgments}")
    console.print(
        f"  Corrected (AI wrong): {stats.corrected_count} "
        f"([yellow]{correction_pct:.1f}%[/yellow])"
    )
    console.print(
        f"  Correct (AI right):   {stats.correct_count} "
        f"([green]{correct_pct:.1f}%[/green])"
    )

    if stats.products:
        products_str = ", ".join(stats.products)
        console.print(f"  Products:             {products_str}")

    if stats.oldest_judgment and stats.newest_judgment:
        # Extract just the date part from ISO format
        oldest_date = stats.oldest_judgment[:10]
        newest_date = stats.newest_judgment[:10]
        console.print(f"  Date range:           {oldest_date} to {newest_date}")

    # Format file size
    size_str = _format_file_size(stats.cache_size_bytes)
    console.print(f"  Cache file:           {stats.cache_path} ({size_str})")


def _display_history_stats(console: Console, stats: HistoryCacheStats) -> None:
    """Display report history statistics."""
    console.print(f"  Total reports:       {stats.total_reports}")

    # Find continuous periods
    periods = _find_continuous_periods(stats.entries)
    if periods:
        console.print("  Continuous periods:")
        for start_month, end_month, count, is_current in periods:
            current_marker = " (current)" if is_current else ""
            console.print(
                f"    • {start_month} to {end_month} ({count} months{current_marker})"
            )

    # Report timeline
    console.print("\n  Report Timeline:")
    sorted_months = sorted(stats.entries.keys())
    latest_month = sorted_months[-1] if sorted_months else None

    for month in sorted_months:
        entry = stats.entries[month]
        gen_date = entry.generated_at.strftime("%b %d")
        latest_marker = "  (latest)" if month == latest_month else ""
        console.print(f"    {month}  ■ {gen_date}{latest_marker}")

    # Next report due
    if latest_month and stats.entries:
        latest_entry = stats.entries[latest_month]
        next_start = latest_entry.last_change_date + timedelta(days=1)
        # Estimate next month
        next_month = _get_next_month(latest_month)
        next_day = next_start + timedelta(days=30)
        recommended = next_day.strftime("%b %d")
        console.print(
            f"\n  Next report due:     {next_month} ({recommended} recommended)"
        )

    # File info
    size_str = _format_file_size(stats.history_size_bytes)
    console.print(f"  History file:        {stats.history_path} ({size_str})")


def _display_inflight_stats(console: Console, stats: InflightCacheStats) -> None:
    """Display in-flight cache statistics."""
    if stats.active_reports == 0:
        console.print("  Active reports:      0")
    else:
        months_str = ", ".join(stats.months)
        console.print(f"  Active reports:      {stats.active_reports} ({months_str})")

    console.print(f"  Cache directory:     {stats.cache_dir}")


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    if size_bytes < BYTES_PER_KB:
        return f"{size_bytes} B"
    if size_bytes < BYTES_PER_MB:
        return f"{size_bytes / BYTES_PER_KB:.0f} KB"
    return f"{size_bytes / BYTES_PER_MB:.1f} MB"


def _get_next_month(month: str) -> str:
    """Get the next month in YYYY-MM format."""
    try:
        year, month_num = map(int, month.split("-"))
        if month_num == MONTHS_IN_YEAR:
            return f"{year + 1}-01"
        return f"{year}-{month_num + 1:02d}"
    except (ValueError, IndexError):
        return "next month"


def _find_continuous_periods(
    entries: dict[str, HistoryEntry],
) -> list[tuple[str, str, int, bool]]:
    """Find continuous monthly periods in history.

    Returns:
        List of (start_month, end_month, count, is_current) tuples
    """
    if not entries:
        return []

    sorted_months = sorted(entries.keys())
    periods: list[tuple[str, str, int, bool]] = []

    start_month = sorted_months[0]
    prev_month = start_month
    count = 1

    for month in sorted_months[1:]:
        expected_next = _get_next_month(prev_month)
        if month == expected_next:
            count += 1
            prev_month = month
        else:
            # End current period, start new one
            is_current = prev_month == sorted_months[-1]
            periods.append((start_month, prev_month, count, is_current))
            start_month = month
            prev_month = month
            count = 1

    # Add final period
    is_current = prev_month == sorted_months[-1]
    periods.append((start_month, prev_month, count, is_current))

    return periods


def display_cache_paths(
    console: Console,
    ai_cache_path: Path,
    history_path: Path,
    inflight_dir: Path,
) -> None:
    """Display paths to all cache directories.

    Args:
        console: Rich console for output
        ai_cache_path: Path to AI cache file
        history_path: Path to history file
        inflight_dir: Path to in-flight cache directory
    """
    console.print("\n[bold cyan]Cache Paths[/bold cyan]")
    console.print("━" * 76)
    console.print(f"  AI Cache:      {ai_cache_path}")
    console.print(f"  History:       {history_path}")
    console.print(f"  In-flight:     {inflight_dir}")
