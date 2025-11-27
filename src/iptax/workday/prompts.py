"""User prompt functions for Workday integration."""

from __future__ import annotations

from datetime import date

import questionary
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from iptax.models import WorkHours
from iptax.workday.utils import _is_valid_float, calculate_working_days


class ProgressController:
    """Controller for progress bar during Workday automation.

    Encapsulates progress bar management and provides callbacks for
    authentication and scraping modules to control the UI.
    """

    def __init__(self, console: Console | None = None) -> None:
        """Initialize ProgressController.

        Args:
            console: Rich console to use (creates new one if not provided)
        """
        self.console = console or Console()
        self._progress: Progress | None = None
        self._task_id: TaskID | None = None
        self._total_steps: int = 0

    def create(self, total_steps: int, description: str = "Working...") -> None:
        """Create and start the progress bar.

        Args:
            total_steps: Total number of steps for the progress bar
            description: Initial description text
        """
        self._total_steps = total_steps
        self._progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
        )
        self._progress.start()
        self._task_id = self._progress.add_task(description, total=total_steps)

    def close(self) -> None:
        """Stop and clean up the progress bar."""
        if self._progress is not None:
            self._progress.stop()
            self._progress = None
            self._task_id = None

    def advance(self, description: str) -> None:
        """Advance the progress bar by one step.

        Args:
            description: New description text to display
        """
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, advance=1, description=description)

    def stop(self) -> None:
        """Stop/hide the progress bar temporarily.

        Use this before showing interactive prompts.
        """
        if self._progress is not None:
            self._progress.stop()

    def resume(self) -> None:
        """Resume the progress bar after stopping.

        Use this after interactive prompts complete.
        """
        if self._progress is not None:
            self._progress.start()

    def __enter__(self) -> ProgressController:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit - ensures progress is cleaned up."""
        self.close()


def prompt_manual_work_hours(
    start_date: date,
    end_date: date,
) -> WorkHours:
    """Prompt user for manual work hours input.

    Calculates default working days based on calendar (Mon-Fri).

    Args:
        start_date: Start of the reporting period
        end_date: End of the reporting period

    Returns:
        WorkHours with user-provided data
    """
    # Calculate defaults
    default_days = calculate_working_days(start_date, end_date)

    month_name = start_date.strftime("%B %Y")

    questionary.print("")
    questionary.print(f"Enter work hours for {month_name}:", style="bold")

    days_str = questionary.text(
        f"Working days in the period [{default_days}]:",
        default=str(default_days),
        validate=lambda x: x.isdigit() or "Must be a number",
    ).unsafe_ask()
    working_days = int(days_str)

    absence_str = questionary.text(
        "Absence days (vacation, sick leave, holidays) [0]:",
        default="0",
        validate=lambda x: x.isdigit() or "Must be a number",
    ).unsafe_ask()
    absence_days = int(absence_str)

    calculated_hours = working_days * 8.0
    hours_str = questionary.text(
        f"Total working hours [{calculated_hours}]:",
        default=str(calculated_hours),
        validate=lambda x: _is_valid_float(x) or "Must be a number",
    ).unsafe_ask()
    total_hours = float(hours_str)

    return WorkHours(
        working_days=working_days,
        absence_days=absence_days,
        total_hours=total_hours,
    )


def prompt_credentials_sync() -> tuple[str, str]:
    """Prompt user for SSO credentials (sync version).

    Returns:
        Tuple of (username, password)
    """
    questionary.print(
        "⚠ SSO login form detected. Please enter your credentials.",
        style="yellow",
    )
    username = questionary.text(
        "Username:",
        validate=lambda x: len(x.strip()) > 0 or "Username cannot be empty",
    ).unsafe_ask()
    password = questionary.password(
        "Password:",
        validate=lambda x: len(x.strip()) > 0 or "Password cannot be empty",
    ).unsafe_ask()
    return username, password


async def prompt_credentials_async() -> tuple[str, str]:
    """Prompt user for SSO credentials (async version).

    Returns:
        Tuple of (username, password)
    """
    questionary.print(
        "⚠ SSO login form detected. Please enter your credentials.",
        style="yellow",
    )
    username = await questionary.text(
        "Username:",
        validate=lambda x: len(x.strip()) > 0 or "Username cannot be empty",
    ).ask_async()
    password = await questionary.password(
        "Password:",
        validate=lambda x: len(x.strip()) > 0 or "Password cannot be empty",
    ).ask_async()
    return username, password
