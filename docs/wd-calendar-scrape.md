# Workday Calendar API Research

This document summarizes findings from reverse-engineering the Workday calendar API for
extracting per-day work hours data.

## Overview

Workday uses internal JSON APIs for calendar data that can be called programmatically
after authentication. These APIs provide per-day time entries, enabling accurate monthly
hour calculations without prorating.

## API Endpoints

### 1. User Info Endpoint

**Endpoint:** `GET /{instance-name}/app-root`

**Purpose:** Get current user's worker ID (required for other API calls)

**Key Response Field:**

```json
{
  "userModel": {
    "iid": "123$4567"
  }
}
```

The `userModel.iid` is the `workerId` needed for calendar APIs.

### 2. Calendar Sidebar (Summary) API

**Endpoint:** `POST /{instance-name}/calendar/sidebar/task/2997$17619.htmld`

**Parameters:**

- `workerId` (required): Worker ID from app-root (e.g., `123$4567`)
- `date` (required): Date in format `YYYY-MM-DD`

**Request:**

```http
POST /{instance-name}/calendar/sidebar/task/2997$17619.htmld
Content-Type: application/x-www-form-urlencoded

workerId=123%244567&date=2025-11-10
```

**Response:** JSON with cumulative totals (YTD) in minutes:

```json
{
  "body": {
    "children": [{
      "items": [
        {"label": {"value": "Standard Hours:"}, "value": {"value": 9384}},
        {"label": {"value": "Overtime:"}, "value": {"value": 0}},
        {"label": {"value": "Time Off / Leave of Absence"}, "value": {"value": 1824}},
        {"label": {"value": "Total Hours:"}, "value": {"value": 11208}}
      ]
    }]
  }
}
```

**Note:** Values are in **minutes** (divide by 60 for hours). This endpoint returns
cumulative YTD totals, not per-period data.

### 3. Calendar Entries API (Per-Day Data)

**Endpoint:**
`POST /{instance-name}/calendar/c1/inst/{week-hash}/rel-task/2997$9444.htmld`

**Week Hash Format:** The week hash encodes date range and is obtained from URL
navigation. Example:

```
6305!CKExEhYKBQgVEKgiEg0xNzYzMjgwMDAwMDAwGhIKBggDEKGZARIICgYI9wEQyEcaEQoG...
```

The base64-like encoded string contains timestamps for the week boundaries.

**Response:** JSON with individual calendar entries:

```json
{
  "body": {
    "children": [{
      "consolidatedList": {
        "children": [
          {
            "widget": "calendarEntry",
            "date": {
              "value": {"Y": "2025", "M": "11", "D": "10", "V": "2025-11-10-08:00"}
            },
            "title": {"value": "Regular/Time Worked"},
            "subtitle1": {"value": "10:00am - 6:00pm"},
            "subtitle2": {"value": "8 Hours"},
            "type": {"instances": [{"text": "Time Tracking"}]}
          }
        ]
      }
    }]
  }
}
```

## Entry Types

| Entry Type          | Type Text        | Description             | Hours   |
| ------------------- | ---------------- | ----------------------- | ------- |
| Regular/Time Worked | Time Tracking    | Normal working hours    | Yes (q) |
| Paid Holiday        | Time Tracking    | Paid holiday hours      | Yes (q) |
| TOIL                | Time Off         | Time Off In Lieu        | Yes (q) |
| Independence Day    | Holiday Calendar | Calendar holiday marker | No (0)  |

Note: (q) = `quantity` field, (0) = `quantity: 0`

## Key Fields in Calendar Entry

| Field        | Path                     | Example Value         | Notes           |
| ------------ | ------------------------ | --------------------- | --------------- |
| Date         | `date.value.V`           | `2025-11-10-08:00`    | ISO+TZ          |
| Title        | `title.value`            | `Regular/Time Worked` | Entry type      |
| Hours (num)  | `quantity.value`         | `8`                   | **Preferred**   |
| Hours (text) | `subtitle2.value`        | `8 Hours`             | Fallback/parse  |
| Time Range   | `subtitle1.value`        | `10:00am - 6:00pm`    | Time Track only |
| Type         | `type.instances[0].text` | `Time Tracking`       | Category        |
| Start Time   | `startMoment.value`      | Full datetime with TZ |                 |
| End Time     | `endMoment.value`        | Full datetime with TZ |                 |

## Complete Entry Examples

### Time Tracking Entry (Regular Work)

```json
{
  "date": "2025-11-10",
  "title": "Regular/Time Worked",
  "subtitle1": "10:00am - 6:00pm",
  "subtitle2": "8 Hours",
  "type": "Time Tracking",
  "quantity": 8
}
```

### Time Tracking Entry (Paid Holiday)

```json
{
  "date": "2025-11-11",
  "title": "Paid Holiday",
  "subtitle1": "8",
  "type": "Time Tracking",
  "quantity": 8
}
```

### Time Off Entry (TOIL)

```json
{
  "date": "2025-11-28",
  "title": "TOIL",
  "subtitle1": "8 Hours",
  "type": "Time Off",
  "quantity": 8
}
```

### Holiday Calendar Marker (No Hours)

```json
{
  "date": "2025-11-11",
  "title": "Independence Day",
  "type": "Holiday Calendar Entry Type",
  "quantity": 0
}
```

## Authentication

Authentication is handled via SSO with Kerberos (SPNEGO):

1. **Firefox Configuration:** Set `network.negotiate-auth.trusted-uris` to include:

   - `https://auth.redhat.com`
   - `https://wd5.myworkday.com`

1. **Prerequisites:** Valid Kerberos ticket via `kinit`

1. **Session:** After SSO authentication, session cookies are used for API calls

## Implementation Notes

### Getting Per-Day Hours for a Month

1. Navigate to the Enter Time page for the target month
1. Iterate through each week using "Select Week" modal
1. For each week, fetch the calendar entries API
1. Parse `consolidatedList.children` for entries
1. Filter entries by date to only include days in target month
1. Categorize by type:
   - `Time Tracking` entries → working hours
   - `Time Off` entries → absence hours
   - `Holiday Calendar Entry Type` → skip (informational only)

### Extracting Hours from Entry

**Preferred method** - use the `quantity` field (numeric):

```python
hours = entry.get("quantity", {}).get("value", 0)  # 8
```

**Fallback** - parse the `subtitle2.value` text:

```python
hours_text = entry.get("subtitle2", {}).get("value", "0 Hours")
hours = float(hours_text.split()[0])  # 8.0
```

### Date Parsing

The date format `YYYY-MM-DD-08:00` includes timezone offset. Extract date:

```python
date_str = entry["date"]["value"]["V"]  # "2025-11-10-08:00"
date = date_str.split("-08:00")[0]  # "2025-11-10"
```

## Week Navigation

The week hash is encoded with timestamps. Week boundaries:

- The week hash contains base64-encoded timestamps for week boundaries
- URL pattern: `/{instance-name}/calendar/c1/inst/{week-hash}/rel-task/2997$9444.htmld`

To navigate to a specific week, use the "Select Week" modal in the UI rather than
constructing week hashs manually.

## Advantages Over UI Scraping

1. **Accuracy:** Per-day data eliminates prorating errors at month boundaries
1. **Speed:** Single API call per week vs. day-by-day navigation
1. **Reliability:** JSON is easier to parse than HTML/accessibility tree
1. **Consistency:** API structure is more stable than UI layout

## Example: Monthly Hours Calculation

```python
from datetime import datetime

def get_monthly_hours(entries: list[dict], year: int, month: int) -> dict:
    """Calculate hours for a specific month from calendar entries."""
    working_hours = 0.0
    time_off_hours = 0.0

    for entry in entries:
        # Parse date
        date_str = entry["date"]["value"]["V"].split("-08:00")[0]
        entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        # Filter to target month
        if entry_date.year != year or entry_date.month != month:
            continue

        # Get hours from quantity (preferred) or parse subtitle2
        hours = entry.get("quantity", {}).get("value", 0)
        if hours == 0:
            hours_text = entry.get("subtitle2", {}).get("value", "")
            if "Hour" in hours_text:
                hours = float(hours_text.split()[0])

        if hours == 0:
            continue

        entry_type = entry["type"]["instances"][0]["text"]

        if entry_type == "Time Tracking":
            working_hours += hours
        elif entry_type == "Time Off":
            time_off_hours += hours
        # Skip "Holiday Calendar Entry Type" - just markers

    return {
        "working_hours": working_hours,
        "time_off_hours": time_off_hours,
        "total_hours": working_hours + time_off_hours
    }
```

## Categorization Logic

For tax reporting, categorize entries as follows:

| Type             | Title               | Category | Count As        |
| ---------------- | ------------------- | -------- | --------------- |
| Time Tracking    | Regular/Time Worked | Work     | Working hours   |
| Time Tracking    | Paid Holiday        | Absence  | Time off (paid) |
| Time Off         | TOIL, Vacation, etc | Absence  | Time off (paid) |
| Holiday Calendar | \*                  | Skip     | Not counted     |

## Discovered 2025-11-27

This research was conducted as part of the iptax project to implement accurate work
hours extraction from Workday for tax reporting purposes.
