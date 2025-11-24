"""Unit tests for CLI module."""

import pytest
from click.testing import CliRunner

from iptax.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    """Provide a CLI test runner."""
    return CliRunner()


@pytest.mark.unit
def test_cli_help(runner: CliRunner) -> None:
    """Test that CLI help works."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "IP Tax Reporter" in result.output


@pytest.mark.unit
def test_report_command_placeholder(runner: CliRunner) -> None:
    """Test that report command shows placeholder message."""
    result = runner.invoke(cli, ["report", "--dry-run"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output


@pytest.mark.unit
def test_config_command_show(runner: CliRunner) -> None:
    """Test that config command shows config path."""
    result = runner.invoke(cli, ["config", "--path"])
    assert result.exit_code == 0
    assert "iptax/settings.yaml" in result.output
