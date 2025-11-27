"""Flask application for mock SSO and Workday servers."""

from typing import Any

from flask import Flask

from tests.e2e.mock_servers.api_routes import api
from tests.e2e.mock_servers.sso_routes import sso
from tests.e2e.mock_servers.workday_routes import workday

# In-memory token store for SSO->Workday token exchange
# Format: {token: username}
_token_store: dict[str, str] = {}


def create_app(
    calendar_data: dict[str, list[dict[str, Any]]] | None = None,
    credentials: dict[str, str] | None = None,
    sso_domain: str = "sso.localhost",
    workday_domain: str = "myworkday.com.localhost",
    port: int = 5080,
) -> Flask:
    """Create Flask app with mock SSO and Workday routes.

    Args:
        calendar_data: Dictionary mapping date strings to calendar entries
        credentials: Dictionary mapping usernames to passwords
        sso_domain: Domain for SSO server
        workday_domain: Domain for Workday server
        port: Port number for the server

    Returns:
        Configured Flask application
    """
    app = Flask(__name__, template_folder="templates")

    # Configure app
    # Secret key is hardcoded for testing only - not used in production (noqa: S105)
    app.config["SECRET_KEY"] = "test-secret-key-for-e2e-only"  # noqa: S105
    app.config["CALENDAR_DATA"] = calendar_data or {}
    app.config["TEST_CREDENTIALS"] = credentials or {"testuser": "testpass"}
    app.config["SSO_DOMAIN"] = sso_domain
    app.config["WORKDAY_DOMAIN"] = workday_domain
    app.config["SERVER_PORT"] = port
    app.config["TOKEN_STORE"] = _token_store

    # Register blueprints
    app.register_blueprint(sso)
    app.register_blueprint(workday)
    app.register_blueprint(api)

    # Health check endpoint
    @app.route("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
