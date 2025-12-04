"""Workday data models and exceptions."""

from __future__ import annotations

import contextlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime

logger = logging.getLogger(__name__)


class WorkdayError(Exception):
    """Base exception for Workday errors."""

    pass


class AuthenticationError(WorkdayError):
    """Failed to authenticate with Workday SSO."""

    pass


class NavigationError(WorkdayError):
    """Failed to navigate within Workday."""

    pass


@dataclass
class CalendarEntry:
    """A single calendar entry from Workday API."""

    entry_date: date
    title: str
    entry_type: str  # "Time Tracking", "Time Off", "Holiday Calendar Entry Type"
    hours: float


@dataclass
class CalendarEntriesCollector:
    """Collects calendar entries from intercepted API responses."""

    entries: list[CalendarEntry] = field(default_factory=list)
    _seen_keys: set[str] = field(default_factory=set)

    def add_entries_from_response(self, response_data: dict) -> int:
        """Parse and add entries from a calendar API response.

        Deduplicates entries based on (date, title, type) to avoid
        counting the same entry multiple times from overlapping weeks.

        Args:
            response_data: JSON response from calendar entries API

        Returns:
            Number of entries added
        """
        added = 0
        try:
            # Navigate to consolidatedList.children
            body = response_data.get("body", {})
            children = body.get("children", [])

            for child in children:
                consolidated_list = child.get("consolidatedList", {})
                entries = consolidated_list.get("children", [])

                for entry in entries:
                    if entry.get("widget") != "calendarEntry":
                        continue

                    parsed = _parse_calendar_entry(entry)
                    if parsed:
                        # Deduplicate based on date + title + type
                        key = f"{parsed.entry_date}|{parsed.title}|{parsed.entry_type}"
                        if key not in self._seen_keys:
                            self._seen_keys.add(key)
                            self.entries.append(parsed)
                            added += 1

        except Exception as e:
            logger.warning("Failed to parse calendar entries: %s", e)

        return added

    def get_hours_for_month(self, year: int, month: int) -> tuple[float, float, float]:
        """Calculate hours for a specific month.

        Args:
            year: Target year
            month: Target month (1-12)

        Returns:
            Tuple of (working_hours, time_off_hours, total_hours)
        """
        working_hours = 0.0
        time_off_hours = 0.0

        for entry in self.entries:
            if entry.entry_date.year != year or entry.entry_date.month != month:
                continue

            if entry.entry_type == "Time Tracking":
                # Check for time off entries that have "Time Tracking" type
                # but are actually paid time off (vacation, PTO, etc.)
                if entry.title in ("Paid Holiday", "Paid Time Off in Hours"):
                    time_off_hours += entry.hours
                else:
                    working_hours += entry.hours
            # Note: We skip "Time Off" entries (e.g., "Annual Leave") because
            # the actual hours are captured in "Time Tracking" entries like
            # "Paid Time Off in Hours". The "Time Off" entries are just
            # absence request/approval markers without actual hour values.
            # Also skip "Holiday Calendar Entry Type" - just markers, no hours

        return working_hours, time_off_hours, working_hours + time_off_hours

    def get_entries_for_range(
        self, start_date: date, end_date: date
    ) -> list[CalendarEntry]:
        """Get all entries within a date range.

        Args:
            start_date: Start of range (inclusive)
            end_date: End of range (inclusive)

        Returns:
            List of calendar entries in the specified range
        """
        return [
            entry
            for entry in self.entries
            if start_date <= entry.entry_date <= end_date
        ]


def _parse_calendar_entry(entry: dict) -> CalendarEntry | None:
    """Parse a single calendar entry from API response.

    Args:
        entry: Entry dict from API response

    Returns:
        CalendarEntry or None if parsing fails
    """
    try:
        # Parse date from "date.value.V" format: "2025-11-10-08:00"
        date_data = entry.get("date", {}).get("value", {})
        date_str = date_data.get("V", "")
        if not date_str:
            return None

        # Remove timezone suffix (e.g., "-08:00")
        # Handle both negative and positive offsets
        date_only = re.sub(r"[+-]\d{2}:\d{2}$", "", date_str)
        entry_date = datetime.strptime(date_only, "%Y-%m-%d").date()

        # Get title
        title = entry.get("title", {}).get("value", "")

        # Get entry type from type.instances[0].text
        entry_type = ""
        type_data = entry.get("type", {})
        instances = type_data.get("instances", [])
        if instances:
            entry_type = instances[0].get("text", "")

        # Get hours - handling differs by entry type
        # For Time Off, quantity is typically days (1 = 8 hours)
        # For Time Tracking, quantity is hours directly
        hours = 0.0
        quantity_data = entry.get("quantity", {})
        quantity_value = float(quantity_data.get("value", 0)) if quantity_data else 0.0

        if entry_type == "Time Off":
            # For Time Off, first try to parse hours from subtitle1 like "8 Hours"
            subtitle1 = entry.get("subtitle1", {}).get("value", "")
            if subtitle1 and "Hour" in subtitle1:
                try:
                    hours = float(subtitle1.split()[0])
                except (ValueError, IndexError):
                    # Fallback: quantity is days, convert to hours
                    hours = quantity_value * 8.0
            elif quantity_value > 0:
                # quantity is likely days (small number like 1, 2)
                hours = quantity_value * 8.0
        elif quantity_value > 0:
            # For Time Tracking, quantity is hours directly
            hours = quantity_value
        else:
            # Fallback to parsing subtitle2 like "8 Hours"
            subtitle2 = entry.get("subtitle2", {}).get("value", "")
            if subtitle2 and "Hour" in subtitle2:
                with contextlib.suppress(ValueError, IndexError):
                    hours = float(subtitle2.split()[0])

        return CalendarEntry(
            entry_date=entry_date,
            title=title,
            entry_type=entry_type,
            hours=hours,
        )

    except Exception as e:
        logger.debug("Failed to parse calendar entry: %s - %s", entry, e)
        return None
