"""Authentication functions for Workday SSO."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from urllib.parse import urlparse

from playwright.async_api import Locator, Page
from rich.console import Console

from iptax.models import WorkdayConfig
from iptax.workday.browser import SSO_LOGIN_TIMEOUT
from iptax.workday.models import AuthenticationError
from iptax.workday.prompts import prompt_credentials_async

logger = logging.getLogger(__name__)

# Signals for login result detection
LOGIN_SUCCESS = "success"
LOGIN_FAILURE = "failure"
KERBEROS_SUCCESS = "kerberos"
SSO_FORM_DETECTED = "sso_form"

# Maximum retry attempts for wrong credentials
MAX_LOGIN_RETRIES = 3

# Type alias for progress control callbacks
ProgressCallback = Callable[[], None] | None


def _is_workday_url(url: str) -> bool:
    """Check if URL is on Workday domain (not SSO)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    else:
        return "myworkday.com" in parsed.netloc


async def _wait_for_workday_url(page: Page) -> str:
    """Wait for URL to be on Workday domain (for Kerberos detection)."""
    await page.wait_for_url("**/myworkday.com/**", timeout=5000)
    return KERBEROS_SUCCESS


async def _wait_for_sso_form(login_form: Locator) -> str:
    """Wait for SSO login form to be visible."""
    await login_form.wait_for(timeout=5000, state="visible")
    return SSO_FORM_DETECTED


async def _race_auth_detection(page: Page, login_form: Locator) -> str:
    """Race between Kerberos success and SSO form detection.

    After initial navigation, we need to detect whether:
    1. Kerberos authentication worked (we're on Workday)
    2. SSO login form appeared (need to enter credentials)

    This race avoids waiting 5s timeout when Kerberos works.
    Note: wait_for_url checks current URL first, so if we're already
    on Workday (Kerberos worked), it returns immediately.

    Args:
        page: Playwright page object
        login_form: The username input field locator

    Returns:
        KERBEROS_SUCCESS if we're on Workday
        SSO_FORM_DETECTED if login form appeared
    """
    kerberos_task = asyncio.create_task(_wait_for_workday_url(page))
    sso_task = asyncio.create_task(_wait_for_sso_form(login_form))

    try:
        done, pending = await asyncio.wait(
            [kerberos_task, sso_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks and consume any exceptions
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

        # First, retrieve all task results to avoid "exception never retrieved"
        # warning. Both tasks can end up in done if they finish quickly (common
        # with mocks).
        winning_result = None
        for task in done:
            try:
                result = task.result()
                if winning_result is None:
                    winning_result = result
            except Exception as e:
                # Expected: one task wins, the other times out. This is normal.
                logger.debug("Auth detection race loser (expected): %s", e)

        if winning_result is not None:
            return winning_result

        # If both failed, check current state
        if _is_workday_url(page.url):
            return KERBEROS_SUCCESS

    except Exception as e:
        logger.warning("Error during auth detection: %s", e)

    # Default to SSO form - will timeout if not present
    return SSO_FORM_DETECTED


async def _wait_for_workday_redirect(page: Page) -> str:
    """Wait for successful redirect to Workday."""
    await page.wait_for_url("**/myworkday.com/**", timeout=SSO_LOGIN_TIMEOUT)
    return LOGIN_SUCCESS


async def _wait_for_login_form_reappear(page: Page) -> str:
    """Wait for login form to reappear (indicates wrong credentials)."""
    # After submit, wait for username field to be visible again
    # This happens when SSO reloads the form due to bad credentials
    username_field = page.get_by_role("textbox", name="Username")
    await username_field.wait_for(timeout=SSO_LOGIN_TIMEOUT, state="visible")
    # Form reappeared - bad credentials
    return LOGIN_FAILURE


class BadCredentialsError(Exception):
    """Raised when SSO login fails due to wrong credentials (retriable)."""

    pass


async def _submit_credentials_once(
    page: Page,
    login_form: Locator,
    username: str,
    password: str,
) -> None:
    """Submit credentials to the SSO login form (single attempt).

    Uses a race condition to detect either:
    - Success: redirect to Workday (may take ~10s with success page)
    - Failure: login form reappears (fast, ~2s)

    Args:
        page: Playwright page object
        login_form: The username input field locator
        username: Username to fill
        password: Password to fill

    Raises:
        BadCredentialsError: If credentials are wrong (retriable)
        AuthenticationError: If login fails for other reasons
    """
    # Fill and submit the form
    await login_form.fill(username)
    await page.get_by_role("textbox", name="Password").fill(password)
    await page.get_by_role("button", name="Log in to SSO").click()

    # Race: wait for either Workday redirect OR login form reappearing
    workday_task = asyncio.create_task(_wait_for_workday_redirect(page))
    error_task = asyncio.create_task(_wait_for_login_form_reappear(page))

    try:
        done, pending = await asyncio.wait(
            [workday_task, error_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks and consume any exceptions
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

        # Process completed tasks
        result = _process_login_race_result(done, page.url)
        if result is not None:
            return  # Success

    except (AuthenticationError, BadCredentialsError):
        raise
    except Exception as e:
        logger.exception("Unexpected error during SSO login")
        raise AuthenticationError(f"SSO login error: {e}") from e


def _raise_bad_credentials() -> None:
    """Raise BadCredentialsError for wrong credentials."""
    raise BadCredentialsError("Wrong username or password")


def _raise_auth_error(current_url: str) -> None:
    """Raise AuthenticationError for login failure."""
    raise AuthenticationError(f"SSO login failed. Current URL: {current_url}")


def _process_login_race_result(
    done: set[asyncio.Task[str]], current_url: str
) -> bool | None:
    """Process the result of login race condition.

    Args:
        done: Set of completed tasks
        current_url: Current page URL

    Returns:
        True if login succeeded, None if failed

    Raises:
        BadCredentialsError: If credentials are wrong
        AuthenticationError: If login failed for other reasons
    """
    # First, retrieve ALL task results to avoid "exception never retrieved"
    # warning. Both tasks can end up in done if they finish quickly (common
    # with mocks). We must retrieve all exceptions before raising any.
    results: list[str] = []
    for task in done:
        try:
            results.append(task.result())
        except (AuthenticationError, BadCredentialsError):
            raise
        except Exception as e:
            # Expected: login race optimization - we race "wait for redirect" vs
            # "wait for form reappear". The loser always times out. This is normal.
            logger.debug("Race condition loser timeout (expected): %s", e)

    # Now process the collected results
    for result in results:
        if result == LOGIN_SUCCESS:
            logger.info("SSO login successful - redirected to Workday")
            return True
        if result == LOGIN_FAILURE:
            logger.warning("SSO login form reappeared - bad credentials")
            _raise_bad_credentials()

    # If we get here, both tasks failed unexpectedly
    if _is_workday_url(current_url):
        return True

    _raise_auth_error(current_url)
    return None  # Unreachable, but satisfies type checker


async def authenticate(
    page: Page,
    config: WorkdayConfig,
    console: Console,
    stop_progress: ProgressCallback = None,
    resume_progress: ProgressCallback = None,
) -> None:
    """Navigate to Workday and handle SSO authentication.

    Args:
        page: Playwright page object
        config: Workday configuration
        console: Rich console for user feedback
        stop_progress: Optional callback to stop progress bar before credential prompt
        resume_progress: Optional callback to resume progress bar after credentials

    Raises:
        AuthenticationError: If SSO authentication fails
    """
    url = config.url
    # URL is guaranteed to be set by Pydantic validation when enabled=True
    assert url is not None, "URL must be set when Workday is enabled"

    logger.info("Navigating to %s", url)
    await page.goto(url, wait_until="domcontentloaded")
    logger.debug("Initial navigation complete, current URL: %s", page.url)

    # Race between Kerberos success (Workday element visible) and SSO form appearing.
    # This avoids waiting 5s timeout when Kerberos works.
    login_form = page.get_by_role("textbox", name="Username")
    auth_result = await _race_auth_detection(page, login_form)

    if auth_result == SSO_FORM_DETECTED:
        logger.info("SSO login form detected - Kerberos auth did not work")

        # SSO form detected - need credentials
        # Stop progress bar before prompting for credentials
        if stop_progress is not None:
            stop_progress()

        if config.auth == "sso+kerberos":
            console.print(
                "[yellow]⚠ Kerberos authentication failed. "
                "SSO login required.[/yellow]"
            )

        # Login with retries for bad credentials
        for attempt in range(MAX_LOGIN_RETRIES):
            username, password = await prompt_credentials_async()
            try:
                await _submit_credentials_once(page, login_form, username, password)
                break  # Success!
            except BadCredentialsError:
                if attempt < MAX_LOGIN_RETRIES - 1:
                    console.print(
                        "[red]✗ Wrong username or password. " "Please try again.[/red]"
                    )
                    # Re-find login form (page reloaded)
                    login_form = page.get_by_role("textbox", name="Username")
                    await login_form.wait_for(
                        timeout=SSO_LOGIN_TIMEOUT, state="visible"
                    )
                else:
                    raise AuthenticationError(
                        f"Login failed after {MAX_LOGIN_RETRIES} attempts"
                    ) from None

        # Resume progress bar after successful form submission
        if resume_progress is not None:
            resume_progress()
    else:
        # Kerberos worked
        logger.info("Kerberos authentication succeeded - on Workday page")

    logger.info("SSO authentication completed")

    # Wait for Workday to fully load (use domcontentloaded, not networkidle
    # because Workday has constant background polling that never settles)
    await page.wait_for_load_state("domcontentloaded")


async def navigate_to_home(page: Page, config: WorkdayConfig) -> None:
    """Navigate to Workday home page after authentication.

    Args:
        page: Playwright page object
        config: Workday configuration
    """
    # Navigate to home page explicitly (needed after SSO redirect)
    # URL is guaranteed to be set by Pydantic validation when enabled=True
    base_url = config.url
    assert base_url is not None, "URL must be set when Workday is enabled"
    home_url = base_url.rstrip("/") + "/d/home.htmld"
    logger.info("Navigating to home: %s", home_url)
    await page.goto(home_url, wait_until="domcontentloaded")

    # Wait a bit for the SPA to initialize
    await page.wait_for_timeout(3000)
