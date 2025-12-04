"""Unit tests for AI review TUI interface."""

import pytest

from iptax.ai.models import Decision, Judgment
from iptax.ai.review import (
    COLORS,
    ICONS,
    ReasonModal,
    ReviewApp,
    ReviewResult,
    needs_review,
)
from iptax.models import Change, Repository


@pytest.fixture
def mock_changes():
    """Create mock changes for testing."""
    return [
        Change(
            title="Add feature X",
            repository=Repository(
                host="github.com",
                path="org/repo1",
                provider_type="github",
            ),
            number=100,
        ),
        Change(
            title="Fix bug Y",
            repository=Repository(
                host="github.com",
                path="org/repo2",
                provider_type="github",
            ),
            number=200,
        ),
        Change(
            title="Update docs",
            repository=Repository(
                host="github.com",
                path="org/repo3",
                provider_type="github",
            ),
            number=300,
        ),
    ]


@pytest.fixture
def judgments_all_confident(mock_changes):
    """Create judgments without any uncertain decisions."""
    return [
        Judgment(
            change_id=mock_changes[0].get_change_id(),
            decision=Decision.INCLUDE,
            reasoning="Contributes to product",
            product="Test Product",
        ),
        Judgment(
            change_id=mock_changes[1].get_change_id(),
            decision=Decision.EXCLUDE,
            reasoning="Unrelated to product",
            product="Test Product",
        ),
        Judgment(
            change_id=mock_changes[2].get_change_id(),
            decision=Decision.INCLUDE,
            reasoning="Documentation update",
            product="Test Product",
        ),
    ]


@pytest.fixture
def judgments_with_uncertain(mock_changes):
    """Create judgments with uncertain decision."""
    return [
        Judgment(
            change_id=mock_changes[0].get_change_id(),
            decision=Decision.INCLUDE,
            reasoning="Contributes to product",
            product="Test Product",
        ),
        Judgment(
            change_id=mock_changes[1].get_change_id(),
            decision=Decision.UNCERTAIN,
            reasoning="Cannot determine",
            product="Test Product",
        ),
        Judgment(
            change_id=mock_changes[2].get_change_id(),
            decision=Decision.EXCLUDE,
            reasoning="Unrelated",
            product="Test Product",
        ),
    ]


def test_needs_review_all_include_exclude(judgments_all_confident):
    """Test needs_review returns False when all decisions are confident."""
    assert needs_review(judgments_all_confident) is False


def test_needs_review_with_uncertain(judgments_with_uncertain):
    """Test needs_review returns True when there are uncertain decisions."""
    assert needs_review(judgments_with_uncertain) is True


def test_icons_mapping():
    """Test that ICONS has correct mappings for all decision types."""
    assert ICONS[Decision.INCLUDE] == "✓"
    assert ICONS[Decision.EXCLUDE] == "✗"
    assert ICONS[Decision.UNCERTAIN] == "?"
    # Verify no ERROR key
    assert Decision.INCLUDE in ICONS
    assert Decision.EXCLUDE in ICONS
    assert Decision.UNCERTAIN in ICONS
    assert len(ICONS) == 3  # Only 3 valid decisions


def test_colors_mapping():
    """Test that COLORS has correct mappings for all decision types."""
    assert COLORS[Decision.INCLUDE] == "green"
    assert COLORS[Decision.EXCLUDE] == "red"
    assert COLORS[Decision.UNCERTAIN] == "orange"
    # Verify no ERROR key
    assert Decision.INCLUDE in COLORS
    assert Decision.EXCLUDE in COLORS
    assert Decision.UNCERTAIN in COLORS
    assert len(COLORS) == 3  # Only 3 valid decisions


def test_review_result_initialization():
    """Test ReviewResult initialization."""
    judgments = [
        Judgment(
            change_id="test/repo#1",
            decision=Decision.INCLUDE,
            reasoning="Test",
            product="Test",
        )
    ]
    result = ReviewResult(judgments=judgments, accepted=True)

    assert result.judgments == judgments
    assert result.accepted is True


def test_review_result_default_not_accepted():
    """Test ReviewResult defaults to not accepted."""
    judgments = [
        Judgment(
            change_id="test/repo#1",
            decision=Decision.INCLUDE,
            reasoning="Test",
            product="Test",
        )
    ]
    result = ReviewResult(judgments=judgments)

    assert result.accepted is False


def test_needs_review_empty_list():
    """Test needs_review with empty list."""
    assert needs_review([]) is False


def test_needs_review_single_include():
    """Test needs_review with single INCLUDE."""
    judgments = [
        Judgment(
            change_id="test/repo#1",
            decision=Decision.INCLUDE,
            reasoning="Test",
            product="Test",
        )
    ]
    assert needs_review(judgments) is False


def test_needs_review_single_uncertain():
    """Test needs_review with single UNCERTAIN."""
    judgments = [
        Judgment(
            change_id="test/repo#1",
            decision=Decision.UNCERTAIN,
            reasoning="Test",
            product="Test",
        )
    ]
    assert needs_review(judgments) is True


def test_needs_review_all_uncertain():
    """Test needs_review with all UNCERTAIN."""
    judgments = [
        Judgment(
            change_id=f"test/repo#{i}",
            decision=Decision.UNCERTAIN,
            reasoning="Cannot determine",
            product="Test",
        )
        for i in range(5)
    ]
    assert needs_review(judgments) is True


def test_icons_are_single_characters():
    """Test that all icons are single characters (for compact display)."""
    for icon in ICONS.values():
        assert len(icon) == 1


def test_colors_are_valid_rich_colors():
    """Test that colors are valid Rich color names."""
    valid_colors = {
        "green",
        "red",
        "orange",
        "ansi_blue",
        "yellow",
        "blue",
        "cyan",
        "magenta",
        "white",
        "black",
    }
    for color in COLORS.values():
        assert color in valid_colors


# Textual TUI Tests using App.run_test()
# Tests are consolidated to minimize app.run_test() calls (each takes ~0.2s overhead)


class TestReviewApp:
    """Tests for ReviewApp Textual application.

    Tests are consolidated into minimal app instances for performance.
    """

    @pytest.fixture
    def sample_changes(self):
        """Create sample changes for testing."""
        return [
            Change(
                title="Add feature X",
                repository=Repository(
                    host="github.com", path="org/repo1", provider_type="github"
                ),
                number=100,
            ),
            Change(
                title="Fix bug Y",
                repository=Repository(
                    host="github.com", path="org/repo2", provider_type="github"
                ),
                number=200,
            ),
        ]

    @pytest.fixture
    def sample_judgments(self, sample_changes):
        """Create sample judgments for testing."""
        return [
            Judgment(
                change_id=sample_changes[0].get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Contributes to product",
                product="Test Product",
            ),
            Judgment(
                change_id=sample_changes[1].get_change_id(),
                decision=Decision.UNCERTAIN,
                reasoning="Cannot determine",
                product="Test Product",
            ),
        ]

    @pytest.mark.asyncio
    async def test_app_basics_and_navigation(self, sample_judgments, sample_changes):
        """Test app mounting, UI elements, navigation, and decision counting.

        Consolidates: mount, changes-list, all navigation keys, escape in list,
        bounds checking, _count_decisions, and done-disabled-with-uncertain.
        """
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            # === Mount and UI ===
            assert app.is_running
            changes_list = app.query_one("#changes-list")
            assert changes_list is not None

            # === Decision counting ===
            include, exclude, uncertain = app._count_decisions()
            assert include == 1
            assert exclude == 0
            assert uncertain == 1

            # === Navigation: down/up arrows ===
            assert app.selected_index == 0
            await pilot.press("down")
            assert app.selected_index == 1
            await pilot.press("up")
            assert app.selected_index == 0

            # === Navigation: vim keys (j/k) ===
            await pilot.press("j")
            assert app.selected_index == 1
            await pilot.press("k")
            assert app.selected_index == 0

            # === Navigation: WASD keys (s/w) ===
            await pilot.press("s")
            assert app.selected_index == 1
            await pilot.press("w")
            assert app.selected_index == 0

            # === Bounds checking ===
            await pilot.press("up")  # Can't go past start
            assert app.selected_index == 0
            await pilot.press("down")
            await pilot.press("down")  # Can't go past end
            assert app.selected_index == 1
            await pilot.press("up")  # Reset to start
            assert app.selected_index == 0

            # === Detail view enter/escape ===
            assert not app.in_detail_view
            await pilot.press("enter")
            assert app.in_detail_view
            await pilot.press("escape")
            assert not app.in_detail_view

            # === Escape in list view does nothing ===
            await pilot.press("escape")
            assert app.is_running
            assert not app.in_detail_view

            # === Done disabled with uncertain ===
            await pilot.press("d")
            assert app.is_running  # Still running - uncertain exists
            assert not app.accepted

    @pytest.mark.asyncio
    async def test_done_enabled_without_uncertain(self, sample_changes):
        """Test that 'd' exits when no uncertain decisions."""
        judgments = [
            Judgment(
                change_id=sample_changes[0].get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Test",
            ),
            Judgment(
                change_id=sample_changes[1].get_change_id(),
                decision=Decision.EXCLUDE,
                reasoning="Test",
                product="Test",
            ),
        ]
        app = ReviewApp(judgments, sample_changes)
        async with app.run_test() as pilot:
            await pilot.press("d")
            assert not app.is_running
            assert app.accepted


class TestReasonModal:
    """Tests for ReasonModal."""

    def test_modal_default_reason(self):
        """Test that ReasonModal default reason is empty."""
        modal = ReasonModal()
        assert modal.current_reason == ""

    def test_modal_with_initial_reason(self):
        """Test modal with initial reason value."""
        modal = ReasonModal("Initial reason")
        assert modal.current_reason == "Initial reason"


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_review_result_instantiation(self):
        """Test that ReviewResult can be instantiated with judgments."""
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
                product="Test",
            )
        ]

        # This test just verifies the function signature works
        # The actual TUI testing is done in TestReviewApp
        # We can't easily test the run() call in unit tests
        # as it starts the event loop
        result = ReviewResult(judgments=judgments, accepted=False)
        assert isinstance(result, ReviewResult)
        assert result.judgments == judgments


class TestReviewAppDetailAndOverride:
    """Tests for detail view, overrides, and edge cases - consolidated."""

    @pytest.mark.asyncio
    async def test_detail_view_flip_and_override(self):
        """Test detail view operations: enter, flip, modal, escape, override display.

        Consolidates: detail view operations, override visibility, r key behavior.
        """
        change = Change(
            title="Test change",
            repository=Repository(
                host="github.com", path="org/repo", provider_type="github"
            ),
            number=100,
        )
        # Create judgment with override
        j = Judgment(
            change_id=change.get_change_id(),
            decision=Decision.EXCLUDE,
            reasoning="Original AI reasoning",
            product="Test Product",
        )
        j.user_decision = Decision.INCLUDE
        j.user_reasoning = "User overrode to include"

        app = ReviewApp([j], [change])
        async with app.run_test() as pilot:
            # === Enter detail view ===
            await pilot.press("enter")
            assert app.in_detail_view

            # === Check override is visible ===
            assert j.was_corrected
            assert j.final_decision == Decision.INCLUDE

            # === Flip opens modal ===
            await pilot.press("f")
            assert app.is_running

            # === First escape closes modal, still in detail ===
            await pilot.press("escape")
            assert app.in_detail_view

            # === r key edits reason (since correction exists) ===
            await pilot.press("r")
            assert app.is_running

            # === Escape modal, escape detail ===
            await pilot.press("escape")
            await pilot.press("escape")
            assert not app.in_detail_view

    @pytest.mark.asyncio
    async def test_r_key_and_missing_change(self):
        """Test r key without correction and missing change handling.

        Consolidates: r key does nothing without correction, orphan judgment handling.
        """
        # Test with orphan judgment (no matching change)
        orphan = Judgment(
            change_id="nonexistent/repo#999",
            decision=Decision.INCLUDE,
            reasoning="Test",
            product="Test",
        )
        app = ReviewApp([orphan], [])
        async with app.run_test() as pilot:
            # Should mount without errors
            assert app.is_running

            # Enter detail view
            await pilot.press("enter")
            assert app.in_detail_view

            # r should do nothing - no correction
            await pilot.press("r")
            assert app.in_detail_view
            assert app.is_running


class TestReasonModalInteraction:
    """Tests for ReasonModal user interactions - consolidated into one test."""

    @pytest.mark.asyncio
    async def test_modal_all_interactions(self):
        """Test all modal dismiss and save methods in sequence.

        Consolidates: skip button, escape key, save button, enter key.
        """
        from textual.app import App

        from iptax.ai.review import ReasonModal

        results: list[str | None] = []

        # Test 1: Skip button
        modal1 = ReasonModal("Initial reason")

        def capture1(v: str | None) -> None:
            results.append(v)

        class App1(App):
            def on_mount(self) -> None:
                self.push_screen(modal1, capture1)

        async with App1().run_test() as pilot:
            await pilot.click("#skip-btn")

        assert results[-1] is None

        # Test 2: Escape key
        modal2 = ReasonModal()

        def capture2(v: str | None) -> None:
            results.append(v)

        class App2(App):
            def on_mount(self) -> None:
                self.push_screen(modal2, capture2)

        async with App2().run_test() as pilot:
            await pilot.press("escape")

        assert results[-1] is None

        # Test 3: Save button
        modal3 = ReasonModal()

        def capture3(v: str | None) -> None:
            results.append(v)

        class App3(App):
            def on_mount(self) -> None:
                self.push_screen(modal3, capture3)

        app3 = App3()
        async with app3.run_test() as pilot:
            app3.screen.query_one("#reason-input").value = "Save button reason"
            await pilot.click("#save-btn")

        assert results[-1] == "Save button reason"

        # Test 4: Enter key
        modal4 = ReasonModal()

        def capture4(v: str | None) -> None:
            results.append(v)

        class App4(App):
            def on_mount(self) -> None:
                self.push_screen(modal4, capture4)

        app4 = App4()
        async with app4.run_test() as pilot:
            inp = app4.screen.query_one("#reason-input")
            inp.focus()
            inp.value = "Enter key reason"
            await pilot.press("enter")

        assert results[-1] == "Enter key reason"


class TestAdvancedNavigation:
    """Tests for pagination and UNCERTAIN flip - consolidated."""

    @pytest.mark.asyncio
    async def test_page_navigation_and_uncertain_flip(self):
        """Test PageUp/Down, Home/End, and flipping UNCERTAIN to INCLUDE.

        Consolidates: page navigation keys, flip uncertain decision.
        """
        # Create 20 changes for pagination
        changes = [
            Change(
                title=f"Change {i}",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=i,
            )
            for i in range(1, 21)
        ]
        judgments = [
            Judgment(
                change_id=c.get_change_id(),
                decision=Decision.UNCERTAIN if i == 0 else Decision.INCLUDE,
                reasoning="Test",
                product="Test",
            )
            for i, c in enumerate(changes)
        ]

        app = ReviewApp(judgments, changes)
        async with app.run_test() as pilot:
            # === Page navigation ===
            await pilot.press("end")
            assert app.selected_index == len(judgments) - 1

            await pilot.press("home")
            assert app.selected_index == 0

            await pilot.press("pagedown")
            assert app.selected_index > 0
            pagedown_pos = app.selected_index

            await pilot.press("pageup")
            assert app.selected_index < pagedown_pos

            # === Flip UNCERTAIN to INCLUDE ===
            await pilot.press("home")  # Go to first (UNCERTAIN)
            await pilot.press("enter")
            assert app.in_detail_view
            await pilot.press("f")  # Flip - opens modal
            await pilot.press("escape")  # Skip modal
            assert judgments[0].user_decision == Decision.INCLUDE


class TestReviewJudgmentsFunction:
    """Tests for review_judgments top-level function."""

    def test_review_judgments_returns_result(self):
        """Test that review_judgments returns ReviewResult."""
        from iptax.ai.review import review_judgments

        # We can't actually run the TUI in unit tests easily, but we can
        # verify the function signature exists and returns correct type
        # This is mainly for import/signature testing
        assert callable(review_judgments)
