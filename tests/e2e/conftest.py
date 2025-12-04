"""Pytest configuration for e2e tests."""

import asyncio
import logging
import shutil
import socket
import tempfile
import threading
import time
import urllib.request
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from werkzeug.serving import make_server

from iptax.models import WorkdayConfig
from iptax.utils.env import get_cache_dir
from iptax.utils.logging import setup_logging
from tests.e2e.mock_servers.app import create_app

# Setup logging for e2e tests
cache_dir = get_cache_dir()
cache_dir.mkdir(parents=True, exist_ok=True)
log_file = cache_dir / "e2e-tests.log"
setup_logging(log_file, extra_handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)
logger.info("E2E tests starting, logs at: %s", log_file)

# Domain names for mock servers
SSO_DOMAIN = "sso.localhost"
WORKDAY_DOMAIN = "myworkday.com.localhost"


def get_free_port() -> int:
    """Get a free port by binding to port 0 and reading the assigned port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Bind to all interfaces for test server - supports different
        # loopback IPs (noqa: S104)
        s.bind(("0.0.0.0", 0))  # noqa: S104
        s.listen(1)
        return s.getsockname()[1]


class MockServerThread(threading.Thread):
    """Thread that runs the mock Flask server."""

    def __init__(self, app, host: str, port: int) -> None:
        super().__init__(daemon=True)
        self.app = app
        self.server = make_server(host, port, app, threaded=True)
        self.host = host
        self.port = port

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()

    @property
    def sso_url(self) -> str:
        """URL for SSO server (different domain)."""
        return f"http://{SSO_DOMAIN}:{self.port}"

    @property
    def workday_url(self) -> str:
        """URL for Workday server (myworkday.com domain)."""
        return f"http://{WORKDAY_DOMAIN}:{self.port}"


@pytest.fixture
def unique_firefox_profile() -> Generator[str, None, None]:
    """Create a unique Firefox profile directory for parallel test execution.

    Uses tempfile to create a truly unique directory per test/worker.
    Automatically cleans up the profile after the test.
    """
    # Create a unique temp directory for this test's Firefox profile
    profile_dir = tempfile.mkdtemp(prefix="iptax-firefox-test-")
    logger.info("Created test Firefox profile: %s", profile_dir)

    # Patch the setup_profile_directory function to use our unique path
    # Must patch where it's imported (client.py), not where it's defined
    def mock_setup_profile() -> str:
        # Clean and recreate to ensure fresh state
        profile_path = Path(profile_dir)
        if profile_path.exists():
            shutil.rmtree(profile_path)
        profile_path.mkdir(parents=True, exist_ok=True)
        logger.info("Using unique Firefox profile at: %s", profile_dir)
        return profile_dir

    with patch("iptax.workday.client.setup_profile_directory", mock_setup_profile):
        yield profile_dir

    # Cleanup after test
    if Path(profile_dir).exists():
        shutil.rmtree(profile_dir)
        logger.info("Cleaned up test Firefox profile: %s", profile_dir)


@pytest.fixture(scope="session")
def mock_server() -> Generator[MockServerThread, None, None]:
    """Start mock SSO/Workday server for e2e testing.

    The server runs in a background thread and is shared across all tests
    (session scope). Each browser has its own cookie jar, so sessions
    don't conflict.

    Uses automatic port selection to avoid conflicts.
    """
    from datetime import date

    from tests.e2e.fixtures.calendar_data import (
        generate_full_work_week,
        generate_week_with_pto,
    )

    # Generate 2 weeks of calendar data for Nov 3-14, 2025
    # Week 1: Nov 3-7 (full work week)
    # Week 2: Nov 10-14 (with 1 PTO on Wednesday Nov 12)
    week1 = date(2025, 11, 3)
    week2 = date(2025, 11, 10)
    calendar_data = {
        **generate_full_work_week(week1),
        **generate_week_with_pto(week2, pto_days=[2]),  # Wednesday PTO
    }

    # Default test credentials
    credentials = {"testuser": "testpass"}

    port = get_free_port()

    app = create_app(
        calendar_data=calendar_data,
        credentials=credentials,
        sso_domain=SSO_DOMAIN,
        workday_domain=WORKDAY_DOMAIN,
        port=port,
    )

    # Bind to all interfaces - *.localhost may resolve to different IPs
    # per domain (noqa: S104). Examples: 127.0.1.1 (sso.localhost),
    # 127.0.2.1 (myworkday.com.localhost), ::1 (IPv6)
    server_thread = MockServerThread(app, "0.0.0.0", port)  # noqa: S104
    server_thread.start()

    # Wait for server to be ready
    for _ in range(50):  # 5 second timeout
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.1)

    yield server_thread

    server_thread.shutdown()


@pytest.fixture(scope="session")
def mock_workday_config(mock_server: MockServerThread) -> WorkdayConfig:
    """Create WorkdayConfig pointing to mock Workday server.

    The URL uses myworkday.com.localhost which:
    1. Resolves to 127.0.0.1 (localhost)
    2. Contains "myworkday.com" to pass _is_workday_url() check
    """
    return WorkdayConfig(
        enabled=True,
        url=mock_server.workday_url,
        auth="sso",  # Use SSO (not Kerberos) for mock
    )


def _playwright_exception_handler(
    loop: asyncio.AbstractEventLoop, context: dict
) -> None:
    """Custom exception handler to suppress Playwright timeout errors during cleanup.

    During test cleanup, Playwright may have pending operations that timeout
    when the browser closes. These are expected and shouldn't be logged as errors.
    """
    exception = context.get("exception")
    if exception is not None:
        # Suppress Playwright timeout errors during cleanup
        exception_str = str(exception)
        if "TimeoutError" in type(exception).__name__ or "Timeout" in exception_str:
            logger.debug(
                "Suppressed expected Playwright timeout during cleanup: %s", exception
            )
            return

    # For non-timeout exceptions, use the default handler
    loop.default_exception_handler(context)


@pytest.fixture(scope="session", autouse=True)
def suppress_playwright_cleanup_errors():
    """Install a custom exception handler to suppress Playwright cleanup errors.

    This prevents "Future exception was never retrieved" errors that occur when
    Playwright operations timeout during browser cleanup.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop during fixture setup - that's fine
        yield
        return

    original_handler = loop.get_exception_handler()
    loop.set_exception_handler(_playwright_exception_handler)

    yield

    # Restore original handler
    loop.set_exception_handler(original_handler)
