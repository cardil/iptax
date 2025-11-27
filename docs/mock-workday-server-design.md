# Mock SSO and Workday Server Design for E2E Testing

## Overview

This document describes the architecture for mock SSO and Workday servers that enable
realistic e2e testing of the Workday integration without requiring real credentials or
network access.

## Problem Statement

Real e2e tests for Workday are impractical because:

1. **Credentials**: Cannot store real credentials in CI/GitHub secrets
1. **MFA**: Multi-factor authentication makes automated testing impossible
1. **Network Dependencies**: Tests would depend on external services

> **Note on UI Breakage Detection**: Ideally, e2e tests would detect upstream UI changes
> that break our integration. However, since we cannot run tests against real Workday
> servers due to security constraints (credentials, MFA), we cannot achieve this. The
> mock server tests verify our code works correctly against the *expected* UI, not that
> the real UI still matches our expectations.

## Recommended Implementation: Flask HTTP Servers

After analyzing the options, **Option A (Python HTTP servers with Flask)** is
recommended:

### Advantages

1. **Realistic Testing**: Playwright navigates to actual HTTP URLs
1. **Full Browser Automation**: Tests exercise the complete authentication flow
1. **Easy Configuration**: Test data injected via server configuration
1. **Portable**: No external dependencies beyond Flask
1. **CI-Friendly**: Runs entirely in-process with pytest

### Alternatives Considered

| Approach                      | Pros              | Cons                     |
| ----------------------------- | ----------------- | ------------------------ |
| Static HTML + route intercept | Simple setup      | Can't test nav redirects |
| Playwright request intercept  | No server needed  | Misses SSO redirect flow |
| **Flask HTTP servers**        | Full flow testing | Slightly more setup      |

## Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                            E2E Test Process                            │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │   Pytest Test    │───▶│  WorkdayClient   │───▶│   Playwright     │  │
│  │                  │    │  (production)    │    │   Browser        │  │
│  └──────────────────┘    └──────────────────┘    └────────┬─────────┘  │
│          │                                                │            │
│          │ configures                                     │ HTTP       │
│          ▼                                                ▼            │
│  ┌──────────────────┐                            ┌──────────────────┐  │
│  │  Test Fixtures   │                            │  Mock Servers    │  │
│  │  - credentials   │                            │  (Flask)         │  │
│  │  - calendar data │                            │                  │  │
│  │  - scenarios     │───────────────────────────▶│  Port: auto      │  │
│  └──────────────────┘                            │                  │  │
│                                                  │  Domains:        │  │
│                                                  │  - sso.localhost │  │
│                                                  │  - myworkday.com │  │
│                                                  │    .localhost    │  │
│                                                  └──────────────────┘  │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Domain Separation

The mock server uses two virtual domains to simulate the real SSO redirect flow:

| Domain                    | Purpose        | URL Pattern                        |
| ------------------------- | -------------- | ---------------------------------- |
| `sso.localhost`           | SSO login page | `http://sso.localhost:*`           |
| `myworkday.com.localhost` | Workday app    | `http://myworkday.com.localhost:*` |

This separation is critical because the production code in
[`src/iptax/workday/auth.py:32-39`](../src/iptax/workday/auth.py:32) checks for
`myworkday.com` in the URL to detect successful authentication:

```python
def _is_workday_url(url: str) -> bool:
    """Check if URL is on Workday domain (not SSO)."""
    parsed = urlparse(url)
    return "myworkday.com" in parsed.netloc
```

The domain `myworkday.com.localhost` contains `myworkday.com` and resolves to localhost,
satisfying both the URL check and local testing requirements.

## Selectors Reference

Based on analysis of [`src/iptax/workday/auth.py`](../src/iptax/workday/auth.py:52) and
[`src/iptax/workday/scraping.py`](../src/iptax/workday/scraping.py:48):

### SSO Login Page

| Element      | Selector                                  | Notes         |
| ------------ | ----------------------------------------- | ------------- |
| Username     | `get_by_role("textbox", name="Username")` | SSO username  |
| Password     | `get_by_role("textbox", name="Password")` | SSO password  |
| Login Button | `get_by_role("button", name="Log in...")` | Submit button |

### Workday Home Page

| Element     | Selector                                  | Notes         |
| ----------- | ----------------------------------------- | ------------- |
| Time Button | `get_by_role("button", name="Time", ...)` | Navigate Time |

### Time Page - Week Selection

| Element          | Selector                              | Notes       |
| ---------------- | ------------------------------------- | ----------- |
| Select Week Link | `get_by_role("link", ..."Select...")` | Opens modal |
| Month Input      | `get_by_role("spinbutton", "Month")`  | In modal    |
| Day Input        | `get_by_role("spinbutton", "Day")`    | In modal    |
| Year Input       | `get_by_role("spinbutton", "Year")`   | In modal    |
| OK Button        | `get_by_role("button", name="OK")`    | Confirm     |

### Time Page - Navigation

| Element       | Selector                                  | Notes           |
| ------------- | ----------------------------------------- | --------------- |
| Week Heading  | `get_by_role("heading", level=2)`         | Pattern: date   |
| Previous Week | `get_by_role("button", ..."Previous...")` | Week navigation |
| Next Week     | `get_by_role("button", ..."Next...")`     | Week navigation |

### Time Page - Summary Section

```html
<section>
  <h2>Summary</h2>
  <dl>
    <div><dt>Standard Hours:</dt><dd>40</dd></div>
    <div><dt>Overtime:</dt><dd>0</dd></div>
    <div><dt>Time Off / Leave of Absence</dt><dd>8</dd></div>
    <div><dt>Total Hours:</dt><dd>48</dd></div>
  </dl>
</section>
```

## API Reference

### Calendar Entries Endpoint

**URL Pattern**: `/rel-task/2997$9444.htmld`

From [`src/iptax/workday/browser.py:37`](../src/iptax/workday/browser.py:37):

```python
CALENDAR_ENTRIES_API_PATTERN = "/rel-task/2997$9444.htmld"
```

### Response Structure

From [`src/iptax/workday/models.py:62-86`](../src/iptax/workday/models.py:62):

```json
{
  "body": {
    "children": [
      {
        "consolidatedList": {
          "children": [
            {
              "widget": "calendarEntry",
              "date": {
                "value": {
                  "V": "2025-04-15-08:00"
                }
              },
              "title": {
                "value": "Regular/Time Worked"
              },
              "type": {
                "instances": [
                  {"text": "Time Tracking"}
                ]
              },
              "quantity": {
                "value": 8
              }
            }
          ]
        }
      }
    ]
  }
}
```

### Entry Types

| Entry Type               | Title Examples           | Hours Source     |
| ------------------------ | ------------------------ | ---------------- |
| `Time Tracking`          | `Regular/Time Worked`    | `quantity.value` |
| `Time Tracking`          | `Paid Holiday`, `PTO...` | Time off         |
| `Time Off`               | `Annual Leave`           | Ignored (marker) |
| `Holiday Calendar Entry` | -                        | Ignored (marker) |

## Server Implementation

### File Structure

```text
tests/
├── e2e/
│   ├── mock_servers/
│   │   ├── __init__.py
│   │   ├── app.py              # Combined Flask app
│   │   ├── sso_routes.py       # SSO login endpoints
│   │   ├── workday_routes.py   # Workday page endpoints
│   │   ├── api_routes.py       # Calendar API endpoints
│   │   └── templates/
│   │       ├── sso_login.html
│   │       ├── workday_home.html
│   │       └── workday_time.html
│   ├── fixtures/
│   │   ├── __init__.py
│   │   ├── calendar_data.py    # Test data generators
│   │   └── scenarios.py        # Pre-built test scenarios
│   ├── conftest.py             # Pytest fixtures for mock servers
│   └── test_workday_e2e.py     # E2E tests
```

### Mock SSO Server Routes

```python
# tests/e2e/mock_servers/sso_routes.py

from flask import Blueprint, request, redirect, render_template, session, current_app

sso = Blueprint('sso', __name__)

@sso.route('/sso/login')
def login_page():
    """Render SSO login form matching real selectors."""
    error = request.args.get('error')
    return render_template('sso_login.html', error=error)

@sso.route('/sso/login', methods=['POST'])
def login_submit():
    """Handle login form submission."""
    username = request.form.get('username')
    password = request.form.get('password')

    credentials = current_app.config.get('TEST_CREDENTIALS', {})
    workday_domain = current_app.config.get('WORKDAY_DOMAIN', 'myworkday.com.localhost')
    port = current_app.config.get('SERVER_PORT', 5080)

    if credentials.get(username) == password:
        session['authenticated'] = True
        session['username'] = username
        # Redirect to Workday domain (triggers _is_workday_url check)
        return redirect(f'http://{workday_domain}:{port}/d/home.htmld')
    else:
        # Reload login page with error (triggers bad credentials detection)
        return render_template('sso_login.html', error='Invalid credentials')

@sso.route('/sso/logout')
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect('/sso/login')
```

### Mock Workday Server Routes

```python
# tests/e2e/mock_servers/workday_routes.py

from flask import Blueprint, render_template, session, redirect, request, current_app
from datetime import date, timedelta

workday = Blueprint('workday', __name__)

# Current week state (managed per-session or globally for tests)
_current_week_start = None

@workday.before_request
def require_auth():
    """Require authentication for all Workday routes."""
    if not session.get('authenticated'):
        sso_domain = current_app.config.get('SSO_DOMAIN', 'sso.localhost')
        port = current_app.config.get('SERVER_PORT', 5080)
        return redirect(f'http://{sso_domain}:{port}/sso/login')

@workday.route('/d/home.htmld')
def home():
    """Workday home page with Time button."""
    return render_template('workday_home.html')

@workday.route('/d/time.htmld')
def time_page():
    """Time page with week selection and calendar."""
    global _current_week_start

    # Handle week navigation via query params
    action = request.args.get('action')
    if action == 'prev':
        _current_week_start -= timedelta(days=7)
    elif action == 'next':
        _current_week_start += timedelta(days=7)
    elif 'date' in request.args:
        # Direct date selection from modal
        _current_week_start = date.fromisoformat(request.args['date'])
        # Align to Monday
        _current_week_start -= timedelta(days=_current_week_start.weekday())

    if _current_week_start is None:
        today = date.today()
        _current_week_start = today - timedelta(days=today.weekday())

    week_end = _current_week_start + timedelta(days=6)

    return render_template(
        'workday_time.html',
        week_start=_current_week_start,
        week_end=week_end,
    )
```

> **Note**: The Workday routes use paths without the `/workday` prefix because they're
> served from the `myworkday.com.localhost` domain. The domain itself indicates it's
> Workday, matching the real URL structure.

### Mock Calendar API Routes

```python
# tests/e2e/mock_servers/api_routes.py

from flask import Blueprint, jsonify, request, current_app
from datetime import date, timedelta

api = Blueprint('api', __name__)

@api.route('/rel-task/2997$9444.htmld')
def calendar_entries():
    """Return calendar entries for the current week.

    Test data is configured via app.config['CALENDAR_DATA'].
    """
    calendar_data = current_app.config.get('CALENDAR_DATA', {})

    # Get week from request context or use default
    week_start_str = request.args.get('week_start')
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

    return jsonify({
        "body": {
            "children": [
                {
                    "consolidatedList": {
                        "children": entries
                    }
                }
            ]
        }
    })

def _make_calendar_entry(entry_date: date, item: dict) -> dict:
    """Create a calendar entry in Workday API format."""
    return {
        "widget": "calendarEntry",
        "date": {
            "value": {
                "V": f"{entry_date.isoformat()}-08:00"
            }
        },
        "title": {
            "value": item.get("title", "Regular/Time Worked")
        },
        "type": {
            "instances": [
                {"text": item.get("type", "Time Tracking")}
            ]
        },
        "quantity": {
            "value": item.get("hours", 8)
        },
        "subtitle1": {
            "value": item.get("subtitle1", "")
        },
        "subtitle2": {
            "value": item.get("subtitle2", "")
        }
    }
```

### HTML Templates

#### SSO Login Page

```html
<!-- tests/e2e/mock_servers/templates/sso_login.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SSO Login</title>
</head>
<body>
    <h1>Corporate SSO Login</h1>

    {% if error %}
    <div class="error" role="alert">{{ error }}</div>
    {% endif %}

    <form method="POST" action="/sso/login">
        <div>
            <label for="username">Username</label>
            <!-- Matches: get_by_role("textbox", name="Username") -->
            <input type="text"
                   id="username"
                   name="username"
                   aria-label="Username"
                   required>
        </div>

        <div>
            <label for="password">Password</label>
            <!-- Matches: get_by_role("textbox", name="Password") -->
            <input type="password"
                   id="password"
                   name="password"
                   aria-label="Password"
                   required>
        </div>

        <div>
            <!-- Matches: get_by_role("button", name="Log in to SSO") -->
            <button type="submit">Log in to SSO</button>
        </div>
    </form>
</body>
</html>
```

#### Workday Home Page

```html
<!-- tests/e2e/mock_servers/templates/workday_home.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Workday - Home</title>
</head>
<body>
    <header>
        <h1>Workday</h1>
        <!-- Global navigation elements if needed -->
    </header>

    <main>
        <section aria-label="Your Top Apps">
            <h2>Your Top Apps</h2>
            <div class="app-grid">
                <!-- Matches: get_by_role("button", name="Time", exact=True) -->
                <button type="button"
                        onclick="window.location='/d/time.htmld'">
                    Time
                </button>

                <!-- Other apps for realism -->
                <button type="button">Benefits</button>
                <button type="button">Pay</button>
            </div>
        </section>
    </main>
</body>
</html>
```

#### Workday Time Page

```html
<!-- tests/e2e/mock_servers/templates/workday_time.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Workday - Time</title>
    <script>
        // Week navigation via JavaScript
        function navigatePrev() {
            window.location = '/d/time.htmld?action=prev';
        }
        function navigateNext() {
            window.location = '/d/time.htmld?action=next';
        }
        function openWeekSelector() {
            document.getElementById('week-modal').style.display = 'block';
        }
        function selectWeek() {
            const month = document.getElementById('month-input').value;
            const day = document.getElementById('day-input').value;
            const year = document.getElementById('year-input').value;
            const date = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
            window.location = `/d/time.htmld?date=${date}`;
        }
        function closeModal() {
            document.getElementById('week-modal').style.display = 'none';
        }

        // Simulate API call when page loads
        document.addEventListener('DOMContentLoaded', function() {
            fetch('/rel-task/2997$9444.htmld?week_start={{ week_start }}')
                .then(r => r.json())
                .then(data => console.log('Calendar data:', data));
        });
    </script>
</head>
<body>
    <header>
        <h1>Time</h1>
    </header>

    <main>
        <nav aria-label="Week Navigation">
            <!-- Matches: get_by_role("link", name="Select Week") -->
            <a href="#" role="link" onclick="openWeekSelector(); return false;">
                Select Week
            </a>
        </nav>

        <section aria-label="Week View">
            <!-- Matches: get_by_role("heading", level=2) with date pattern -->
            <h2>
              {{ week_start.strftime('%b %d') }} -
              {{ week_end.strftime('%d, %Y') }}
            </h2>

            <div class="navigation">
                <!-- Matches: get_by_role("button", name="Previous Week") -->
                <button type="button" onclick="navigatePrev()">Previous Week</button>

                <!-- Matches: get_by_role("button", name="Next Week") -->
                <button type="button" onclick="navigateNext()">Next Week</button>
            </div>
        </section>

        <section>
            <h2>Summary</h2>
            <!-- Matches CSS: section:has(h2:has-text('Summary')) dl -->
            <dl>
                <div>
                    <dt>Standard Hours:</dt>
                    <dd>40</dd>
                </div>
                <div>
                    <dt>Overtime:</dt>
                    <dd>0</dd>
                </div>
                <div>
                    <dt>Time Off / Leave of Absence</dt>
                    <dd>0</dd>
                </div>
                <div>
                    <dt>Total Hours:</dt>
                    <dd>40</dd>
                </div>
            </dl>
        </section>
    </main>

    <!-- Week Selection Modal -->
    <div id="week-modal" role="dialog" style="display: none;">
        <div class="modal-content">
            <h3>Select Week</h3>
            <div>
                <label for="month-input">Month</label>
                <!-- Matches: get_by_role("spinbutton", name="Month") -->
                <input type="number"
                       id="month-input"
                       role="spinbutton"
                       aria-label="Month"
                       min="1"
                       max="12"
                       value="{{ week_start.month }}">
            </div>
            <div>
                <label for="day-input">Day</label>
                <!-- Matches: get_by_role("spinbutton", name="Day") -->
                <input type="number"
                       id="day-input"
                       role="spinbutton"
                       aria-label="Day"
                       min="1"
                       max="31"
                       value="{{ week_start.day }}">
            </div>
            <div>
                <label for="year-input">Year</label>
                <!-- Matches: get_by_role("spinbutton", name="Year") -->
                <input type="number"
                       id="year-input"
                       role="spinbutton"
                       aria-label="Year"
                       min="2020"
                       max="2030"
                       value="{{ week_start.year }}">
            </div>
            <div>
                <!-- Matches: get_by_role("button", name="OK") -->
                <button type="button" onclick="selectWeek()">OK</button>
                <button type="button" onclick="closeModal()">Cancel</button>
            </div>
        </div>
    </div>
</body>
</html>
```

## Test Data Fixtures

### Calendar Data Generator

```python
# tests/e2e/fixtures/calendar_data.py

from datetime import date, timedelta
from typing import Any

def generate_full_work_week(week_start: date) -> dict[str, list[dict[str, Any]]]:
    """Generate a standard 40-hour work week (8 hours Mon-Fri)."""
    data = {}
    for day_offset in range(5):  # Monday to Friday
        entry_date = week_start + timedelta(days=day_offset)
        data[entry_date.isoformat()] = [
            {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
        ]
    return data

def generate_partial_week(week_start: date, hours_per_day: list[float]) -> dict:
    """Generate a week with variable hours per day."""
    data = {}
    for day_offset, hours in enumerate(hours_per_day):
        if hours > 0:
            entry_date = week_start + timedelta(days=day_offset)
            data[entry_date.isoformat()] = [
                {
                    "title": "Regular/Time Worked",
                    "type": "Time Tracking",
                    "hours": hours
                }
            ]
    return data

def generate_week_with_pto(
    week_start: date,
    pto_days: list[int],  # Day offsets (0=Monday, 4=Friday)
    pto_hours: float = 8.0
) -> dict:
    """Generate a week with PTO on specified days."""
    data = generate_full_work_week(week_start)

    for day_offset in pto_days:
        entry_date = week_start + timedelta(days=day_offset)
        date_str = entry_date.isoformat()
        # Replace work entry with PTO
        data[date_str] = [
            {
                "title": "Paid Time Off in Hours",
                "type": "Time Tracking",
                "hours": pto_hours
            }
        ]

    return data

def generate_empty_week() -> dict:
    """Generate an empty week (no entries)."""
    return {}

def generate_month_data(
    year: int,
    month: int,
    pattern: str = "full"
) -> dict[str, list[dict[str, Any]]]:
    """Generate calendar data for an entire month.

    Patterns:
    - "full": Full 8-hour days Mon-Fri
    - "partial": Mix of full and partial days
    - "with_pto": Include some PTO days
    - "empty": No entries
    """
    from calendar import monthcalendar

    data = {}
    weeks = monthcalendar(year, month)

    for week in weeks:
        # Find Monday of the week
        monday_day = week[0]
        if monday_day == 0:
            continue  # Week starts in previous month

        week_start = date(year, month, monday_day)

        if pattern == "full":
            data.update(generate_full_work_week(week_start))
        elif pattern == "partial":
            # Vary hours
            data.update(generate_partial_week(week_start, [8, 6, 8, 4, 8]))
        elif pattern == "with_pto":
            # One day of PTO per week
            data.update(generate_week_with_pto(week_start, [2]))  # Wednesday off
        elif pattern == "empty":
            pass

    return data
```

### Pre-built Test Scenarios

```python
# tests/e2e/fixtures/scenarios.py

from dataclasses import dataclass
from datetime import date
from typing import Any

@dataclass
class TestScenario:
    """A complete test scenario configuration."""
    name: str
    credentials: dict[str, str]
    calendar_data: dict[str, list[dict[str, Any]]]
    expected_working_hours: float
    expected_time_off_hours: float
    expected_working_days: int

# Successful login with full work month
SCENARIO_FULL_MONTH = TestScenario(
    name="full_month",
    credentials={"testuser": "testpass"},
    calendar_data={
        # November 2025: 20 working days × 8 hours = 160 hours
        **generate_month_data(2025, 11, "full"),
    },
    expected_working_hours=160.0,
    expected_time_off_hours=0.0,
    expected_working_days=20,
)

# Month with PTO
SCENARIO_WITH_PTO = TestScenario(
    name="with_pto",
    credentials={"testuser": "testpass"},
    calendar_data={
        # Week with 2 days PTO
        "2025-11-03": [
            {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
        ],
        "2025-11-04": [
            {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
        ],
        "2025-11-05": [
            {"title": "Paid Time Off in Hours", "type": "Time Tracking", "hours": 8}
        ],
        "2025-11-06": [
            {"title": "Paid Time Off in Hours", "type": "Time Tracking", "hours": 8}
        ],
        "2025-11-07": [
            {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
        ],
    },
    expected_working_hours=24.0,
    expected_time_off_hours=16.0,
    expected_working_days=5,
)

# Invalid credentials scenario
SCENARIO_BAD_CREDENTIALS = TestScenario(
    name="bad_credentials",
    credentials={"testuser": "wrongpass"},
    calendar_data={},
    expected_working_hours=0.0,
    expected_time_off_hours=0.0,
    expected_working_days=0,
)

# Empty month (no entries)
SCENARIO_EMPTY_MONTH = TestScenario(
    name="empty_month",
    credentials={"testuser": "testpass"},
    calendar_data={},
    expected_working_hours=0.0,
    expected_time_off_hours=0.0,
    expected_working_days=0,
)
```

## Pytest Fixtures

### Server Lifecycle Management

```python
# tests/e2e/conftest.py

import pytest
import socket
import threading
from datetime import date
from typing import Generator
from werkzeug.serving import make_server

from tests.e2e.mock_servers.app import create_app
from iptax.models import WorkdayConfig

# Domain names for mock servers
SSO_DOMAIN = "sso.localhost"
WORKDAY_DOMAIN = "myworkday.com.localhost"


def get_free_port() -> int:
    """Get a free port by binding to port 0 and reading the assigned port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


class MockServerThread(threading.Thread):
    """Thread that runs the mock Flask server."""

    def __init__(self, app, host: str, port: int):
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
def mock_calendar_data() -> dict:
    """Override this fixture to provide custom calendar data."""
    from tests.e2e.fixtures.calendar_data import generate_full_work_week
    from datetime import date, timedelta

    # Default: current week with full work days
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    return generate_full_work_week(week_start)


@pytest.fixture
def mock_credentials() -> dict[str, str]:
    """Override this fixture to provide custom test credentials."""
    return {"testuser": "testpass"}


@pytest.fixture
def mock_server(
    mock_calendar_data: dict,
    mock_credentials: dict[str, str],
) -> Generator[MockServerThread, None, None]:
    """Start mock SSO/Workday server for e2e testing.

    The server runs in a background thread and is automatically
    shut down after the test completes.

    Uses automatic port selection to avoid conflicts.
    """
    port = get_free_port()

    app = create_app(
        calendar_data=mock_calendar_data,
        credentials=mock_credentials,
        sso_domain=SSO_DOMAIN,
        workday_domain=WORKDAY_DOMAIN,
        port=port,
    )

    # Server binds to 0.0.0.0 to accept connections from any loopback address
    # This is necessary because:
    # - *.localhost may resolve to ::1 (IPv6) or different 127.x.x.x addresses
    # - /etc/hosts may define different IPs for each domain (127.0.1.1, 127.0.2.1)
    server_thread = MockServerThread(app, "0.0.0.0", port)
    server_thread.start()

    # Wait for server to be ready
    import time
    import urllib.request
    for _ in range(50):  # 5 second timeout
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health")
            break
        except Exception:
            time.sleep(0.1)

    yield server_thread

    server_thread.shutdown()


@pytest.fixture
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
```

### Hosts File Configuration

The `.localhost` TLD is reserved (RFC 6761) and typically resolves automatically, but
behavior varies by system:

- **Linux**: May resolve to `::1` (IPv6) or `127.0.0.1`
- **macOS**: Usually resolves to `127.0.0.1`
- **Windows**: Requires explicit hosts entries

For consistent behavior, add to `/etc/hosts`:

```text
127.0.1.1   sso.localhost
127.0.2.1   myworkday.com.localhost
```

Using different loopback addresses (127.0.1.1, 127.0.2.1) ensures the domains are truly
separate, even though they hit the same server bound to `0.0.0.0`.

> **Why `0.0.0.0`?** The server binds to all interfaces because:
>
> - `*.localhost` may resolve to `::1` (IPv6) on some systems
> - Custom `/etc/hosts` entries may use different 127.x.x.x addresses
> - Binding only to `127.0.0.1` would reject connections from other addresses

## Example E2E Test

```python
# tests/e2e/test_workday_e2e.py

import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from iptax.workday.client import WorkdayClient
from iptax.models import WorkHours


@pytest.fixture
def mock_calendar_data():
    """Provide test data for November 2025."""
    return {
        # Week 1: Nov 3-7
        "2025-11-03": [
            {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
        ],
        "2025-11-04": [
            {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
        ],
        "2025-11-05": [
            {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
        ],
        "2025-11-06": [
            {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
        ],
        "2025-11-07": [
            {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
        ],
    }


@pytest.mark.e2e
class TestWorkdayIntegration:
    """E2E tests for Workday integration using mock servers."""

    async def test_successful_login_and_data_extraction(
        self,
        mock_server,
        mock_workday_config,
    ):
        """Test complete flow: login → navigate → extract hours.

        Verifies:
        1. Navigation to SSO (sso.localhost)
        2. Login form submission
        3. Redirect to Workday (myworkday.com.localhost)
        4. Data extraction via calendar API
        """
        # Arrange
        client = WorkdayClient(mock_workday_config)
        start_date = date(2025, 11, 1)
        end_date = date(2025, 11, 30)

        # Mock the credential prompt to return test credentials
        with patch(
            "iptax.workday.prompts.prompt_credentials_async",
            new_callable=AsyncMock,
            return_value=("testuser", "testpass"),
        ):
            # Act
            result = await client.fetch_work_hours(
                start_date=start_date,
                end_date=end_date,
                headless=True,
            )

        # Assert
        assert isinstance(result, WorkHours)
        assert result.total_hours == 40.0  # One week of data
        assert result.working_days > 0

    async def test_invalid_credentials_raises_error(
        self,
        mock_server,
        mock_workday_config,
    ):
        """Test that invalid credentials raise AuthenticationError."""
        from iptax.workday.models import AuthenticationError

        client = WorkdayClient(mock_workday_config)

        # Mock credential prompt to return wrong password
        with patch(
            "iptax.workday.prompts.prompt_credentials_async",
            new_callable=AsyncMock,
            return_value=("testuser", "wrongpass"),
        ):
            with pytest.raises(AuthenticationError):
                await client.fetch_work_hours(
                    start_date=date(2025, 11, 1),
                    end_date=date(2025, 11, 30),
                    headless=True,
                )

    async def test_empty_calendar_returns_zero_hours(
        self,
        mock_server,
        mock_workday_config,
    ):
        """Test extraction when no calendar entries exist."""
        # Override calendar data to be empty for this test
        mock_server.app.config['CALENDAR_DATA'] = {}

        client = WorkdayClient(mock_workday_config)

        with patch(
            "iptax.workday.prompts.prompt_credentials_async",
            new_callable=AsyncMock,
            return_value=("testuser", "testpass"),
        ):
            result = await client.fetch_work_hours(
                start_date=date(2025, 11, 1),
                end_date=date(2025, 11, 30),
                headless=True,
            )

        assert result.total_hours == 0.0

    async def test_week_navigation(
        self,
        mock_server,
        mock_workday_config,
    ):
        """Test that week navigation triggers API calls correctly."""
        # Set up multi-week data
        mock_server.app.config['CALENDAR_DATA'] = {
            # Week 1
            "2025-11-03": [
                {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
            ],
            # Week 2
            "2025-11-10": [
                {"title": "Regular/Time Worked", "type": "Time Tracking", "hours": 8}
            ],
        }

        client = WorkdayClient(mock_workday_config)

        with patch(
            "iptax.workday.prompts.prompt_credentials_async",
            new_callable=AsyncMock,
            return_value=("testuser", "testpass"),
        ):
            result = await client.fetch_work_hours(
                start_date=date(2025, 11, 1),
                end_date=date(2025, 11, 15),
                headless=True,
            )

        # Should have collected data from both weeks
        assert result.total_hours == 16.0
```

## Configuration

### Automatic Port Selection

The mock server uses automatic port selection to avoid conflicts:

```python
def get_free_port() -> int:
    """Get a free port by binding to port 0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 0))
        s.listen(1)
        return s.getsockname()[1]
```

This eliminates port conflicts when running tests in parallel or when another process is
using the default port.

### Domain Resolution

| Domain                    | Suggested IP | Purpose                        |
| ------------------------- | ------------ | ------------------------------ |
| `sso.localhost`           | `127.0.1.1`  | SSO login (non-Workday domain) |
| `myworkday.com.localhost` | `127.0.2.1`  | Workday app (passes URL check) |

The server binds to `0.0.0.0` to accept connections from any of these addresses.

### Running Tests

```bash
# Run all e2e tests
make e2e

# Run only Workday e2e tests
pytest tests/e2e/test_workday_e2e.py -v

# Run with visible browser for debugging
HEADLESS=0 pytest tests/e2e/test_workday_e2e.py -v
```

## Implementation Checklist

1. [ ] Create `tests/e2e/mock_servers/` directory structure
1. [ ] Implement Flask app with SSO, Workday, and API routes
1. [ ] Create HTML templates matching production selectors
1. [ ] Implement calendar data generators
1. [ ] Add pytest fixtures for server lifecycle
1. [ ] Write initial e2e test for happy path
1. [ ] Add tests for error scenarios
1. [ ] Update Makefile with e2e test targets
1. [ ] Document in testing.md

## Security Considerations

1. **Test Credentials**: Only use in test environment; never in production
1. **Port Binding**: Use localhost only to prevent external access
1. **Session Management**: Simple in-memory sessions (not production-grade)

## Future Enhancements

1. **Response Delays**: Add configurable latency to simulate real network
1. **Error Injection**: Simulate network failures and timeouts
1. **Multi-User**: Support concurrent test sessions
1. **Recording Mode**: Capture real Workday responses for replay
