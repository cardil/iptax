"""Unit tests for iptax.workday.client module."""

from datetime import date
from unittest.mock import patch

import pytest

from iptax.models import WorkdayConfig, WorkHours
from iptax.workday import WorkdayClient, WorkdayError


class TestWorkdayClientGetWorkHours:
    """Test WorkdayClient.get_work_hours method."""

    def test_disabled_workday_non_interactive_raises(self):
        """Test that disabled Workday raises error in non-interactive mode."""
        config = WorkdayConfig(enabled=False)
        client = WorkdayClient(config)

        with pytest.raises(WorkdayError) as exc_info:
            client.get_work_hours(
                date(2024, 11, 1),
                date(2024, 11, 30),
                interactive=False,
            )

        assert "Workday integration is disabled" in str(exc_info.value)

    def test_disabled_workday_interactive_calls_manual_prompt(self):
        """Test that disabled Workday falls back to manual in interactive mode."""
        config = WorkdayConfig(enabled=False)
        client = WorkdayClient(config)

        with patch("iptax.workday.client.prompt_manual_work_hours") as mock_prompt:
            mock_prompt.return_value = WorkHours(
                working_days=21,
                total_hours=168.0,
            )

            result = client.get_work_hours(
                date(2024, 11, 1),
                date(2024, 11, 30),
                interactive=True,
            )

            mock_prompt.assert_called_once_with(date(2024, 11, 1), date(2024, 11, 30))
            assert result.working_days == 21

    def test_not_implemented_interactive_calls_manual_prompt(self):
        """Test that NotImplementedError falls back to manual in interactive mode."""
        config = WorkdayConfig(
            enabled=True,
            url="https://workday.example.org",
        )
        client = WorkdayClient(config)

        with (
            patch("iptax.workday.client.prompt_manual_work_hours") as mock_prompt,
            patch("iptax.workday.client.questionary") as mock_questionary,
        ):
            mock_prompt.return_value = WorkHours(
                working_days=21,
                total_hours=168.0,
            )

            result = client.get_work_hours(
                date(2024, 11, 1),
                date(2024, 11, 30),
                interactive=True,
            )

            mock_questionary.print.assert_called()
            mock_prompt.assert_called_once_with(date(2024, 11, 1), date(2024, 11, 30))
            assert result.working_days == 21


class TestWorkdayClientErrorTelemetry:
    """Test WorkdayClient._display_error_telemetry method."""

    def test_displays_error_info(self):
        """Test that error telemetry displays diagnostic info."""
        config = WorkdayConfig(
            enabled=True,
            url="https://workday.example.org",
            auth="sso+kerberos",
        )
        client = WorkdayClient(config)

        with patch("iptax.workday.client.questionary") as mock_questionary:
            test_error = Exception("Test error message")
            client._display_error_telemetry(test_error)

            # Check that print was called with error info
            calls = mock_questionary.print.call_args_list
            assert len(calls) >= 4
            # Check for key diagnostic info in calls
            all_calls_str = " ".join(str(c) for c in calls)
            assert "authentication failed" in all_calls_str.lower()
            assert "workday.example.org" in all_calls_str
