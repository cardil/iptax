"""Tests for CLI flows module."""

import logging
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console
from rich.prompt import Confirm

from iptax.ai.review import ReviewResult
from iptax.cache.inflight import InFlightCache
from iptax.cli import flows
from iptax.cli.flows import (
    FlowOptions,
    OutputOptions,
    _display_collection_summary,
    _display_inflight_summary,
    _get_playwright_command,
    _install_playwright_firefox,
    _is_playwright_firefox_installed,
    _resolve_review_month,
    _save_judgments_to_ai_cache,
    clear_ai_cache,
    clear_history_cache,
    clear_inflight_cache,
    confirm_or_force,
    ensure_browser_installed,
    init_flow,
)
from iptax.models import (
    Change,
    Decision,
    InFlightReport,
    Judgment,
    Repository,
    WorkHours,
)
from iptax.utils.env import cache_dir_for_home

from .conftest import strip_ansi

logger = logging.getLogger(__name__)


class TestGetPlaywrightCommand:
    """Tests for _get_playwright_command function."""

    @pytest.mark.unit
    def test_returns_playwright_path_when_found(self):
        """Test returns direct playwright path when found in PATH."""
        with patch("shutil.which", return_value="/usr/local/bin/playwright"):
            result = _get_playwright_command()

        assert result == ["/usr/local/bin/playwright"]

    @pytest.mark.unit
    def test_returns_python_module_when_playwright_not_found(self):
        """Test returns python -m playwright when not in PATH."""
        import sys

        with patch("shutil.which", return_value=None):
            result = _get_playwright_command()

        assert result == [sys.executable, "-m", "playwright"]


class TestIsPlaywrightFirefoxInstalled:
    """Tests for _is_playwright_firefox_installed function."""

    @pytest.mark.unit
    def test_returns_true_when_firefox_in_output(self):
        """Test returns True when firefox path found in output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/home/user/.cache/ms-playwright/firefox-1495\n"

        with (
            patch("shutil.which", return_value="/usr/bin/playwright"),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            result = _is_playwright_firefox_installed()

        assert result is True
        mock_run.assert_called_once()
        # Verify correct command was used
        call_args = mock_run.call_args
        assert "install" in call_args[0][0]
        assert "--list" in call_args[0][0]

    @pytest.mark.unit
    def test_returns_false_when_firefox_not_in_output(self):
        """Test returns False when firefox not in output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/home/user/.cache/ms-playwright/chromium-1234\n"

        with (
            patch("shutil.which", return_value=None),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = _is_playwright_firefox_installed()

        assert result is False

    @pytest.mark.unit
    def test_returns_false_on_nonzero_return_code(self):
        """Test returns False when command fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with (
            patch("shutil.which", return_value=None),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = _is_playwright_firefox_installed()

        assert result is False

    @pytest.mark.unit
    def test_returns_false_on_file_not_found(self):
        """Test returns False when playwright command not found."""
        with (
            patch("shutil.which", return_value=None),
            patch("subprocess.run", side_effect=FileNotFoundError()),
        ):
            result = _is_playwright_firefox_installed()

        assert result is False


class TestInstallPlaywrightFirefox:
    """Tests for _install_playwright_firefox function."""

    @pytest.mark.unit
    def test_returns_true_on_success(self):
        """Test returns True on successful install."""
        console = Console(file=StringIO(), force_terminal=True)

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("shutil.which", return_value=None),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = _install_playwright_firefox(console)

        assert result is True
        output = strip_ansi(console.file.getvalue())
        assert "Installing Playwright Firefox" in output
        assert "Playwright Firefox browser installed" in output

    @pytest.mark.unit
    def test_returns_false_on_failure(self):
        """Test returns False on install failure."""
        console = Console(file=StringIO(), force_terminal=True)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "install error"

        with (
            patch("shutil.which", return_value=None),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = _install_playwright_firefox(console)

        assert result is False
        output = strip_ansi(console.file.getvalue())
        assert "Failed to install browser" in output

    @pytest.mark.unit
    def test_returns_false_on_file_not_found(self):
        """Test returns False when playwright not found."""
        console = Console(file=StringIO(), force_terminal=True)

        with (
            patch("shutil.which", return_value=None),
            patch("subprocess.run", side_effect=FileNotFoundError()),
        ):
            result = _install_playwright_firefox(console)

        assert result is False
        output = strip_ansi(console.file.getvalue())
        assert "Playwright not found" in output


class TestEnsureBrowserInstalled:
    """Tests for ensure_browser_installed function."""

    @pytest.mark.unit
    def test_returns_true_when_already_installed(self):
        """Test returns True when browser already installed."""
        console = Console(file=StringIO(), force_terminal=True)

        with patch.object(flows, "_is_playwright_firefox_installed", return_value=True):
            result = ensure_browser_installed(console)

        assert result is True

    @pytest.mark.unit
    def test_installs_when_not_present(self):
        """Test installs browser when not present."""
        console = Console(file=StringIO(), force_terminal=True)

        with (
            patch.object(flows, "_is_playwright_firefox_installed", return_value=False),
            patch.object(
                flows, "_install_playwright_firefox", return_value=True
            ) as mock_install,
        ):
            result = ensure_browser_installed(console)

        assert result is True
        mock_install.assert_called_once_with(console)


class TestInitFlow:
    """Tests for init_flow function."""

    @pytest.mark.unit
    def test_shows_already_installed(self):
        """Test shows message when Firefox already installed."""
        console = Console(file=StringIO(), force_terminal=True)

        with patch.object(flows, "_is_playwright_firefox_installed", return_value=True):
            result = init_flow(console)

        assert result is True
        output = strip_ansi(console.file.getvalue())
        assert "Initializing iptax" in output
        assert "already installed" in output

    @pytest.mark.unit
    def test_installs_when_not_present(self):
        """Test installs browser when not present."""
        console = Console(file=StringIO(), force_terminal=True)

        with (
            patch.object(flows, "_is_playwright_firefox_installed", return_value=False),
            patch.object(
                flows, "_install_playwright_firefox", return_value=True
            ) as mock_install,
        ):
            result = init_flow(console)

        assert result is True
        mock_install.assert_called_once_with(console)

    @pytest.mark.unit
    def test_returns_false_on_install_failure(self):
        """Test returns False when install fails."""
        console = Console(file=StringIO(), force_terminal=True)

        with (
            patch.object(flows, "_is_playwright_firefox_installed", return_value=False),
            patch.object(flows, "_install_playwright_firefox", return_value=False),
        ):
            result = init_flow(console)

        assert result is False


class TestFetchChanges:
    """Tests for fetch_changes flow."""

    @pytest.mark.unit
    def test_fetches_and_prints_count(self):
        """Test that fetch_changes fetches and prints change count."""
        console = Console(file=StringIO(), force_terminal=True)
        settings = MagicMock()
        start_date = date(2024, 10, 1)
        end_date = date(2024, 10, 31)

        mock_changes = [
            Change(
                title="Test change",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]

        with patch.object(flows, "did_fetch_changes", return_value=mock_changes):
            result = flows.fetch_changes(console, settings, start_date, end_date)

        assert result == mock_changes
        output = strip_ansi(console.file.getvalue())
        assert "Fetching changes" in output
        assert "Found 1 change" in output

    @pytest.mark.unit
    def test_returns_empty_list(self):
        """Test that fetch_changes returns empty list when no changes."""
        console = Console(file=StringIO(), force_terminal=True)
        settings = MagicMock()

        with patch.object(flows, "did_fetch_changes", return_value=[]):
            result = flows.fetch_changes(
                console, settings, date(2024, 10, 1), date(2024, 10, 31)
            )

        assert result == []
        output = strip_ansi(console.file.getvalue())
        assert "Found 0 changes" in output


class TestLoadSettings:
    """Tests for load_settings flow."""

    @pytest.mark.unit
    def test_loads_and_prints_confirmation(self):
        """Test that load_settings loads and prints confirmation."""
        console = Console(file=StringIO(), force_terminal=True)
        mock_settings = MagicMock()

        with patch.object(flows, "config_load_settings", return_value=mock_settings):
            result = flows.load_settings(console)

        assert result == mock_settings
        output = console.file.getvalue()
        assert "Settings loaded" in output


class TestLoadHistory:
    """Tests for load_history flow."""

    @pytest.mark.unit
    def test_loads_and_prints_confirmation(self):
        """Test that load_history loads and prints confirmation."""
        console = Console(file=StringIO(), force_terminal=True)

        with patch.object(flows, "HistoryManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager_cls.return_value = mock_manager

            result = flows.load_history(console)

        assert result == mock_manager
        mock_manager.load.assert_called_once()
        output = console.file.getvalue()
        assert "History loaded" in output


class TestReview:
    """Tests for review flow."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_shows_summary_and_calls_tui(self):
        """Test that review shows summary and calls TUI."""
        console = Console(file=StringIO(), force_terminal=True)
        changes = [
            Change(
                title="Test change",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]
        judgments = [
            Judgment(
                change_id=changes[0].get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Product",
            )
        ]

        mock_result = MagicMock()
        mock_result.judgments = judgments
        mock_result.accepted = True

        with (
            patch.object(flows, "run_review_tui", return_value=mock_result),
            patch.object(flows, "display_review_results"),
        ):
            result = await flows.review(console, judgments, changes)

        assert result == mock_result
        output = strip_ansi(console.file.getvalue())
        # New format: "AI analysis: INCLUDE(✓): 1"
        assert "AI analysis" in output
        assert "INCLUDE" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_shows_all_decision_counts(self):
        """Test that review shows counts for all decision types."""
        console = Console(file=StringIO(), force_terminal=True)
        changes = [
            Change(
                title=f"Change {i}",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100 + i,
            )
            for i in range(3)
        ]
        judgments = [
            Judgment(
                change_id=changes[0].get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Product",
            ),
            Judgment(
                change_id=changes[1].get_change_id(),
                decision=Decision.EXCLUDE,
                reasoning="Test",
                product="Product",
            ),
            Judgment(
                change_id=changes[2].get_change_id(),
                decision=Decision.UNCERTAIN,
                reasoning="Test",
                product="Product",
            ),
        ]

        mock_result = MagicMock()
        mock_result.judgments = judgments
        mock_result.accepted = True

        with (
            patch.object(flows, "run_review_tui", return_value=mock_result),
            patch.object(flows, "display_review_results"),
        ):
            await flows.review(console, judgments, changes)

        output = strip_ansi(console.file.getvalue())
        # New format includes indicators: "INCLUDE(✓): 1  EXCLUDE(✗): 1"
        assert "INCLUDE" in output
        assert "EXCLUDE" in output
        assert "UNCERTAIN" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_calls_display_results_after_tui(self):
        """Test that review calls display_review_results after TUI."""
        console = Console(file=StringIO(), force_terminal=True)
        changes = [
            Change(
                title="Test",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]
        judgments = [
            Judgment(
                change_id=changes[0].get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Product",
            )
        ]

        mock_result = MagicMock()
        mock_result.judgments = judgments
        mock_result.accepted = False

        with (
            patch.object(flows, "run_review_tui", return_value=mock_result),
            patch.object(flows, "display_review_results") as mock_display,
        ):
            await flows.review(console, judgments, changes)

        mock_display.assert_called_once_with(
            console, judgments, changes, accepted=False
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_early_for_empty_judgments(self):
        """Test that review returns early for empty judgments list."""
        console = Console(file=StringIO(), force_terminal=True)
        changes = []
        judgments: list[Judgment] = []

        result = await flows.review(console, judgments, changes)

        assert result.judgments == []
        assert result.accepted is False
        output = strip_ansi(console.file.getvalue())
        assert "No AI judgments to review" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sets_user_decision_when_accepted(self):
        """Test that accepted review sets user_decision on judgments."""
        console = Console(file=StringIO(), force_terminal=True)
        changes = [
            Change(
                title="Test change",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]
        judgments = [
            Judgment(
                change_id=changes[0].get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Product",
                user_decision=None,  # Not yet reviewed
            )
        ]

        # Create a copy for the result
        result_judgments = [
            Judgment(
                change_id=changes[0].get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Product",
                user_decision=None,
            )
        ]

        mock_result = ReviewResult(judgments=result_judgments, accepted=True)

        with (
            patch.object(flows, "run_review_tui", return_value=mock_result),
            patch.object(flows, "display_review_results"),
        ):
            result = await flows.review(console, judgments, changes)

        # User decision should be set to AI decision when accepted
        assert result.judgments[0].user_decision == Decision.INCLUDE


class TestDisplayInflightSummary:
    """Tests for _display_inflight_summary function."""

    @pytest.mark.unit
    def test_displays_basic_summary(self):
        """Test that basic in-flight summary is displayed."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )

        _display_inflight_summary(console, report)

        output = strip_ansi(console.file.getvalue())
        assert "In-Flight Report Summary" in output
        assert "2024-11" in output
        assert "2024-11-01" in output
        assert "2024-11-30" in output
        assert "Changes Collected" in output

    @pytest.mark.unit
    def test_displays_workday_hours(self):
        """Test that Workday hours are displayed when present."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            total_hours=160.0,
            working_days=20,
            workday_validated=True,
        )

        _display_inflight_summary(console, report)

        output = strip_ansi(console.file.getvalue())
        assert "160" in output
        assert "20 days" in output
        assert "Complete" in output

    @pytest.mark.unit
    def test_displays_pto_when_present(self):
        """Test that PTO hours are displayed when absence_days > 0."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            total_hours=160.0,
            working_days=20,
            absence_days=2,  # 2 days PTO
            workday_validated=True,
        )

        _display_inflight_summary(console, report)

        output = strip_ansi(console.file.getvalue())
        assert "Paid Time Off" in output
        assert "2 days" in output
        assert "16 hours" in output  # 2 * 8

    @pytest.mark.unit
    def test_displays_incomplete_workday(self):
        """Test that incomplete Workday validation is shown."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            total_hours=120.0,
            working_days=15,
            workday_validated=False,
        )

        _display_inflight_summary(console, report)

        output = strip_ansi(console.file.getvalue())
        assert "INCOMPLETE" in output

    @pytest.mark.unit
    def test_displays_judgments_count(self):
        """Test that judgments count is displayed when present."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            judgments=[
                Judgment(
                    change_id="test-id",
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product",
                )
            ],
        )

        _display_inflight_summary(console, report)

        output = strip_ansi(console.file.getvalue())
        assert "AI Judgments" in output
        assert "1" in output


class TestDisplayCollectionSummary:
    """Tests for _display_collection_summary function."""

    @pytest.mark.unit
    def test_displays_changes_count(self):
        """Test that changes count is displayed."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=[
                Change(
                    title="Test",
                    repository=Repository(
                        host="github.com", path="org/repo", provider_type="github"
                    ),
                    number=100,
                )
            ],
        )

        _display_collection_summary(console, report)

        output = strip_ansi(console.file.getvalue())
        assert "Data Collection" in output
        assert "Did changes: 1" in output

    @pytest.mark.unit
    def test_displays_workday_data(self):
        """Test that Workday data is displayed when present."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            total_hours=160.0,
            working_days=20,
            workday_validated=True,
        )

        _display_collection_summary(console, report)

        output = strip_ansi(console.file.getvalue())
        assert "Work time: 20 days, 160 hours" in output

    @pytest.mark.unit
    def test_displays_pto_when_present(self):
        """Test that PTO info is displayed when absence_days > 0."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            total_hours=160.0,
            working_days=20,
            absence_days=2,  # 2 days PTO
            workday_validated=True,
        )

        _display_collection_summary(console, report)

        output = strip_ansi(console.file.getvalue())
        assert "Paid Time Off" in output
        assert "2 days" in output
        assert "16 hours" in output  # 2 * 8

    @pytest.mark.unit
    def test_displays_validation_warning(self):
        """Test that validation warning is displayed when incomplete."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            total_hours=120.0,
            working_days=15,
            workday_validated=False,
        )

        _display_collection_summary(console, report)

        output = strip_ansi(console.file.getvalue())
        assert "INCOMPLETE" in output


class TestResolveReviewMonth:
    """Tests for _resolve_review_month function."""

    @pytest.mark.unit
    def test_returns_none_for_empty_reports(self):
        """Test that None is returned when no reports available."""
        result = _resolve_review_month(None, [])
        assert result is None

    @pytest.mark.unit
    def test_returns_latest_for_none(self):
        """Test that latest report is returned for None spec."""
        reports = ["2024-09", "2024-10", "2024-11"]
        result = _resolve_review_month(None, reports)
        assert result == "2024-11"

    @pytest.mark.unit
    def test_returns_latest_for_current_alias(self):
        """Test that latest report is returned for 'current' alias."""
        reports = ["2024-09", "2024-10", "2024-11"]
        result = _resolve_review_month("current", reports)
        assert result == "2024-11"

    @pytest.mark.unit
    def test_returns_latest_for_latest_alias(self):
        """Test that latest report is returned for 'latest' alias."""
        reports = ["2024-09", "2024-10", "2024-11"]
        result = _resolve_review_month("latest", reports)
        assert result == "2024-11"

    @pytest.mark.unit
    def test_returns_previous_for_last_alias(self):
        """Test that second most recent is returned for 'last' alias."""
        reports = ["2024-09", "2024-10", "2024-11"]
        result = _resolve_review_month("last", reports)
        assert result == "2024-10"

    @pytest.mark.unit
    def test_returns_previous_for_previous_alias(self):
        """Test that second most recent is returned for 'previous' alias."""
        reports = ["2024-09", "2024-10", "2024-11"]
        result = _resolve_review_month("previous", reports)
        assert result == "2024-10"

    @pytest.mark.unit
    def test_returns_previous_for_prev_alias(self):
        """Test that second most recent is returned for 'prev' alias."""
        reports = ["2024-09", "2024-10", "2024-11"]
        result = _resolve_review_month("prev", reports)
        assert result == "2024-10"

    @pytest.mark.unit
    def test_returns_latest_when_only_one_report_for_last(self):
        """Test that latest is returned when only one report for 'last'."""
        reports = ["2024-11"]
        result = _resolve_review_month("last", reports)
        assert result == "2024-11"

    @pytest.mark.unit
    def test_returns_explicit_month_when_found(self):
        """Test that explicit YYYY-MM is returned when found."""
        reports = ["2024-09", "2024-10", "2024-11"]
        result = _resolve_review_month("2024-10", reports)
        assert result == "2024-10"

    @pytest.mark.unit
    def test_returns_none_for_unknown_month(self):
        """Test that None is returned for unknown month."""
        reports = ["2024-09", "2024-10", "2024-11"]
        result = _resolve_review_month("2024-12", reports)
        assert result is None


class TestSaveJudgmentsToAiCache:
    """Tests for _save_judgments_to_ai_cache function."""

    @pytest.mark.unit
    def test_saves_all_judgments(self):
        """Test that all judgments are saved to AI cache."""
        console = Console(file=StringIO(), force_terminal=True)
        judgments = [
            Judgment(
                change_id="test-1",
                decision=Decision.INCLUDE,
                reasoning="Test 1",
                product="Product",
            ),
            Judgment(
                change_id="test-2",
                decision=Decision.EXCLUDE,
                reasoning="Test 2",
                product="Product",
            ),
        ]

        with patch.object(flows, "JudgmentCacheManager") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache

            _save_judgments_to_ai_cache(console, judgments)

        assert mock_cache.add_judgment.call_count == 2
        output = strip_ansi(console.file.getvalue())
        assert "Saved 2 judgments" in output


class TestCollectFlow:
    """Tests for collect_flow function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_collection(self, isolated_home):
        """Test successful data collection flow."""
        console = Console(file=StringIO(), force_terminal=True)
        cache_file = cache_dir_for_home(isolated_home) / "test.json"

        mock_settings = MagicMock()
        mock_settings.workday.enabled = False  # Skip workday for simplicity

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "did_fetch_changes", return_value=[]),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.exists.return_value = False
            mock_cache.save.return_value = str(cache_file)
            mock_cache_cls.return_value = mock_cache

            result = await flows.collect_flow(console, month="2024-11")

        assert result is True
        mock_cache.save.assert_called_once()
        output = strip_ansi(console.file.getvalue())
        assert "Saved to" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_existing_report_without_force_fails(self, isolated_home):
        """Test that existing report without force returns False."""
        logger.debug("Using isolated home: %s", isolated_home)
        console = Console(file=StringIO(), force_terminal=True)

        mock_settings = MagicMock()

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.exists.return_value = True
            mock_cache.load.return_value = InFlightReport(
                month="2024-11",
                workday_start=date(2024, 11, 1),
                workday_end=date(2024, 11, 30),
                changes_since=date(2024, 10, 25),
                changes_until=date(2024, 11, 25),
            )
            mock_cache_cls.return_value = mock_cache

            result = await flows.collect_flow(
                console, month="2024-11", options=FlowOptions(force=False)
            )

        assert result is False
        output = strip_ansi(console.file.getvalue())
        assert "already exists" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_force_deletes_existing(self, isolated_home):
        """Test that force option deletes existing report."""
        console = Console(file=StringIO(), force_terminal=True)
        cache_file = cache_dir_for_home(isolated_home) / "test.json"

        mock_settings = MagicMock()
        mock_settings.workday.enabled = False

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "did_fetch_changes", return_value=[]),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.exists.return_value = True
            mock_cache.save.return_value = str(cache_file)
            mock_cache_cls.return_value = mock_cache

            result = await flows.collect_flow(
                console, month="2024-11", options=FlowOptions(force=True)
            )

        assert result is True
        mock_cache.delete.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skip_did_option(self, isolated_home):
        """Test that skip_did option skips Did collection."""
        console = Console(file=StringIO(), force_terminal=True)
        cache_file = cache_dir_for_home(isolated_home) / "test.json"

        mock_settings = MagicMock()
        mock_settings.workday.enabled = False

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "did_fetch_changes") as mock_fetch,
            patch.object(flows, "InFlightCache") as mock_cache_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.exists.return_value = False
            mock_cache.save.return_value = str(cache_file)
            mock_cache_cls.return_value = mock_cache

            await flows.collect_flow(
                console, month="2024-11", options=FlowOptions(skip_did=True)
            )

        mock_fetch.assert_not_called()
        output = strip_ansi(console.file.getvalue())
        assert "Skipping Did" in output


class TestReviewFlow:
    """Tests for review_flow function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_reports_fails(self):
        """Test that review fails when no reports available."""
        console = Console(file=StringIO(), force_terminal=True)

        with patch.object(flows, "InFlightCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.list_all.return_value = []
            mock_cache_cls.return_value = mock_cache

            result = await flows.review_flow(console)

        assert result is False
        output = strip_ansi(console.file.getvalue())
        assert "No in-flight reports found" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_changes_fails(self):
        """Test that review fails when report has no changes."""
        console = Console(file=StringIO(), force_terminal=True)

        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=[],  # No changes
        )

        with patch.object(flows, "InFlightCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.list_all.return_value = ["2024-11"]
            mock_cache.load.return_value = report
            mock_cache_cls.return_value = mock_cache

            result = await flows.review_flow(console)

        assert result is False
        output = strip_ansi(console.file.getvalue())
        assert "No changes to review" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_already_reviewed_without_force_shows_summary(self):
        """Test that already reviewed report shows summary without re-review."""
        console = Console(file=StringIO(), force_terminal=True)

        changes = [
            Change(
                title="Test",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=changes,
            judgments=[
                Judgment(
                    change_id=changes[0].get_change_id(),
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product",
                    user_decision=Decision.INCLUDE,  # Already reviewed
                )
            ],
        )

        with (
            patch.object(flows, "InFlightCache") as mock_cache_cls,
            patch.object(flows, "display_review_results"),
        ):
            mock_cache = MagicMock()
            mock_cache.list_all.return_value = ["2024-11"]
            mock_cache.load.return_value = report
            mock_cache_cls.return_value = mock_cache

            result = await flows.review_flow(console)

        assert result is True
        output = strip_ansi(console.file.getvalue())
        assert "already been reviewed" in output


class TestReportFlow:
    """Tests for report_flow function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_report_generation(self, isolated_home):
        """Test successful report generation flow."""
        logger.debug("Using isolated home: %s", isolated_home)
        console = Console(file=StringIO(), force_terminal=True)

        mock_settings = MagicMock()
        mock_settings.workday.enabled = False
        mock_settings.product.name = "TestProduct"
        mock_settings.ai.provider = "test"
        mock_settings.ai.model = "test-model"

        changes = [
            Change(
                title="Test",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=changes,
            judgments=[
                Judgment(
                    change_id=changes[0].get_change_id(),
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product",
                    user_decision=Decision.INCLUDE,
                )
            ],
        )

        mock_review_result = ReviewResult(judgments=report.judgments, accepted=True)

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
            patch.object(flows, "run_review_tui", return_value=mock_review_result),
            patch.object(flows, "display_review_results"),
            patch.object(flows, "JudgmentCacheManager"),
            patch.object(flows, "dist_flow", return_value=True) as mock_dist,
            patch.object(flows, "save_report_date"),  # Prevent history leak
        ):
            mock_cache = MagicMock()
            mock_cache.exists.return_value = True
            mock_cache.load.return_value = report
            mock_cache_cls.return_value = mock_cache

            result = await flows.report_flow(
                console, month="2024-11", options=FlowOptions(skip_ai=True)
            )

            # Verify dist_flow was called
            mock_dist.assert_called_once()

        assert result is True
        output = strip_ansi(console.file.getvalue())
        assert "Report complete for 2024-11" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_runs_collect_when_no_inflight(self, isolated_home):
        """Test that collect is run when no in-flight exists."""
        console = Console(file=StringIO(), force_terminal=True)
        cache_file = cache_dir_for_home(isolated_home) / "test.json"

        mock_settings = MagicMock()
        mock_settings.workday.enabled = False

        # report_flow checks: (1) force delete, (2) need collect? -> both False
        # collect_flow checks: (1) existing? -> False
        # Then after save, subsequent checks return True (report exists)
        exists_calls = [False, False, False, True]

        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=[],
        )

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "did_fetch_changes", return_value=[]),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
            patch.object(flows, "dist_flow", return_value=True),
            patch.object(flows, "save_report_date"),  # Prevent history leak
        ):
            mock_cache = MagicMock()
            mock_cache.exists.side_effect = exists_calls + [True] * 10
            mock_cache.load.return_value = report
            mock_cache.save.return_value = str(cache_file)
            mock_cache_cls.return_value = mock_cache

            result = await flows.report_flow(
                console,
                month="2024-11",
                options=FlowOptions(skip_ai=True, skip_review=True),
            )

        assert result is True
        output = strip_ansi(console.file.getvalue())
        assert "Saved to" in output  # From collect flow

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skips_review_tui_when_already_reviewed(self, isolated_home):
        """Test that report_flow skips TUI when all judgments already reviewed."""
        logger.debug("Using isolated home: %s", isolated_home)
        console = Console(file=StringIO(), force_terminal=True)

        mock_settings = MagicMock()
        mock_settings.workday.enabled = False
        mock_settings.product.name = "TestProduct"
        mock_settings.ai.provider = "test"
        mock_settings.ai.model = "test-model"

        changes = [
            Change(
                title="Test",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=changes,
            judgments=[
                Judgment(
                    change_id=changes[0].get_change_id(),
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product",
                    user_decision=Decision.INCLUDE,  # Already reviewed
                )
            ],
        )

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
            patch.object(flows, "run_review_tui") as mock_tui,
            patch.object(flows, "display_review_results"),
            patch.object(flows, "dist_flow", return_value=True),
            patch.object(flows, "save_report_date"),
        ):
            mock_cache = MagicMock()
            mock_cache.exists.return_value = True
            mock_cache.load.return_value = report
            mock_cache_cls.return_value = mock_cache

            result = await flows.report_flow(console, month="2024-11")

        assert result is True
        # TUI should NOT be called since report is already reviewed
        mock_tui.assert_not_called()


class TestFetchWorkdayData:
    """Tests for _fetch_workday_data function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fetches_and_validates(self):
        """Test that Workday data is fetched and validated."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        mock_settings = MagicMock()

        mock_work_hours = WorkHours(
            working_days=20,
            absence_days=0,
            total_hours=160.0,
            calendar_entries=[],
        )

        with (
            patch.object(flows, "WorkdayClient") as mock_client_cls,
            patch.object(flows, "validate_workday_coverage", return_value=[]),
        ):
            mock_client = MagicMock()
            mock_client.fetch_work_hours = AsyncMock(return_value=mock_work_hours)
            mock_client_cls.return_value = mock_client

            await flows._fetch_workday_data(
                console, report, mock_settings, date(2024, 11, 1), date(2024, 11, 30)
            )

        assert report.workday_validated is True
        assert report.total_hours == 160.0
        assert report.working_days == 20
        output = strip_ansi(console.file.getvalue())
        assert "All workdays have entries" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_shows_warning_for_missing_days_user_continues(self):
        """Test that warning is shown for missing Workday days and user continues."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        mock_settings = MagicMock()

        mock_work_hours = WorkHours(
            working_days=18,
            absence_days=0,
            total_hours=144.0,
            calendar_entries=[],
        )

        missing_days = [date(2024, 11, 4), date(2024, 11, 5)]

        with (
            patch.object(flows, "WorkdayClient") as mock_client_cls,
            patch.object(flows, "validate_workday_coverage", return_value=missing_days),
            patch.object(Confirm, "ask", return_value=True),  # User continues anyway
        ):
            mock_client = MagicMock()
            mock_client.fetch_work_hours = AsyncMock(return_value=mock_work_hours)
            mock_client_cls.return_value = mock_client

            result = await flows._fetch_workday_data(
                console, report, mock_settings, date(2024, 11, 1), date(2024, 11, 30)
            )

        assert result is True  # User chose to continue
        assert report.workday_validated is False
        output = strip_ansi(console.file.getvalue())
        assert "WARNING" in output
        assert "Missing Workday entries" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_missing_days_user_declines(self):
        """Test that user can decline to continue with missing Workday days."""
        console = Console(file=StringIO(), force_terminal=True)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        mock_settings = MagicMock()

        mock_work_hours = WorkHours(
            working_days=18,
            absence_days=0,
            total_hours=144.0,
            calendar_entries=[],
        )

        missing_days = [date(2024, 11, 4), date(2024, 11, 5)]

        with (
            patch.object(flows, "WorkdayClient") as mock_client_cls,
            patch.object(flows, "validate_workday_coverage", return_value=missing_days),
            patch.object(Confirm, "ask", return_value=False),  # User declines
        ):
            mock_client = MagicMock()
            mock_client.fetch_work_hours = AsyncMock(return_value=mock_work_hours)
            mock_client_cls.return_value = mock_client

            result = await flows._fetch_workday_data(
                console, report, mock_settings, date(2024, 11, 1), date(2024, 11, 30)
            )

        assert result is False  # User declined
        output = strip_ansi(console.file.getvalue())
        assert "Aborted by user" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_missing_days_non_interactive_fails(self):
        """Test that missing Workday days fails in non-interactive mode."""
        console = Console(file=StringIO(), force_terminal=False)  # Non-interactive
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        mock_settings = MagicMock()

        mock_work_hours = WorkHours(
            working_days=18,
            absence_days=0,
            total_hours=144.0,
            calendar_entries=[],
        )

        missing_days = [date(2024, 11, 4), date(2024, 11, 5)]

        with (
            patch.object(flows, "WorkdayClient") as mock_client_cls,
            patch.object(flows, "validate_workday_coverage", return_value=missing_days),
        ):
            mock_client = MagicMock()
            mock_client.fetch_work_hours = AsyncMock(return_value=mock_work_hours)
            mock_client_cls.return_value = mock_client

            result = await flows._fetch_workday_data(
                console, report, mock_settings, date(2024, 11, 1), date(2024, 11, 30)
            )

        assert result is False  # Non-interactive mode fails immediately
        output = strip_ansi(console.file.getvalue())
        assert "Cannot proceed with incomplete Workday coverage" in output
        assert "non-interactive mode" in output


class TestRunAiFiltering:
    """Tests for _run_ai_filtering function."""

    @pytest.mark.unit
    def test_runs_ai_filtering(self):
        """Test that AI filtering is run on changes."""
        console = Console(file=StringIO(), force_terminal=True)
        mock_settings = MagicMock()
        mock_settings.product.name = "TestProduct"
        mock_settings.ai.provider = "test"
        mock_settings.ai.model = "test-model"

        changes = [
            Change(
                title="Test change",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]

        mock_response = MagicMock()
        mock_response.judgments = [
            MagicMock(
                change_id=changes[0].get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Test reasoning",
            )
        ]

        with (
            patch.object(flows, "JudgmentCacheManager") as mock_cache_cls,
            patch.object(flows, "build_judgment_prompt", return_value="prompt"),
            patch.object(flows, "AIProvider") as mock_provider_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.get_history_for_prompt.return_value = []
            mock_cache_cls.return_value = mock_cache

            mock_provider = MagicMock()
            mock_provider.judge_changes.return_value = mock_response
            mock_provider_cls.return_value = mock_provider

            result = flows._run_ai_filtering(console, changes, mock_settings)

        assert len(result) == 1
        assert result[0].decision == Decision.INCLUDE

    @pytest.mark.unit
    def test_uses_cached_history(self):
        """Test that cached history is used for AI prompt."""
        console = Console(file=StringIO(), force_terminal=True)
        mock_settings = MagicMock()
        mock_settings.product.name = "TestProduct"
        mock_settings.ai.provider = "test"
        mock_settings.ai.model = "test-model"

        cached_judgments = [
            Judgment(
                change_id="old-1",
                decision=Decision.INCLUDE,
                reasoning="Old",
                product="TestProduct",
            )
        ]

        mock_response = MagicMock()
        mock_response.judgments = []

        with (
            patch.object(flows, "JudgmentCacheManager") as mock_cache_cls,
            patch.object(flows, "build_judgment_prompt") as mock_build,
            patch.object(flows, "AIProvider") as mock_provider_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.get_history_for_prompt.return_value = cached_judgments
            mock_cache_cls.return_value = mock_cache

            mock_provider = MagicMock()
            mock_provider.judge_changes.return_value = mock_response
            mock_provider_cls.return_value = mock_provider

            mock_build.return_value = "prompt"

            flows._run_ai_filtering(console, [], mock_settings)

        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args
        assert call_kwargs[1]["history"] == cached_judgments
        output = strip_ansi(console.file.getvalue())
        assert "Using 1 cached judgments" in output

    @pytest.mark.unit
    def test_uses_ai_config_advanced_options(self):
        """Test that AI config advanced options are passed to prompt builder."""
        from iptax.models import GeminiProviderConfig

        console = Console(file=StringIO(), force_terminal=True)
        mock_settings = MagicMock()
        mock_settings.product.name = "TestProduct"
        mock_settings.ai = GeminiProviderConfig(
            model="gemini-1.5-pro",
            hints=["Focus on security fixes", "Ignore documentation changes"],
            max_learnings=50,
            correction_ratio=0.5,
        )

        changes = [
            Change(
                title="Security fix",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]

        mock_response = MagicMock()
        mock_response.judgments = [
            MagicMock(
                change_id=changes[0].get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Security fix",
            )
        ]

        with (
            patch.object(flows, "JudgmentCacheManager") as mock_cache_cls,
            patch.object(flows, "build_judgment_prompt") as mock_build,
            patch.object(flows, "AIProvider") as mock_provider_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.get_history_for_prompt.return_value = []
            mock_cache_cls.return_value = mock_cache

            mock_provider = MagicMock()
            mock_provider.judge_changes.return_value = mock_response
            mock_provider_cls.return_value = mock_provider

            mock_build.return_value = "prompt"

            flows._run_ai_filtering(console, changes, mock_settings)

        # Check that get_history_for_prompt was called with custom values
        mock_cache.get_history_for_prompt.assert_called_once_with(
            "TestProduct",
            max_entries=50,
            correction_ratio=0.5,
        )

        # Check that build_judgment_prompt was called with hints
        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args
        assert call_kwargs[1]["hints"] == [
            "Focus on security fixes",
            "Ignore documentation changes",
        ]

    @pytest.mark.unit
    def test_uses_defaults_for_disabled_ai_config(self):
        """Test that default values are used when AI is disabled config type."""
        from iptax.models import DisabledAIConfig

        console = Console(file=StringIO(), force_terminal=True)
        mock_settings = MagicMock()
        mock_settings.product.name = "TestProduct"
        mock_settings.ai = DisabledAIConfig()

        mock_response = MagicMock()
        mock_response.judgments = []

        with (
            patch.object(flows, "JudgmentCacheManager") as mock_cache_cls,
            patch.object(flows, "build_judgment_prompt") as mock_build,
            patch.object(flows, "AIProvider") as mock_provider_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.get_history_for_prompt.return_value = []
            mock_cache_cls.return_value = mock_cache

            mock_provider = MagicMock()
            mock_provider.judge_changes.return_value = mock_response
            mock_provider_cls.return_value = mock_provider

            mock_build.return_value = "prompt"

            flows._run_ai_filtering(console, [], mock_settings)

        # Check that get_history_for_prompt was called with defaults
        mock_cache.get_history_for_prompt.assert_called_once()
        call_kwargs = mock_cache.get_history_for_prompt.call_args
        # Defaults from AIProviderConfigBase
        assert call_kwargs[1]["max_entries"] == 20
        assert call_kwargs[1]["correction_ratio"] == 0.75

        # Check that hints is None
        mock_build.assert_called_once()
        build_kwargs = mock_build.call_args
        assert build_kwargs[1]["hints"] is None


class TestDistFlow:
    """Tests for dist_flow function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_dist_ai_enabled(self, tmp_path):
        """Test successful dist with AI enabled and all judgments reviewed."""
        console = Console(file=StringIO(), force_terminal=True)
        output_dir = tmp_path / "output"

        mock_settings = MagicMock()
        mock_settings.workday.enabled = False
        mock_settings.ai.provider = "test"

        changes = [
            Change(
                title="Test change",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
                url="https://github.com/org/repo/pull/100",
            )
        ]
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=changes,
            judgments=[
                Judgment(
                    change_id=changes[0].get_change_id(),
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product",
                    user_decision=Decision.INCLUDE,
                )
            ],
        )

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
            patch.object(flows, "compile_report") as mock_compile,
            patch.object(flows, "generate_all") as mock_generate,
        ):
            mock_cache = MagicMock()
            mock_cache.list_all.return_value = ["2024-11"]
            mock_cache.load.return_value = report
            mock_cache_cls.return_value = mock_cache

            mock_report_data = MagicMock()
            mock_compile.return_value = mock_report_data

            mock_generate.return_value = [tmp_path / "report.md"]

            output_options = OutputOptions(output_dir=output_dir, output_format="md")
            result = await flows.dist_flow(
                console,
                month="2024-11",
                output_options=output_options,
                force=False,
            )

        assert result is True
        mock_compile.assert_called_once()
        mock_generate.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ai_disabled_without_force_fails(self):
        """Test that AI disabled without force flag fails."""
        console = Console(file=StringIO(), force_terminal=True)

        mock_settings = MagicMock()
        mock_settings.workday.enabled = False
        mock_settings.ai.provider = None  # AI disabled

        changes = [
            Change(
                title="Test change",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=changes,
            judgments=[],  # No AI judgments
        )

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.list_all.return_value = ["2024-11"]
            mock_cache.load.return_value = report
            mock_cache_cls.return_value = mock_cache

            result = await flows.dist_flow(console, month="2024-11", force=False)

        assert result is False
        output = strip_ansi(console.file.getvalue())
        assert "Changes require manual review" in output
        assert "--force" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ai_disabled_with_force_succeeds(self, tmp_path):
        """Test that AI disabled with force flag succeeds."""
        console = Console(file=StringIO(), force_terminal=True)

        mock_settings = MagicMock()
        mock_settings.workday.enabled = False
        mock_settings.ai.provider = None  # AI disabled

        changes = [
            Change(
                title="Test change",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
                url="https://github.com/org/repo/pull/100",
            )
        ]
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=changes,
            judgments=[],  # No AI judgments
        )

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
            patch.object(flows, "compile_report") as mock_compile,
            patch.object(flows, "generate_all") as mock_generate,
        ):
            mock_cache = MagicMock()
            mock_cache.list_all.return_value = ["2024-11"]
            mock_cache.load.return_value = report
            mock_cache_cls.return_value = mock_cache

            mock_report_data = MagicMock()
            mock_compile.return_value = mock_report_data

            mock_generate.return_value = [tmp_path / "report.md"]

            result = await flows.dist_flow(
                console,
                month="2024-11",
                output_options=flows.OutputOptions(),
                force=True,
            )

            assert result is True
        mock_compile.assert_called_once()
        mock_generate.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_changes_fails(self):
        """Test that dist fails when no changes to report."""
        console = Console(file=StringIO(), force_terminal=True)

        mock_settings = MagicMock()

        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=[],  # No changes
        )

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.list_all.return_value = ["2024-11"]
            mock_cache.load.return_value = report
            mock_cache_cls.return_value = mock_cache

            result = await flows.dist_flow(
                console, month="2024-11", output_options=OutputOptions()
            )

        assert result is False
        output = strip_ansi(console.file.getvalue())
        assert "No changes" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_report_not_found_fails(self):
        """Test that dist fails when report not found."""
        console = Console(file=StringIO(), force_terminal=True)

        mock_settings = MagicMock()

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.exists.return_value = False
            mock_cache_cls.return_value = mock_cache

            result = await flows.dist_flow(
                console, month="2024-11", output_options=OutputOptions()
            )

        assert result is False
        output = strip_ansi(console.file.getvalue())
        assert "No in-flight report found" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unreviewed_judgments_fail(self):
        """Test that dist fails when judgments not all reviewed."""
        console = Console(file=StringIO(), force_terminal=True)

        mock_settings = MagicMock()
        mock_settings.workday.enabled = False
        mock_settings.ai.provider = "test"

        changes = [
            Change(
                title="Test",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=changes,
            judgments=[
                Judgment(
                    change_id=changes[0].get_change_id(),
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product",
                    user_decision=None,  # Not reviewed
                )
            ],
        )

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.list_all.return_value = ["2024-11"]
            mock_cache.load.return_value = report
            mock_cache_cls.return_value = mock_cache

            result = await flows.dist_flow(console, month="2024-11")

        assert result is False
        output = strip_ansi(console.file.getvalue())
        assert "judgment(s) not reviewed" in output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_missing_hours_when_workday_enabled_fails(self):
        """Test that dist fails when Workday enabled but hours missing."""
        console = Console(file=StringIO(), force_terminal=True)

        mock_settings = MagicMock()
        mock_settings.workday.enabled = True
        mock_settings.ai.provider = "test"

        changes = [
            Change(
                title="Test",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=changes,
            judgments=[
                Judgment(
                    change_id=changes[0].get_change_id(),
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product",
                    user_decision=Decision.INCLUDE,
                )
            ],
            total_hours=None,  # Missing hours
        )

        with (
            patch.object(flows, "config_load_settings", return_value=mock_settings),
            patch.object(flows, "InFlightCache") as mock_cache_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.list_all.return_value = ["2024-11"]
            mock_cache.load.return_value = report
            mock_cache_cls.return_value = mock_cache

            result = await flows.dist_flow(console, month="2024-11")

        assert result is False
        output = strip_ansi(console.file.getvalue())
        assert "Missing work hours data" in output


class TestConfirmOrForce:
    """Tests for confirm_or_force function."""

    @pytest.mark.unit
    def test_returns_true_when_force_is_true(self):
        """Test returns True immediately when force=True."""
        result = confirm_or_force("Any prompt?", force=True)
        assert result is True

    @pytest.mark.unit
    def test_returns_true_when_user_confirms(self):
        """Test returns True when user confirms."""
        with patch("iptax.cli.flows.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.unsafe_ask.return_value = True
            result = confirm_or_force("Continue?", force=False)

        assert result is True
        mock_confirm.assert_called_once_with("Continue?", default=False)

    @pytest.mark.unit
    def test_returns_false_when_user_declines(self):
        """Test returns False when user declines."""
        with patch("iptax.cli.flows.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.unsafe_ask.return_value = False
            result = confirm_or_force("Continue?", force=False)

        assert result is False


class TestClearAiCache:
    """Tests for clear_ai_cache function."""

    @pytest.mark.unit
    def test_clears_cache_when_force(self, tmp_path: Path, capsys):
        """Test clears AI cache without confirmation when force=True."""
        ai_cache = tmp_path / "ai_cache.json"
        ai_cache.write_text("{}")

        with patch("iptax.cli.flows.get_ai_cache_path", return_value=ai_cache):
            clear_ai_cache(force=True)

        assert not ai_cache.exists()
        captured = capsys.readouterr()
        assert "Cleared AI judgment cache" in captured.out

    @pytest.mark.unit
    def test_prints_message_when_no_cache(self, tmp_path: Path, capsys):
        """Test prints message when no AI cache exists."""
        ai_cache = tmp_path / "nonexistent.json"

        with patch("iptax.cli.flows.get_ai_cache_path", return_value=ai_cache):
            clear_ai_cache(force=True)

        captured = capsys.readouterr()
        assert "No AI cache to clear" in captured.out

    @pytest.mark.unit
    def test_cancels_when_user_declines(self, tmp_path: Path, capsys):
        """Test prints cancelled when user declines confirmation."""
        ai_cache = tmp_path / "ai_cache.json"
        ai_cache.write_text("{}")

        with (
            patch("iptax.cli.flows.get_ai_cache_path", return_value=ai_cache),
            patch("iptax.cli.flows.questionary.confirm") as mock_confirm,
        ):
            mock_confirm.return_value.unsafe_ask.return_value = False
            clear_ai_cache(force=False)

        assert ai_cache.exists()  # File should still exist
        captured = capsys.readouterr()
        assert "cancelled" in captured.out


class TestClearInflightCache:
    """Tests for clear_inflight_cache function."""

    @pytest.mark.unit
    def test_clears_all_when_force(self, capsys):
        """Test clears all in-flight reports when force=True."""
        mock_cache = MagicMock(spec=InFlightCache)
        mock_cache.clear_all.return_value = 3

        clear_inflight_cache(mock_cache, force=True)

        mock_cache.clear_all.assert_called_once()
        captured = capsys.readouterr()
        assert "Cleared 3 in-flight report(s)" in captured.out

    @pytest.mark.unit
    def test_cancels_when_user_declines(self, capsys):
        """Test prints cancelled when user declines."""
        mock_cache = MagicMock(spec=InFlightCache)

        with patch("iptax.cli.flows.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.unsafe_ask.return_value = False
            clear_inflight_cache(mock_cache, force=False)

        mock_cache.clear_all.assert_not_called()
        captured = capsys.readouterr()
        assert "cancelled" in captured.out


class TestClearHistoryCache:
    """Tests for clear_history_cache function."""

    @pytest.mark.unit
    def test_clears_history_when_force(self, tmp_path: Path, capsys):
        """Test clears history when force=True."""
        history_file = tmp_path / "history.json"
        history_file.write_text("{}")

        with (
            patch("iptax.cli.flows.get_history_path", return_value=history_file),
            patch("iptax.cli.flows.HistoryManager") as mock_mgr_cls,
        ):
            mock_mgr = MagicMock()
            mock_mgr_cls.return_value = mock_mgr

            clear_history_cache(force=True)

        mock_mgr.clear.assert_called_once()
        captured = capsys.readouterr()
        assert "Cleared report history" in captured.out

    @pytest.mark.unit
    def test_prints_message_when_no_history(self, tmp_path: Path, capsys):
        """Test prints message when no history exists."""
        history_file = tmp_path / "nonexistent.json"

        with patch("iptax.cli.flows.get_history_path", return_value=history_file):
            clear_history_cache(force=True)

        captured = capsys.readouterr()
        assert "No history to clear" in captured.out

    @pytest.mark.unit
    def test_cancels_when_user_declines(self, tmp_path: Path, capsys):
        """Test prints cancelled when user declines."""
        history_file = tmp_path / "history.json"
        history_file.write_text("{}")

        with (
            patch("iptax.cli.flows.get_history_path", return_value=history_file),
            patch("iptax.cli.flows.questionary.confirm") as mock_confirm,
        ):
            mock_confirm.return_value.unsafe_ask.return_value = False
            clear_history_cache(force=False)

        assert history_file.exists()
        captured = capsys.readouterr()
        assert "cancelled" in captured.out
