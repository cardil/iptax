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


class TestReviewApp:
    """Tests for ReviewApp Textual application."""

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
    async def test_app_mounts_successfully(self, sample_judgments, sample_changes):
        """Test that ReviewApp mounts without errors."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test():
            # App should mount successfully
            assert app.is_running

    @pytest.mark.asyncio
    async def test_app_shows_changes_list(self, sample_judgments, sample_changes):
        """Test that ReviewApp displays changes list."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test():
            # Should have changes-list container
            changes_list = app.query_one("#changes-list")
            assert changes_list is not None

    @pytest.mark.asyncio
    async def test_navigation_down(self, sample_judgments, sample_changes):
        """Test down arrow navigation."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            assert app.selected_index == 0
            await pilot.press("down")
            assert app.selected_index == 1

    @pytest.mark.asyncio
    async def test_navigation_up(self, sample_judgments, sample_changes):
        """Test up arrow navigation."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            app.selected_index = 1
            app._refresh_list()
            await pilot.press("up")
            assert app.selected_index == 0

    @pytest.mark.asyncio
    async def test_navigation_vim_keys(self, sample_judgments, sample_changes):
        """Test vim-style navigation keys."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            # j moves down
            await pilot.press("j")
            assert app.selected_index == 1
            # k moves up
            await pilot.press("k")
            assert app.selected_index == 0

    @pytest.mark.asyncio
    async def test_navigation_wasd_keys(self, sample_judgments, sample_changes):
        """Test WASD-style navigation keys."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            # s moves down
            await pilot.press("s")
            assert app.selected_index == 1
            # w moves up
            await pilot.press("w")
            assert app.selected_index == 0

    @pytest.mark.asyncio
    async def test_enter_detail_view(self, sample_judgments, sample_changes):
        """Test entering detail view with Enter."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            assert not app.in_detail_view
            await pilot.press("enter")
            assert app.in_detail_view

    @pytest.mark.asyncio
    async def test_escape_from_detail_view(self, sample_judgments, sample_changes):
        """Test escaping from detail view."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert app.in_detail_view
            await pilot.press("escape")
            assert not app.in_detail_view

    @pytest.mark.asyncio
    async def test_escape_does_nothing_in_list_view(
        self, sample_judgments, sample_changes
    ):
        """Test that escape does nothing in list view (use Ctrl+C to quit)."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            await pilot.press("escape")
            # App should still be running - escape only closes modals/detail view
            assert app.is_running
            assert not app.in_detail_view

    @pytest.mark.asyncio
    async def test_cannot_navigate_past_bounds(self, sample_judgments, sample_changes):
        """Test that navigation respects list bounds."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            # At start, can't go up
            await pilot.press("up")
            assert app.selected_index == 0

            # Go to end
            await pilot.press("down")
            assert app.selected_index == 1

            # Can't go past end
            await pilot.press("down")
            assert app.selected_index == 1

    @pytest.mark.asyncio
    async def test_count_decisions(self, sample_judgments, sample_changes):
        """Test _count_decisions method."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test():
            include, exclude, uncertain = app._count_decisions()
            assert include == 1
            assert exclude == 0
            assert uncertain == 1

    @pytest.mark.asyncio
    async def test_done_disabled_with_uncertain(self, sample_judgments, sample_changes):
        """Test that 'd' doesn't exit when uncertain decisions exist."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            await pilot.press("d")
            # Should still be running because there are uncertain decisions
            assert app.is_running
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


class TestReviewAppDetailView:
    """Tests for ReviewApp detail view functionality."""

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
        ]

    @pytest.mark.asyncio
    async def test_detail_view_shows_content(self, sample_judgments, sample_changes):
        """Test that detail view shows judgment content."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            # Enter detail view
            await pilot.press("enter")
            assert app.in_detail_view

    @pytest.mark.asyncio
    async def test_flip_decision_in_detail_view(self, sample_judgments, sample_changes):
        """Test flipping decision in detail view opens modal."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert app.in_detail_view
            # Flip should open modal
            await pilot.press("f")
            # Modal should be pushed - app still running
            assert app.is_running

    @pytest.mark.asyncio
    async def test_escape_returns_to_list_from_detail(
        self, sample_judgments, sample_changes
    ):
        """Test that escape from detail view returns to list (not quit)."""
        app = ReviewApp(sample_judgments, sample_changes)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert app.in_detail_view
            await pilot.press("escape")
            # Should return to list, not quit
            assert app.is_running
            assert not app.in_detail_view


class TestReviewAppWithUserOverride:
    """Tests for ReviewApp with user overrides."""

    @pytest.fixture
    def sample_changes(self):
        """Create sample changes for testing."""
        return [
            Change(
                title="Test change",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            ),
        ]

    @pytest.fixture
    def judgment_with_override(self, sample_changes):
        """Create judgment with user override."""
        j = Judgment(
            change_id=sample_changes[0].get_change_id(),
            decision=Decision.EXCLUDE,
            reasoning="Original AI reasoning",
            product="Test Product",
        )
        j.user_decision = Decision.INCLUDE
        j.user_reasoning = "User overrode to include"
        return [j]

    @pytest.mark.asyncio
    async def test_shows_override_in_detail(
        self, judgment_with_override, sample_changes
    ):
        """Test that user override is visible in detail view."""
        app = ReviewApp(judgment_with_override, sample_changes)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert app.in_detail_view
            # Check the judgment shows the override
            j = app.judgments[0]
            assert j.was_corrected
            assert j.final_decision == Decision.INCLUDE

    @pytest.mark.asyncio
    async def test_edit_reason_key_in_detail(
        self, judgment_with_override, sample_changes
    ):
        """Test that 'r' key works for editing reason when corrected."""
        app = ReviewApp(judgment_with_override, sample_changes)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert app.in_detail_view
            # Press r to edit reason
            await pilot.press("r")
            # Modal should be pushed
            assert app.is_running

    @pytest.mark.asyncio
    async def test_r_key_does_nothing_without_correction(self, sample_changes):
        """Test that 'r' key does nothing when no correction exists."""
        judgments = [
            Judgment(
                change_id=sample_changes[0].get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Test",
            )
        ]
        app = ReviewApp(judgments, sample_changes)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert app.in_detail_view
            # r should do nothing - no correction yet
            await pilot.press("r")
            # Still in detail view, app running
            assert app.in_detail_view
            assert app.is_running


class TestReviewAppMissingChange:
    """Tests for ReviewApp when change is not in change_map."""

    @pytest.fixture
    def orphan_judgment(self):
        """Create judgment for non-existent change."""
        return [
            Judgment(
                change_id="nonexistent/repo#999",
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Test",
            )
        ]

    @pytest.mark.asyncio
    async def test_handles_missing_change(self, orphan_judgment):
        """Test that app handles judgments without matching change."""
        app = ReviewApp(orphan_judgment, [])
        async with app.run_test() as pilot:
            # Should mount without errors
            assert app.is_running
            # Enter detail view
            await pilot.press("enter")
            assert app.in_detail_view


class TestReasonModalInteraction:
    """Tests for ReasonModal user interactions."""

    @pytest.mark.asyncio
    async def test_modal_skip_button(self):
        """Test that Skip button dismisses modal with None."""
        from iptax.ai.review import ReasonModal

        modal = ReasonModal("Initial reason")
        result = None

        def handle_result(value: str | None) -> None:
            nonlocal result
            result = value

        # Create a minimal app to test modal
        from textual.app import App

        class TestApp(App):
            def on_mount(self) -> None:
                self.push_screen(modal, handle_result)

        app = TestApp()
        async with app.run_test() as pilot:
            # Click skip button
            await pilot.click("#skip-btn")
            # Should dismiss with None
            assert result is None

    @pytest.mark.asyncio
    async def test_modal_escape_key(self):
        """Test that escape key dismisses modal with None."""
        from iptax.ai.review import ReasonModal

        modal = ReasonModal()
        result = "not-set"

        def handle_result(value: str | None) -> None:
            nonlocal result
            result = value

        from textual.app import App

        class TestApp(App):
            def on_mount(self) -> None:
                self.push_screen(modal, handle_result)

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.press("escape")
            # Should dismiss with None
            assert result is None

    @pytest.mark.asyncio
    async def test_modal_save_button(self):
        """Test that Save button returns input value."""
        from iptax.ai.review import ReasonModal

        modal = ReasonModal()
        result = None

        def handle_result(value: str | None) -> None:
            nonlocal result
            result = value

        from textual.app import App

        class TestApp(App):
            def on_mount(self) -> None:
                self.push_screen(modal, handle_result)

        app = TestApp()
        async with app.run_test() as pilot:
            # Type in input
            reason_input = app.screen.query_one("#reason-input")
            reason_input.value = "Test reason"
            # Click save
            await pilot.click("#save-btn")
            # Should return the typed value
            assert result == "Test reason"

    @pytest.mark.asyncio
    async def test_modal_input_submit(self):
        """Test that Enter in input field submits the form."""
        from iptax.ai.review import ReasonModal

        modal = ReasonModal()
        result = None

        def handle_result(value: str | None) -> None:
            nonlocal result
            result = value

        from textual.app import App

        class TestApp(App):
            def on_mount(self) -> None:
                self.push_screen(modal, handle_result)

        app = TestApp()
        async with app.run_test() as pilot:
            # Focus and type in input
            reason_input = app.screen.query_one("#reason-input")
            reason_input.focus()
            reason_input.value = "Submitted reason"
            # Press enter to submit
            await pilot.press("enter")
            # Should return the value
            assert result == "Submitted reason"


class TestNavigationKeys:
    """Tests for extended navigation keys (PageUp/Down, Home, End)."""

    @pytest.fixture
    def many_changes(self):
        """Create many changes for pagination testing."""
        return [
            Change(
                title=f"Change {i}",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=i,
            )
            for i in range(1, 21)  # Start from 1 since number must be > 0
        ]

    @pytest.fixture
    def many_judgments(self, many_changes):
        """Create many judgments for pagination testing."""
        return [
            Judgment(
                change_id=change.get_change_id(),
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Test",
            )
            for change in many_changes
        ]

    @pytest.mark.asyncio
    async def test_pagedown_navigation(self, many_judgments, many_changes):
        """Test PageDown key moves selection down by viewport height."""
        app = ReviewApp(many_judgments, many_changes)
        async with app.run_test() as pilot:
            assert app.selected_index == 0
            await pilot.press("pagedown")
            # Should have moved down
            assert app.selected_index > 0

    @pytest.mark.asyncio
    async def test_pageup_navigation(self, many_judgments, many_changes):
        """Test PageUp key moves selection up by viewport height."""
        app = ReviewApp(many_judgments, many_changes)
        async with app.run_test() as pilot:
            # Move down first
            app.selected_index = 15
            app._refresh_list()
            await pilot.press("pageup")
            # Should have moved up
            assert app.selected_index < 15

    @pytest.mark.asyncio
    async def test_home_key(self, many_judgments, many_changes):
        """Test Home key jumps to first item."""
        app = ReviewApp(many_judgments, many_changes)
        async with app.run_test() as pilot:
            # Move to middle
            app.selected_index = 10
            app._refresh_list()
            await pilot.press("home")
            assert app.selected_index == 0

    @pytest.mark.asyncio
    async def test_end_key(self, many_judgments, many_changes):
        """Test End key jumps to last item."""
        app = ReviewApp(many_judgments, many_changes)
        async with app.run_test() as pilot:
            await pilot.press("end")
            assert app.selected_index == len(many_judgments) - 1


class TestFlipUncertainDecision:
    """Tests for flipping UNCERTAIN decisions."""

    @pytest.fixture
    def uncertain_change(self):
        """Create a change for testing."""
        return [
            Change(
                title="Uncertain change",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]

    @pytest.fixture
    def uncertain_judgment(self, uncertain_change):
        """Create an uncertain judgment."""
        return [
            Judgment(
                change_id=uncertain_change[0].get_change_id(),
                decision=Decision.UNCERTAIN,
                reasoning="Cannot determine",
                product="Test",
            )
        ]

    @pytest.mark.asyncio
    async def test_flip_uncertain_to_include(
        self, uncertain_judgment, uncertain_change
    ):
        """Test flipping UNCERTAIN decision defaults to INCLUDE."""
        app = ReviewApp(uncertain_judgment, uncertain_change)
        async with app.run_test() as pilot:
            await pilot.press("enter")  # Enter detail view
            assert app.in_detail_view
            await pilot.press("f")  # Flip decision - opens modal
            # Modal should be open, skip it
            await pilot.press("escape")
            # Decision should have been flipped to INCLUDE
            assert uncertain_judgment[0].user_decision == Decision.INCLUDE


class TestReviewJudgmentsFunction:
    """Tests for review_judgments top-level function."""

    def test_review_judgments_returns_result(self):
        """Test that review_judgments returns ReviewResult."""
        from iptax.ai.review import review_judgments

        # We can't actually run the TUI in unit tests easily, but we can
        # verify the function signature exists and returns correct type
        # This is mainly for import/signature testing
        assert callable(review_judgments)


class TestUserReasoningDisplay:
    """Tests for displaying user reasoning in detail view."""

    @pytest.fixture
    def change_with_reasoning(self):
        """Create a change for testing."""
        return [
            Change(
                title="Test change",
                repository=Repository(
                    host="github.com", path="org/repo", provider_type="github"
                ),
                number=100,
            )
        ]

    @pytest.fixture
    def judgment_with_reasoning(self, change_with_reasoning):
        """Create judgment with user reasoning."""
        j = Judgment(
            change_id=change_with_reasoning[0].get_change_id(),
            decision=Decision.EXCLUDE,
            reasoning="AI reasoning",
            product="Test",
        )
        j.user_decision = Decision.INCLUDE
        j.user_reasoning = "User explanation for override"
        return [j]

    @pytest.mark.asyncio
    async def test_detail_view_shows_user_reasoning(
        self, judgment_with_reasoning, change_with_reasoning
    ):
        """Test that detail view displays user reasoning when present."""
        app = ReviewApp(judgment_with_reasoning, change_with_reasoning)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert app.in_detail_view
            # Verify judgment has user reasoning
            j = app.judgments[0]
            assert j.user_reasoning == "User explanation for override"
            assert j.was_corrected
