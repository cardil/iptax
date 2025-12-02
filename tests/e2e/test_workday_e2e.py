"""End-to-end tests for Workday integration using mock servers.

This module tests the core Workday authentication flows:
1. Kerberos path - already authenticated, no SSO form
2. SSO path - login form with retry on wrong password
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from iptax.models import WorkdayConfig, WorkHours
from iptax.workday.client import WorkdayClient
from tests.e2e.conftest import MockServerThread


@pytest.mark.e2e
@pytest.mark.timeout(60)  # 60 seconds per test (should be quick vs mock server)
class TestWorkdayIntegration:
    """E2E tests for Workday integration using mock servers.

    Only essential happy path tests:
    1. Kerberos path (no SSO form)
    2. SSO path with retry (wrong password first, then correct)
    """

    @pytest.mark.asyncio
    async def test_kerberos_auth_path(
        self,
        mock_server: MockServerThread,
        unique_firefox_profile: str,  # noqa: ARG002 - Enables parallel tests
    ):
        """Test Kerberos authentication - no SSO form, direct to Workday.

        Simulates a user with valid Kerberos ticket who bypasses SSO.
        """
        # Configure for Kerberos mode - set a session to skip SSO form
        mock_server.app.config["AUTO_AUTH_SESSION"] = "kerberos_user_session"

        # Use sso+kerberos auth mode
        config = WorkdayConfig(
            enabled=True,
            url=mock_server.workday_url,
            auth="sso+kerberos",
        )

        client = WorkdayClient(config)
        start_date = date(2025, 11, 3)
        end_date = date(2025, 11, 14)  # 2 weeks

        result = await client.fetch_work_hours(
            start_date=start_date,
            end_date=end_date,
            headless=True,
        )

        assert isinstance(result, WorkHours)
        # 2 weeks: 10 business days, 1 PTO on Nov 12 (Wednesday of week 2)
        # total_hours = all logged hours (working + PTO)
        assert result.total_hours == 80.0  # 10 days x 8 hours (includes PTO)
        assert result.working_days == 10  # 10 business days in range
        assert result.absence_days == 1  # 1 PTO day

    @pytest.mark.asyncio
    async def test_sso_auth_with_retry(
        self,
        mock_server: MockServerThread,
        mock_workday_config: WorkdayConfig,
        unique_firefox_profile: str,  # noqa: ARG002 - Enables parallel tests
    ):
        """Test SSO auth: wrong password first, then correct on retry.

        Verifies:
        1. First login attempt with wrong password fails
        2. Second attempt with correct password succeeds
        3. Data is extracted correctly after successful login
        """
        # Ensure SSO form is used (not auto-auth from previous test)
        mock_server.app.config["AUTO_AUTH_SESSION"] = None

        client = WorkdayClient(mock_workday_config)
        start_date = date(2025, 11, 3)
        end_date = date(2025, 11, 14)  # 2 weeks

        # Track credential attempts
        attempts: list[int] = []

        async def mock_prompt() -> tuple[str, str]:
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                return ("testuser", "wrongpass")  # First attempt: wrong password
            return ("testuser", "testpass")  # Second attempt: correct password

        with patch(
            "iptax.workday.auth.prompt_credentials_async",
            new_callable=AsyncMock,
            side_effect=mock_prompt,
        ):
            result = await client.fetch_work_hours(
                start_date=start_date,
                end_date=end_date,
                headless=True,
            )

        # Verify we had to retry
        assert len(attempts) == 2, "Should have made 2 credential attempts"

        # Verify data extraction worked
        assert isinstance(result, WorkHours)
        # 2 weeks: 10 business days, 1 PTO on Nov 12 (Wednesday of week 2)
        # total_hours = all logged hours (working + PTO)
        assert result.total_hours == 80.0  # 10 days x 8 hours (includes PTO)
        assert result.working_days == 10  # 10 business days in range
        assert result.absence_days == 1  # 1 PTO day
