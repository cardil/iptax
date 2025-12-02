"""E2E tests for AI provider - uses real AI if system config available."""

from datetime import UTC, datetime

import pytest

from iptax.ai import AIProvider, build_judgment_prompt
from iptax.ai.models import AIDecision, Judgment
from iptax.config import load_settings
from iptax.models import Change, DisabledAIConfig, Repository


@pytest.fixture
def ai_config():
    """Load AI config from system settings, skip if disabled."""
    try:
        settings = load_settings()
    except Exception:
        pytest.skip("No iptax config available")

    if isinstance(settings.ai, DisabledAIConfig):
        pytest.skip("AI is disabled in config")

    return settings.ai


@pytest.fixture
def sample_changes() -> list[Change]:
    """Create diverse sample changes for testing.

    Includes changes from:
    - Product repos (should be INCLUDE)
    - Personal/unrelated repos (should be EXCLUDE)
    - Mixed relevance repos
    """
    return [
        # Product-related changes (should be INCLUDE)
        Change(
            title="Add new parser for Python code",
            repository=Repository(
                host="github.com", path="acme/parser-core", provider_type="github"
            ),
            number=101,
        ),
        Change(
            title="Fix tokenizer bug in Java analyzer",
            repository=Repository(
                host="github.com", path="acme/analyzer-tools", provider_type="github"
            ),
            number=102,
        ),
        Change(
            title="Improve performance of code analysis",
            repository=Repository(
                host="gitlab.com", path="acme/analysis-engine", provider_type="gitlab"
            ),
            number=103,
        ),
        # Personal project changes (should be EXCLUDE)
        Change(
            title="Add recipe for chocolate cake",
            repository=Repository(
                host="github.com", path="john/my-recipes", provider_type="github"
            ),
            number=201,
        ),
        Change(
            title="Update my personal website",
            repository=Repository(
                host="github.com", path="john/personal-site", provider_type="github"
            ),
            number=202,
        ),
        # Infrastructure/mixed (might be UNCERTAIN or EXCLUDE)
        Change(
            title="Update CI/CD pipeline for all repos",
            repository=Repository(
                host="github.com", path="acme/infra", provider_type="github"
            ),
            number=301,
        ),
    ]


@pytest.mark.e2e
@pytest.mark.slow
def test_real_ai_judgment(ai_config, sample_changes: list[Change]) -> None:
    """Test real AI judgment with configured provider.

    This is a comprehensive happy path test that:
    1. Loads AI config from system settings
    2. Creates a provider instance with diverse changes from multiple repos
    3. Builds a prompt with history (including corrections)
    4. Sends the prompt to the real AI
    5. Validates the response structure
    6. Verifies AI can distinguish product-related from personal changes
    """
    # Create sample history with both confirmed and corrected judgments
    history = [
        Judgment(
            change_id="github.com/acme/parser-legacy#50",
            decision=AIDecision.INCLUDE,
            reasoning="This adds core parser functionality to the product",
            product="Acme Code Analysis Suite",
            timestamp=datetime.now(UTC),
        ),
        Judgment(
            change_id="github.com/acme/ci-tools#25",
            decision=AIDecision.EXCLUDE,
            reasoning="This is general CI/CD infrastructure",
            user_decision=AIDecision.INCLUDE,
            user_reasoning="This CI tool is specifically for code analysis",
            product="Acme Code Analysis Suite",
            timestamp=datetime.now(UTC),
        ),
    ]

    # Create provider
    provider = AIProvider(ai_config)

    # Build prompt with history
    prompt = build_judgment_prompt(
        product=(
            "Acme Code Analysis Suite - " "tools for parsing and analyzing source code"
        ),
        changes=sample_changes,
        history=history,
    )

    # Verify prompt includes history
    assert "Previous Judgment History" in prompt
    assert history[0].change_id in prompt
    assert history[1].change_id in prompt
    assert "corrected from" in prompt

    # Make real AI call
    response = provider.judge_changes(prompt)

    # Verify response structure
    assert len(response.judgments) == len(sample_changes)

    # Create a mapping for easier verification
    judgments_by_id = {j.change_id: j for j in response.judgments}

    # Verify each judgment
    for item in response.judgments:
        # Verify decision is valid
        assert item.decision in [
            AIDecision.INCLUDE,
            AIDecision.EXCLUDE,
            AIDecision.UNCERTAIN,
        ]

        # Verify reasoning is provided
        assert item.reasoning
        assert len(item.reasoning) > 0

        # Verify change_id matches one of our changes
        assert item.change_id in [c.get_change_id() for c in sample_changes]

    # Verify product-related changes are likely INCLUDE
    product_change_ids = [
        "github.com/acme/parser-core#101",
        "github.com/acme/analyzer-tools#102",
        "gitlab.com/acme/analysis-engine#103",
    ]

    for change_id in product_change_ids:
        judgment = judgments_by_id.get(change_id)
        assert judgment is not None, f"Missing judgment for {change_id}"
        # These should be INCLUDE, but we allow UNCERTAIN for edge cases
        assert judgment.decision in [
            AIDecision.INCLUDE,
            AIDecision.UNCERTAIN,
        ], (
            f"Expected INCLUDE/UNCERTAIN for product change {change_id}, "
            f"got {judgment.decision}"
        )

    # Verify personal project changes are likely EXCLUDE
    personal_change_ids = [
        "github.com/john/my-recipes#201",
        "github.com/john/personal-site#202",
    ]

    for change_id in personal_change_ids:
        judgment = judgments_by_id.get(change_id)
        assert judgment is not None, f"Missing judgment for {change_id}"
        # These should be EXCLUDE
        assert judgment.decision in [
            AIDecision.EXCLUDE,
            AIDecision.UNCERTAIN,
        ], (
            f"Expected EXCLUDE/UNCERTAIN for personal change {change_id}, "
            f"got {judgment.decision}"
        )
