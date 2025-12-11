"""Tests for total recorded days calculation bug fix."""

from datetime import date
from io import StringIO

import pytest
from rich.console import Console

from iptax.cli.flows import _display_collection_summary, _display_inflight_summary
from iptax.models import InFlightReport

from .conftest import strip_ansi


class TestTotalDaysCalculation:
    """Tests for total recorded days calculation."""

    @pytest.mark.unit
    def test_inflight_summary_total_days_with_pto(self):
        """Test that total days = work days + PTO days in inflight summary."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            total_hours=160.0,  # 19 work days + 1 PTO day = 20 days * 8h = 160h
            working_days=20,  # This represents all working calendar days
            absence_days=1,  # 1 day PTO
            workday_validated=True,
        )

        _display_inflight_summary(console, report)

        output = strip_ansi(console.file.getvalue())

        # Work time should show effective days (19) and hours (152)
        assert "Work Time: 19 days, 152 hours" in output

        # PTO should show 1 day, 8 hours
        assert "Paid Time Off: 1 days, 8 hours" in output

        # Total should be work days (19) + PTO days (1) = 20, hours = 160
        assert "Total Recorded: 20 days, 160 hours" in output

    @pytest.mark.unit
    def test_collection_summary_total_days_with_pto(self):
        """Test that total days = work days + PTO days in collection summary."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            total_hours=160.0,
            working_days=20,
            absence_days=1,
            workday_validated=True,
        )

        _display_collection_summary(console, report)

        output = strip_ansi(console.file.getvalue())

        # Work time should show effective days and hours
        assert "Work time: 19 days, 152 hours" in output

        # PTO should show correct values
        assert "Paid Time Off: 1 days, 8 hours" in output

        # Total should be correct: 20 days, 160 hours
        assert "Total recorded: 20 days, 160 hours" in output

    @pytest.mark.unit
    def test_inflight_summary_total_days_multiple_pto(self):
        """Test total days calculation with multiple PTO days."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            total_hours=176.0,  # 18 work days + 4 PTO days = 22 days * 8h = 176h
            working_days=22,
            absence_days=4,  # 4 days PTO
            workday_validated=True,
        )

        _display_inflight_summary(console, report)

        output = strip_ansi(console.file.getvalue())

        # effective_days = (176 - 4*8) / 8 = 144 / 8 = 18
        assert "Work Time: 18 days, 144 hours" in output
        assert "Paid Time Off: 4 days, 32 hours" in output
        # Total: 18 + 4 = 22 days
        assert "Total Recorded: 22 days, 176 hours" in output

    @pytest.mark.unit
    def test_collection_summary_no_pto(self):
        """Test that summary works correctly when there's no PTO."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            total_hours=160.0,
            working_days=20,
            absence_days=0,  # No PTO
            workday_validated=True,
        )

        _display_collection_summary(console, report)

        output = strip_ansi(console.file.getvalue())

        # Work time only, no PTO section
        assert "Work time: 20 days, 160 hours" in output
        # No PTO should be shown
        assert "Paid Time Off" not in output
        # No total should be shown when there's no PTO
        assert "Total recorded" not in output
