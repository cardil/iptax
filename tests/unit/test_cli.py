"""Unit tests for CLI module."""

from datetime import date
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from iptax.cli import app
from iptax.cli.app import _parse_date, cli


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
    assert "history.json" in result.output


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

    from iptax.cache.history import HistoryManager
    from iptax.models import HistoryEntry

    # Set XDG_CACHE_HOME to temp directory
    cache_dir = tmp_path / "cache" / "iptax"
    cache_dir.mkdir(parents=True)
    history_file = cache_dir / "history.json"

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

    from iptax.cache.history import HistoryManager
    from iptax.models import HistoryEntry

    # Set XDG_CACHE_HOME to temp directory
    cache_dir = tmp_path / "cache" / "iptax"
    cache_dir.mkdir(parents=True)
    history_file = cache_dir / "history.json"

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
def test_report_command_invalid_month_format(
    runner: CliRunner, tmp_path, monkeypatch
) -> None:
    """Test that report command handles invalid month format."""
    # Create minimal did config
    did_config = tmp_path / "did-config"
    did_config.write_text("[general]\n[github.com]\ntype = github\n")

    # Create minimal config so we can reach month validation
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

    result = runner.invoke(cli, ["report", "--month", "invalid-format"])
    assert result.exit_code != 0
    # Check that ValueError was raised with appropriate message
    assert result.exception is not None
    assert "Invalid month format" in str(result.exception)


class TestParseDate:
    """Tests for _parse_date helper function."""

    @pytest.mark.unit
    def test_valid_date(self):
        """Test parsing a valid date string."""
        result = _parse_date("2024-11-15")
        assert result == date(2024, 11, 15)

    @pytest.mark.unit
    def test_invalid_date_format(self):
        """Test parsing an invalid date format raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter) as exc_info:
            _parse_date("invalid")
        assert "Invalid date format" in str(exc_info.value)
        assert "expected YYYY-MM-DD" in str(exc_info.value)

    @pytest.mark.unit
    def test_partial_date(self):
        """Test parsing a partial date raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter):
            _parse_date("2024-11")


class TestCacheCommand:
    """Tests for cache command."""

    @pytest.mark.unit
    def test_cache_list_empty(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test cache list with no reports."""
        cache_dir = tmp_path / "cache" / "iptax"
        cache_dir.mkdir(parents=True)
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        result = runner.invoke(cli, ["cache", "list"])
        assert result.exit_code == 0
        assert "No in-flight reports found" in result.output

    @pytest.mark.unit
    def test_cache_list_with_reports(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test cache list with existing reports."""
        cache_dir = tmp_path / "cache" / "iptax" / "inflight"
        cache_dir.mkdir(parents=True)
        # Create a mock cache file
        (cache_dir / "2024-11.json").write_text('{"month": "2024-11"}')

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        result = runner.invoke(cli, ["cache", "list"])
        assert result.exit_code == 0
        assert "2024-11" in result.output

    @pytest.mark.unit
    def test_cache_clear_specific_month(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test clearing a specific month's cache."""
        cache_dir = tmp_path / "cache" / "iptax" / "inflight"
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / "2024-11.json"
        cache_file.write_text('{"month": "2024-11"}')

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        result = runner.invoke(cli, ["cache", "clear", "--month", "2024-11"])
        assert result.exit_code == 0
        assert "Cleared in-flight report for 2024-11" in result.output
        assert not cache_file.exists()

    @pytest.mark.unit
    def test_cache_clear_nonexistent_month(
        self, runner: CliRunner, tmp_path, monkeypatch
    ):
        """Test clearing a nonexistent month's cache."""
        cache_dir = tmp_path / "cache" / "iptax" / "inflight"
        cache_dir.mkdir(parents=True)

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        result = runner.invoke(cli, ["cache", "clear", "--month", "2024-12"])
        assert result.exit_code == 0
        assert "No in-flight report found for 2024-12" in result.output

    @pytest.mark.unit
    def test_cache_clear_all_confirmed(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test clearing all cache with confirmation."""
        cache_dir = tmp_path / "cache" / "iptax" / "inflight"
        cache_dir.mkdir(parents=True)
        (cache_dir / "2024-10.json").write_text('{"month": "2024-10"}')
        (cache_dir / "2024-11.json").write_text('{"month": "2024-11"}')

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        # Mock questionary confirmation
        with patch.object(app, "questionary") as mock_q:
            mock_q.confirm.return_value.unsafe_ask.return_value = True
            result = runner.invoke(cli, ["cache", "clear"])

        assert result.exit_code == 0
        assert "Cleared 2 in-flight report(s)" in result.output

    @pytest.mark.unit
    def test_cache_clear_all_cancelled(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test clearing all cache with cancellation."""
        cache_dir = tmp_path / "cache" / "iptax" / "inflight"
        cache_dir.mkdir(parents=True)
        (cache_dir / "2024-11.json").write_text('{"month": "2024-11"}')

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        # Mock questionary confirmation (user cancels)
        with patch.object(app, "questionary") as mock_q:
            mock_q.confirm.return_value.unsafe_ask.return_value = False
            result = runner.invoke(cli, ["cache", "clear"])

        assert result.exit_code == 0
        assert "Cancelled" in result.output
        # File should still exist
        assert (cache_dir / "2024-11.json").exists()


class TestConfigCommand:
    """Tests for config command."""

    @pytest.mark.unit
    def test_config_show_no_config(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test config show when no config exists."""
        config_dir = tmp_path / "config" / "iptax"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        result = runner.invoke(cli, ["config", "--show"])
        assert result.exit_code == 1
        assert "Error" in result.output

    @pytest.mark.unit
    def test_config_validate_no_config(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test config validate when no config exists."""
        config_dir = tmp_path / "config" / "iptax"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        result = runner.invoke(cli, ["config", "--validate"])
        assert result.exit_code == 1
        assert "invalid" in result.output


class TestReviewCommand:
    """Tests for review command."""

    @pytest.mark.unit
    def test_review_help(self, runner: CliRunner):
        """Test review command help."""
        result = runner.invoke(cli, ["review", "--help"])
        assert result.exit_code == 0
        assert "Review AI judgments" in result.output


class TestCollectCommand:
    """Tests for collect command."""

    @pytest.mark.unit
    def test_collect_help(self, runner: CliRunner):
        """Test collect command help."""
        result = runner.invoke(cli, ["collect", "--help"])
        assert result.exit_code == 0
        assert "Collect data" in result.output


class TestReportCommand:
    """Tests for report command."""

    @pytest.mark.unit
    def test_report_help(self, runner: CliRunner):
        """Test report command help."""
        result = runner.invoke(cli, ["report", "--help"])
        assert result.exit_code == 0
        assert "Generate IP tax report" in result.output


class TestHistoryCommand:
    """Tests for history command."""

    @pytest.mark.unit
    def test_history_json_format(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test history command with JSON format."""
        from datetime import UTC, datetime

        from iptax.cache.history import HistoryManager
        from iptax.models import HistoryEntry

        cache_dir = tmp_path / "cache" / "iptax"
        cache_dir.mkdir(parents=True)
        history_file = cache_dir / "history.json"

        manager = HistoryManager(history_path=history_file)
        manager._history = {
            "2024-10": HistoryEntry(
                last_cutoff_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }
        manager._loaded = True
        manager.save()

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        result = runner.invoke(cli, ["history", "--format", "json"])
        assert result.exit_code == 0
        assert '"2024-10"' in result.output

    @pytest.mark.unit
    def test_history_yaml_format(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test history command with YAML format."""
        from datetime import UTC, datetime

        from iptax.cache.history import HistoryManager
        from iptax.models import HistoryEntry

        cache_dir = tmp_path / "cache" / "iptax"
        cache_dir.mkdir(parents=True)
        history_file = cache_dir / "history.json"

        manager = HistoryManager(history_path=history_file)
        manager._history = {
            "2024-10": HistoryEntry(
                last_cutoff_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }
        manager._loaded = True
        manager.save()

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        result = runner.invoke(cli, ["history", "--format", "yaml"])
        assert result.exit_code == 0
        assert "2024-10" in result.output


class TestAsyncCommand:
    """Tests for async_command decorator."""

    @pytest.mark.unit
    def test_async_command_runs_async_function(self):
        """Test that async_command decorator runs async functions."""
        from iptax.cli.app import async_command

        call_count = 0

        @async_command
        async def test_func() -> str:
            nonlocal call_count
            call_count += 1
            return "result"

        result = test_func()
        assert result == "result"
        assert call_count == 1


class TestMain:
    """Tests for main entry point."""

    @pytest.mark.unit
    def test_main_calls_setup_logging(self):
        """Test that main sets up logging and calls cli."""
        with (
            patch.object(app, "_setup_logging") as mock_setup,
            patch.object(app, "cli") as mock_cli,
        ):
            app.main()
            mock_setup.assert_called_once()
            mock_cli.assert_called_once()
