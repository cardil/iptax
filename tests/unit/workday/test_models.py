"""Tests for workday.models module."""

from __future__ import annotations

from datetime import date

import pytest

from iptax.models import WorkdayCalendarEntry
from iptax.workday.models import (
    AuthenticationError,
    CalendarEntriesCollector,
    NavigationError,
    WorkdayError,
    _parse_calendar_entry,
)


class TestExceptions:
    """Test Workday exception classes."""

    def test_workday_error_is_exception(self) -> None:
        """Test WorkdayError inheritance."""
        with pytest.raises(WorkdayError):
            raise WorkdayError("Test error")

    def test_authentication_error_is_workday_error(self) -> None:
        """Test AuthenticationError inheritance."""
        with pytest.raises(WorkdayError):
            raise AuthenticationError("Auth failed")

    def test_navigation_error_is_workday_error(self) -> None:
        """Test NavigationError inheritance."""
        with pytest.raises(WorkdayError):
            raise NavigationError("Nav failed")


class TestParseCalendarEntry:
    """Test _parse_calendar_entry function."""

    def test_parse_time_tracking_entry(self) -> None:
        """Test parsing a regular time tracking entry."""
        entry_data = {
            "widget": "calendarEntry",
            "date": {"value": {"V": "2025-11-10-08:00"}},
            "title": {"value": "Regular/Time Worked"},
            "type": {"instances": [{"text": "Time Tracking"}]},
            "quantity": {"value": 8},
        }
        result = _parse_calendar_entry(entry_data)
        assert result is not None
        assert result.entry_date == date(2025, 11, 10)
        assert result.title == "Regular/Time Worked"
        assert result.entry_type == "Time Tracking"
        assert result.hours == 8.0

    def test_parse_entry_with_positive_timezone(self) -> None:
        """Test parsing entry with positive timezone offset."""
        entry_data = {
            "widget": "calendarEntry",
            "date": {"value": {"V": "2025-11-10+01:00"}},
            "title": {"value": "Regular/Time Worked"},
            "type": {"instances": [{"text": "Time Tracking"}]},
            "quantity": {"value": 8},
        }
        result = _parse_calendar_entry(entry_data)
        assert result is not None
        assert result.entry_date == date(2025, 11, 10)

    def test_parse_time_off_entry_with_hours_in_subtitle(self) -> None:
        """Test parsing time off entry with hours in subtitle1."""
        entry_data = {
            "widget": "calendarEntry",
            "date": {"value": {"V": "2025-11-28-08:00"}},
            "title": {"value": "TOIL"},
            "type": {"instances": [{"text": "Time Off"}]},
            "subtitle1": {"value": "8 Hours"},
            "quantity": {"value": 1},
        }
        result = _parse_calendar_entry(entry_data)
        assert result is not None
        assert result.hours == 8.0  # Parsed from subtitle1

    def test_parse_time_off_entry_with_quantity_as_days(self) -> None:
        """Test parsing time off entry with quantity as days (converted to hours)."""
        entry_data = {
            "widget": "calendarEntry",
            "date": {"value": {"V": "2025-11-28-08:00"}},
            "title": {"value": "Vacation"},
            "type": {"instances": [{"text": "Time Off"}]},
            "quantity": {"value": 1},
        }
        result = _parse_calendar_entry(entry_data)
        assert result is not None
        assert result.hours == 8.0  # 1 day * 8 hours

    def test_parse_time_off_with_invalid_subtitle_falls_back_to_days(self) -> None:
        """Test time off with invalid subtitle falls back to days conversion."""
        entry_data = {
            "widget": "calendarEntry",
            "date": {"value": {"V": "2025-11-28-08:00"}},
            "title": {"value": "Vacation"},
            "type": {"instances": [{"text": "Time Off"}]},
            "subtitle1": {"value": "invalid"},
            "quantity": {"value": 2},
        }
        result = _parse_calendar_entry(entry_data)
        assert result is not None
        assert result.hours == 16.0  # 2 days * 8 hours

    def test_parse_entry_with_subtitle2_fallback(self) -> None:
        """Test parsing entry using subtitle2 as fallback."""
        entry_data = {
            "widget": "calendarEntry",
            "date": {"value": {"V": "2025-11-10-08:00"}},
            "title": {"value": "Custom Entry"},
            "type": {"instances": [{"text": "Time Tracking"}]},
            "subtitle2": {"value": "6 Hours"},
        }
        result = _parse_calendar_entry(entry_data)
        assert result is not None
        assert result.hours == 6.0

    def test_parse_entry_missing_date_value(self) -> None:
        """Test parsing entry with missing date value returns None."""
        entry_data = {
            "widget": "calendarEntry",
            "date": {"value": {}},
            "title": {"value": "Test"},
            "type": {"instances": [{"text": "Time Tracking"}]},
        }
        result = _parse_calendar_entry(entry_data)
        assert result is None

    def test_parse_entry_invalid_date_format(self) -> None:
        """Test parsing entry with invalid date format returns None."""
        entry_data = {
            "widget": "calendarEntry",
            "date": {"value": {"V": "invalid-date"}},
            "title": {"value": "Test"},
            "type": {"instances": [{"text": "Time Tracking"}]},
        }
        result = _parse_calendar_entry(entry_data)
        assert result is None

    def test_parse_entry_missing_type_instances(self) -> None:
        """Test parsing entry with missing type instances."""
        entry_data = {
            "widget": "calendarEntry",
            "date": {"value": {"V": "2025-11-10-08:00"}},
            "title": {"value": "Test"},
            "type": {},
            "quantity": {"value": 8},
        }
        result = _parse_calendar_entry(entry_data)
        assert result is not None
        assert result.entry_type == ""

    def test_parse_entry_with_invalid_subtitle2(self) -> None:
        """Test parsing entry with invalid subtitle2 format returns zero hours."""
        entry_data = {
            "widget": "calendarEntry",
            "date": {"value": {"V": "2025-11-10-08:00"}},
            "title": {"value": "Test"},
            "type": {"instances": [{"text": "Time Tracking"}]},
            "subtitle2": {"value": "invalid"},
        }
        result = _parse_calendar_entry(entry_data)
        assert result is not None
        assert result.hours == 0.0

    def test_parse_entry_exception_returns_none(self) -> None:
        """Test that parsing exception returns None."""
        entry_data = {"invalid": "structure"}
        result = _parse_calendar_entry(entry_data)
        assert result is None


class TestCalendarEntriesCollector:
    """Test CalendarEntriesCollector class."""

    def test_add_entries_from_response(self) -> None:
        """Test adding entries from API response."""
        collector = CalendarEntriesCollector()
        response_data = {
            "body": {
                "children": [
                    {
                        "consolidatedList": {
                            "children": [
                                {
                                    "widget": "calendarEntry",
                                    "date": {"value": {"V": "2025-11-10-08:00"}},
                                    "title": {"value": "Regular/Time Worked"},
                                    "type": {"instances": [{"text": "Time Tracking"}]},
                                    "quantity": {"value": 8},
                                }
                            ]
                        }
                    }
                ]
            }
        }
        added = collector.add_entries_from_response(response_data)
        assert added == 1
        assert len(collector.entries) == 1

    def test_add_multiple_entries(self) -> None:
        """Test adding multiple entries from response."""
        collector = CalendarEntriesCollector()
        response_data = {
            "body": {
                "children": [
                    {
                        "consolidatedList": {
                            "children": [
                                {
                                    "widget": "calendarEntry",
                                    "date": {"value": {"V": "2025-11-10-08:00"}},
                                    "title": {"value": "Regular/Time Worked"},
                                    "type": {"instances": [{"text": "Time Tracking"}]},
                                    "quantity": {"value": 8},
                                },
                                {
                                    "widget": "calendarEntry",
                                    "date": {"value": {"V": "2025-11-11-08:00"}},
                                    "title": {"value": "Paid Holiday"},
                                    "type": {"instances": [{"text": "Time Tracking"}]},
                                    "quantity": {"value": 8},
                                },
                            ]
                        }
                    }
                ]
            }
        }
        added = collector.add_entries_from_response(response_data)
        assert added == 2
        assert len(collector.entries) == 2

    def test_deduplication_same_entry(self) -> None:
        """Test that duplicate entries are not added twice."""
        collector = CalendarEntriesCollector()
        response_data = {
            "body": {
                "children": [
                    {
                        "consolidatedList": {
                            "children": [
                                {
                                    "widget": "calendarEntry",
                                    "date": {"value": {"V": "2025-11-10-08:00"}},
                                    "title": {"value": "Regular/Time Worked"},
                                    "type": {"instances": [{"text": "Time Tracking"}]},
                                    "quantity": {"value": 8},
                                }
                            ]
                        }
                    }
                ]
            }
        }
        added1 = collector.add_entries_from_response(response_data)
        added2 = collector.add_entries_from_response(response_data)
        assert added1 == 1
        assert added2 == 0
        assert len(collector.entries) == 1

    def test_skips_non_calendar_entries(self) -> None:
        """Test that non-calendarEntry widgets are skipped."""
        collector = CalendarEntriesCollector()
        response_data = {
            "body": {
                "children": [
                    {
                        "consolidatedList": {
                            "children": [
                                {
                                    "widget": "someOtherWidget",
                                    "date": {"value": {"V": "2025-11-10-08:00"}},
                                }
                            ]
                        }
                    }
                ]
            }
        }
        added = collector.add_entries_from_response(response_data)
        assert added == 0

    def test_handles_malformed_response(self) -> None:
        """Test that malformed responses don't crash the collector."""
        collector = CalendarEntriesCollector()
        response_data = {"body": {}}
        added = collector.add_entries_from_response(response_data)
        assert added == 0

    def test_get_hours_for_month(self) -> None:
        """Test calculating hours for a specific month."""
        collector = CalendarEntriesCollector()
        collector.entries = [
            WorkdayCalendarEntry(
                entry_date=date(2025, 11, 10),
                title="Regular/Time Worked",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2025, 11, 11),
                title="Paid Holiday",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2025, 11, 28),
                title="Paid Time Off in Hours",
                entry_type="Time Tracking",
                hours=8.0,
            ),
        ]
        working, pto, holiday, total = collector.get_hours_for_month(2025, 11)
        assert working == 8.0
        assert pto == 8.0
        assert holiday == 8.0
        assert total == 24.0

    def test_get_hours_for_month_filters_by_date(self) -> None:
        """Test that get_hours_for_month filters entries by month and year."""
        collector = CalendarEntriesCollector()
        collector.entries = [
            WorkdayCalendarEntry(
                entry_date=date(2025, 11, 10),
                title="Regular/Time Worked",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            WorkdayCalendarEntry(
                entry_date=date(2025, 12, 5),
                title="Regular/Time Worked",
                entry_type="Time Tracking",
                hours=8.0,
            ),
        ]
        working, _pto, _holiday, total = collector.get_hours_for_month(2025, 11)
        assert working == 8.0
        assert total == 8.0

    def test_get_hours_counts_time_off_without_time_tracking(self) -> None:
        """Test that Time Off entries are counted when no Time Tracking exists."""
        collector = CalendarEntriesCollector()
        collector.entries = [
            WorkdayCalendarEntry(
                entry_date=date(2025, 11, 10),
                title="Regular/Time Worked",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            # Time Off entry without corresponding Time Tracking (future PTO)
            WorkdayCalendarEntry(
                entry_date=date(2025, 11, 28),
                title="TOIL",
                entry_type="Time Off",
                hours=8.0,
            ),
        ]
        working, pto, holiday, total = collector.get_hours_for_month(2025, 11)
        assert working == 8.0
        assert pto == 8.0  # Time Off entry counted
        assert holiday == 0.0
        assert total == 16.0
