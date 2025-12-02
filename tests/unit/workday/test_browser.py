"""Unit tests for iptax.workday.browser module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from iptax.models import WorkdayConfig
from iptax.workday.browser import (
    _build_firefox_prefs,
    dump_debug_snapshot,
    setup_browser_logging,
    setup_profile_directory,
)


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


class TestSetupProfileDirectory:
    """Test setup_profile_directory function."""

    def test_creates_fresh_profile_directory(self):
        """Test that a fresh profile directory is created."""
        with (
            patch("iptax.workday.browser.get_cache_dir") as mock_cache,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            mock_cache.return_value = Path(tmpdir)
            result = setup_profile_directory()
            assert "firefox-profile" in result
            assert Path(result).exists()

    def test_removes_existing_profile_directory(self):
        """Test that existing profile is removed before creating new one."""
        with (
            patch("iptax.workday.browser.get_cache_dir") as mock_cache,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            mock_cache.return_value = Path(tmpdir)
            profile_dir = Path(tmpdir) / "firefox-profile"
            profile_dir.mkdir()
            marker = profile_dir / "old_marker.txt"
            marker.write_text("old content")

            result = setup_profile_directory()
            assert Path(result).exists()
            assert not marker.exists()  # Old content was removed


class TestSetupBrowserLogging:
    """Test setup_browser_logging function."""

    def test_creates_log_file_and_handlers(self):
        """Test that browser logging creates log file and attaches handlers."""
        with (
            patch("iptax.workday.browser.get_cache_dir") as mock_cache,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            mock_cache.return_value = Path(tmpdir)
            mock_page = MagicMock()
            mock_page.on = MagicMock()

            log_file = setup_browser_logging(mock_page)

            try:
                # Check that handlers were attached
                assert mock_page.on.call_count == 4
                event_types = [call[0][0] for call in mock_page.on.call_args_list]
                assert "console" in event_types
                assert "pageerror" in event_types
                assert "response" in event_types
                assert "request" in event_types

                # Check log file was created
                log_path = Path(tmpdir) / "browser-devconsole.log"
                assert log_path.exists()
            finally:
                log_file.close()


class TestDumpDebugSnapshot:
    """Test dump_debug_snapshot function."""

    @pytest.mark.asyncio
    async def test_creates_snapshot_file(self):
        """Test that debug snapshot creates yaml file."""
        with (
            patch("iptax.workday.browser.get_cache_dir") as mock_cache,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            mock_cache.return_value = Path(tmpdir)
            mock_page = MagicMock()
            mock_page.url = "https://example.com/test"
            mock_page.title = MagicMock(return_value="Test Page")
            mock_page.accessibility = MagicMock()
            mock_page.accessibility.snapshot = MagicMock(
                return_value={"role": "document"}
            )
            mock_page.screenshot = MagicMock()

            error = ValueError("Test error")
            result = await dump_debug_snapshot(mock_page, "test_context", error)

            assert "test_context" in result
            assert Path(result).exists()
            content = Path(result).read_text()
            assert "test_context" in content
            assert "Test error" in content

    @pytest.mark.asyncio
    async def test_handles_accessibility_snapshot_failure(self):
        """Test graceful handling of accessibility snapshot failure."""
        with (
            patch("iptax.workday.browser.get_cache_dir") as mock_cache,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            mock_cache.return_value = Path(tmpdir)
            mock_page = MagicMock()
            mock_page.url = "https://example.com"
            mock_page.title = MagicMock(side_effect=Exception("Title failed"))
            mock_page.accessibility = MagicMock()
            mock_page.accessibility.snapshot = MagicMock(
                side_effect=Exception("Snapshot failed")
            )
            mock_page.screenshot = MagicMock(side_effect=Exception("Screenshot failed"))

            error = ValueError("Original error")
            result = await dump_debug_snapshot(mock_page, "error_context", error)

            assert Path(result).exists()

    @pytest.mark.asyncio
    async def test_uses_timestamp_when_env_set(self):
        """Test that timestamp is included when env var is set."""
        with (
            patch("iptax.workday.browser.get_cache_dir") as mock_cache,
            patch.dict("os.environ", {"IPTAX_WORKDAY_DUMP_TS": "true"}),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            mock_cache.return_value = Path(tmpdir)
            mock_page = MagicMock()
            mock_page.url = "https://example.com"
            mock_page.title = MagicMock(return_value="Title")
            mock_page.accessibility = MagicMock()
            mock_page.accessibility.snapshot = MagicMock(return_value={})
            mock_page.screenshot = MagicMock()

            error = ValueError("Error")
            result = await dump_debug_snapshot(mock_page, "ts_context", error)

            # Should contain timestamp in filename
            filename = Path(result).name
            assert "ts_context_" in filename
