"""Textual-based TUI review interface for AI judgments."""

from contextlib import suppress
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from iptax.models import Change, Decision, Judgment

# Decision icons
ICONS = {
    Decision.INCLUDE: "✓",
    Decision.EXCLUDE: "✗",
    Decision.UNCERTAIN: "?",
}

COLORS = {
    Decision.INCLUDE: "green",
    Decision.EXCLUDE: "red",
    Decision.UNCERTAIN: "orange",
}


class ListScroll(VerticalScroll):
    """VerticalScroll without up/down key bindings.

    This allows using up/down arrows for list navigation without
    triggering scroll behavior. PageUp/Down and mouse scroll still work.
    """

    # Override to remove all navigation bindings - we handle them in the app
    BINDINGS: ClassVar[list] = []

    # Textual widget method override - intentionally untyped to match parent
    def scroll_visible(  # type: ignore[no-untyped-def]
        self,
        *args,  # noqa: ANN002 - Textual widget signature
        **kwargs,  # noqa: ANN003 - Textual widget signature
    ) -> None:
        """Override to prevent automatic scroll-to-visible behavior."""
        pass

    # Textual widget method override - intentionally untyped to match parent
    def scroll_to_widget(  # type: ignore[no-untyped-def,override]
        self,
        *args,  # noqa: ANN002 - Textual widget signature
        **kwargs,  # noqa: ANN003 - Textual widget signature
    ) -> None:
        """Override to prevent scroll-to-widget behavior."""
        pass

    # Textual widget method override - intentionally untyped to match parent
    def scroll_to_center(  # type: ignore[no-untyped-def]
        self,
        *args,  # noqa: ANN002 - Textual widget signature
        **kwargs,  # noqa: ANN003 - Textual widget signature
    ) -> None:
        """Override to prevent scroll-to-center behavior."""
        pass

    def action_scroll_up(self) -> None:
        """Block scroll_up action."""
        pass

    def action_scroll_down(self) -> None:
        """Block scroll_down action."""
        pass


class ReviewResult:
    """Result of the review process."""

    def __init__(self, judgments: list[Judgment], *, accepted: bool = False) -> None:
        """Initialize review result.

        Args:
            judgments: List of judgments (potentially modified)
            accepted: Whether user accepted (keyword-only)
        """
        self.judgments = judgments
        self.accepted = accepted


def needs_review(judgments: list[Judgment]) -> bool:
    """Check if any judgment is UNCERTAIN (needs human review).

    Args:
        judgments: List of AI judgments

    Returns:
        True if any judgment has UNCERTAIN decision
    """
    return any(j.decision == Decision.UNCERTAIN for j in judgments)


class ReasonModal(ModalScreen[str | None]):
    """Modal for entering reason for decision change."""

    CSS = """
    ReasonModal {
        align: center middle;
    }

    #reason-dialog {
        width: 60;
        height: auto;
        min-height: 12;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #reason-dialog Label {
        margin-bottom: 1;
    }

    #reason-input {
        margin-bottom: 1;
    }

    #reason-buttons {
        height: auto;
        min-height: 3;
        layout: horizontal;
        align: center middle;
    }

    #reason-buttons Button {
        margin: 0 1;
        min-width: 10;
    }
    """

    def __init__(self, current_reason: str = "") -> None:
        super().__init__()
        self.current_reason = current_reason

    def compose(self) -> ComposeResult:
        """Create modal content."""
        with Container(id="reason-dialog"):
            yield Label("Why are you changing this decision?")
            yield Input(
                placeholder="Enter reason (optional)",
                value=self.current_reason,
                id="reason-input",
            )
            with Container(id="reason-buttons"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Skip", variant="default", id="skip-btn")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input field - submit the form."""
        self.dismiss(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-btn":
            reason_input = self.query_one("#reason-input", Input)
            self.dismiss(reason_input.value)
        else:
            self.dismiss(None)

    def on_key(self, event: Key) -> None:
        """Handle escape key."""
        if event.key == "escape":
            self.dismiss(None)
            event.stop()  # Prevent bubbling to app-level key handlers


class ReviewApp(App):
    """Textual app for reviewing AI judgments."""

    TITLE = "iptax"
    ENABLE_COMMAND_PALETTE = False

    CSS = """
    #list-container {
        height: 1fr;
        padding: 1;
    }

    #changes-list {
        height: 1fr;
        scrollbar-gutter: stable;
    }

    .change-row {
        height: 1;
    }

    .change-row:focus {
        /* Prevent focus styling */
    }

    .selected {
        background: $primary-background-darken-1;
        color: white;
    }

    #footer-bar {
        height: 1;
        background: $panel;
        padding: 0 1;
        dock: bottom;
    }

    .detail-header {
        background: $primary;
        color: $text;
        padding: 0 1;
        text-style: bold;
        height: 3;
    }

    .detail-section {
        padding: 1;
        margin-top: 1;
    }

    .detail-section-title {
        color: $secondary;
        text-style: bold;
        margin-bottom: 1;
    }

    .ai-decision-include {
        color: green;
        text-style: bold;
    }

    .ai-decision-exclude {
        color: red;
        text-style: bold;
    }

    .ai-decision-uncertain {
        color: orange;
        text-style: bold;
    }

    .user-override {
        color: ansi_blue;
        text-style: italic;
    }
    """

    def __init__(
        self,
        judgments: list[Judgment],
        changes: list[Change],
    ) -> None:
        super().__init__()
        self.theme = "textual-ansi"
        self.judgments = judgments
        self.changes = changes
        self.change_map = {c.get_change_id(): c for c in changes}
        self.accepted = False
        self.in_detail_view = False
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Container(
            ListScroll(id="changes-list"),
            id="list-container",
        )
        yield Static(id="footer-bar")

    def on_mount(self) -> None:
        """Initialize the UI after mounting."""
        self._refresh_list()
        self._refresh_footer()

    def _count_decisions(self) -> tuple[int, int, int]:
        """Count decisions by type."""
        include_count = sum(
            1 for j in self.judgments if j.final_decision == Decision.INCLUDE
        )
        exclude_count = sum(
            1 for j in self.judgments if j.final_decision == Decision.EXCLUDE
        )
        uncertain_count = sum(
            1 for j in self.judgments if j.final_decision == Decision.UNCERTAIN
        )
        return include_count, exclude_count, uncertain_count

    def _refresh_list(self) -> None:
        """Refresh the changes list."""
        changes_list = self.query_one("#changes-list", ListScroll)
        changes_list.remove_children()

        for i, judgment in enumerate(self.judgments):
            change = self.change_map.get(judgment.change_id)
            icon = ICONS[judgment.final_decision]
            color = COLORS[judgment.final_decision]
            title = change.title if change else judgment.change_id

            # Add edited marker on right side, dimmed
            edited_marker = " [dim]*[/]" if judgment.was_corrected else ""
            row_content = f"  [{color}]{icon}[/] {title}{edited_marker}"

            # Use CSS class for selection styling
            classes = (
                "change-row selected" if i == self.selected_index else "change-row"
            )
            row = Static(row_content, classes=classes)
            changes_list.mount(row)

        # Store row references for later updates
        self._row_widgets: list[Static] = list(changes_list.query(Static))

    def _update_selection(self, old_index: int, new_index: int) -> None:
        """Update selection using CSS class changes."""
        if not hasattr(self, "_row_widgets") or not self._row_widgets:
            return

        # Update old row - remove selected class
        if 0 <= old_index < len(self._row_widgets):
            old_row = self._row_widgets[old_index]
            old_row.remove_class("selected")

        # Update new row - add selected class
        if 0 <= new_index < len(self._row_widgets):
            new_row = self._row_widgets[new_index]
            new_row.add_class("selected")

            # Check if new row is visible, scroll if needed
            self._ensure_row_visible(new_row, new_index)

    def _ensure_row_visible(self, _row: Static, index: int) -> None:
        """Scroll only if the row is outside the visible viewport."""
        with suppress(AttributeError, LookupError):
            changes_list = self.query_one("#changes-list", ListScroll)

            # Get viewport info
            scroll_y = changes_list.scroll_y
            viewport_height = changes_list.size.height

            # Row position (each row is 1 unit high)
            row_top = index
            row_bottom = index + 1
            viewport_bottom = scroll_y + viewport_height

            # Only scroll if row is outside visible area
            if row_top < scroll_y:
                # Row is above viewport - scroll up to show it
                changes_list.scroll_to(y=row_top, animate=False)
            elif row_bottom > viewport_bottom:
                # Row is below viewport - scroll down to show it
                changes_list.scroll_to(y=row_bottom - viewport_height, animate=False)

    def _refresh_footer(self) -> None:
        """Refresh the footer bar based on current view."""
        footer = self.query_one("#footer-bar", Static)
        include_count, exclude_count, uncertain_count = self._count_decisions()
        total = len(self.judgments)
        current = self.selected_index + 1 if total else 0

        status = (
            f"[{current}/{total}] "
            f"[green]✓INCLUDE: {include_count}[/]  "
            f"[red]✗EXCLUDE: {exclude_count}[/]  "
            f"[orange]?UNCERTAIN: {uncertain_count}[/]"
        )

        if self.in_detail_view:
            judgment = self.judgments[self.selected_index]
            keys = "[bold]Esc[/] Back  [bold]f[/] Flip"
            if judgment.was_corrected:
                keys += "  [bold]r[/] Reason"
            footer.update(f"{status}   {keys}")
        else:
            keys = "[bold]↑↓[/] Navigate  [bold]Enter[/] Details"
            if uncertain_count == 0:
                keys += "  [bold]d[/] Review Done"
            keys += "  [bold]Ctrl+Q[/] Quit"
            footer.update(f"{status}   {keys}")

    def _show_detail_view(self) -> None:
        """Show detail view for selected judgment."""
        self.in_detail_view = True
        judgment = self.judgments[self.selected_index]
        change = self.change_map.get(judgment.change_id)

        title = change.title if change else judgment.change_id
        repo = judgment.change_id
        url = change.get_url() if change else "N/A"

        # Build colorful detail view
        ai_color = COLORS[judgment.decision]
        ai_icon = ICONS[judgment.decision]
        current_color = COLORS[judgment.final_decision]
        current_icon = ICONS[judgment.final_decision]

        content_parts = []

        # Header
        content_parts.append(
            f"[bold reverse] Change Details [{self.selected_index + 1}/"
            f"{len(self.judgments)}] [/]\n"
        )

        # Change info section
        content_parts.append("[bold ansi_blue]📋 Change Information[/]")
        content_parts.append(f"   [bold]Title:[/] {title}")
        content_parts.append(f"   [bold]Repo:[/] {repo}")
        content_parts.append(f"   [bold]URL:[/] {url}\n")

        # AI Decision section
        content_parts.append("[bold ansi_blue]🤖 AI Analysis[/]")
        content_parts.append(
            f"   [bold]Decision:[/] [{ai_color}]{ai_icon} {judgment.decision.value}[/]"
        )
        content_parts.append(f"   [bold]Reasoning:[/] {judgment.reasoning}\n")

        # Current Decision section
        content_parts.append("[bold ansi_blue]📊 Current Status[/]")
        content_parts.append(
            f"   [bold]Decision:[/] [{current_color}]{current_icon} "
            f"{judgment.final_decision.value}[/]"
        )

        if judgment.was_corrected and judgment.user_decision:
            content_parts.append(
                f"   [bold]User Override:[/] [ansi_blue italic]"
                f"{judgment.user_decision.value}[/]"
            )
            if judgment.user_reasoning:
                content_parts.append(
                    f"   [bold]User Reason:[/] [ansi_blue italic]"
                    f"{judgment.user_reasoning}[/]"
                )

        # Update UI for detail view - remove all children first
        list_container = self.query_one("#list-container", Container)
        list_container.remove_children()
        # Don't use fixed ID to avoid DuplicateIds on refresh
        list_container.mount(
            Static("\n".join(content_parts), classes="detail-content", markup=True)
        )

        self._refresh_footer()

    def _show_list_view(self) -> None:
        """Return to list view."""
        self.in_detail_view = False
        list_container = self.query_one("#list-container", Container)
        list_container.remove_children()
        list_container.mount(ListScroll(id="changes-list"))
        self._refresh_list()
        self._refresh_footer()

    def _flip_decision(self) -> None:
        """Flip decision and prompt for reason."""
        judgment = self.judgments[self.selected_index]
        current = judgment.final_decision

        if current == Decision.INCLUDE:
            new_decision = Decision.EXCLUDE
        elif current == Decision.EXCLUDE:
            new_decision = Decision.INCLUDE
        else:  # UNCERTAIN
            new_decision = Decision.INCLUDE

        # Set new decision first
        judgment.user_decision = new_decision

        # Prompt for reason via modal
        def handle_reason(reason: str | None) -> None:
            if reason:
                judgment.user_reasoning = reason
            # If user decision matches AI decision, clear user data
            if judgment.user_decision == judgment.decision:
                judgment.user_decision = None
                judgment.user_reasoning = None
            if self.in_detail_view:
                self._show_detail_view()
            else:
                self._refresh_list()
            self._refresh_footer()

        self.push_screen(ReasonModal(judgment.user_reasoning or ""), handle_reason)

    def _edit_reason(self) -> None:
        """Edit the reason for current decision."""
        judgment = self.judgments[self.selected_index]

        def handle_reason(reason: str | None) -> None:
            if reason is not None:  # User didn't cancel
                judgment.user_reasoning = reason if reason else None
            # If user decision matches AI decision, clear user data
            if judgment.user_decision == judgment.decision:
                judgment.user_decision = None
                judgment.user_reasoning = None
            self._show_detail_view()
            self._refresh_footer()

        self.push_screen(ReasonModal(judgment.user_reasoning or ""), handle_reason)

    def _get_viewport_height(self) -> int:
        """Get the viewport height for page navigation."""
        try:
            changes_list = self.query_one("#changes-list", ListScroll)
            return max(1, changes_list.size.height)
        except LookupError:
            return 10  # Fallback when widget is missing

    def _handle_detail_key(self, key: str) -> None:
        """Handle key events in detail view."""
        if key == "escape":
            self._show_list_view()
        elif key == "f":
            self._flip_decision()
        elif key == "r":
            judgment = self.judgments[self.selected_index]
            if judgment.was_corrected:
                self._edit_reason()

    def _move_selection(self, new_index: int) -> None:
        """Update selection to a new index."""
        old_index = self.selected_index
        self.selected_index = new_index
        self._update_selection(old_index, self.selected_index)
        self._refresh_footer()

    def _handle_list_key(self, key: str) -> None:
        """Handle key events in list view."""
        if key in {"up", "k", "w"} and self.selected_index > 0:
            self._move_selection(self.selected_index - 1)
        elif (
            key in {"down", "j", "s"} and self.selected_index < len(self.judgments) - 1
        ):
            self._move_selection(self.selected_index + 1)
        elif key == "pageup" and self.selected_index > 0:
            viewport_height = self._get_viewport_height()
            self._move_selection(max(0, self.selected_index - viewport_height))
        elif key == "pagedown" and self.selected_index < len(self.judgments) - 1:
            viewport_height = self._get_viewport_height()
            self._move_selection(
                min(len(self.judgments) - 1, self.selected_index + viewport_height)
            )
        elif key == "home" and self.judgments and self.selected_index > 0:
            self._move_selection(0)
        elif (
            key == "end"
            and self.judgments
            and self.selected_index < len(self.judgments) - 1
        ):
            self._move_selection(len(self.judgments) - 1)
        elif key == "enter" and self.judgments:
            self._show_detail_view()
        elif key == "d":
            _, _, uncertain_count = self._count_decisions()
            if uncertain_count == 0:
                self.accepted = True
                self.exit()
        # Note: Escape only closes modals/detail view, not the main list
        # Use Ctrl+Q to quit the app

    def on_key(self, event: Key) -> None:
        """Handle key events."""
        if self.in_detail_view:
            self._handle_detail_key(event.key)
        else:
            self._handle_list_key(event.key)


def review_judgments(
    judgments: list[Judgment],
    changes: list[Change],
) -> ReviewResult:
    """Interactive review of AI judgments using Textual TUI.

    Args:
        judgments: List of AI judgments to review
        changes: List of changes (for title lookup)

    Returns:
        ReviewResult with potentially modified judgments
    """
    app = ReviewApp(judgments, changes)
    app.run()

    return ReviewResult(judgments=judgments, accepted=app.accepted)
