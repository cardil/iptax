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
def test_report_command_placeholder(runner: CliRunner, tmp_path, monkeypatch) -> None:
    """Test that report command requires configuration."""
    # The report command now requires valid configuration
    # Test that it shows helpful error message when config is missing
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    result = runner.invoke(cli, ["report", "--dry-run"])
    assert result.exit_code == 1
    assert "Configuration error" in result.output
    assert "iptax config" in result.output


@pytest.mark.unit
def test_config_command_path_flag(runner: CliRunner) -> None:
    """Test that config command with --path flag shows config path."""
    result = runner.invoke(cli, ["config", "--path"])
    assert result.exit_code == 0
    assert "iptax" in result.output  # Should contain path to iptax config


@pytest.mark.unit
def test_history_command_path_flag(runner: CliRunner) -> None:
    """Test that history command with --path flag shows history path."""
    result = runner.invoke(cli, ["history", "--path"])
    assert result.exit_code == 0
    assert "history.toml" in result.output


@pytest.mark.unit
def test_history_command_with_invalid_month_format(runner: CliRunner) -> None:
    """Test that history command with invalid month format shows error."""
    result = runner.invoke(cli, ["history", "--month", "invalid"])
    assert result.exit_code == 1
    assert "Invalid month format" in result.output
    assert "expected YYYY-MM" in result.output


@pytest.mark.unit
def test_history_command_with_valid_month_format(
    runner: CliRunner, tmp_path, monkeypatch
) -> None:
    """Test that history command normalizes month format correctly."""
    # Create a test history file
    from datetime import UTC, date, datetime

    from iptax.history import HistoryManager
    from iptax.models import HistoryEntry

    # Set XDG_CACHE_HOME to temp directory
    cache_dir = tmp_path / "cache" / "iptax"
    cache_dir.mkdir(parents=True)
    history_file = cache_dir / "history.toml"

    # Create history with normalized month key
    manager = HistoryManager(history_path=history_file)
    manager._history = {
        "2024-10": HistoryEntry(
            last_cutoff_date=date(2024, 10, 25),
            generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
        )
    }
    manager._loaded = True
    manager.save()

    # Test with zero-padded month (use monkeypatch to isolate env changes)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    result = runner.invoke(cli, ["history", "--month", "2024-10"])
    assert result.exit_code == 0
    assert "2024-10" in result.output


@pytest.mark.unit
def test_history_command_with_missing_month(
    runner: CliRunner, tmp_path, monkeypatch
) -> None:
    """Test that history command handles missing month correctly."""
    from datetime import UTC, date, datetime

    from iptax.history import HistoryManager
    from iptax.models import HistoryEntry

    # Set XDG_CACHE_HOME to temp directory
    cache_dir = tmp_path / "cache" / "iptax"
    cache_dir.mkdir(parents=True)
    history_file = cache_dir / "history.toml"

    # Create history with a different month
    manager = HistoryManager(history_path=history_file)
    manager._history = {
        "2024-10": HistoryEntry(
            last_cutoff_date=date(2024, 10, 25),
            generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
        )
    }
    manager._loaded = True
    manager.save()

    # Test with month that doesn't exist
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    result = runner.invoke(cli, ["history", "--month", "2024-11"])
    assert result.exit_code == 0
    assert "No history entry found for 2024-11" in result.output


@pytest.mark.unit
def test_history_command_empty_history(
    runner: CliRunner, tmp_path, monkeypatch
) -> None:
    """Test that history command handles empty history correctly."""
    # Set XDG_CACHE_HOME to temp directory with no history file
    cache_dir = tmp_path / "cache" / "iptax"
    cache_dir.mkdir(parents=True)

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    result = runner.invoke(cli, ["history"])
    assert result.exit_code == 0
    assert "No report history found" in result.output
