"""Unit tests for CLI module."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from iptax.cli import app
from iptax.cli.app import (
    _gather_ai_cache_stats,
    _gather_history_stats,
    _gather_inflight_stats,
    _parse_date,
    cli,
)
from iptax.utils.env import cache_dir_for_home


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
def test_history_command_with_invalid_month_format(
    runner: CliRunner, isolated_home
) -> None:
    """Test that history command with invalid month format shows error."""
    # isolated_home sets HOME and clears XDG vars for test isolation
    cache_dir_for_home(isolated_home).mkdir(parents=True, exist_ok=True)
    result = runner.invoke(cli, ["history", "--month", "invalid"])
    assert result.exit_code == 1
    assert "Invalid month format" in result.output
    assert "expected YYYY-MM" in result.output


@pytest.mark.unit
def test_history_command_with_valid_month_format(
    runner: CliRunner, isolated_home
) -> None:
    """Test that history command normalizes month format correctly."""
    from datetime import UTC, date, datetime

    from iptax.cache.history import HistoryManager
    from iptax.models import HistoryEntry

    cache_dir = cache_dir_for_home(isolated_home)
    cache_dir.mkdir(parents=True)
    history_file = cache_dir / "history.json"

    # Create history with normalized month key
    manager = HistoryManager(history_path=history_file)
    manager._history = {
        "2024-10": HistoryEntry(
            first_change_date=date(2024, 9, 21),
            last_change_date=date(2024, 10, 25),
            generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
        )
    }
    manager._loaded = True
    manager.save()

    result = runner.invoke(cli, ["history", "--month", "2024-10"])
    assert result.exit_code == 0
    assert "2024-10" in result.output


@pytest.mark.unit
def test_history_command_with_missing_month(runner: CliRunner, isolated_home) -> None:
    """Test that history command handles missing month correctly."""
    from datetime import UTC, date, datetime

    from iptax.cache.history import HistoryManager
    from iptax.models import HistoryEntry

    cache_dir = cache_dir_for_home(isolated_home)
    cache_dir.mkdir(parents=True)
    history_file = cache_dir / "history.json"

    # Create history with a different month
    manager = HistoryManager(history_path=history_file)
    manager._history = {
        "2024-10": HistoryEntry(
            first_change_date=date(2024, 9, 21),
            last_change_date=date(2024, 10, 25),
            generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
        )
    }
    manager._loaded = True
    manager.save()

    result = runner.invoke(cli, ["history", "--month", "2024-11"])
    assert result.exit_code == 0
    assert "No history entry found for 2024-11" in result.output


@pytest.mark.unit
def test_history_command_empty_history(runner: CliRunner, isolated_home) -> None:
    """Test that history command handles empty history correctly."""
    cache_dir = cache_dir_for_home(isolated_home)
    cache_dir.mkdir(parents=True)

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
        import json

        cache_dir = tmp_path / "cache" / "iptax" / "inflight"
        cache_dir.mkdir(parents=True)
        # Create a valid InFlightReport cache file with all required fields
        valid_report = {
            "schema_version": 2,
            "month": "2024-11",
            "workday_start": "2024-11-01",
            "workday_end": "2024-11-30",
            "changes_since": "2024-10-25",
            "changes_until": "2024-11-25",
            "created_at": "2024-11-01T10:00:00+00:00",
            "changes": [],
            "judgments": [],
            "workday_entries": [],
            "workday_validated": False,
        }
        (cache_dir / "2024-11.json").write_text(json.dumps(valid_report))

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
    def test_cache_clear_history_month(self, runner: CliRunner, isolated_home):
        """Test clearing a specific month's history entry."""
        import json

        from iptax.cache.history import HistoryManager
        from iptax.models import HistoryEntry

        cache_dir = cache_dir_for_home(isolated_home)
        cache_dir.mkdir(parents=True)
        history_file = cache_dir / "history.json"

        # Create history with multiple entries
        manager = HistoryManager(history_path=history_file)
        manager._history = {
            "2024-10": HistoryEntry(
                first_change_date=date(2024, 9, 21),
                last_change_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            ),
            "2024-11": HistoryEntry(
                first_change_date=date(2024, 10, 26),
                last_change_date=date(2024, 11, 25),
                generated_at=datetime(2024, 11, 26, 10, 0, 0, tzinfo=UTC),
            ),
        }
        manager._loaded = True
        manager.save()

        result = runner.invoke(
            cli, ["cache", "clear", "--history", "--month", "2024-10"]
        )
        assert result.exit_code == 0
        assert "Cleared history entry for 2024-10" in result.output

        # Verify only 2024-10 was deleted
        data = json.loads(history_file.read_text())
        assert "2024-10" not in data
        assert "2024-11" in data

    @pytest.mark.unit
    def test_cache_clear_history_month_nonexistent(
        self, runner: CliRunner, isolated_home
    ):
        """Test clearing a nonexistent month's history entry."""
        from iptax.cache.history import HistoryManager
        from iptax.models import HistoryEntry

        cache_dir = cache_dir_for_home(isolated_home)
        cache_dir.mkdir(parents=True)
        history_file = cache_dir / "history.json"

        # Create history with one entry
        manager = HistoryManager(history_path=history_file)
        manager._history = {
            "2024-10": HistoryEntry(
                first_change_date=date(2024, 9, 21),
                last_change_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }
        manager._loaded = True
        manager.save()

        result = runner.invoke(
            cli, ["cache", "clear", "--history", "--month", "2024-12"]
        )
        assert result.exit_code == 0
        assert "No history entry found for 2024-12" in result.output

    @pytest.mark.unit
    def test_cache_clear_inflight_and_history_month(
        self, runner: CliRunner, isolated_home
    ):
        """Test clearing both in-flight and history for a specific month."""
        import json

        from iptax.cache.history import HistoryManager
        from iptax.models import HistoryEntry

        cache_dir = cache_dir_for_home(isolated_home)
        cache_dir.mkdir(parents=True)

        # Create in-flight cache
        inflight_dir = cache_dir / "inflight"
        inflight_dir.mkdir()
        (inflight_dir / "2024-11.json").write_text('{"month": "2024-11"}')

        # Create history
        history_file = cache_dir / "history.json"
        manager = HistoryManager(history_path=history_file)
        manager._history = {
            "2024-11": HistoryEntry(
                first_change_date=date(2024, 10, 26),
                last_change_date=date(2024, 11, 25),
                generated_at=datetime(2024, 11, 26, 10, 0, 0, tzinfo=UTC),
            )
        }
        manager._loaded = True
        manager.save()

        result = runner.invoke(
            cli, ["cache", "clear", "--inflight", "--history", "--month", "2024-11"]
        )
        assert result.exit_code == 0
        assert "Cleared in-flight report for 2024-11" in result.output
        assert "Cleared history entry for 2024-11" in result.output

        # Verify both were deleted
        assert not (inflight_dir / "2024-11.json").exists()
        data = json.loads(history_file.read_text())
        assert "2024-11" not in data

    @pytest.mark.unit
    def test_cache_clear_ai_with_month_warning(self, runner: CliRunner, isolated_home):
        """Test that using --ai with --month shows a warning."""
        # isolated_home ensures test runs in isolated environment
        cache_dir = cache_dir_for_home(isolated_home)
        cache_dir.mkdir(parents=True)

        result = runner.invoke(cli, ["cache", "clear", "--ai", "--month", "2024-11"])
        assert result.exit_code == 0
        assert "AI cache cannot be cleared per-month" in result.output

    @pytest.mark.unit
    def test_cache_clear_all_confirmed(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test clearing all cache with confirmation."""
        cache_dir = tmp_path / "cache" / "iptax" / "inflight"
        cache_dir.mkdir(parents=True)
        (cache_dir / "2024-10.json").write_text('{"month": "2024-10"}')
        (cache_dir / "2024-11.json").write_text('{"month": "2024-11"}')

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        # Use --force to skip confirmations
        result = runner.invoke(cli, ["cache", "clear", "--force"])

        assert result.exit_code == 0
        assert "Cleared 2 in-flight report(s)" in result.output

    @pytest.mark.unit
    def test_cache_clear_all_cancelled(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test clearing all cache with cancellation."""
        cache_dir = tmp_path / "cache" / "iptax" / "inflight"
        cache_dir.mkdir(parents=True)
        (cache_dir / "2024-11.json").write_text('{"month": "2024-11"}')

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        # Mock questionary confirmation (user cancels) - now in flows module
        with patch("iptax.cli.flows.questionary") as mock_q:
            mock_q.confirm.return_value.unsafe_ask.return_value = False
            result = runner.invoke(cli, ["cache", "clear"])

        assert result.exit_code == 0
        assert "cancelled" in result.output
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
    def test_history_json_format(self, runner: CliRunner, isolated_home):
        """Test history command with JSON format."""
        from datetime import UTC, datetime

        from iptax.cache.history import HistoryManager
        from iptax.models import HistoryEntry

        cache_dir = cache_dir_for_home(isolated_home)
        cache_dir.mkdir(parents=True)
        history_file = cache_dir / "history.json"

        manager = HistoryManager(history_path=history_file)
        manager._history = {
            "2024-10": HistoryEntry(
                first_change_date=date(2024, 9, 21),
                last_change_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }
        manager._loaded = True
        manager.save()

        result = runner.invoke(cli, ["history", "--format", "json"])
        assert result.exit_code == 0
        assert '"2024-10"' in result.output

    @pytest.mark.unit
    def test_history_yaml_format(self, runner: CliRunner, isolated_home):
        """Test history command with YAML format."""
        from datetime import UTC, datetime

        from iptax.cache.history import HistoryManager
        from iptax.models import HistoryEntry

        cache_dir = cache_dir_for_home(isolated_home)
        cache_dir.mkdir(parents=True)
        history_file = cache_dir / "history.json"

        manager = HistoryManager(history_path=history_file)
        manager._history = {
            "2024-10": HistoryEntry(
                first_change_date=date(2024, 9, 21),
                last_change_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }
        manager._loaded = True
        manager.save()

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


class TestGatherAiCacheStats:
    """Tests for _gather_ai_cache_stats function."""

    @pytest.mark.unit
    def test_gather_with_empty_cache(self, tmp_path):
        """Test gathering stats from empty AI cache."""
        cache_path = tmp_path / "ai_cache.json"

        with (
            patch.object(app, "get_ai_cache_path", return_value=cache_path),
            patch.object(app, "JudgmentCacheManager") as mock_mgr,
        ):
            mock_instance = MagicMock()
            mock_instance.stats.return_value = {
                "total_judgments": 0,
                "corrected_count": 0,
                "correct_count": 0,
                "correction_rate": 0.0,
                "products": [],
                "oldest_judgment": None,
                "newest_judgment": None,
            }
            mock_mgr.return_value = mock_instance

            stats = _gather_ai_cache_stats()

        assert stats.total_judgments == 0
        assert stats.corrected_count == 0
        assert stats.cache_size_bytes == 0

    @pytest.mark.unit
    def test_gather_with_existing_cache(self, tmp_path):
        """Test gathering stats from existing AI cache."""
        cache_path = tmp_path / "ai_cache.json"
        cache_path.write_text('{"judgments": {}}')

        with (
            patch.object(app, "get_ai_cache_path", return_value=cache_path),
            patch.object(app, "JudgmentCacheManager") as mock_mgr,
        ):
            mock_instance = MagicMock()
            mock_instance.stats.return_value = {
                "total_judgments": 5,
                "corrected_count": 1,
                "correct_count": 4,
                "correction_rate": 0.2,
                "products": ["Product A"],
                "oldest_judgment": "2024-10-01T10:00:00+00:00",
                "newest_judgment": "2024-10-15T10:00:00+00:00",
            }
            mock_mgr.return_value = mock_instance

            stats = _gather_ai_cache_stats()

        assert stats.total_judgments == 5
        assert stats.corrected_count == 1
        assert stats.products == ["Product A"]
        assert stats.cache_size_bytes > 0


class TestGatherHistoryStats:
    """Tests for _gather_history_stats function."""

    @pytest.mark.unit
    def test_gather_with_no_history(self, tmp_path):
        """Test gathering stats when no history exists."""
        history_path = tmp_path / "history.json"

        with (
            patch.object(app, "HistoryManager") as mock_mgr,
            patch.object(app, "get_history_path", return_value=history_path),
        ):
            mock_instance = MagicMock()
            mock_instance.get_all_entries.return_value = {}
            mock_mgr.return_value = mock_instance

            stats = _gather_history_stats()

        assert stats.total_reports == 0
        assert stats.entries == {}
        assert stats.history_size_bytes == 0

    @pytest.mark.unit
    def test_gather_with_existing_history(self, tmp_path):
        """Test gathering stats from existing history."""
        from iptax.models import HistoryEntry

        history_path = tmp_path / "history.json"
        history_path.write_text("{}")

        entries = {
            "2024-10": HistoryEntry(
                first_change_date=date(2024, 9, 21),
                last_change_date=date(2024, 10, 25),
                generated_at=datetime(2024, 10, 26, 10, 0, 0, tzinfo=UTC),
            )
        }

        with (
            patch.object(app, "HistoryManager") as mock_mgr,
            patch.object(app, "get_history_path", return_value=history_path),
        ):
            mock_instance = MagicMock()
            mock_instance.get_all_entries.return_value = entries
            mock_mgr.return_value = mock_instance

            stats = _gather_history_stats()

        assert stats.total_reports == 1
        assert "2024-10" in stats.entries
        assert stats.history_size_bytes > 0


class TestGatherInflightStats:
    """Tests for _gather_inflight_stats function."""

    @pytest.mark.unit
    def test_gather_with_no_inflight(self, tmp_path):
        """Test gathering stats when no in-flight reports exist."""
        inflight_dir = tmp_path / "inflight"
        inflight_dir.mkdir()

        with (
            patch.object(app, "InFlightCache") as mock_cache,
            patch.object(app, "get_inflight_cache_dir", return_value=inflight_dir),
        ):
            mock_instance = MagicMock()
            mock_instance.list_all.return_value = []
            mock_cache.return_value = mock_instance

            stats = _gather_inflight_stats()

        assert stats.active_reports == 0
        assert stats.months == []
        assert stats.cache_dir == inflight_dir

    @pytest.mark.unit
    def test_gather_with_active_reports(self, tmp_path):
        """Test gathering stats with active in-flight reports."""
        inflight_dir = tmp_path / "inflight"
        inflight_dir.mkdir()

        with (
            patch.object(app, "InFlightCache") as mock_cache,
            patch.object(app, "get_inflight_cache_dir", return_value=inflight_dir),
        ):
            mock_instance = MagicMock()
            mock_instance.list_all.return_value = ["2024-10", "2024-11"]
            mock_cache.return_value = mock_instance

            stats = _gather_inflight_stats()

        assert stats.active_reports == 2
        assert stats.months == ["2024-10", "2024-11"]


class TestCacheStatsCommand:
    """Tests for cache stats command."""

    @pytest.mark.unit
    def test_cache_stats_displays_output(
        self, runner: CliRunner, tmp_path, monkeypatch
    ):
        """Test that cache stats command displays statistics."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        # Create cache directories
        cache_dir = tmp_path / "cache" / "iptax"
        cache_dir.mkdir(parents=True)
        inflight_dir = cache_dir / "inflight"
        inflight_dir.mkdir()

        result = runner.invoke(cli, ["cache", "stats"])
        assert result.exit_code == 0
        assert "Cache Statistics" in result.output
        assert "AI Judgment Cache" in result.output
        assert "Report History" in result.output
        assert "In-flight Cache" in result.output


class TestCachePathCommand:
    """Tests for cache path command."""

    @pytest.mark.unit
    def test_cache_path_displays_paths(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test that cache path command displays all paths."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        result = runner.invoke(cli, ["cache", "path"])
        assert result.exit_code == 0
        assert "Cache Paths" in result.output
        assert "AI Cache" in result.output
        assert "History" in result.output
        assert "In-flight" in result.output

    @pytest.mark.unit
    def test_cache_path_ai_flag(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test that --ai flag returns only AI cache path."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        result = runner.invoke(cli, ["cache", "path", "--ai"])
        assert result.exit_code == 0
        # Should be just the path, no formatting
        assert "Cache Paths" not in result.output
        assert "ai_cache.json" in result.output

    @pytest.mark.unit
    def test_cache_path_history_flag(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test that --history flag returns only history path."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        result = runner.invoke(cli, ["cache", "path", "--history"])
        assert result.exit_code == 0
        # Should be just the path, no formatting
        assert "Cache Paths" not in result.output
        assert "history.json" in result.output

    @pytest.mark.unit
    def test_cache_path_inflight_flag(self, runner: CliRunner, tmp_path, monkeypatch):
        """Test that --inflight flag returns only in-flight dir."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        result = runner.invoke(cli, ["cache", "path", "--inflight"])
        assert result.exit_code == 0
        # Should be just the path, no formatting
        assert "Cache Paths" not in result.output
        assert "inflight" in result.output


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

    @pytest.mark.unit
    def test_main_catches_unexpected_exceptions(self, tmp_path):
        """Test that main catches and logs unexpected exceptions."""
        log_file = tmp_path / "iptax.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        with (
            patch.object(app, "_setup_logging"),
            patch.object(app, "_get_log_file", return_value=log_file),
            patch.object(app, "cli", side_effect=RuntimeError("Test error")),
            pytest.raises(SystemExit) as exc_info,
        ):
            app.main()

        assert exc_info.value.code == 1
