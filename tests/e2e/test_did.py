"""End-to-end tests for did integration.

These tests run against real did configuration and providers.
They are skipped if:
- did config file doesn't exist at ~/.did/config or path from DID_CONFIG env var
- No providers are configured

Set DID_CONFIG environment variable to use a custom did config file path.

Note: These tests fetch changes from did ONCE per test run to minimize API calls.
"""

import os
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from iptax.did import fetch_changes
from iptax.models import (
    Change,
    DidConfig,
    EmployeeInfo,
    ProductConfig,
    Repository,
    Settings,
)


def get_did_config_path() -> Path | None:
    """Get did config path from env var or default location.

    Returns:
        Path to did config file if it exists, None otherwise
    """
    # Check environment variable first
    if config_path := os.environ.get("DID_CONFIG"):
        path = Path(config_path).expanduser()
        if path.exists():
            return path

    # Check default location
    default_path = Path.home() / ".did" / "config"
    if default_path.exists():
        return default_path

    return None


def get_providers_from_config(config_path: Path) -> list[str]:
    """Extract provider names from did config file.

    Args:
        config_path: Path to did config file

    Returns:
        List of provider section names (e.g., ["github.com", "gitlab.example.org"])
    """
    providers = []

    with config_path.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            # Section headers are like [github.com] or [gitlab.example.org]
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                # Skip [general] section
                if section != "general":
                    providers.append(section)

    return providers


# Check if did config exists before running any tests
did_config_path = get_did_config_path()
skip_reason = "did config not found - set DID_CONFIG env var or create ~/.did/config"
requires_did_config = pytest.mark.skipif(
    did_config_path is None,
    reason=skip_reason,
)


@pytest.fixture(scope="session")
def real_settings() -> Settings:
    """Create settings using real did config file.

    This fixture creates a Settings object configured to use the actual
    did config file from the system, enabling real e2e testing.
    """
    config_path = get_did_config_path()
    if config_path is None:
        pytest.skip(skip_reason)

    providers = get_providers_from_config(config_path)
    if not providers:
        pytest.skip("No providers configured in did config file")

    return Settings(
        employee=EmployeeInfo(
            name="E2E Test User",
            supervisor="E2E Test Supervisor",
        ),
        product=ProductConfig(name="E2E Test Product"),
        did=DidConfig(
            config_path=str(config_path),
            providers=providers,
        ),
    )


@pytest.fixture(scope="session")
def test_date_range() -> tuple[date, date]:
    """Provide a recent date range for testing.

    Uses the last 30 days to increase likelihood of finding changes.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    return start_date, end_date


@pytest.fixture(scope="session")
def fetched_changes(
    real_settings: Settings,
    test_date_range: tuple[date, date],
) -> list[Change]:
    """Fetch changes once per session and reuse across ALL tests.

    This fixture fetches changes from the real did SDK exactly once
    and caches the result for all tests, making the suite fast.
    """
    start_date, end_date = test_date_range
    return fetch_changes(real_settings, start_date, end_date)


@pytest.mark.e2e
@requires_did_config
class TestDidIntegration:
    """Real end-to-end tests using actual did configuration.

    All tests use a single shared fetch that happens once per session.
    """

    def test_fetch_executes_successfully(
        self,
        fetched_changes: list[Change],
    ) -> None:
        """Test that fetch_changes executes successfully.

        Verifies returned data is a list (may be empty).
        """
        assert isinstance(fetched_changes, list)

    def test_returns_change_objects(
        self,
        fetched_changes: list[Change],
    ) -> None:
        """Test that all returned items are proper Change objects."""
        if not fetched_changes:
            pytest.skip("No changes found in test date range")

        # All items should be Change objects with required attributes
        assert all(isinstance(c, Change) for c in fetched_changes)

        for change in fetched_changes:
            assert change.title
            assert isinstance(change.repository, Repository)
            assert change.number > 0
            assert change.repository.host
            assert change.repository.path
            assert change.repository.provider_type in ("github", "gitlab")

    def test_repository_structure(
        self,
        fetched_changes: list[Change],
    ) -> None:
        """Test that repositories have correct structure."""
        if not fetched_changes:
            pytest.skip("No changes found in test date range")

        for change in fetched_changes:
            repo = change.repository

            # Verify display name formatting
            display_name = repo.get_display_name()
            assert " / " in display_name

            # Verify URL generation
            url = repo.get_url()
            assert url.startswith("https://")
            assert repo.host in url
            assert repo.path in url

            # Verify __str__ works
            assert str(repo) == display_name

    def test_url_construction(
        self,
        fetched_changes: list[Change],
    ) -> None:
        """Test that PR/MR URLs are constructed correctly."""
        if not fetched_changes:
            pytest.skip("No changes found in test date range")

        for change in fetched_changes:
            url = change.get_url()

            # Verify URL format based on provider
            if change.repository.provider_type == "github":
                assert "/pull/" in url
            else:  # gitlab
                assert "/-/merge_requests/" in url

            assert url.endswith(str(change.number))

            # Verify change_id and display reference
            assert "#" in change.get_change_id()  # change_id always uses #
            display_ref = change.get_display_reference()
            # GitHub uses #, GitLab uses !
            if change.repository.provider_type == "github":
                assert f"#{change.number}" in display_ref
            else:  # gitlab
                assert f"!{change.number}" in display_ref

    def test_emoji_cleaning(
        self,
        fetched_changes: list[Change],
    ) -> None:
        """Test that emoji codes are cleaned from titles."""
        if not fetched_changes:
            pytest.skip("No changes found in test date range")

        # Pattern for emoji codes like :rocket:, :bug:, :sparkles:
        emoji_pattern = re.compile(r":[a-z_]+:")

        for change in fetched_changes:
            # Verify no common emoji codes remain
            assert ":rocket:" not in change.title
            assert ":bug:" not in change.title
            assert ":sparkles:" not in change.title

            # Title shouldn't have emoji pattern (e.g., :word:)
            if change.title:
                match = emoji_pattern.search(change.title)
                assert match is None, f"Found emoji {match.group()} in: {change.title}"

    def test_provider_filtering(
        self,
        fetched_changes: list[Change],
        real_settings: Settings,
    ) -> None:
        """Test that only configured providers are used."""
        if not fetched_changes:
            pytest.skip("No changes found in test date range")

        configured_providers = real_settings.did.providers

        for change in fetched_changes:
            # Host should match one of the configured providers (prefix matching)
            # e.g., host "gitlab.cee.redhat.com" matches provider "gitlab.cee"
            host_matches = any(
                change.repository.host == provider
                or change.repository.host.startswith(f"{provider}.")
                for provider in configured_providers
            )
            assert host_matches, (
                f"Host {change.repository.host!r} not matched by "
                f"any provider: {configured_providers}"
            )

    def test_config_validation_error(self) -> None:
        """Test that validation error is raised for invalid config.

        Note: DidConfig validates at creation time via Pydantic.
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            Settings(
                employee=EmployeeInfo(name="Test", supervisor="Test"),
                product=ProductConfig(name="Test"),
                did=DidConfig(
                    config_path="/nonexistent/path",
                    providers=["github.com"],
                ),
            )

        assert "did config file not found" in str(exc_info.value)
