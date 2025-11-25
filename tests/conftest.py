"""Pytest configuration and shared fixtures for iptax-reporter tests."""

import os
from collections.abc import Generator
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
def tmp_config_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide a temporary config directory for testing."""
    config_dir = tmp_path / "config" / "iptax"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Set environment variable to use temp config
    old_config_home = os.environ.get("XDG_CONFIG_HOME")
    os.environ["XDG_CONFIG_HOME"] = str(tmp_path / "config")

    yield config_dir

    # Restore original config
    if old_config_home:
        os.environ["XDG_CONFIG_HOME"] = old_config_home
    else:
        os.environ.pop("XDG_CONFIG_HOME", None)


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide a temporary cache directory for testing."""
    cache_dir = tmp_path / "cache" / "iptax"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Set environment variable to use temp cache
    old_cache_home = os.environ.get("XDG_CACHE_HOME")
    os.environ["XDG_CACHE_HOME"] = str(tmp_path / "cache")

    yield cache_dir

    # Restore original cache
    if old_cache_home:
        os.environ["XDG_CACHE_HOME"] = old_cache_home
    else:
        os.environ.pop("XDG_CACHE_HOME", None)


@pytest.fixture
def sample_did_output() -> str:
    """Provide sample output from the did tool."""
    return """# Changes

* [feat: Add new feature (knative-extensions/kn-plugin-event#421)](https://github.com/knative-extensions/kn-plugin-event/pull/421)
* [fix: Fix bug in handler (cncf/toolbox#040)](https://github.com/cncf/toolbox/pull/40)
* [docs: Update documentation (knative/docs#1290)](https://github.com/knative/docs/pull/1290)

# Projects

* [knative-extensions / kn-plugin-event](https://github.com/knative-extensions/kn-plugin-event)
* [cncf / toolbox](https://github.com/cncf/toolbox)
* [knative / docs](https://github.com/knative/docs)
"""


@pytest.fixture
def sample_settings() -> dict:
    """Provide sample settings for testing."""
    return {
        "employee": {
            "name": "Test User",
            "email": "test@example.com",
        },
        "supervisor": {
            "name": "Test Supervisor",
        },
        "product": {
            "name": "Test Product",
        },
        "cutoff": {
            "start_day": 22,
            "end_day": 25,
        },
        "creative_work_percentage": 0.8,
        "ai": {
            "provider": "gemini",
            "model": "gemini-pro",
            "api_key": "test-api-key",
        },
        "workday": {
            "enabled": False,
        },
        "did": {
            "config_path": "~/.did/config",
        },
    }


@pytest.fixture
def sample_history() -> dict:
    """Provide sample history for testing."""
    return {
        "2024-10": {
            "last_cutoff_date": "2024-10-25",
        },
        "2024-11": {
            "last_cutoff_date": "2024-11-25",
        },
    }
