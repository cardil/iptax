"""Progress UI for AI operations."""

from collections.abc import Generator
from contextlib import contextmanager

from rich.console import Console
from rich.status import Status


@contextmanager
def ai_progress(
    console: Console, message: str = "Consulting AI..."
) -> Generator[Status, None, None]:
    """Context manager that shows a spinner during AI calls.

    Usage:
        with ai_progress(console, "Analyzing changes..."):
            response = provider.judge_changes(prompt)

    Args:
        console: Rich console for output
        message: Status message to display during processing

    Yields:
        Status object (can be used to update message if needed)
    """
    with console.status(f"[bold blue]{message}[/]", spinner="dots") as status:
        yield status
