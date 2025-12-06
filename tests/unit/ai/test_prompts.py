"""Unit tests for AI prompt building."""

from datetime import UTC, datetime

import pytest

from iptax.ai.models import Decision, Judgment
from iptax.ai.prompts import build_judgment_prompt
from iptax.models import Change, Repository


@pytest.fixture
def sample_change() -> Change:
    """Create a sample change for testing."""
    return Change(
        title="Fix memory leak in parser",
        repository=Repository(
            host="github.com",
            path="org/project",
            provider_type="github",
        ),
        number=123,
    )


@pytest.fixture
def sample_changes() -> list[Change]:
    """Create multiple sample changes for testing."""
    return [
        Change(
            title="Fix memory leak in parser",
            repository=Repository(
                host="github.com",
                path="org/project",
                provider_type="github",
            ),
            number=123,
        ),
        Change(
            title="Update README badges",
            repository=Repository(
                host="gitlab.com",
                path="group/subgroup/repo",
                provider_type="gitlab",
            ),
            number=456,
        ),
        Change(
            title="Add unit tests for feature X",
            repository=Repository(
                host="github.com",
                path="another/repo",
                provider_type="github",
            ),
            number=789,
        ),
    ]


@pytest.fixture
def confirmed_judgment() -> Judgment:
    """Create a confirmed (not corrected) judgment."""
    return Judgment(
        change_id="github.com/org/project#100",
        decision=Decision.INCLUDE,
        reasoning="This change adds core functionality to the product",
        product="Test Product",
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def corrected_judgment() -> Judgment:
    """Create a corrected judgment with user override."""
    return Judgment(
        change_id="github.com/org/project#101",
        decision=Decision.EXCLUDE,
        reasoning="This appears to be infrastructure work",
        user_decision=Decision.INCLUDE,
        user_reasoning="Actually, this is product-specific infrastructure",
        product="Test Product",
        timestamp=datetime.now(UTC),
    )


def test_empty_history_single_change(sample_change: Change) -> None:
    """Test prompt building with no history and single change."""
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=[sample_change],
        history=[],
    )

    # Should include product name
    assert "Test Product" in prompt

    # Should include change information
    assert "Fix memory leak in parser" in prompt
    assert sample_change.get_change_id() in prompt
    assert sample_change.get_url() in prompt

    # Should have YAML code block delimiters
    assert "```yaml" in prompt
    assert "```" in prompt

    # Should include response format instructions
    assert "judgments:" in prompt
    assert "change_id:" in prompt
    assert "decision:" in prompt
    assert "reasoning:" in prompt

    # Should define decision types
    assert "INCLUDE" in prompt
    assert "EXCLUDE" in prompt
    assert "UNCERTAIN" in prompt

    # Should NOT have history section
    assert "Previous Judgment History" not in prompt


def test_with_confirmed_history(
    sample_change: Change, confirmed_judgment: Judgment
) -> None:
    """Test prompt building with confirmed judgment in history."""
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=[sample_change],
        history=[confirmed_judgment],
    )

    # Should include history section
    assert "Previous Judgment History" in prompt

    # Should show the confirmed judgment
    assert confirmed_judgment.change_id in prompt
    assert f"confirmed {confirmed_judgment.decision.value}" in prompt
    assert confirmed_judgment.reasoning in prompt


def test_with_corrected_history(
    sample_change: Change, corrected_judgment: Judgment
) -> None:
    """Test prompt building with corrected judgment in history."""
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=[sample_change],
        history=[corrected_judgment],
    )

    # Should include history section
    assert "Previous Judgment History" in prompt

    # Should show the correction
    assert corrected_judgment.change_id in prompt
    assert f"corrected from {corrected_judgment.decision.value}" in prompt
    assert f"to {corrected_judgment.final_decision.value}" in prompt

    # Should show both AI and user reasoning
    assert "AI reasoning:" in prompt
    assert corrected_judgment.reasoning in prompt
    assert "User correction:" in prompt
    assert corrected_judgment.user_reasoning in prompt


def test_with_multiple_history_items(
    sample_change: Change,
    confirmed_judgment: Judgment,
    corrected_judgment: Judgment,
) -> None:
    """Test prompt building with multiple history items."""
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=[sample_change],
        history=[confirmed_judgment, corrected_judgment],
    )

    # Should include both judgments
    assert confirmed_judgment.change_id in prompt
    assert corrected_judgment.change_id in prompt

    # Should show confirmation for first
    assert f"confirmed {confirmed_judgment.decision.value}" in prompt

    # Should show correction for second
    assert f"corrected from {corrected_judgment.decision.value}" in prompt


def test_multiple_changes(sample_changes: list[Change]) -> None:
    """Test prompt building with multiple changes."""
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=sample_changes,
        history=[],
    )

    # Should include all changes
    for change in sample_changes:
        assert change.title in prompt
        assert change.get_change_id() in prompt
        assert change.get_url() in prompt


def test_yaml_code_block_delimiters(sample_change: Change) -> None:
    """Test that prompt includes proper YAML code block delimiters."""
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=[sample_change],
        history=[],
    )

    # Should have opening delimiter
    assert "```yaml" in prompt

    # Should have closing delimiter after example
    lines = prompt.split("\n")
    yaml_start = None
    yaml_end = None

    for i, line in enumerate(lines):
        if "```yaml" in line:
            yaml_start = i
        elif yaml_start is not None and "```" in line and "yaml" not in line:
            yaml_end = i
            break

    assert yaml_start is not None, "YAML code block start not found"
    assert yaml_end is not None, "YAML code block end not found"
    assert yaml_end > yaml_start, "YAML code block end should come after start"


def test_change_id_format_matches_model(sample_changes: list[Change]) -> None:
    """Test that change_id format in prompt matches Change.get_change_id()."""
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=sample_changes,
        history=[],
    )

    # Verify each change's ID is in the prompt in the correct format
    for change in sample_changes:
        expected_id = change.get_change_id()
        assert expected_id in prompt

        # Verify format: host/path#number
        assert "#" in expected_id
        parts = expected_id.split("#")
        assert len(parts) == 2
        assert "/" in parts[0]  # Should have host/path
        assert parts[1].isdigit()  # Number should be digits


def test_empty_changes_list() -> None:
    """Test prompt building with empty changes list."""
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=[],
        history=[],
    )

    # Should still have basic structure
    assert "Test Product" in prompt
    assert "```yaml" in prompt
    assert "Current Changes to Judge" in prompt


def test_github_and_gitlab_changes() -> None:
    """Test that both GitHub and GitLab changes are formatted correctly."""
    changes = [
        Change(
            title="GitHub PR",
            repository=Repository(
                host="github.com",
                path="owner/repo",
                provider_type="github",
            ),
            number=123,
        ),
        Change(
            title="GitLab MR",
            repository=Repository(
                host="gitlab.example.org",
                path="group/subgroup/project",
                provider_type="gitlab",
            ),
            number=456,
        ),
    ]

    prompt = build_judgment_prompt(
        product="Test Product",
        changes=changes,
        history=[],
    )

    # Verify GitHub URL format
    assert "github.com/owner/repo#123" in prompt
    assert "https://github.com/owner/repo/pull/123" in prompt

    # Verify GitLab URL format
    assert "gitlab.example.org/group/subgroup/project#456" in prompt
    assert (
        "https://gitlab.example.org/group/subgroup/project/-/merge_requests/456"
        in prompt
    )


def test_with_hints(sample_change: Change) -> None:
    """Test prompt building with hints."""
    hints = ["Focus on user-facing features", "Exclude infrastructure repos"]
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=[sample_change],
        history=[],
        hints=hints,
    )

    # Should include hints section
    assert "Additional insights:" in prompt

    # Should include all hints
    for hint in hints:
        assert hint in prompt
        assert f"- {hint}" in prompt


def test_without_hints(sample_change: Change) -> None:
    """Test prompt building without hints (None)."""
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=[sample_change],
        history=[],
        hints=None,
    )

    # Should NOT include hints section
    assert "Additional insights:" not in prompt


def test_with_empty_hints_list(sample_change: Change) -> None:
    """Test prompt building with empty hints list."""
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=[sample_change],
        history=[],
        hints=[],
    )

    # Should NOT include hints section (empty list is falsy)
    assert "Additional insights:" not in prompt


def test_hints_appear_before_history(
    sample_change: Change, confirmed_judgment: Judgment
) -> None:
    """Test that hints section appears before history section."""
    hints = ["Custom hint"]
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=[sample_change],
        history=[confirmed_judgment],
        hints=hints,
    )

    # Both sections should be present
    assert "Additional insights:" in prompt
    assert "Previous Judgment History" in prompt

    # Hints should appear before history
    hints_pos = prompt.find("Additional insights:")
    history_pos = prompt.find("Previous Judgment History")
    assert hints_pos < history_pos


def test_hints_with_multiple_changes_and_history(
    sample_changes: list[Change],
    confirmed_judgment: Judgment,
    corrected_judgment: Judgment,
) -> None:
    """Test prompt with hints, multiple changes, and history."""
    hints = ["Hint 1", "Hint 2"]
    prompt = build_judgment_prompt(
        product="Test Product",
        changes=sample_changes,
        history=[confirmed_judgment, corrected_judgment],
        hints=hints,
    )

    # All sections should be present
    assert "Additional insights:" in prompt
    assert "Previous Judgment History" in prompt
    assert "Current Changes to Judge" in prompt

    # All hints should be present
    for hint in hints:
        assert hint in prompt

    # All changes should be present
    for change in sample_changes:
        assert change.title in prompt

    # All history items should be present
    assert confirmed_judgment.change_id in prompt
    assert corrected_judgment.change_id in prompt
