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
