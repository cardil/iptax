"""Workday Calendar API routes for mock server."""

from datetime import date, timedelta

from flask import Blueprint, current_app, jsonify, request

api = Blueprint("api", __name__)


@api.route("/rel-task/2997$9444.htmld")
def calendar_entries():
    """Return calendar entries for the current week.

    Test data is configured via app.config['CALENDAR_DATA'].
    """
    calendar_data = current_app.config.get("CALENDAR_DATA", {})

    # Get week from request context or use default
    week_start_str = request.args.get("week_start")
    if week_start_str:
        week_start = date.fromisoformat(week_start_str)
    else:
        # Use the current week from session/global state
        week_start = date.today() - timedelta(days=date.today().weekday())

    # Build calendar entries for this week
    entries = []
    for day_offset in range(7):
        entry_date = week_start + timedelta(days=day_offset)
        date_str = entry_date.isoformat()

        if date_str in calendar_data:
            for item in calendar_data[date_str]:
                entries.append(_make_calendar_entry(entry_date, item))

    return jsonify(
        {"body": {"children": [{"consolidatedList": {"children": entries}}]}}
    )


def _make_calendar_entry(entry_date: date, item: dict) -> dict:
    """Create a calendar entry in Workday API format.

    Args:
        entry_date: Date of the entry
        item: Dictionary with title, type, hours, etc.

    Returns:
        Calendar entry dict matching Workday API structure
    """
    return {
        "widget": "calendarEntry",
        "date": {"value": {"V": f"{entry_date.isoformat()}-08:00"}},
        "title": {"value": item.get("title", "Regular/Time Worked")},
        "type": {"instances": [{"text": item.get("type", "Time Tracking")}]},
        "quantity": {"value": item.get("hours", 8)},
        "subtitle1": {"value": item.get("subtitle1", "")},
        "subtitle2": {"value": item.get("subtitle2", "")},
    }
