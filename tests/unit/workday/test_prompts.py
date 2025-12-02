"""Unit tests for iptax.workday.prompts module."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from iptax.workday.prompts import (
    ProgressController,
    prompt_credentials_async,
    prompt_credentials_sync,
    prompt_manual_work_hours,
)


class TestPromptManualWorkHours:
    """Test prompt_manual_work_hours function."""

    def test_prompts_with_calculated_defaults(self):
        """Test that manual prompt uses calculated defaults."""

        with patch("iptax.workday.prompts.questionary") as mock_questionary:
            mock_text = MagicMock()
            mock_text.unsafe_ask.side_effect = ["21", "2", "168.0"]
            mock_questionary.text.return_value = mock_text

            result = prompt_manual_work_hours(
                date(2024, 11, 1),
                date(2024, 11, 30),
            )

            assert result.working_days == 21
            assert result.absence_days == 2
            assert result.total_hours == 168.0

            # Check that text was called 3 times (days, absence, hours)
            assert mock_questionary.text.call_count == 3


class TestPromptCredentialsSync:
    """Test prompt_credentials_sync function."""

    def test_prompts_for_username_and_password(self):
        """Test that credentials prompt asks for username and password."""

        with patch("iptax.workday.prompts.questionary") as mock_questionary:
            mock_text = MagicMock()
            mock_text.unsafe_ask.return_value = "testuser"
            mock_password = MagicMock()
            mock_password.unsafe_ask.return_value = "testpass"

            mock_questionary.text.return_value = mock_text
            mock_questionary.password.return_value = mock_password

            username, password = prompt_credentials_sync()

            assert username == "testuser"
            # Hardcoded password is for test assertion only (noqa:S105)
            assert password == "testpass"  # noqa: S105
            mock_questionary.text.assert_called_once()
            mock_questionary.password.assert_called_once()


class TestPromptCredentialsAsync:
    """Test prompt_credentials_async function."""

    @pytest.mark.asyncio
    async def test_prompts_for_username_and_password_async(self):
        """Test that async credentials prompt asks for username and password."""
        from unittest.mock import AsyncMock

        with patch("iptax.workday.prompts.questionary") as mock_questionary:
            mock_text = MagicMock()
            mock_text.unsafe_ask_async = AsyncMock(return_value="testuser")
            mock_password = MagicMock()
            mock_password.unsafe_ask_async = AsyncMock(return_value="testpass")

            mock_questionary.text.return_value = mock_text
            mock_questionary.password.return_value = mock_password

            username, password = await prompt_credentials_async()

            assert username == "testuser"
            # Hardcoded password is for test assertion only (noqa:S105)
            assert password == "testpass"  # noqa: S105
            mock_questionary.text.assert_called_once()
            mock_questionary.password.assert_called_once()


class TestProgressController:
    """Test ProgressController class."""

    def test_context_manager_creates_and_closes(self):
        """Test that ProgressController works as a context manager."""
        with patch("iptax.workday.prompts.Console") as mock_console_cls:
            mock_console = MagicMock()
            mock_console_cls.return_value = mock_console

            with ProgressController() as progress:
                assert progress is not None
                assert progress._progress is None  # Not created yet

    def test_create_starts_progress(self):
        """Test that create() starts the progress bar."""
        with patch("iptax.workday.prompts.Console"):
            progress = ProgressController()
            progress.create(10, "Testing...")

            assert progress._progress is not None
            assert progress._task_id is not None
            assert progress._total_steps == 10

            progress.close()

    def test_advance_updates_progress(self):
        """Test that advance() updates the progress bar."""
        with patch("iptax.workday.prompts.Console"):
            progress = ProgressController()
            progress.create(5, "Starting...")

            # Mock the progress object
            mock_progress = MagicMock()
            progress._progress = mock_progress
            progress._task_id = "test_task"

            progress.advance("Step 1")

            mock_progress.update.assert_called_once_with(
                "test_task", advance=1, description="Step 1"
            )

            progress.close()

    def test_stop_and_resume(self):
        """Test that stop() and resume() work correctly."""
        with patch("iptax.workday.prompts.Console"):
            progress = ProgressController()
            progress.create(5, "Starting...")

            # Mock the progress object
            mock_progress = MagicMock()
            progress._progress = mock_progress

            progress.stop()
            mock_progress.stop.assert_called_once()

            progress.resume()
            mock_progress.start.assert_called_once()

            progress.close()

    def test_advance_with_no_progress_does_nothing(self):
        """Test that advance() does nothing when progress is not created."""
        progress = ProgressController()
        # Should not raise an exception
        progress.advance("Test")

    def test_stop_with_no_progress_does_nothing(self):
        """Test that stop() does nothing when progress is not created."""
        progress = ProgressController()
        # Should not raise an exception
        progress.stop()

    def test_resume_with_no_progress_does_nothing(self):
        """Test that resume() does nothing when progress is not created."""
        progress = ProgressController()
        # Should not raise an exception
        progress.resume()
