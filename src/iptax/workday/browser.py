"""Browser setup and configuration for Workday automation."""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from typing import TYPE_CHECKING

import yaml
from playwright.async_api import ConsoleMessage, Request, Response

from iptax.utils.env import get_cache_dir

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TextIO

    from playwright.async_api import Page

    from iptax.models import WorkdayConfig

# HTTP status codes
HTTP_OK = 200
HTTP_UNAUTHORIZED = 401

# Viewport size for desktop layout (720p - smaller for faster rendering)
DESKTOP_VIEWPORT = {"width": 1280, "height": 720}

# Global timeout settings (milliseconds)
DEFAULT_TIMEOUT = 30000  # 30 seconds for most operations
ELEMENT_TIMEOUT = 10000  # 10 seconds for element visibility
SSO_LOGIN_TIMEOUT = 15000  # 15 seconds for SSO login (includes success page delay)

# Workday API endpoint patterns
CALENDAR_ENTRIES_API_PATTERN = "/rel-task/2997$9444.htmld"

logger = logging.getLogger(__name__)


def _build_firefox_prefs(config: WorkdayConfig) -> dict[str, str | bool | float]:
    """Build Firefox preferences for authentication.

    Sets Kerberos/SPNEGO prefs based on auth method:
    - "sso+kerberos": Enable SPNEGO for trusted URIs
    - "sso": Explicitly disable SPNEGO to force login form

    Args:
        config: Workday configuration

    Returns:
        Dict of Firefox preferences
    """
    firefox_prefs: dict[str, str | bool | float] = {}

    if config.auth == "sso+kerberos" and config.trusted_uris:
        # Enable Kerberos/SPNEGO for specified URIs
        uris = ",".join(config.trusted_uris)
        firefox_prefs["network.negotiate-auth.trusted-uris"] = uris
        firefox_prefs["network.negotiate-auth.delegation-uris"] = uris
        logger.info("Firefox SPNEGO enabled for URIs: %s", uris)
    else:
        # Explicitly disable SPNEGO by setting trusted URIs to empty
        # This prevents Firefox from auto-negotiating with Kerberos tickets
        firefox_prefs["network.negotiate-auth.trusted-uris"] = ""
        firefox_prefs["network.negotiate-auth.delegation-uris"] = ""
        logger.info("Firefox SPNEGO disabled - using SSO login form")

    return firefox_prefs


def setup_profile_directory() -> str:
    """Set up a fresh Firefox profile directory.

    Returns:
        Path to the profile directory
    """
    user_data_dir = get_cache_dir() / "firefox-profile"
    if user_data_dir.exists():
        logger.info("Removing old Firefox profile: %s", user_data_dir)
        shutil.rmtree(user_data_dir)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Created fresh Firefox profile at: %s", user_data_dir)
    return str(user_data_dir)


def setup_browser_logging(page: Page) -> TextIO:
    """Set up browser console and error logging.

    Args:
        page: Playwright page object

    Returns:
        Log file handle (caller must close it)
    """
    browser_log_path = get_cache_dir() / "browser-devconsole.log"
    browser_log_file = browser_log_path.open("w", encoding="utf-8")
    logger.info("Browser console logs: %s", browser_log_path)

    def _make_console_logger(log_file: TextIO) -> Callable[[ConsoleMessage], None]:
        def _log_console(msg: ConsoleMessage) -> None:
            log_file.write(f"[CONSOLE:{msg.type}] {msg.text}\n")
            log_file.flush()

        return _log_console

    def _make_page_error_logger(log_file: TextIO) -> Callable[[object], None]:
        def _log_page_error(err: object) -> None:
            log_file.write(f"[PAGE ERROR] {err}\n")
            log_file.flush()
            # Log as warning since these are Workday's JS errors, not our code
            logger.warning("Browser page error (Workday JS): %s", err)

        return _log_page_error

    def _make_response_logger(log_file: TextIO) -> Callable[[Response], None]:
        def _log_response(response: Response) -> None:
            url = response.url
            status = response.status
            headers = response.headers

            # Write all responses to browser log file
            log_file.write(f"[RESPONSE] {status} {url}\n")
            log_file.flush()

            # Log auth-related responses to main logger
            if status == HTTP_UNAUTHORIZED or "www-authenticate" in headers:
                logger.info(
                    "AUTH RESPONSE: %s %s - WWW-Authenticate: %s",
                    status,
                    url,
                    headers.get("www-authenticate", "NONE"),
                )
            elif "auth" in url.lower() or "sso" in url.lower():
                logger.info("SSO RESPONSE: %s %s", status, url)

        return _log_response

    def _make_request_logger(log_file: TextIO) -> Callable[[Request], None]:
        def _log_request(request: Request) -> None:
            url = request.url
            headers = request.headers

            # Write all requests to browser log file
            log_file.write(f"[REQUEST] {request.method} {url}\n")
            log_file.flush()

            # Log auth-related requests to main logger
            if "authorization" in headers:
                auth_header = headers["authorization"]
                auth_type = (
                    auth_header.split()[0] if " " in auth_header else auth_header[:20]
                )
                logger.info(
                    "AUTH REQUEST: %s - Authorization: %s...",
                    url,
                    auth_type,
                )
            elif "auth" in url.lower() or "sso" in url.lower():
                logger.debug("SSO REQUEST: %s", url)

        return _log_request

    page.on("console", _make_console_logger(browser_log_file))
    page.on("pageerror", _make_page_error_logger(browser_log_file))
    page.on("response", _make_response_logger(browser_log_file))
    page.on("request", _make_request_logger(browser_log_file))

    return browser_log_file


async def dump_debug_snapshot(page: Page, context: str, error: Exception) -> str:
    """Dump accessibility snapshot and screenshot for debugging.

    Args:
        page: Playwright page object
        context: Context string for the filename (e.g., "navigation_failed")
        error: The exception that occurred

    Returns:
        Path to the snapshot file
    """
    logger.info("Dumping debug snapshot for context: %s", context)
    snapshot_dir = get_cache_dir() / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Use timestamp in filename only if IPTAX_WORKDAY_DUMP_TS is set
    use_timestamp = os.environ.get("IPTAX_WORKDAY_DUMP_TS", "").lower() in (
        "1",
        "true",
        "yes",
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if use_timestamp:
        snapshot_path = snapshot_dir / f"{context}_{timestamp}.yaml"
        screenshot_path = snapshot_dir / f"{context}_{timestamp}.png"
    else:
        # Overwrite same file each time for easier debugging
        snapshot_path = snapshot_dir / f"{context}.yaml"
        screenshot_path = snapshot_dir / f"{context}.png"

    # Get page info
    current_url = page.url
    logger.debug("Current URL: %s", current_url)
    try:
        title = await page.title()
    except Exception:
        title = "unknown"

    # Get accessibility snapshot
    logger.debug("Getting accessibility snapshot...")
    try:
        a11y_snapshot = await page.accessibility.snapshot()
    except Exception as e:
        logger.warning("Failed to get accessibility snapshot: %s", e)
        a11y_snapshot = {"error": str(e)}

    # Build the debug data structure
    debug_data = {
        "context": context,
        "timestamp": timestamp,
        "url": current_url,
        "title": title,
        "error": {
            "type": type(error).__name__,
            "message": str(error),
        },
        "accessibility_snapshot": a11y_snapshot,
    }

    # Write YAML snapshot
    with snapshot_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(debug_data, f, default_flow_style=False, allow_unicode=True)

    logger.info("Debug snapshot saved to: %s", snapshot_path)

    # Take screenshot
    try:
        await page.screenshot(path=str(screenshot_path), full_page=True)
        logger.info("Screenshot saved to: %s", screenshot_path)
    except Exception as e:
        logger.warning("Failed to save screenshot: %s", e)

    return str(snapshot_path)
