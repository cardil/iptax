"""Unit tests for AI TUI progress indicators."""

from unittest.mock import Mock

import pytest
from rich.console import Console

from iptax.ai.tui import ai_progress


def test_ai_progress_context_manager():
    """Test ai_progress context manager shows and hides spinner."""
    mock_console = Mock(spec=Console)
    mock_status = Mock()
    mock_console.status.return_value.__enter__ = Mock(return_value=mock_status)
    mock_console.status.return_value.__exit__ = Mock(return_value=None)

    with ai_progress(mock_console, "Test message"):
        pass

    # Verify console.status was called with correct parameters
    mock_console.status.assert_called_once_with(
        "[bold blue]Test message[/]", spinner="dots"
    )


def test_ai_progress_default_message():
    """Test ai_progress uses default message when none provided."""
    mock_console = Mock(spec=Console)
    mock_status = Mock()
    mock_console.status.return_value.__enter__ = Mock(return_value=mock_status)
    mock_console.status.return_value.__exit__ = Mock(return_value=None)

    with ai_progress(mock_console):
        pass

    # Verify default message was used
    mock_console.status.assert_called_once_with(
        "[bold blue]Consulting AI...[/]", spinner="dots"
    )


def test_ai_progress_yields_status():
    """Test ai_progress yields the status object."""
    mock_console = Mock(spec=Console)
    mock_status = Mock()
    mock_console.status.return_value.__enter__ = Mock(return_value=mock_status)
    mock_console.status.return_value.__exit__ = Mock(return_value=None)

    with ai_progress(mock_console, "Test") as status:
        assert status == mock_status


def test_ai_progress_with_real_console():
    """Test ai_progress works with a real Console object."""
    console = Console()

    # Should not raise any exceptions
    with ai_progress(console, "Processing..."):
        # Simulate some work
        pass


def test_ai_progress_exception_handling():
    """Test ai_progress properly handles exceptions."""
    mock_console = Mock(spec=Console)
    mock_status = Mock()
    mock_console.status.return_value.__enter__ = Mock(return_value=mock_status)
    mock_console.status.return_value.__exit__ = Mock(return_value=None)

    with (
        pytest.raises(ValueError, match="Test exception"),
        ai_progress(mock_console, "Test"),
    ):
        raise ValueError("Test exception")

    # Verify __exit__ was called (cleanup happened)
    assert mock_console.status.return_value.__exit__.called


def test_ai_progress_multiple_calls():
    """Test ai_progress can be called multiple times."""
    mock_console = Mock(spec=Console)
    mock_status = Mock()
    mock_console.status.return_value.__enter__ = Mock(return_value=mock_status)
    mock_console.status.return_value.__exit__ = Mock(return_value=None)

    # First call
    with ai_progress(mock_console, "First"):
        pass

    # Second call
    with ai_progress(mock_console, "Second"):
        pass

    # Verify console.status was called twice
    assert mock_console.status.call_count == 2
