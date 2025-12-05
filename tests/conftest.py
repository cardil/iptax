"""Pytest configuration and shared fixtures for iptax-reporter tests."""

from pathlib import Path

import pytest
from _pytest.config import Config


def pytest_configure(config: Config) -> None:
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "requires_did: Tests requiring did installation")
    config.addinivalue_line(
        "markers", "requires_workday: Tests requiring Workday access"
    )


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch) -> Path:
    """Set up isolated HOME environment for testing.

    This fixture ensures that HOME is set to a temp directory and that
    XDG_CONFIG_HOME is unset to avoid interference from the CI environment.
    This is critical for tests that rely on default path resolution.

    Returns:
        Path: The temporary home directory
    """
    # Clear XDG_CONFIG_HOME to ensure HOME is used
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    # Set HOME to temp directory
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def make_judgment():
    """Factory fixture for creating Judgment instances with defaults."""
    from iptax.ai.models import Decision, Judgment

    def _make(
        change_id: str = "test#1",
        decision: Decision | str = Decision.INCLUDE,
        reasoning: str = "Test reasoning",
        product: str = "Test Product",
        **kwargs: str | Decision | None,
    ) -> Judgment:
        """Create a Judgment with sensible defaults for testing.

        Args:
            change_id: Change ID (default: "test#1")
            decision: AI decision (default: INCLUDE)
            reasoning: AI reasoning (default: "Test reasoning")
            product: Product name (default: "Test Product")
            **kwargs: Additional Judgment fields (url, description,
                ai_provider, user_decision)

        Returns:
            Judgment instance
        """
        # Set defaults for fields with empty string defaults in the model
        defaults = {
            "url": "https://test.com/pr/1",
            "description": "Test change",
            "ai_provider": "test-provider",
        }
        defaults.update(kwargs)

        return Judgment(
            change_id=change_id,
            decision=decision,
            reasoning=reasoning,
            product=product,
            **defaults,
        )

    return _make
