"""SSO authentication routes for mock server."""

import secrets

from flask import Blueprint, current_app, redirect, render_template, request, session

sso = Blueprint("sso", __name__)


@sso.route("/sso/login")
def login_page():
    """Render SSO login form matching real selectors."""
    error = request.args.get("error")
    return render_template("sso_login.html", error=error)


@sso.route("/sso/login", methods=["POST"])
def login_submit():
    """Handle login form submission.

    On success: Set session and redirect to Workday (myworkday.com.localhost)
    On failure: Reload login page with error (triggers bad credentials detection)
    """
    username = request.form.get("username")
    password = request.form.get("password")

    credentials = current_app.config.get("TEST_CREDENTIALS", {})
    workday_domain = current_app.config.get("WORKDAY_DOMAIN", "myworkday.com.localhost")
    port = current_app.config.get("SERVER_PORT", 5080)

    if credentials.get(username) == password:
        # Generate a one-time token for SSO->Workday exchange
        token = secrets.token_urlsafe(32)
        token_store = current_app.config.get("TOKEN_STORE", {})
        token_store[token] = username

        # Redirect to Workday with token (simulates SAML assertion)
        return redirect(f"http://{workday_domain}:{port}/sso/callback?token={token}")

    # Reload login page with error (triggers bad credentials detection)
    return render_template("sso_login.html", error="Invalid credentials")


@sso.route("/sso/logout")
def logout():
    """Clear session and redirect to login."""
    session.clear()
    sso_domain = current_app.config.get("SSO_DOMAIN", "sso.localhost")
    port = current_app.config.get("SERVER_PORT", 5080)
    return redirect(f"http://{sso_domain}:{port}/sso/login")
