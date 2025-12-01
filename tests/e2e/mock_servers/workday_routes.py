"""Workday application routes for mock server."""

from datetime import date, timedelta

from flask import Blueprint, current_app, redirect, render_template, request, session

workday = Blueprint("workday", __name__)

# Current week state (managed globally for tests)
_current_week_start = None


@workday.before_request
def require_auth():
    """Require authentication for all Workday routes except SSO callback."""
    # Skip auth check for SSO callback (it establishes the session)
    if request.endpoint == "workday.sso_callback":
        return None

    if not session.get("authenticated"):
        # Check for Kerberos auto-auth (simulates valid Kerberos ticket)
        auto_auth = current_app.config.get("AUTO_AUTH_SESSION")
        if auto_auth:
            session["authenticated"] = True
            session["username"] = auto_auth
            return None

        # No Kerberos - redirect to SSO login
        sso_domain = current_app.config.get("SSO_DOMAIN", "sso.localhost")
        port = current_app.config.get("SERVER_PORT", 5080)
        return redirect(f"http://{sso_domain}:{port}/sso/login")
    return None  # Explicitly return None when authenticated


@workday.route("/sso/callback")
def sso_callback():
    """SSO callback - validate token and create session.

    This simulates SAML assertion/OAuth token validation.
    """
    token = request.args.get("token")
    token_store = current_app.config.get("TOKEN_STORE", {})

    username = token_store.pop(token, None)  # One-time use token
    if username:
        session["authenticated"] = True
        session["username"] = username
        return redirect("/d/home.htmld")

    # Invalid/expired token - redirect to SSO
    sso_domain = current_app.config.get("SSO_DOMAIN", "sso.localhost")
    port = current_app.config.get("SERVER_PORT", 5080)
    return redirect(f"http://{sso_domain}:{port}/sso/login")


@workday.route("/")
def root():
    """Root path - redirect to home."""
    return redirect("/d/home.htmld")


@workday.route("/d/home.htmld")
def home():
    """Workday home page with Time button."""
    return render_template("workday_home.html")


@workday.route("/d/time.htmld")
def time_page():
    """Time page with week selection and calendar."""

    global _current_week_start  # noqa: PLW0603

    # Initialize week if not set
    if _current_week_start is None:
        today = date.today()
        _current_week_start = today - timedelta(days=today.weekday())

    # Handle week navigation via query params
    action = request.args.get("action")
    if action == "prev":
        _current_week_start -= timedelta(days=7)
    elif action == "next":
        _current_week_start += timedelta(days=7)
    elif "date" in request.args:
        # Direct date selection from modal
        _current_week_start = date.fromisoformat(request.args["date"])
        # Align to Monday
        _current_week_start -= timedelta(days=_current_week_start.weekday())

    week_end = _current_week_start + timedelta(days=6)

    return render_template(
        "workday_time.html",
        week_start=_current_week_start,
        week_end=week_end,
    )
