"""Unit tests for iptax.workday.browser module."""

from iptax.models import WorkdayConfig
from iptax.workday.browser import _build_firefox_prefs


class TestBuildFirefoxPrefs:
    """Test _build_firefox_prefs function for Kerberos configuration."""

    def test_sso_kerberos_with_trusted_uris_sets_prefs(self):
        """Test that sso+kerberos with trusted_uris sets Kerberos prefs."""
        config = WorkdayConfig(
            enabled=True,
            url="https://workday.example.org",
            auth="sso+kerberos",
            trusted_uris=["*.example.org", "*.sso.example.org"],
        )

        prefs = _build_firefox_prefs(config)

        assert "network.negotiate-auth.trusted-uris" in prefs
        assert "network.negotiate-auth.delegation-uris" in prefs
        assert (
            "*.example.org,*.sso.example.org"
            in prefs["network.negotiate-auth.trusted-uris"]
        )

    def test_sso_without_kerberos_no_prefs(self):
        """Test that sso (without kerberos) explicitly disables SPNEGO.

        Even with trusted_uris configured, when auth="sso", Kerberos prefs
        should be set to empty strings, ensuring the browser shows the login
        form instead of auto-authenticating with existing Kerberos tickets.
        """
        config = WorkdayConfig(
            enabled=True,
            url="https://workday.example.org",
            auth="sso",
            trusted_uris=["*.example.org", "*.sso.example.org"],
        )

        prefs = _build_firefox_prefs(config)

        # Should set empty URIs to explicitly disable SPNEGO
        assert prefs["network.negotiate-auth.trusted-uris"] == ""
        assert prefs["network.negotiate-auth.delegation-uris"] == ""

    def test_sso_kerberos_without_trusted_uris_no_prefs(self):
        """Test that sso+kerberos without trusted_uris disables SPNEGO."""
        config = WorkdayConfig(
            enabled=True,
            url="https://workday.example.org",
            auth="sso+kerberos",
            trusted_uris=[],
        )

        prefs = _build_firefox_prefs(config)

        # Empty trusted_uris means SPNEGO is disabled
        assert prefs["network.negotiate-auth.trusted-uris"] == ""
        assert prefs["network.negotiate-auth.delegation-uris"] == ""

    def test_sso_without_kerberos_and_no_trusted_uris(self):
        """Test that sso without kerberos explicitly disables SPNEGO."""
        config = WorkdayConfig(
            enabled=True,
            url="https://workday.example.org",
            auth="sso",
            trusted_uris=[],
        )

        prefs = _build_firefox_prefs(config)

        # Should set empty URIs to explicitly disable SPNEGO
        assert prefs["network.negotiate-auth.trusted-uris"] == ""
        assert prefs["network.negotiate-auth.delegation-uris"] == ""
