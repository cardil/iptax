"""Tests for CLI elements module."""

from datetime import UTC, date, datetime
from io import StringIO

import pytest
from rich.console import Console

from iptax.ai.models import Decision, Judgment
from iptax.cli import elements
from iptax.models import Change, HistoryEntry, InFlightReport, Repository

from .conftest import strip_ansi


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
        assert "Found 1 change" in output

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
        # New format includes indicator: "INCLUDE(✓): 1"
        import re

        assert re.search(
            r"INCLUDE.*: 1", output
        ), f"Expected 'INCLUDE.*: 1' in: {output}"
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
        # New format includes indicators: "INCLUDE(✓): 1  EXCLUDE(✗): 1"
        import re

        assert re.search(
            r"INCLUDE.*: 1", output
        ), f"Expected 'INCLUDE.*: 1' in: {output}"
        assert re.search(
            r"EXCLUDE.*: 1", output
        ), f"Expected 'EXCLUDE.*: 1' in: {output}"
        assert re.search(
            r"UNCERTAIN.*: 1", output
        ), f"Expected 'UNCERTAIN.*: 1' in: {output}"


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


class TestDisplayInflightTable:
    """Tests for display_inflight_table function."""

    def _create_report(
        self,
        month: str = "2024-11",
        *,
        with_changes: bool = False,
        workday_state: str = "none",
        review_state: str = "none",
    ) -> InFlightReport:
        """Create an InFlightReport with specified state.

        Args:
            month: Month in YYYY-MM format.
            with_changes: Whether to include changes.
            workday_state: One of "none", "incomplete", "validated".
            review_state: One of "none", "analyzed", "reviewed".
        """
        changes = []
        if with_changes:
            changes = [
                Change(
                    title="Test Change",
                    repository=Repository(
                        host="github.com",
                        path="org/repo",
                        provider_type="github",
                    ),
                    number=123,
                )
            ]

        # Set workday fields based on state
        total_hours = None
        workday_validated = False
        if workday_state == "incomplete":
            total_hours = 10.0
        elif workday_state == "validated":
            total_hours = 10.0
            workday_validated = True

        # Set judgment fields based on review state
        judgments = []
        if review_state in ("analyzed", "reviewed"):
            for change in changes:
                judgment = Judgment(
                    change_id=change.get_change_id(),
                    decision=Decision.INCLUDE,
                    reasoning="Test reasoning",
                    product="Test Product",
                )
                if review_state == "reviewed":
                    judgment.user_decision = Decision.INCLUDE
                judgments.append(judgment)

        return InFlightReport(
            month=month,
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=changes,
            total_hours=total_hours,
            workday_validated=workday_validated,
            judgments=judgments,
        )

    @pytest.mark.unit
    def test_empty_reports_list(self):
        """Test display with no in-flight reports."""
        console = Console(file=StringIO(), force_terminal=True)
        reports: list[tuple[str, InFlightReport]] = []

        elements.display_inflight_table(console, reports)

        output = console.file.getvalue()
        # Should still show table title
        assert "In-flight Reports" in output

    @pytest.mark.unit
    def test_single_report_collecting(self):
        """Test display of single report in collecting state."""
        console = Console(file=StringIO(), force_terminal=True)
        report = self._create_report()
        reports = [("2024-11", report)]

        elements.display_inflight_table(console, reports)

        output = strip_ansi(console.file.getvalue())
        assert "2024-11" in output
        assert "Collecting" in output

    @pytest.mark.unit
    def test_single_report_ready_for_dist(self):
        """Test display of report ready for dist."""
        console = Console(file=StringIO(), force_terminal=True)
        report = self._create_report(
            with_changes=True,
            workday_state="validated",
            review_state="reviewed",
        )
        reports = [("2024-11", report)]

        elements.display_inflight_table(console, reports)

        output = strip_ansi(console.file.getvalue())
        assert "2024-11" in output
        assert "Ready for dist" in output

    @pytest.mark.unit
    def test_multiple_reports_different_states(self):
        """Test display of multiple reports in different states."""
        console = Console(file=StringIO(), force_terminal=True)
        reports = [
            (
                "2024-10",
                self._create_report(
                    month="2024-10",
                    with_changes=True,
                    workday_state="validated",
                    review_state="reviewed",
                ),
            ),
            (
                "2024-11",
                self._create_report(
                    month="2024-11",
                    with_changes=True,
                ),
            ),
            ("2024-12", self._create_report(month="2024-12")),
        ]

        elements.display_inflight_table(console, reports)

        output = strip_ansi(console.file.getvalue())
        assert "2024-10" in output
        assert "2024-11" in output
        assert "2024-12" in output
        assert "Ready for dist" in output
        assert "Needs Workday" in output
        assert "Collecting" in output

    @pytest.mark.unit
    def test_legend_displayed(self):
        """Test that legend is displayed."""
        console = Console(file=StringIO(), force_terminal=True)
        reports: list[tuple[str, InFlightReport]] = []

        elements.display_inflight_table(console, reports)

        output = strip_ansi(console.file.getvalue())
        assert "Legend:" in output
        assert "complete" in output
        assert "pending" in output
        assert "skipped" in output

    @pytest.mark.unit
    def test_workday_disabled(self):
        """Test display when workday is disabled."""
        console = Console(file=StringIO(), force_terminal=True)
        report = self._create_report(
            with_changes=True,
            review_state="reviewed",
        )
        reports = [("2024-11", report)]

        elements.display_inflight_table(console, reports, workday_enabled=False)

        output = strip_ansi(console.file.getvalue())
        assert "Ready for dist" in output

    @pytest.mark.unit
    def test_workday_incomplete_warning(self):
        """Test display when workday is incomplete."""
        console = Console(file=StringIO(), force_terminal=True)
        report = self._create_report(
            with_changes=True,
            workday_state="incomplete",
        )
        reports = [("2024-11", report)]

        elements.display_inflight_table(console, reports)

        output = strip_ansi(console.file.getvalue())
        assert "Workday incomplete" in output
