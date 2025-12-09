"""E2E tests for AI provider - uses LiteLLM mock responses."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from iptax.ai import AIProvider, build_judgment_prompt
from iptax.ai.models import Decision, Judgment
from iptax.models import Change, GeminiProviderConfig, Repository


@pytest.fixture
def ai_config():
    """Create a mock AI config for testing."""
    return GeminiProviderConfig(
        provider="gemini",
        model="gemini-2.0-flash",
        api_key_env="GEMINI_API_KEY",
    )


@pytest.fixture
def mock_ai_response():
    """Create a mock LiteLLM response with valid YAML."""
    return """```yaml
judgments:
-   change_id: "github.com/acme/parser-core#101"
    decision: INCLUDE
    reasoning: "Adds core parser functionality for code analysis product"
-   change_id: "github.com/acme/analyzer-tools#102"
    decision: INCLUDE
    reasoning: "Fixes bug in Java analyzer, part of code analysis suite"
-   change_id: "gitlab.com/acme/analysis-engine#103"
    decision: INCLUDE
    reasoning: "Performance improvements for the code analysis engine"
-   change_id: "github.com/john/my-recipes#201"
    decision: EXCLUDE
    reasoning: "Personal recipe project unrelated to code analysis"
-   change_id: "github.com/john/personal-site#202"
    decision: EXCLUDE
    reasoning: "Personal website not related to the product"
-   change_id: "github.com/acme/infra#301"
    decision: UNCERTAIN
    reasoning: "CI/CD infrastructure may or may not be product-specific"
```"""


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
def test_ai_judgment(
    ai_config,
    sample_changes: list[Change],
    mock_ai_response: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test AI judgment with LiteLLM mock response.

    This test verifies the full AI provider flow using LiteLLM's mock feature:
    1. Creates a provider instance with mock config
    2. Builds a prompt with history (including corrections)
    3. Uses LiteLLM mock_response for deterministic testing
    4. Validates the response structure
    5. Verifies correct parsing of judgments
    """
    # Set mock API key in environment for config validation
    monkeypatch.setenv("GEMINI_API_KEY", "test-mock-key")

    # Create sample history with both confirmed and corrected judgments
    history = [
        Judgment(
            change_id="github.com/acme/parser-legacy#50",
            decision=Decision.INCLUDE,
            reasoning="This adds core parser functionality to the product",
            product="Acme Code Analysis Suite",
            timestamp=datetime.now(UTC),
        ),
        Judgment(
            change_id="github.com/acme/ci-tools#25",
            decision=Decision.EXCLUDE,
            reasoning="This is general CI/CD infrastructure",
            user_decision=Decision.INCLUDE,
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

    # Mock litellm.completion to use mock_response
    # See: https://docs.litellm.ai/docs/completion/mock_requests
    mock_response_obj = MagicMock()
    mock_response_obj.choices = [MagicMock()]
    mock_response_obj.choices[0].message.content = mock_ai_response

    with patch("iptax.ai.provider.litellm.completion", return_value=mock_response_obj):
        response = provider.judge_changes(prompt)

    # Verify response structure
    assert len(response.judgments) == len(sample_changes)

    # Create a mapping for easier verification
    judgments_by_id = {j.change_id: j for j in response.judgments}

    # Verify each judgment
    for item in response.judgments:
        # Verify decision is valid
        assert item.decision in [
            Decision.INCLUDE,
            Decision.EXCLUDE,
            Decision.UNCERTAIN,
        ]

        # Verify reasoning is provided
        assert item.reasoning
        assert len(item.reasoning) > 0

        # Verify change_id matches one of our changes
        assert item.change_id in [c.get_change_id() for c in sample_changes]

    # Verify product-related changes are INCLUDE (deterministic with mock)
    product_change_ids = [
        "github.com/acme/parser-core#101",
        "github.com/acme/analyzer-tools#102",
        "gitlab.com/acme/analysis-engine#103",
    ]

    for change_id in product_change_ids:
        judgment = judgments_by_id.get(change_id)
        assert judgment is not None, f"Missing judgment for {change_id}"
        assert judgment.decision == Decision.INCLUDE, (
            f"Expected INCLUDE for product change {change_id}, "
            f"got {judgment.decision}"
        )

    # Verify personal project changes are EXCLUDE
    personal_change_ids = [
        "github.com/john/my-recipes#201",
        "github.com/john/personal-site#202",
    ]

    for change_id in personal_change_ids:
        judgment = judgments_by_id.get(change_id)
        assert judgment is not None, f"Missing judgment for {change_id}"
        assert judgment.decision == Decision.EXCLUDE, (
            f"Expected EXCLUDE for personal change {change_id}, "
            f"got {judgment.decision}"
        )

    # Verify infrastructure change is UNCERTAIN
    infra_judgment = judgments_by_id.get("github.com/acme/infra#301")
    assert infra_judgment is not None
    assert infra_judgment.decision == Decision.UNCERTAIN
