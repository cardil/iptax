"""Tests for CLI flows module."""

from datetime import date
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from iptax.cli import flows
from iptax.models import Change, Decision, Judgment, Repository

from .conftest import strip_ansi


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
        assert "AI Analysis Summary" in output
        assert "INCLUDE: 1" in output

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
        assert "INCLUDE: 1" in output
        assert "EXCLUDE: 1" in output
        assert "UNCERTAIN: 1" in output

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
