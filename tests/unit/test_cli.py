"""Unit tests for CLI module."""

import pytest
from click.testing import CliRunner

from iptax.cli import _setup_logging, cli


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


@pytest.mark.unit
def test_report_command_did_integration_error(
    runner: CliRunner, tmp_path, monkeypatch
) -> None:
    """Test that report command handles DidIntegrationError."""
    from unittest.mock import patch

    from iptax.did import DidIntegrationError

    # Create minimal config
    config_dir = tmp_path / "config" / "iptax"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "settings.yaml"
    config_file.write_text(
        """
employee:
    name: "Test User"
    supervisor: "Test Supervisor"
product:
    name: "Test Product"
did:
    providers:
        - github.com
"""
    )

    did_config = tmp_path / ".did"
    did_config.mkdir()
    (did_config / "config").write_text("")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(tmp_path))

    # Mock fetch_changes to raise DidIntegrationError
    with patch("iptax.cli.fetch_changes") as mock_fetch:
        mock_fetch.side_effect = DidIntegrationError("Did error")

        result = runner.invoke(cli, ["report", "--dry-run"])
        assert result.exit_code == 1
        assert "Did integration error" in result.output


@pytest.mark.unit
def test_report_command_history_corrupted_error(
    runner: CliRunner, tmp_path, monkeypatch
) -> None:
    """Test that report command handles HistoryCorruptedError."""
    from unittest.mock import patch

    from iptax.history import HistoryCorruptedError

    # Create minimal config
    config_dir = tmp_path / "config" / "iptax"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "settings.yaml"
    config_file.write_text(
        """
employee:
    name: "Test User"
    supervisor: "Test Supervisor"
product:
    name: "Test Product"
did:
    providers:
        - github.com
"""
    )

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    # Mock HistoryManager.load to raise HistoryCorruptedError
    with patch("iptax.cli.HistoryManager") as mock_manager:
        mock_manager.return_value.load.side_effect = HistoryCorruptedError(
            "Corrupted history"
        )

        result = runner.invoke(cli, ["report", "--dry-run"])
        assert result.exit_code == 1
        assert "History error" in result.output


@pytest.mark.unit
def test_report_command_keyboard_interrupt(
    runner: CliRunner, tmp_path, monkeypatch
) -> None:
    """Test that report command handles KeyboardInterrupt gracefully."""
    from unittest.mock import patch

    # Create minimal config
    config_dir = tmp_path / "config" / "iptax"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "settings.yaml"
    config_file.write_text(
        """
employee:
    name: "Test User"
    supervisor: "Test Supervisor"
product:
    name: "Test Product"
did:
    providers:
        - github.com
"""
    )

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    # Mock fetch_changes to raise KeyboardInterrupt
    with patch("iptax.cli.fetch_changes") as mock_fetch:
        mock_fetch.side_effect = KeyboardInterrupt()

        result = runner.invoke(cli, ["report", "--dry-run"])
        assert result.exit_code == 1
        assert "cancelled" in result.output


@pytest.mark.unit
def test_report_command_invalid_month_format(
    runner: CliRunner, tmp_path, monkeypatch
) -> None:
    """Test that report command handles invalid month format."""
    # Create minimal config so we can reach month validation
    config_dir = tmp_path / "config" / "iptax"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "settings.yaml"
    config_file.write_text(
        """
employee:
    name: "Test User"
    supervisor: "Test Supervisor"
product:
    name: "Test Product"
did:
    providers:
        - github.com
"""
    )

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    result = runner.invoke(cli, ["report", "--month", "invalid-format"])
    assert result.exit_code == 1
    assert "Invalid month format" in result.output
    assert "expected YYYY-MM" in result.output


@pytest.mark.unit
def test_config_command_existing_config_overwrite_yes(
    runner: CliRunner, tmp_path, monkeypatch
) -> None:
    """Test config command when existing config exists and user confirms overwrite."""
    from unittest.mock import Mock, patch

    # Create existing config file
    config_dir = tmp_path / "config" / "iptax"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "settings.yaml"
    config_file.write_text("old: config")

    # Create did config
    did_config = tmp_path / ".did"
    did_config.mkdir()
    (did_config / "config").write_text("[general]\n[github]\ntype = github\n")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(tmp_path))

    # Mock questionary.confirm to return True (user says yes to overwrite)
    with patch("iptax.cli.questionary.confirm") as mock_confirm:
        mock_confirm_instance = Mock()
        mock_confirm_instance.unsafe_ask.return_value = True
        mock_confirm.return_value = mock_confirm_instance

        # Mock create_default_config to avoid running full wizard
        with patch("iptax.cli.create_default_config"):
            result = runner.invoke(cli, ["config"])

        # Should have asked about overwrite
        mock_confirm.assert_called_once()
        assert "Do you want to overwrite it?" in mock_confirm.call_args[0][0]
        assert result.exit_code == 0


@pytest.mark.unit
def test_config_command_existing_config_overwrite_no(
    runner: CliRunner, tmp_path, monkeypatch
) -> None:
    """Test config command when existing config exists and user declines overwrite."""
    from unittest.mock import Mock, patch

    # Create existing config file
    config_dir = tmp_path / "config" / "iptax"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "settings.yaml"
    config_file.write_text("old: config")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    # Mock questionary.confirm to return False (user says no to overwrite)
    with patch("iptax.cli.questionary.confirm") as mock_confirm:
        mock_confirm_instance = Mock()
        mock_confirm_instance.unsafe_ask.return_value = False
        mock_confirm.return_value = mock_confirm_instance

        result = runner.invoke(cli, ["config"])

        # Should have asked about overwrite
        mock_confirm.assert_called_once()
        assert "Configuration not changed" in result.output
        assert result.exit_code == 0

        # Original config should be unchanged
        assert config_file.read_text() == "old: config"


@pytest.mark.unit
def test_setup_logging_creates_cache_dir_and_log_file(tmp_path, monkeypatch) -> None:
    """Test that _setup_logging creates cache directory and configures logging."""
    from unittest.mock import patch

    # Set XDG_CACHE_HOME to temp directory
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

    # Mock setup_logging to verify it's called with correct path
    with patch("iptax.cli.setup_logging") as mock_setup:
        _setup_logging()

        # Verify cache directory was created
        expected_cache_dir = cache_dir / "iptax"
        assert expected_cache_dir.exists()

        # Verify setup_logging was called with correct log file path
        mock_setup.assert_called_once()
        log_file_arg = mock_setup.call_args[0][0]
        assert log_file_arg == expected_cache_dir / "iptax.log"
