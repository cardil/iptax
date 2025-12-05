"""Tests for CLI app error handling paths."""

from datetime import date
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from iptax.cache.history import HistoryCorruptedError
from iptax.cli.app import cli
from iptax.config import ConfigError
from iptax.did import DidIntegrationError
from iptax.workday import WorkdayError


@pytest.fixture
def runner() -> CliRunner:
    """Provide a CLI test runner."""
    return CliRunner()


class TestReportCommandErrors:
    """Test error handling in report command."""

    @pytest.mark.unit
    def test_report_config_error(self, runner: CliRunner):
        """Test report command handles ConfigError."""
        with patch("iptax.cli.app.flows.report_flow") as mock_flow:
            mock_flow.side_effect = ConfigError("Missing config")
            result = runner.invoke(cli, ["report"])
            assert result.exit_code == 1
            assert "Configuration error" in result.output

    @pytest.mark.unit
    def test_report_did_integration_error(self, runner: CliRunner):
        """Test report command handles DidIntegrationError."""
        with patch("iptax.cli.app.flows.report_flow") as mock_flow:
            mock_flow.side_effect = DidIntegrationError("Did failed")
            result = runner.invoke(cli, ["report"])
            assert result.exit_code == 1
            assert "Did integration error" in result.output

    @pytest.mark.unit
    def test_report_history_corrupted_error(self, runner: CliRunner):
        """Test report command handles HistoryCorruptedError."""
        with patch("iptax.cli.app.flows.report_flow") as mock_flow:
            mock_flow.side_effect = HistoryCorruptedError("Corrupted")
            result = runner.invoke(cli, ["report"])
            assert result.exit_code == 1
            assert "History error" in result.output

    @pytest.mark.unit
    def test_report_workday_error(self, runner: CliRunner):
        """Test report command handles WorkdayError."""
        with patch("iptax.cli.app.flows.report_flow") as mock_flow:
            mock_flow.side_effect = WorkdayError("Workday failed")
            result = runner.invoke(cli, ["report"])
            assert result.exit_code == 1
            assert "Workday error" in result.output

    @pytest.mark.unit
    def test_report_keyboard_interrupt(self, runner: CliRunner):
        """Test report command handles KeyboardInterrupt."""
        with patch("iptax.cli.app.flows.report_flow") as mock_flow:
            mock_flow.side_effect = KeyboardInterrupt()
            result = runner.invoke(cli, ["report"])
            assert result.exit_code == 1
            assert "cancelled" in result.output.lower()

    @pytest.mark.unit
    def test_report_failure_returns_false(self, runner: CliRunner):
        """Test report command exits with error when flow returns False."""
        with patch("iptax.cli.app.flows.report_flow") as mock_flow:
            mock_flow.return_value = False
            result = runner.invoke(cli, ["report"])
            assert result.exit_code == 1

    @pytest.mark.unit
    def test_report_with_date_overrides(self, runner: CliRunner):
        """Test report command with date override options."""
        with patch("iptax.cli.app.flows.report_flow") as mock_flow:
            mock_flow.return_value = True
            result = runner.invoke(
                cli,
                [
                    "report",
                    "--workday-start",
                    "2024-11-01",
                    "--workday-end",
                    "2024-11-30",
                    "--did-start",
                    "2024-10-25",
                    "--did-end",
                    "2024-11-25",
                ],
            )
            assert result.exit_code == 0
            mock_flow.assert_called_once()
            call_kwargs = mock_flow.call_args
            overrides = call_kwargs[1]["overrides"]
            assert overrides.workday_start == date(2024, 11, 1)
            assert overrides.workday_end == date(2024, 11, 30)
            assert overrides.did_start == date(2024, 10, 25)
            assert overrides.did_end == date(2024, 11, 25)


class TestCollectCommandErrors:
    """Test error handling in collect command."""

    @pytest.mark.unit
    def test_collect_config_error(self, runner: CliRunner):
        """Test collect command handles ConfigError."""
        with patch("iptax.cli.app.flows.collect_flow") as mock_flow:
            mock_flow.side_effect = ConfigError("Missing config")
            result = runner.invoke(cli, ["collect"])
            assert result.exit_code == 1
            assert "Configuration error" in result.output

    @pytest.mark.unit
    def test_collect_did_integration_error(self, runner: CliRunner):
        """Test collect command handles DidIntegrationError."""
        with patch("iptax.cli.app.flows.collect_flow") as mock_flow:
            mock_flow.side_effect = DidIntegrationError("Did failed")
            result = runner.invoke(cli, ["collect"])
            assert result.exit_code == 1
            assert "Did integration error" in result.output

    @pytest.mark.unit
    def test_collect_workday_error(self, runner: CliRunner):
        """Test collect command handles WorkdayError."""
        with patch("iptax.cli.app.flows.collect_flow") as mock_flow:
            mock_flow.side_effect = WorkdayError("Workday failed")
            result = runner.invoke(cli, ["collect"])
            assert result.exit_code == 1
            assert "Workday error" in result.output

    @pytest.mark.unit
    def test_collect_keyboard_interrupt(self, runner: CliRunner):
        """Test collect command handles KeyboardInterrupt."""
        with patch("iptax.cli.app.flows.collect_flow") as mock_flow:
            mock_flow.side_effect = KeyboardInterrupt()
            result = runner.invoke(cli, ["collect"])
            assert result.exit_code == 1
            assert "cancelled" in result.output.lower()

    @pytest.mark.unit
    def test_collect_failure_returns_false(self, runner: CliRunner):
        """Test collect command exits with error when flow returns False."""
        with patch("iptax.cli.app.flows.collect_flow") as mock_flow:
            mock_flow.return_value = False
            result = runner.invoke(cli, ["collect"])
            assert result.exit_code == 1

    @pytest.mark.unit
    def test_collect_with_date_overrides(self, runner: CliRunner):
        """Test collect command with date override options."""
        with patch("iptax.cli.app.flows.collect_flow") as mock_flow:
            mock_flow.return_value = True
            result = runner.invoke(
                cli,
                [
                    "collect",
                    "--workday-start",
                    "2024-11-01",
                    "--did-end",
                    "2024-11-25",
                ],
            )
            assert result.exit_code == 0
            mock_flow.assert_called_once()

    @pytest.mark.unit
    def test_collect_with_skip_options(self, runner: CliRunner):
        """Test collect command with skip flags."""
        with patch("iptax.cli.app.flows.collect_flow") as mock_flow:
            mock_flow.return_value = True
            result = runner.invoke(
                cli,
                ["collect", "--skip-did", "--skip-workday"],
            )
            assert result.exit_code == 0
            mock_flow.assert_called_once()
            call_kwargs = mock_flow.call_args
            options = call_kwargs[1]["options"]
            assert options.skip_did is True
            assert options.skip_workday is True


class TestReviewCommandErrors:
    """Test error handling in review command."""

    @pytest.mark.unit
    def test_review_config_error(self, runner: CliRunner):
        """Test review command handles ConfigError."""
        with patch("iptax.cli.app.flows.review_flow") as mock_flow:
            mock_flow.side_effect = ConfigError("Missing config")
            result = runner.invoke(cli, ["review"])
            assert result.exit_code == 1
            assert "Configuration error" in result.output

    @pytest.mark.unit
    def test_review_keyboard_interrupt(self, runner: CliRunner):
        """Test review command handles KeyboardInterrupt."""
        with patch("iptax.cli.app.flows.review_flow") as mock_flow:
            mock_flow.side_effect = KeyboardInterrupt()
            result = runner.invoke(cli, ["review"])
            assert result.exit_code == 1
            assert "cancelled" in result.output.lower()

    @pytest.mark.unit
    def test_review_failure_returns_false(self, runner: CliRunner):
        """Test review command exits with error when flow returns False."""
        with patch("iptax.cli.app.flows.review_flow") as mock_flow:
            mock_flow.return_value = False
            result = runner.invoke(cli, ["review"])
            assert result.exit_code == 1

    @pytest.mark.unit
    def test_review_with_month_option(self, runner: CliRunner):
        """Test review command with month option."""
        with patch("iptax.cli.app.flows.review_flow") as mock_flow:
            mock_flow.return_value = True
            result = runner.invoke(cli, ["review", "--month", "2024-11"])
            assert result.exit_code == 0
            mock_flow.assert_called_once()
            assert mock_flow.call_args[1]["month"] == "2024-11"

    @pytest.mark.unit
    def test_review_with_force_option(self, runner: CliRunner):
        """Test review command with force option."""
        with patch("iptax.cli.app.flows.review_flow") as mock_flow:
            mock_flow.return_value = True
            result = runner.invoke(cli, ["review", "--force"])
            assert result.exit_code == 0
            mock_flow.assert_called_once()
            assert mock_flow.call_args[1]["force"] is True


class TestHistoryCommandErrors:
    """Test error handling in history command."""

    @pytest.mark.unit
    def test_history_corrupted_file(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test history command handles corrupted file."""
        # Create corrupted history file
        cache_dir = tmp_path / "cache" / "iptax"
        cache_dir.mkdir(parents=True)
        history_file = cache_dir / "history.toml"
        history_file.write_text("invalid [ toml syntax")

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        result = runner.invoke(cli, ["history"])
        assert result.exit_code == 1
        assert "Error" in result.output


class TestConfigCommand:
    """Test config command paths."""

    @pytest.mark.unit
    def test_config_show_valid_config(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test config show with valid config."""
        # Create minimal did config
        did_config = tmp_path / "did-config"
        did_config.write_text("[general]\n[github.com]\ntype = github\n")

        # Create valid config
        config_dir = tmp_path / "config" / "iptax"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "settings.yaml"
        config_file.write_text(
            f"""
employee:
    name: "Test User"
    supervisor: "Test Supervisor"
product:
    name: "Test Product"
did:
    config_path: "{did_config}"
    providers:
        - github.com
"""
        )

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        result = runner.invoke(cli, ["config", "--show"])
        assert result.exit_code == 0
        assert "Test User" in result.output

    @pytest.mark.unit
    def test_config_validate_valid_config(
        self, runner: CliRunner, tmp_path, monkeypatch
    ):
        """Test config validate with valid config."""
        # Create minimal did config
        did_config = tmp_path / "did-config"
        did_config.write_text("[general]\n[github.com]\ntype = github\n")

        # Create valid config
        config_dir = tmp_path / "config" / "iptax"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "settings.yaml"
        config_file.write_text(
            f"""
employee:
    name: "Test User"
    supervisor: "Test Supervisor"
product:
    name: "Test Product"
did:
    config_path: "{did_config}"
    providers:
        - github.com
"""
        )

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        result = runner.invoke(cli, ["config", "--validate"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    @pytest.mark.unit
    def test_config_interactive_cancel(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test config interactive wizard cancellation."""
        config_dir = tmp_path / "config" / "iptax"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "settings.yaml"
        config_file.write_text("# existing config\n")

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        with patch("iptax.cli.app.questionary") as mock_q:
            # User says no to overwrite
            mock_q.confirm.return_value.unsafe_ask.return_value = False
            result = runner.invoke(cli, ["config"])
            assert result.exit_code == 0
            assert "not changed" in result.output.lower()

    @pytest.mark.unit
    def test_config_interactive_keyboard_interrupt(
        self, runner: CliRunner, tmp_path, monkeypatch
    ):
        """Test config interactive wizard handles KeyboardInterrupt."""
        config_dir = tmp_path / "config" / "iptax"
        config_dir.mkdir(parents=True)

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        with patch("iptax.cli.app.create_default_config") as mock_create:
            mock_create.side_effect = KeyboardInterrupt()
            result = runner.invoke(cli, ["config"])
            assert result.exit_code == 1
            assert "cancelled" in result.output.lower()

    @pytest.mark.unit
    def test_config_interactive_error(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test config interactive wizard handles ConfigError."""
        config_dir = tmp_path / "config" / "iptax"
        config_dir.mkdir(parents=True)

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        with patch("iptax.cli.app.create_default_config") as mock_create:
            mock_create.side_effect = ConfigError("Config failed")
            result = runner.invoke(cli, ["config"])
            assert result.exit_code == 1
            assert "Error" in result.output


class TestWorkdayCommand:
    """Test workday command."""

    @pytest.mark.unit
    def test_workday_help(self, runner: CliRunner):
        """Test workday command help."""
        result = runner.invoke(cli, ["workday", "--help"])
        assert result.exit_code == 0
        assert "Workday integration" in result.output

    @pytest.mark.unit
    def test_workday_config_error(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test workday command handles ConfigError."""
        config_dir = tmp_path / "config" / "iptax"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        result = runner.invoke(cli, ["workday"])
        assert result.exit_code == 1
        assert "Configuration error" in result.output


class TestCliGroup:
    """Test CLI group behavior."""

    @pytest.mark.unit
    def test_cli_without_subcommand_invokes_report(self, runner: CliRunner):
        """Test that running bare 'iptax' invokes report command."""
        with patch("iptax.cli.app.flows.report_flow") as mock_flow:
            mock_flow.return_value = True
            result = runner.invoke(cli, [])
            assert result.exit_code == 0
            mock_flow.assert_called_once()

    @pytest.mark.unit
    def test_cli_with_options_passed_to_report(self, runner: CliRunner):
        """Test that CLI options are passed to report command."""
        with patch("iptax.cli.app.flows.report_flow") as mock_flow:
            mock_flow.return_value = True
            result = runner.invoke(
                cli,
                ["--month", "2024-11", "--skip-ai", "--force"],
            )
            assert result.exit_code == 0
            mock_flow.assert_called_once()
            call_kwargs = mock_flow.call_args
            options = call_kwargs[1]["options"]
            assert options.skip_ai is True
            assert options.force is True


class TestSetupLogging:
    """Test logging setup."""

    @pytest.mark.unit
    def test_setup_logging_creates_directory(self, tmp_path, monkeypatch):
        """Test that _setup_logging creates cache directory."""
        from iptax.cli.app import _setup_logging

        cache_dir = tmp_path / "cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

        with patch("iptax.cli.app.setup_logging") as mock_setup:
            _setup_logging()
            mock_setup.assert_called_once()
            # Verify the directory was created
            assert (cache_dir / "iptax").exists()
