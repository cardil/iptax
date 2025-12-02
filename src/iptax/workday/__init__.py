"""Workday integration package for fetching work hours."""

from iptax.workday.client import WorkdayClient
from iptax.workday.models import (
    AuthenticationError,
    CalendarEntriesCollector,
    CalendarEntry,
    NavigationError,
    WorkdayError,
)
from iptax.workday.prompts import prompt_manual_work_hours
from iptax.workday.utils import calculate_working_days

__all__ = [
    "AuthenticationError",
    "CalendarEntriesCollector",
    "CalendarEntry",
    "NavigationError",
    "WorkdayClient",
    "WorkdayError",
    "calculate_working_days",
    "prompt_manual_work_hours",
]
