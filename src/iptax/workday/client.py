"""Workday client for fetching work hours."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

import questionary
from playwright.async_api import Page, ViewportSize, async_playwright
from rich.console import Console

from iptax.models import WorkdayConfig, WorkHours
from iptax.workday.auth import authenticate, navigate_to_home
from iptax.workday.browser import (
    DEFAULT_TIMEOUT,
    DESKTOP_VIEWPORT,
    _build_firefox_prefs,
    dump_debug_snapshot,
    setup_browser_logging,
    setup_profile_directory,
)
from iptax.workday.driver import PlaywrightDriver
from iptax.workday.models import AuthenticationError, WorkdayError
from iptax.workday.prompts import ProgressController, prompt_manual_work_hours
from iptax.workday.scraping import extract_work_hours, navigate_to_time_page

logger = logging.getLogger(__name__)


class WorkdayClient:
    """Client for fetching work hours from Workday."""

    def __init__(self, config: WorkdayConfig) -> None:
        """Initialize WorkdayClient.

        Args:
            config: Workday configuration
        """
        self.config = config
        self.console = Console()
        self._progress_ctrl: ProgressController | None = None

    async def fetch_work_hours(
        self, start_date: date, end_date: date, headless: bool = True
    ) -> WorkHours:
        """Fetch work hours from Workday for date range.

        Authentication flow:
        1. Launch Playwright with persistent context for SPNEGO (if sso+kerberos)
        2. Navigate to Workday URL and handle SSO
        3. Navigate to Time page and extract work hours

        Args:
            start_date: Start of the reporting period
            end_date: End of the reporting period
            headless: Whether to run browser in headless mode (default: True)

        Returns:
            WorkHours with data from Workday

        Raises:
            AuthenticationError: If SSO authentication fails
            WorkdayError: If navigation or data extraction fails
        """
        # Set up fresh Firefox profile for SPNEGO
        user_data_dir = setup_profile_directory()
        firefox_prefs = _build_firefox_prefs(self.config)

        # Calculate progress steps:
        # 5 pre-steps (navigate, SSO, home, time button, time page)
        # + weeks_count (one per week processed)
        # + 1 final step ("Work hours collected")
        weeks_count = self._calculate_weeks_count(start_date, end_date)
        total_steps = 6 + weeks_count

        with ProgressController(self.console) as progress:
            self._progress_ctrl = progress
            progress.create(total_steps, "Connecting to Workday...")

            async with async_playwright() as p:
                logger.info("Launching Firefox for Kerberos/SPNEGO authentication")

                viewport_size: ViewportSize = {
                    "width": DESKTOP_VIEWPORT["width"],
                    "height": DESKTOP_VIEWPORT["height"],
                }
                context = await p.firefox.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=headless,
                    firefox_user_prefs=firefox_prefs or None,
                    viewport=viewport_size,
                    timeout=DEFAULT_TIMEOUT,
                )
                page = context.pages[0] if context.pages else await context.new_page()
                page.set_default_timeout(DEFAULT_TIMEOUT)

                browser_log_file = setup_browser_logging(page)
                logger.info("Starting Workday navigation to: %s", self.config.url)

                try:
                    await self._navigate_and_authenticate(page)
                    await self._navigate_to_time_page(page, start_date)
                    return await self._extract_work_hours(page, start_date, end_date)
                except Exception as e:
                    logger.exception("Workday automation failed")
                    snapshot_path = await dump_debug_snapshot(page, "workday_error", e)
                    logger.info("Debug snapshot saved to: %s", snapshot_path)
                    self.console.print(
                        f"[dim]Debug snapshot saved: {snapshot_path}[/dim]"
                    )
                    raise
                finally:
                    browser_log_file.close()
                    await context.close()

    def _calculate_weeks_count(self, start_date: date, end_date: date) -> int:
        """Calculate the number of weeks to process."""
        # Each week is ~7 days, calculate how many weeks span the date range
        days = (end_date - start_date).days + 1
        return (days + 6) // 7  # Round up

    def _advance_progress(self, description: str) -> None:
        """Advance the progress bar by one step."""
        if self._progress_ctrl is not None:
            self._progress_ctrl.advance(description)

    async def _navigate_and_authenticate(self, page: Page) -> None:
        """Navigate to Workday and handle SSO authentication.

        Args:
            page: Playwright page object

        Raises:
            AuthenticationError: If SSO authentication fails
        """
        url = self.config.url
        if url is None:
            raise ValueError("Workday URL is not configured")
        self._advance_progress("Connecting to Workday...")

        await authenticate(
            page,
            self.config,
            self.console,
            stop_progress=self._progress_ctrl.stop if self._progress_ctrl else None,
            resume_progress=self._progress_ctrl.resume if self._progress_ctrl else None,
        )

        self._advance_progress("SSO authentication completed")

        # Navigate to home page explicitly (needed after SSO redirect)
        await navigate_to_home(page, self.config)
        self._advance_progress("Workday home page loaded")

    async def _navigate_to_time_page(self, page: Page, target_date: date) -> None:
        """Navigate from Workday home to the Time entry page for a specific week.

        Args:
            page: Playwright page object
            target_date: The target date to navigate to
        """
        self._advance_progress("Looking for Time button...")
        driver = PlaywrightDriver(page)
        await navigate_to_time_page(driver, target_date)
        self._advance_progress("Navigated to time entry page")

    async def _extract_work_hours(
        self, page: Page, start_date: date, end_date: date
    ) -> WorkHours:
        """Extract work hours from the Time page for the given date range.

        Args:
            page: Playwright page object
            start_date: Start of the reporting period
            end_date: End of the reporting period

        Returns:
            WorkHours with aggregated data
        """
        # Pass progress callback to update for each week
        driver = PlaywrightDriver(page)
        result = await extract_work_hours(
            driver, start_date, end_date, progress_callback=self._advance_progress
        )

        self._advance_progress("Work hours collected")

        return result

    def _display_error_telemetry(self, error: Exception) -> None:
        """Display diagnostic information on authentication failure.

        Args:
            error: The exception that occurred
        """
        questionary.print("❌ Workday authentication failed", style="bold red")
        questionary.print("")
        questionary.print("Diagnostic info:", style="bold")
        questionary.print(f"  - Workday URL: {self.config.url}")
        questionary.print(f"  - Auth method: {self.config.auth}")
        questionary.print(f"  - Error: {error}")
        questionary.print("")

    def get_work_hours(
        self,
        start_date: date,
        end_date: date,
        interactive: bool = True,
        headless: bool = True,
    ) -> WorkHours:
        """Get work hours, with fallback to manual input on failure.

        On auth failure:
        1. Display telemetry/error info
        2. Ask user: [R]etry / [M]anual input
        3. If manual: prompt for working_days and total_hours

        Args:
            start_date: Start of the reporting period
            end_date: End of the reporting period
            interactive: Whether to prompt for manual input on failure
            headless: Whether to run browser in headless mode (default: True)

        Returns:
            WorkHours with data from Workday or manual input

        Raises:
            WorkdayError: If Workday is disabled and not interactive
            NotImplementedError: If automation not implemented and not interactive
            AuthenticationError: If authentication fails and not interactive
        """

        if not self.config.enabled:
            if interactive:
                return prompt_manual_work_hours(start_date, end_date)
            raise WorkdayError("Workday integration is disabled")

        # Try fetching from Workday
        try:
            return asyncio.run(
                self.fetch_work_hours(start_date, end_date, headless=headless)
            )
        except NotImplementedError:
            if interactive:
                questionary.print(
                    "⚠ Workday automation not yet implemented. "
                    "Falling back to manual input.",
                    style="yellow",
                )
                questionary.print("")
                return prompt_manual_work_hours(start_date, end_date)
            raise
        except Exception as e:
            if interactive:
                self._display_error_telemetry(e)
                choice = questionary.select(
                    "What would you like to do?",
                    choices=[
                        questionary.Choice("Retry", value="retry"),
                        questionary.Choice(
                            "Input working hours manually", value="manual"
                        ),
                        questionary.Choice("Exit", value="exit"),
                    ],
                    default="manual",
                ).unsafe_ask()
                if choice == "retry":
                    return self.get_work_hours(
                        start_date, end_date, interactive, headless
                    )
                if choice == "exit":
                    raise AuthenticationError(str(e)) from e
                return prompt_manual_work_hours(start_date, end_date)
            raise AuthenticationError(str(e)) from e
