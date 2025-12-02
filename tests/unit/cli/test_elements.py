"""Tests for CLI elements module."""

import re
from datetime import UTC, date, datetime
from io import StringIO

import pytest
from rich.console import Console

from iptax.ai.models import Decision, Judgment
from iptax.cli import elements
from iptax.models import Change, HistoryEntry, Repository

# Regex to strip ANSI escape codes
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return ANSI_ESCAPE.sub("", text)


class TestDisplayChanges:
    """Tests for display_changes function."""

    @pytest.mark.unit
    def test_empty_changes(self):
        """Test display with no changes."""
        console = Console(file=StringIO(), force_terminal=True)
        changes: list[Change] = []

        elements.display_changes(
            console, changes, date(2024, 10, 1), date(2024, 10, 31)
        )

        output = strip_ansi(console.file.getvalue())
        assert "No changes found" in output

    @pytest.mark.unit
    def test_displays_date_range(self):
        """Test that date range is displayed."""
        console = Console(file=StringIO(), force_terminal=True)
        changes: list[Change] = []

        elements.display_changes(
            console, changes, date(2024, 10, 1), date(2024, 10, 31)
        )

        output = strip_ansi(console.file.getvalue())
        assert "2024-10-01" in output
        assert "2024-10-31" in output

    @pytest.mark.unit
    def test_displays_change_count(self):
        """Test that change count is displayed."""
        console = Console(file=StringIO(), force_terminal=True)
        changes = [
            Change(
                title="Test change",
                repository=Repository(
                    host="github.com",
                    path="org/repo",
                    provider_type="github",
                ),
                number=100,
            )
        ]

        elements.display_changes(
            console, changes, date(2024, 10, 1), date(2024, 10, 31)
        )

        output = strip_ansi(console.file.getvalue())
        assert "Found 1 changes" in output

    @pytest.mark.unit
    def test_displays_change_title(self):
        """Test that change title is displayed."""
        console = Console(file=StringIO(), force_terminal=True)
        changes = [
            Change(
                title="Fix critical bug in parser",
                repository=Repository(
                    host="github.com",
                    path="org/repo",
                    provider_type="github",
                ),
                number=100,
            )
        ]

        elements.display_changes(
            console, changes, date(2024, 10, 1), date(2024, 10, 31)
        )

        output = strip_ansi(console.file.getvalue())
        assert "Fix critical bug in parser" in output


class TestDisplayReviewResults:
    """Tests for display_review_results function."""

    @pytest.mark.unit
    def test_cancelled_review(self):
        """Test display when review is cancelled."""
        console = Console(file=StringIO(), force_terminal=True)
        judgments: list[Judgment] = []
        changes: list[Change] = []

        elements.display_review_results(console, judgments, changes, accepted=False)

        output = strip_ansi(console.file.getvalue())
        assert "cancelled" in output

    @pytest.mark.unit
    def test_accepted_review_with_includes(self):
        """Test display with included changes."""
        console = Console(file=StringIO(), force_terminal=True)
        change = Change(
            title="Test change",
            repository=Repository(
                host="github.com", path="org/repo", provider_type="github"
            ),
            number=100,
        )
        judgments = [
            Judgment(
                change_id=change.get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Test Product",
            )
        ]

        elements.display_review_results(console, judgments, [change], accepted=True)

        output = strip_ansi(console.file.getvalue())
        assert "INCLUDE: 1" in output
        assert "Test change" in output

    @pytest.mark.unit
    def test_displays_decision_counts(self):
        """Test that all decision counts are displayed."""
        console = Console(file=StringIO(), force_terminal=True)
        changes = [
            Change(
                title=f"Change {i}",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100 + i,
            )
            for i in range(3)
        ]
        judgments = [
            Judgment(
                change_id=changes[0].get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Product",
            ),
            Judgment(
                change_id=changes[1].get_change_id(),
                decision=Decision.EXCLUDE,
                reasoning="Test",
                product="Product",
            ),
            Judgment(
                change_id=changes[2].get_change_id(),
                decision=Decision.UNCERTAIN,
                reasoning="Test",
                product="Product",
            ),
        ]

        elements.display_review_results(console, judgments, changes, accepted=True)

        output = strip_ansi(console.file.getvalue())
        assert "INCLUDE: 1" in output
        assert "EXCLUDE: 1" in output
        assert "UNCERTAIN: 1" in output


class TestDisplayHistoryTable:
    """Tests for display_history_table function."""

    @pytest.mark.unit
    def test_empty_entries(self):
        """Test display with no history entries."""
        console = Console(file=StringIO(), force_terminal=True)
        entries: dict[str, HistoryEntry] = {}

        elements.display_history_table(console, entries)

        output = console.file.getvalue()
        # Should still show table headers
        assert "Report History" in output

    @pytest.mark.unit
    def test_single_entry(self):
        """Test display with one history entry."""
        console = Console(file=StringIO(), force_terminal=True)
        entries = {
            "2024-10": HistoryEntry(
                last_cutoff_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }

        elements.display_history_table(console, entries)

        output = strip_ansi(console.file.getvalue())
        assert "2024-10" in output
        assert "2024-10-25" in output

    @pytest.mark.unit
    def test_next_start_date_shown(self):
        """Test that next start date is shown."""
        console = Console(file=StringIO(), force_terminal=True)
        entries = {
            "2024-10": HistoryEntry(
                last_cutoff_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }

        elements.display_history_table(console, entries)

        output = strip_ansi(console.file.getvalue())
        assert "Next report will start from" in output
        assert "2024-10-26" in output


class TestFormatHistoryJson:
    """Tests for format_history_json function."""

    @pytest.mark.unit
    def test_empty_entries(self):
        """Test JSON formatting of empty entries."""
        entries: dict[str, HistoryEntry] = {}
        result = elements.format_history_json(entries)
        assert result == "{}"

    @pytest.mark.unit
    def test_single_entry(self):
        """Test JSON formatting of single entry."""
        entries = {
            "2024-10": HistoryEntry(
                last_cutoff_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }
        result = elements.format_history_json(entries)
        assert "2024-10" in result
        assert "2024-10-25" in result
        assert '"last_cutoff_date"' in result


class TestFormatHistoryYaml:
    """Tests for format_history_yaml function."""

    @pytest.mark.unit
    def test_empty_entries(self):
        """Test YAML formatting of empty entries."""
        entries: dict[str, HistoryEntry] = {}
        result = elements.format_history_yaml(entries)
        assert result == "{}\n"

    @pytest.mark.unit
    def test_single_entry(self):
        """Test YAML formatting of single entry."""
        entries = {
            "2024-10": HistoryEntry(
                last_cutoff_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }
        result = elements.format_history_yaml(entries)
        assert "2024-10" in result
        assert "2024-10-25" in result
        assert "last_cutoff_date" in result
