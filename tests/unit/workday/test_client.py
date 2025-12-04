"""Unit tests for iptax.workday.client module."""

from collections.abc import Callable
from datetime import date
from typing import NoReturn
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iptax.models import WorkdayConfig, WorkHours
from iptax.workday import WorkdayClient, WorkdayError
from iptax.workday.models import AuthenticationError


def _close_coro_and_raise(error: Exception) -> Callable[[object], NoReturn]:
    """Create a side_effect function that closes coroutine before raising."""

    def side_effect(coro: object) -> NoReturn:
        if hasattr(coro, "close"):
            coro.close()
        raise error

    return side_effect


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
            patch(
                "asyncio.run",
                side_effect=_close_coro_and_raise(RuntimeError("Connection failed")),
            ),
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
            patch(
                "asyncio.run",
                side_effect=_close_coro_and_raise(RuntimeError("Connection failed")),
            ),
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
            patch(
                "asyncio.run",
                side_effect=_close_coro_and_raise(RuntimeError("Connection failed")),
            ),
            pytest.raises(AuthenticationError),
        ):
            client.get_work_hours(
                date(2024, 11, 1),
                date(2024, 11, 30),
                interactive=False,
            )


class TestWorkdayClientInit:
    """Test WorkdayClient.__init__ method."""

    def test_init_sets_config(self):
        """Test that __init__ sets config correctly."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        client = WorkdayClient(config)

        assert client.config is config
        assert client._progress_ctrl is None

    def test_init_with_disabled_config(self):
        """Test that __init__ works with disabled config."""
        config = WorkdayConfig(enabled=False)
        client = WorkdayClient(config)

        assert client.config.enabled is False
        assert client.console is not None


class TestWorkdayClientRetryFlow:
    """Test WorkdayClient.get_work_hours retry flow."""

    def test_generic_exception_interactive_retry_then_success(self):
        """Test retry flow when user selects retry and succeeds."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        client = WorkdayClient(config)

        call_count = [0]
        results = [
            RuntimeError("First attempt failed"),
            WorkHours(working_days=22, total_hours=176.0),
        ]

        def fetch_side_effect(coro: object) -> WorkHours:
            # Close the coroutine to avoid "never awaited" warning
            if hasattr(coro, "close"):
                coro.close()
            call_count[0] += 1
            result = results[call_count[0] - 1]
            if isinstance(result, Exception):
                raise result
            return result

        with (
            patch("asyncio.run", side_effect=fetch_side_effect),
            patch("iptax.workday.client.questionary") as mock_questionary,
        ):
            mock_questionary.select.return_value.unsafe_ask.return_value = "retry"

            result = client.get_work_hours(
                date(2024, 11, 1),
                date(2024, 11, 30),
                interactive=True,
            )

            assert result.working_days == 22
            assert call_count[0] == 2


class TestWorkdayClientFetchWorkHours:
    """Test WorkdayClient.fetch_work_hours async method."""

    @pytest.fixture
    def mock_console(self):
        """Create a mock console with is_jupyter=False to prevent ipywidgets warning."""
        mock = MagicMock()
        mock.is_jupyter = False
        return mock

    @pytest.fixture
    def config(self):
        """Create test config."""
        return WorkdayConfig(enabled=True, url="https://workday.example.org")

    @pytest.fixture
    def mock_playwright_context(self):
        """Create mock Playwright context manager."""
        mock_page = MagicMock()
        mock_page.set_default_timeout = MagicMock()

        mock_context = AsyncMock()
        mock_context.pages = [mock_page]
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.launch_persistent_context = AsyncMock(return_value=mock_context)

        mock_playwright = MagicMock()
        mock_playwright.firefox = mock_browser

        return mock_playwright, mock_context, mock_page

    @pytest.mark.asyncio
    async def test_fetch_work_hours_happy_path(
        self, config, mock_console, mock_playwright_context, tmp_path
    ):
        """Test successful fetch_work_hours execution."""
        mock_playwright, mock_context, _ = mock_playwright_context
        expected_hours = WorkHours(working_days=21, total_hours=168.0, absence_days=0)

        # Create mock log file
        mock_log_file = MagicMock()

        with (
            patch("iptax.workday.client.async_playwright") as mock_async_playwright,
            patch("iptax.workday.client.setup_profile_directory") as mock_profile,
            patch("iptax.workday.client.setup_browser_logging") as mock_logging,
            patch("iptax.workday.client.authenticate") as mock_auth,
            patch("iptax.workday.client.navigate_to_home") as mock_nav_home,
            patch("iptax.workday.client.navigate_to_time_page") as mock_nav_time,
            patch("iptax.workday.client.extract_work_hours") as mock_extract,
            patch("iptax.workday.client.ProgressController") as mock_progress_cls,
        ):
            # Setup mocks
            mock_async_playwright.return_value.__aenter__.return_value = mock_playwright
            mock_profile.return_value = str(tmp_path / "test-profile")
            mock_logging.return_value = mock_log_file
            mock_auth.return_value = None
            mock_nav_home.return_value = None
            mock_nav_time.return_value = None
            mock_extract.return_value = expected_hours

            # Setup progress controller mock
            mock_progress = MagicMock()
            mock_progress_cls.return_value.__enter__.return_value = mock_progress

            client = WorkdayClient(config, console=mock_console)
            result = await client.fetch_work_hours(
                date(2024, 11, 1), date(2024, 11, 30), headless=True
            )

            assert result.working_days == 21
            assert result.total_hours == 168.0
            mock_auth.assert_called_once()
            mock_extract.assert_called_once()
            mock_log_file.close.assert_called_once()
            mock_context.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_work_hours_authentication_error(
        self, config, mock_console, mock_playwright_context, tmp_path
    ):
        """Test fetch_work_hours when authentication fails."""
        mock_playwright, _mock_context, _ = mock_playwright_context

        # Create mock log file
        mock_log_file = MagicMock()

        with (
            patch("iptax.workday.client.async_playwright") as mock_async_playwright,
            patch("iptax.workday.client.setup_profile_directory") as mock_profile,
            patch("iptax.workday.client.setup_browser_logging") as mock_logging,
            patch("iptax.workday.client.authenticate") as mock_auth,
            patch("iptax.workday.client.dump_debug_snapshot") as mock_snapshot,
            patch("iptax.workday.client.ProgressController") as mock_progress_cls,
            pytest.raises(AuthenticationError),
        ):
            # Setup mocks
            mock_async_playwright.return_value.__aenter__.return_value = mock_playwright
            mock_profile.return_value = str(tmp_path / "test-profile")
            mock_logging.return_value = mock_log_file
            mock_auth.side_effect = AuthenticationError("SSO failed")
            mock_snapshot.return_value = str(tmp_path / "snapshot.txt")

            # Setup progress controller mock
            mock_progress = MagicMock()
            mock_progress_cls.return_value.__enter__.return_value = mock_progress

            client = WorkdayClient(config, console=mock_console)
            await client.fetch_work_hours(
                date(2024, 11, 1), date(2024, 11, 30), headless=True
            )

    @pytest.mark.asyncio
    async def test_fetch_work_hours_navigation_error(
        self, config, mock_console, mock_playwright_context, tmp_path
    ):
        """Test fetch_work_hours when time page navigation fails."""
        mock_playwright, _mock_context, _ = mock_playwright_context

        # Create mock log file
        mock_log_file = MagicMock()

        with (
            patch("iptax.workday.client.async_playwright") as mock_async_playwright,
            patch("iptax.workday.client.setup_profile_directory") as mock_profile,
            patch("iptax.workday.client.setup_browser_logging") as mock_logging,
            patch("iptax.workday.client.authenticate") as mock_auth,
            patch("iptax.workday.client.navigate_to_home") as mock_nav_home,
            patch("iptax.workday.client.navigate_to_time_page") as mock_nav_time,
            patch("iptax.workday.client.dump_debug_snapshot") as mock_snapshot,
            patch("iptax.workday.client.ProgressController") as mock_progress_cls,
            pytest.raises(WorkdayError),
        ):
            # Setup mocks
            mock_async_playwright.return_value.__aenter__.return_value = mock_playwright
            mock_profile.return_value = str(tmp_path / "test-profile")
            mock_logging.return_value = mock_log_file
            mock_auth.return_value = None
            mock_nav_home.return_value = None
            mock_nav_time.side_effect = WorkdayError("Time button not found")
            mock_snapshot.return_value = str(tmp_path / "snapshot.txt")

            # Setup progress controller mock
            mock_progress = MagicMock()
            mock_progress_cls.return_value.__enter__.return_value = mock_progress

            client = WorkdayClient(config, console=mock_console)
            await client.fetch_work_hours(
                date(2024, 11, 1), date(2024, 11, 30), headless=True
            )

    @pytest.mark.asyncio
    async def test_fetch_work_hours_with_no_existing_pages(
        self, config, mock_console, tmp_path
    ):
        """Test fetch_work_hours creates new page when context has no pages."""
        mock_page = MagicMock()
        mock_page.set_default_timeout = MagicMock()

        mock_context = AsyncMock()
        mock_context.pages = []  # No existing pages
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.launch_persistent_context = AsyncMock(return_value=mock_context)

        mock_playwright = MagicMock()
        mock_playwright.firefox = mock_browser

        mock_log_file = MagicMock()
        expected_hours = WorkHours(working_days=20, total_hours=160.0)

        with (
            patch("iptax.workday.client.async_playwright") as mock_async_playwright,
            patch("iptax.workday.client.setup_profile_directory") as mock_profile,
            patch("iptax.workday.client.setup_browser_logging") as mock_logging,
            patch("iptax.workday.client.authenticate") as mock_auth,
            patch("iptax.workday.client.navigate_to_home") as mock_nav_home,
            patch("iptax.workday.client.navigate_to_time_page") as mock_nav_time,
            patch("iptax.workday.client.extract_work_hours") as mock_extract,
            patch("iptax.workday.client.ProgressController") as mock_progress_cls,
        ):
            mock_async_playwright.return_value.__aenter__.return_value = mock_playwright
            mock_profile.return_value = str(tmp_path / "test-profile")
            mock_logging.return_value = mock_log_file
            mock_auth.return_value = None
            mock_nav_home.return_value = None
            mock_nav_time.return_value = None
            mock_extract.return_value = expected_hours

            mock_progress = MagicMock()
            mock_progress_cls.return_value.__enter__.return_value = mock_progress

            client = WorkdayClient(config, console=mock_console)
            result = await client.fetch_work_hours(
                date(2024, 11, 1), date(2024, 11, 30), headless=True
            )

            # Should have created a new page
            mock_context.new_page.assert_called_once()
            assert result.working_days == 20


class TestWorkdayClientConsoleInjection:
    """Test WorkdayClient console dependency injection."""

    def test_init_with_custom_console(self):
        """Test that custom console is used when provided."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")
        mock_console = MagicMock()
        mock_console.is_jupyter = False

        client = WorkdayClient(config, console=mock_console)

        assert client.console is mock_console

    def test_init_creates_default_console(self):
        """Test that default console is created when not provided."""
        config = WorkdayConfig(enabled=True, url="https://workday.example.org")

        client = WorkdayClient(config)

        assert client.console is not None
