"""Tests for total recorded days calculation bug fix."""

from datetime import date
from io import StringIO

import pytest
from rich.console import Console

from iptax.cli.flows import _display_inflight_summary
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
            # 23 calendar working days, but only 19 worked + 1 PTO recorded.
            # Previously, total_days used working_days (23) causing 23 vs 20 bug.
            working_days=23,
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
            # Example with missing days: 25 calendar working days vs 22 recorded.
            working_days=25,
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
    def test_inflight_summary_with_holidays_and_pto(self):
        """Test total days calculation with both holidays and PTO."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-12",
            workday_start=date(2024, 12, 1),
            workday_end=date(2024, 12, 31),
            changes_since=date(2024, 11, 25),
            changes_until=date(2024, 12, 25),
            total_hours=184.0,  # 15 work + 5 PTO + 3 holidays = 23 days * 8h = 184h
            working_days=23,
            absence_days=5,  # 5 days PTO
            holiday_days=3,  # 3 days holidays
            workday_validated=True,
        )

        _display_inflight_summary(console, report)

        output = strip_ansi(console.file.getvalue())

        # effective_days = (184 - (5+3)*8) / 8 = 120 / 8 = 15
        assert "Work Time: 15 days, 120 hours" in output
        assert "Paid Time Off: 5 days, 40 hours" in output
        assert "Holidays: 3 days, 24 hours" in output
        # Total: 15 + 5 + 3 = 23 days
        assert "Total Recorded: 23 days, 184 hours" in output
