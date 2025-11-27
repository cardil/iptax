"""Tests for workday.auth module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from iptax.models import WorkdayConfig
from iptax.workday.auth import (
    MAX_LOGIN_RETRIES,
    BadCredentialsError,
    _is_workday_url,
    _process_login_race_result,
    _raise_auth_error,
    _raise_bad_credentials,
    _submit_credentials_once,
    _wait_for_login_form_reappear,
    _wait_for_workday_redirect,
    authenticate,
    navigate_to_home,
)
from iptax.workday.models import AuthenticationError


class TestIsWorkdayUrl:
    """Test _is_workday_url function."""

    def test_valid_workday_url(self) -> None:
        """Test that myworkday.com URLs are recognized."""
        assert _is_workday_url("https://wd5.myworkday.com/example/d/home.htmld")

    def test_non_workday_url(self) -> None:
        """Test that non-Workday URLs are not recognized."""
        assert not _is_workday_url("https://auth.example.org/sso")

    def test_invalid_url(self) -> None:
        """Test that invalid URLs return False."""
        assert not _is_workday_url("not-a-url")

    def test_empty_url(self) -> None:
        """Test that empty URLs return False."""
        assert not _is_workday_url("")


class TestBadCredentialsError:
    """Test BadCredentialsError exception."""

    def test_is_exception(self) -> None:
        """Test BadCredentialsError can be raised."""
        with pytest.raises(BadCredentialsError):
            raise BadCredentialsError("Wrong password")


class TestRaiseHelpers:
    """Test raise helper functions."""

    def test_raise_bad_credentials(self) -> None:
        """Test _raise_bad_credentials raises BadCredentialsError."""
        with pytest.raises(BadCredentialsError, match="Wrong username or password"):
            _raise_bad_credentials()

    def test_raise_auth_error(self) -> None:
        """Test _raise_auth_error raises AuthenticationError."""
        with pytest.raises(
            AuthenticationError,
            match=r"SSO login failed\. Current URL: http://test\.com",
        ):
            _raise_auth_error("http://test.com")


class TestProcessLoginRaceResult:
    """Test _process_login_race_result function."""

    @pytest.mark.asyncio
    async def test_login_success(self) -> None:
        """Test processing successful login result."""
        task = AsyncMock()
        task.result.return_value = "success"
        done = {task}
        result = _process_login_race_result(done, "https://wd5.myworkday.com/example")
        assert result is True

    @pytest.mark.asyncio
    async def test_login_failure(self) -> None:
        """Test processing failed login (bad credentials)."""
        task = MagicMock()
        task.result.return_value = "failure"
        done = {task}
        with pytest.raises(BadCredentialsError):
            _process_login_race_result(done, "https://auth.example.org/sso")

    @pytest.mark.asyncio
    async def test_login_race_result_already_on_workday(self) -> None:
        """Test when URL is already on Workday (fallback check)."""
        task = AsyncMock()
        task.result.side_effect = Exception("Task failed")
        done = {task}
        result = _process_login_race_result(done, "https://wd5.myworkday.com/example")
        assert result is True

    @pytest.mark.asyncio
    async def test_login_race_result_not_on_workday(self) -> None:
        """Test when URL is not on Workday and tasks failed."""
        task = MagicMock()
        task.result.side_effect = Exception("Task failed")
        done = {task}
        with pytest.raises(AuthenticationError):
            _process_login_race_result(done, "https://auth.example.org/sso")


class TestAuthenticate:
    """Test authenticate function."""

    @pytest.fixture
    def mock_page(self) -> MagicMock:
        """Create a mock Playwright page."""
        page = MagicMock()
        page.goto = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.get_by_role = MagicMock()
        return page

    @pytest.fixture
    def config(self) -> WorkdayConfig:
        """Create a Workday config."""
        return WorkdayConfig(
            enabled=True, url="https://wd5.myworkday.com/example", auth="sso"
        )

    @pytest.fixture
    def console(self) -> Console:
        """Create a Rich console."""
        return Console()

    @pytest.mark.asyncio
    async def test_authenticate_with_kerberos_success(
        self, mock_page: MagicMock, config: WorkdayConfig, console: Console
    ) -> None:
        """Test authentication when Kerberos succeeds (no SSO form)."""
        # Simulate Kerberos success - no SSO form appears
        mock_page.url = "https://wd5.myworkday.com/example/d/home.htmld"
        login_form = MagicMock()
        login_form.wait_for = AsyncMock(side_effect=Exception("Timeout - no SSO form"))
        mock_page.get_by_role.return_value = login_form

        await authenticate(mock_page, config, console)

        # Should have navigated to URL with domcontentloaded
        # (for fast SSO redirect detection)
        mock_page.goto.assert_called_once_with(
            "https://wd5.myworkday.com/example", wait_until="domcontentloaded"
        )
        # Should have waited for page load
        mock_page.wait_for_load_state.assert_called()

    @pytest.mark.asyncio
    async def test_authenticate_sso_form_bad_credentials(
        self, mock_page: MagicMock, config: WorkdayConfig, console: Console
    ) -> None:
        """Test authentication fails after MAX_LOGIN_RETRIES bad credential attempts."""
        # Simulate SSO form appearing (not on Workday URL)
        mock_page.url = "https://auth.example.org/sso"
        mock_page.wait_for_url = AsyncMock(side_effect=Exception("Not on Workday"))

        login_form = MagicMock()
        login_form.wait_for = AsyncMock()  # SSO form is visible
        login_form.fill = AsyncMock()
        mock_page.get_by_role.return_value = login_form

        # Mock password field and button
        password_field = MagicMock()
        password_field.fill = AsyncMock()
        login_button = MagicMock()
        login_button.click = AsyncMock()

        def get_by_role_handler(role: str, **kwargs: str) -> MagicMock:
            name = kwargs.get("name")
            if role == "textbox" and name == "Username":
                return login_form
            if role == "textbox" and name == "Password":
                return password_field
            if role == "button" and name == "Log in to SSO":
                return login_button
            return MagicMock()

        mock_page.get_by_role.side_effect = get_by_role_handler

        # Mock credential prompt to return credentials
        with patch(
            "iptax.workday.auth.prompt_credentials_async",
            new_callable=AsyncMock,
            return_value=("testuser", "wrongpass"),
        ):
            # After login, SSO form reappears (bad credentials)
            mock_page.wait_for_url = AsyncMock(side_effect=Exception("Still on SSO"))

            with pytest.raises(AuthenticationError) as exc_info:
                await authenticate(mock_page, config, console)

            assert f"{MAX_LOGIN_RETRIES} attempts" in str(exc_info.value)


class TestAsyncHelpers:
    """Test async helper functions."""

    @pytest.fixture
    def mock_page(self) -> MagicMock:
        """Create a mock Playwright page."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_wait_for_workday_redirect(self, mock_page: MagicMock) -> None:
        """Test waiting for Workday redirect."""
        mock_page.wait_for_url = AsyncMock()
        result = await _wait_for_workday_redirect(mock_page)
        assert result == "success"
        mock_page.wait_for_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_login_form_reappear(self, mock_page: MagicMock) -> None:
        """Test waiting for login form to reappear."""
        username_field = MagicMock()
        username_field.wait_for = AsyncMock()
        mock_page.get_by_role.return_value = username_field
        result = await _wait_for_login_form_reappear(mock_page)
        assert result == "failure"
        username_field.wait_for.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_credentials_once_success(self, mock_page: MagicMock) -> None:
        """Test successful credential submission."""
        login_form = MagicMock()
        login_form.fill = AsyncMock()
        password_field = MagicMock()
        password_field.fill = AsyncMock()
        login_button = MagicMock()
        login_button.click = AsyncMock()

        mock_page.get_by_role = MagicMock(
            side_effect=lambda role, **kwargs: {
                ("textbox", "Password"): password_field,
                ("button", "Log in to SSO"): login_button,
            }.get((role, kwargs.get("name")), MagicMock())
        )
        mock_page.url = "https://wd5.myworkday.com/example"
        mock_page.wait_for_url = AsyncMock()

        await _submit_credentials_once(mock_page, login_form, "user", "pass")
        login_form.fill.assert_called_once_with("user")
        password_field.fill.assert_called_once_with("pass")
        login_button.click.assert_called_once()


class TestNavigateToHome:
    """Test navigate_to_home function."""

    @pytest.fixture
    def mock_page(self) -> MagicMock:
        """Create a mock Playwright page."""
        page = MagicMock()
        page.goto = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        return page

    @pytest.fixture
    def config(self) -> WorkdayConfig:
        """Create a Workday config."""
        return WorkdayConfig(
            enabled=True, url="https://wd5.myworkday.com/example", auth="sso"
        )

    @pytest.mark.asyncio
    async def test_navigate_to_home(
        self, mock_page: MagicMock, config: WorkdayConfig
    ) -> None:
        """Test navigation to home page."""
        await navigate_to_home(mock_page, config)

        # Should navigate to home.htmld
        mock_page.goto.assert_called_once_with(
            "https://wd5.myworkday.com/example/d/home.htmld",
            wait_until="domcontentloaded",
        )
        # Should wait for SPA initialization
        mock_page.wait_for_timeout.assert_called_once_with(3000)

    @pytest.mark.asyncio
    async def test_navigate_to_home_strips_trailing_slash(
        self, mock_page: MagicMock
    ) -> None:
        """Test that trailing slash is handled correctly."""
        config = WorkdayConfig(
            enabled=True, url="https://wd5.myworkday.com/example/", auth="sso"
        )
        await navigate_to_home(mock_page, config)

        # Should strip trailing slash before adding /d/home.htmld
        mock_page.goto.assert_called_once_with(
            "https://wd5.myworkday.com/example/d/home.htmld",
            wait_until="domcontentloaded",
        )
