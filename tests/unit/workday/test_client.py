"""Unit tests for iptax.workday.client module."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from iptax.models import WorkdayConfig, WorkHours
from iptax.workday import WorkdayClient, WorkdayError
from iptax.workday.models import AuthenticationError


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
            patch.object(client, "fetch_work_hours", side_effect=NotImplementedError()),
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


class TestWorkdayClientCalculateWeeks:
    """Test WorkdayClient._calculate_weeks_count method."""

    def test_single_week(self):
        """Test calculation for a single week."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        client = WorkdayClient(config)

        # 7 days = 1 week
        result = client._calculate_weeks_count(date(2024, 11, 1), date(2024, 11, 7))
        assert result == 1

    def test_full_month(self):
        """Test calculation for a full month (30 days)."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        client = WorkdayClient(config)

        # 30 days = 5 weeks (rounded up)
        result = client._calculate_weeks_count(date(2024, 11, 1), date(2024, 11, 30))
        assert result == 5

    def test_partial_week(self):
        """Test calculation for partial weeks."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        client = WorkdayClient(config)

        # 10 days = 2 weeks (rounded up)
        result = client._calculate_weeks_count(date(2024, 11, 1), date(2024, 11, 10))
        assert result == 2


class TestWorkdayClientAdvanceProgress:
    """Test WorkdayClient._advance_progress method."""

    def test_advance_progress_with_controller(self):
        """Test that progress advances when controller is set."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        client = WorkdayClient(config)

        mock_progress = MagicMock()
        client._progress_ctrl = mock_progress

        client._advance_progress("Test step")

        mock_progress.advance.assert_called_once_with("Test step")

    def test_advance_progress_without_controller(self):
        """Test that progress is skipped when no controller."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        client = WorkdayClient(config)

        # Should not raise when _progress_ctrl is None
        client._advance_progress("Test step")


class TestWorkdayClientGetWorkHoursExceptions:
    """Test WorkdayClient.get_work_hours exception handling."""

    def test_generic_exception_interactive_exit(self):
        """Test generic exception with exit in interactive mode."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        client = WorkdayClient(config)

        with (
            patch("asyncio.run", side_effect=RuntimeError("Connection failed")),
            patch("iptax.workday.client.questionary") as mock_questionary,
            pytest.raises(AuthenticationError),
        ):
            mock_questionary.select.return_value.unsafe_ask.return_value = "exit"
            client.get_work_hours(
                date(2024, 11, 1),
                date(2024, 11, 30),
                interactive=True,
            )

    def test_generic_exception_interactive_manual(self):
        """Test generic exception with manual input in interactive mode."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        client = WorkdayClient(config)

        with (
            patch("asyncio.run", side_effect=RuntimeError("Connection failed")),
            patch("iptax.workday.client.questionary") as mock_questionary,
            patch("iptax.workday.client.prompt_manual_work_hours") as mock_prompt,
        ):
            mock_questionary.select.return_value.unsafe_ask.return_value = "manual"
            mock_prompt.return_value = WorkHours(working_days=20, total_hours=160.0)

            result = client.get_work_hours(
                date(2024, 11, 1),
                date(2024, 11, 30),
                interactive=True,
            )

            assert result.working_days == 20
            mock_prompt.assert_called_once()

    def test_generic_exception_non_interactive_raises(self):
        """Test that generic exception raises in non-interactive mode."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        client = WorkdayClient(config)

        with (
            patch("asyncio.run", side_effect=RuntimeError("Connection failed")),
            pytest.raises(AuthenticationError),
        ):
            client.get_work_hours(
                date(2024, 11, 1),
                date(2024, 11, 30),
                interactive=False,
            )

    def test_not_implemented_non_interactive_raises(self):
        """Test that NotImplementedError raises in non-interactive mode."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        client = WorkdayClient(config)

        with (
            patch("asyncio.run", side_effect=NotImplementedError()),
            pytest.raises(NotImplementedError),
        ):
            client.get_work_hours(
                date(2024, 11, 1),
                date(2024, 11, 30),
                interactive=False,
            )
