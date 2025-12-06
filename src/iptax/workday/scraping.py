"""Web scraping and navigation functions for Workday."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Coroutine
from datetime import date
from typing import Any

from iptax.models import WorkHours
from iptax.workday.browser import (
    CALENDAR_ENTRIES_API_PATTERN,
    ELEMENT_TIMEOUT,
    HTTP_OK,
)
from iptax.workday.models import CalendarEntriesCollector, NavigationError
from iptax.workday.protocols import (
    BrowserDriverProtocol,
    LocatorProtocol,
    ResponseProtocol,
)
from iptax.workday.utils import _parse_week_range, calculate_working_days

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressCallback = Callable[[str], None] | None


async def navigate_to_time_page(
    driver: BrowserDriverProtocol, target_date: date
) -> None:
    """Navigate from Workday home to the Time entry page for a specific week.

    Uses the "Select Week" option to jump directly to the target date,
    which is much faster than navigating week by week.

    Args:
        driver: Browser driver object
        target_date: The target date to navigate to
    """
    logger.info("Looking for Time button...")

    # Wait for the page to have the "Your Top Apps" section loaded
    # Try to find the Time button with different strategies
    time_button = driver.get_by_role("button", name="Time", exact=True)

    # Wait for the Time button
    try:
        await time_button.wait_for(state="visible")
    except Exception:
        # If button not found, the home page might not have loaded properly
        logger.warning("Time button not found on first attempt")

        # Try scrolling to find the button
        await driver.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await driver.wait_for_timeout(1000)

        # Try again with shorter timeout
        await time_button.wait_for(timeout=ELEMENT_TIMEOUT, state="visible")

    logger.info("Clicking Time button...")
    await time_button.click()

    # Wait for navigation to complete
    await driver.wait_for_load_state("domcontentloaded")
    await driver.wait_for_timeout(2000)

    # Use "Select Week" to jump directly to the target date
    # This is faster than clicking "This Week" and then navigating
    await select_week_via_modal(driver, target_date)

    logger.info("Navigated to time entry page")


async def select_week_via_modal(
    driver: BrowserDriverProtocol, target_date: date
) -> None:
    """Select a specific week using the Select Week modal.

    On the Time page (before entering calendar view), there's a "Select Week"
    link that opens a modal with date spinbuttons. This is much faster than
    navigating week by week.

    The modal has three spinbuttons: Month, Day, Year.

    Args:
        driver: Browser driver object
        target_date: The target date to navigate to
    """
    logger.info("Selecting week for %s...", target_date)

    # Click "Select Week" link (it's a link, not a button on this page)
    select_week_link = driver.get_by_role("link", name=re.compile(r"Select Week"))
    try:
        await select_week_link.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    except Exception:
        # Maybe it's visible as a button instead
        select_week_link = driver.get_by_role("button", name=re.compile(r"Select Week"))
        await select_week_link.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)

    logger.debug("Clicking 'Select Week'")
    await select_week_link.click()

    # Wait for modal to appear
    await driver.wait_for_timeout(1000)

    # The modal uses spinbuttons for Month, Day, Year
    month_input = driver.get_by_role("spinbutton", name="Month")
    day_input = driver.get_by_role("spinbutton", name="Day")
    year_input = driver.get_by_role("spinbutton", name="Year")

    await month_input.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)

    # Fill in the date values - spinbuttons need keyboard input
    month_str = str(target_date.month)
    day_str = str(target_date.day)
    year_str = str(target_date.year)

    logger.debug("Entering date: %s/%s/%s", month_str, day_str, year_str)

    # For spinbuttons, we need to:
    # 1. Click to focus
    # 2. Select all (Ctrl+A)
    # 3. Type the value

    await month_input.click()
    await driver.keyboard.press("Control+a")
    await driver.keyboard.type(month_str)

    await day_input.click()
    await driver.keyboard.press("Control+a")
    await driver.keyboard.type(day_str)

    await year_input.click()
    await driver.keyboard.press("Control+a")
    await driver.keyboard.type(year_str)

    await driver.wait_for_timeout(500)

    # Click OK button to confirm
    ok_button = driver.get_by_role("button", name="OK")
    await ok_button.click()

    # Wait for calendar to load
    await driver.wait_for_load_state("domcontentloaded")
    await driver.wait_for_timeout(2000)

    # Verify we're on the calendar page by checking for the week heading
    week_start, week_end = await get_current_week_range(driver)
    logger.info("Navigated to week: %s - %s", week_start, week_end)


async def navigate_previous_week(driver: BrowserDriverProtocol) -> None:
    """Navigate to the previous week.

    Waits until the week heading actually changes to confirm navigation.

    Args:
        driver: Browser driver object
    """
    # Get current week heading before clicking
    current_heading = await get_week_heading_text(driver)
    logger.debug("Current week heading before prev: %s", current_heading)

    prev_button = driver.get_by_role("button", name="Previous Week")
    await prev_button.click()

    # Wait until heading changes (confirming navigation completed)
    await wait_for_week_change(driver, current_heading)


async def navigate_next_week(driver: BrowserDriverProtocol) -> None:
    """Navigate to the next week.

    Waits until the week heading actually changes to confirm navigation.

    Args:
        driver: Browser driver object
    """
    # Get current week heading before clicking
    current_heading = await get_week_heading_text(driver)
    logger.debug("Current week heading before next: %s", current_heading)

    next_button = driver.get_by_role("button", name="Next Week")
    await next_button.click()

    # Wait until heading changes (confirming navigation completed)
    await wait_for_week_change(driver, current_heading)


async def get_week_heading_text(driver: BrowserDriverProtocol) -> str:
    """Get the current week heading text.

    Args:
        driver: Browser driver object

    Returns:
        Week heading text (e.g., "Nov 24 - 30, 2025")
    """
    week_heading = driver.get_by_role(
        "heading", name=re.compile(r"\w+ \d+.*\d{4}"), level=2
    )
    return await week_heading.text_content() or ""


async def wait_for_week_change(
    driver: BrowserDriverProtocol, old_heading: str, timeout: int = 5000
) -> None:
    """Wait until the week heading changes from the old value.

    Args:
        driver: Browser driver object
        old_heading: The heading text before navigation
        timeout: Maximum time to wait in milliseconds
    """
    week_heading = driver.get_by_role(
        "heading", name=re.compile(r"\w+ \d+.*\d{4}"), level=2
    )

    # Wait for heading text to be different from old value
    start_time = asyncio.get_event_loop().time()
    while True:
        current = await week_heading.text_content() or ""
        if current != old_heading:
            logger.debug("Week heading changed to: %s", current)
            # Give the Summary section time to update as well
            await driver.wait_for_timeout(500)
            return

        elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
        if elapsed >= timeout:
            logger.warning(
                "Timeout waiting for week change (still showing: %s)", current
            )
            return

        await driver.wait_for_timeout(100)


async def get_current_week_range(driver: BrowserDriverProtocol) -> tuple[date, date]:
    """Get the start and end dates of the currently displayed week.

    Parses the week heading like "Nov 24 - 30, 2025" or
    "Dec 30, 2024 - Jan 5, 2025".

    Args:
        driver: Browser driver object

    Returns:
        Tuple of (week_start, week_end) dates
    """
    # Find the heading with week range (e.g., "Nov 24 - 30, 2025")
    # This is a level 2 heading with the date range pattern
    week_heading = driver.get_by_role(
        "heading", name=re.compile(r"\w+ \d+.*\d{4}"), level=2
    )
    week_text = await week_heading.text_content()
    if week_text is None:
        raise NavigationError("Week heading has no text content")
    logger.debug("Found week heading: %s", week_text)

    return _parse_week_range(week_text.strip())


async def extract_work_hours(
    driver: BrowserDriverProtocol,
    start_date: date,
    end_date: date,
    progress_callback: ProgressCallback = None,
) -> WorkHours:
    """Extract work hours from the Time page for the given date range.

    Uses API response interception to collect per-day calendar entries,
    enabling accurate monthly totals without prorating.

    Args:
        driver: Browser driver object
        start_date: Start of the reporting period
        end_date: End of the reporting period
        progress_callback: Optional callback to report progress

    Returns:
        WorkHours with aggregated data and individual calendar entries
    """
    # Navigate to previous week first, so when we set up the response handler
    # and navigate back to the first week, we capture its API response
    logger.info("Navigating to previous week to prepare for data capture")
    await navigate_previous_week(driver)

    # Set up collector and response handler for calendar entries API
    collector = CalendarEntriesCollector()
    handle_calendar_response = create_calendar_response_handler(collector)

    # Register response handler AFTER going back, before navigating forward
    driver.on("response", handle_calendar_response)

    try:
        # Navigate forward to first week - this triggers the API call we want
        logger.info("Navigating forward to start week to capture data")
        await navigate_next_week(driver)

        # Navigate through weeks to trigger API calls
        weeks_visited = []
        week_number = 0

        while True:
            # Get current week's date range
            week_start, week_end = await get_current_week_range(driver)
            weeks_visited.append(f"{week_start} - {week_end}")

            # Check if this week overlaps with our date range
            if week_start > end_date:
                break  # Past our date range

            week_number += 1

            # Log progress
            logger.info("Collecting data for week: %s - %s", week_start, week_end)

            # Report progress via callback
            if progress_callback is not None:
                progress_callback(f"Processing week {week_number}...")

            # Wait for any pending API responses
            await driver.wait_for_timeout(500)

            # Check if we need to continue to next week
            if week_end >= end_date:
                break

            # Navigate to next week
            await navigate_next_week(driver)

        # Calculate hours from collected entries
        working_hours, time_off_hours, total = collector.get_hours_for_month(
            start_date.year, start_date.month
        )

        # Log collected entries for debugging
        entries_in_month = [
            e
            for e in collector.entries
            if e.entry_date.year == start_date.year
            and e.entry_date.month == start_date.month
        ]
        logger.info(
            "Collected %d entries for %s-%02d from %d total entries",
            len(entries_in_month),
            start_date.year,
            start_date.month,
            len(collector.entries),
        )
        for entry in entries_in_month:
            logger.debug(
                "  %s: %s (%s) - %.1f hours",
                entry.entry_date,
                entry.title,
                entry.entry_type,
                entry.hours,
            )

        logger.info(
            "Per-day calculation: working=%.1f, time_off=%.1f, total=%.1f",
            working_hours,
            time_off_hours,
            total,
        )
        logger.info("Weeks visited: %s", weeks_visited)

        # Calculate working days and absence days
        working_days = calculate_working_days(start_date, end_date)
        absence_days = int(time_off_hours / 8.0) if time_off_hours > 0 else 0

        logger.info(
            "Final: working_days=%d, absence_days=%d, total_hours=%.1f",
            working_days,
            absence_days,
            total,
        )

        # Get entries in the requested range
        range_entries = collector.get_entries_for_range(start_date, end_date)

        return WorkHours(
            working_days=working_days,
            absence_days=absence_days,
            total_hours=total,
            calendar_entries=range_entries,
        )

    finally:
        # Clean up response handler
        driver.remove_listener("response", handle_calendar_response)


async def extract_week_summary(driver: BrowserDriverProtocol) -> dict[str, float]:
    """Extract summary data from the current week view.

    The Summary section in Workday has a definition list (<dl>) structure:
    - <dt> "Standard Hours:" </dt><dd> "24" </dd>
    - <dt> "Overtime:" </dt><dd> "0" </dd>
    - <dt> "Time Off / Leave of Absence" </dt><dd> "16" </dd>
    - <dt> "Total Hours:" </dt><dd> "40" </dd>

    Playwright's accessibility API doesn't expose proper definitionlist roles
    for Workday's HTML, so we use CSS selectors to match the DOM directly.

    Args:
        driver: Browser driver object

    Returns:
        Dict with standard_hours, overtime, time_off keys

    Raises:
        NavigationError: If summary data cannot be extracted
    """
    summary = {"standard_hours": 0.0, "overtime": 0.0, "time_off": 0.0}

    # Use CSS selectors to find the Summary section's definition list
    # The section contains an h2 with "Summary" text
    summary_dl = driver.locator("section:has(h2:has-text('Summary')) dl")

    # Wait for the dl to be visible
    try:
        await summary_dl.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    except Exception as e:
        raise NavigationError(f"Summary definition list not found: {e}") from e

    # Extract values using CSS selectors for dt/dd pairs
    # Standard Hours
    summary["standard_hours"] = await get_definition_value_css(
        summary_dl, "Standard Hours:"
    )
    logger.debug("Standard hours: %s", summary["standard_hours"])

    # Overtime
    summary["overtime"] = await get_definition_value_css(summary_dl, "Overtime:")
    logger.debug("Overtime: %s", summary["overtime"])

    # Time Off / Leave of Absence (note: no colon in the term name)
    summary["time_off"] = await get_definition_value_css(
        summary_dl, "Time Off / Leave of Absence"
    )
    logger.debug("Time off: %s", summary["time_off"])

    return summary


async def get_definition_value_css(dl: LocatorProtocol, term_name: str) -> float:
    """Get the value from a definition list term using CSS selectors.

    The DOM structure is:
    <dl>
        <div class="...">
            <dt>Standard Hours:</dt>
            <dd>24</dd>
        </div>
        ...
    </dl>

    Args:
        dl: Locator for the definition list
        term_name: The term name to find (e.g., "Standard Hours:")

    Returns:
        The numeric value from the corresponding definition

    Raises:
        NavigationError: If the term cannot be found or value extracted
    """
    # Escape quotes in term_name for CSS selector
    escaped_term = term_name.replace("'", "\\'")

    # Find the row div containing the dt with matching text, then get dd
    # Using :has() to find parent div containing the specific dt
    row = dl.locator(f"div:has(dt:text-is('{escaped_term}'))")
    definition = row.locator("dd")

    try:
        text = await definition.text_content(timeout=5000)
    except Exception as e:
        raise NavigationError(
            f"Could not find definition for '{term_name}': {e}"
        ) from e

    if text is None:
        raise NavigationError(f"Definition for '{term_name}' has no text content")

    text = text.strip()
    if not text:
        raise NavigationError(f"Definition for '{term_name}' is empty")

    # Try to parse as number (may be "24" or "0")
    try:
        return float(text)
    except ValueError as e:
        raise NavigationError(
            f"Could not parse numeric value for '{term_name}': got '{text}'"
        ) from e


def create_calendar_response_handler(
    collector: CalendarEntriesCollector,
) -> Callable[[ResponseProtocol], Coroutine[Any, Any, None]]:
    """Create a response handler for calendar entries API.

    Args:
        collector: CalendarEntriesCollector to add entries to

    Returns:
        Async function to handle calendar responses
    """

    async def handle_calendar_response(response: ResponseProtocol) -> None:
        """Handle calendar entries API responses."""
        if CALENDAR_ENTRIES_API_PATTERN not in response.url:
            return

        try:
            # Only process successful JSON responses
            if response.status != HTTP_OK:
                return

            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return

            data = await response.json()
            added = collector.add_entries_from_response(data)
            logger.debug(
                "Calendar API response: added %d entries from %s",
                added,
                response.url,
            )
        except Exception as e:
            logger.warning("Failed to process calendar response: %s", e)

    return handle_calendar_response
