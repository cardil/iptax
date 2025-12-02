"""Unit tests for AI provider integration."""

import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from iptax.ai.models import AIDecision, AIResponse
from iptax.ai.provider import AIDisabledError, AIProvider, AIProviderError
from iptax.models import DisabledAIConfig, GeminiProviderConfig, VertexAIProviderConfig


@pytest.fixture
def gemini_config() -> GeminiProviderConfig:
    """Create a Gemini provider config."""
    return GeminiProviderConfig(
        provider="gemini",
        model="gemini-2.5-pro",
        api_key_env="TEST_GEMINI_KEY",
    )


@pytest.fixture
def vertex_config() -> VertexAIProviderConfig:
    """Create a Vertex AI provider config."""
    return VertexAIProviderConfig(
        provider="vertex",
        model="gemini-2.5-pro",
        project_id="test-project",
        location="us-east5",
    )


@pytest.fixture
def disabled_config() -> DisabledAIConfig:
    """Create a disabled AI config."""
    return DisabledAIConfig(provider="disabled")


def test_disabled_provider_raises(disabled_config: DisabledAIConfig) -> None:
    """Test that AIDisabledError is raised for disabled config."""
    with pytest.raises(AIDisabledError, match="AI is disabled"):
        AIProvider(disabled_config)


def test_gemini_provider_build_params(gemini_config: GeminiProviderConfig) -> None:
    """Test Gemini provider parameter building."""
    with patch.dict(os.environ, {"TEST_GEMINI_KEY": "test-api-key"}):
        provider = AIProvider(gemini_config)
        model, params = provider._build_llm_params()

        # Verify model format
        assert model == "gemini/gemini-2.5-pro"

        # Verify API key
        assert params["api_key"] == "test-api-key"


def test_gemini_api_key_from_env(gemini_config: GeminiProviderConfig) -> None:
    """Test Gemini API key loading from environment variable."""
    with patch.dict(os.environ, {"TEST_GEMINI_KEY": "env-api-key"}):
        provider = AIProvider(gemini_config)
        model, params = provider._build_gemini_params()

        assert model == "gemini/gemini-2.5-pro"
        assert params["api_key"] == "env-api-key"


def test_gemini_api_key_from_file(
    gemini_config: GeminiProviderConfig, tmp_path: Path
) -> None:
    """Test Gemini API key loading from .env file."""
    # Create a temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_GEMINI_KEY=file-api-key\n")

    # Update config to use the file
    gemini_config.api_key_file = str(env_file)

    with patch.dict(os.environ, {}, clear=True):
        # Clear environment first
        provider = AIProvider(gemini_config)
        model, params = provider._build_gemini_params()

        assert model == "gemini/gemini-2.5-pro"
        assert params["api_key"] == "file-api-key"


def test_gemini_api_key_missing(gemini_config: GeminiProviderConfig) -> None:
    """Test error when Gemini API key is not found."""
    with patch.dict(os.environ, {}, clear=True):
        provider = AIProvider(gemini_config)

        with pytest.raises(
            AIProviderError, match="API key not found in environment variable"
        ):
            provider._build_gemini_params()


def test_gemini_api_key_file_not_found(gemini_config: GeminiProviderConfig) -> None:
    """Test error when Gemini API key file doesn't exist."""
    gemini_config.api_key_file = "/nonexistent/path/.env"

    provider = AIProvider(gemini_config)

    with pytest.raises(AIProviderError, match="API key file not found"):
        provider._build_gemini_params()


def test_gemini_with_max_tokens(gemini_config: GeminiProviderConfig) -> None:
    """Test Gemini provider with max_tokens set."""
    gemini_config.max_tokens = 2048

    with patch.dict(os.environ, {"TEST_GEMINI_KEY": "test-key"}):
        provider = AIProvider(gemini_config)
        model, params = provider._build_gemini_params()

        assert model == "gemini/gemini-2.5-pro"
        assert params["max_tokens"] == "2048"


def test_vertex_provider_build_params(vertex_config: VertexAIProviderConfig) -> None:
    """Test Vertex AI provider parameter building."""
    provider = AIProvider(vertex_config)
    model, params = provider._build_llm_params()

    # Verify model format
    assert model == "vertex_ai/gemini-2.5-pro"

    # Verify project and location
    assert params["vertex_project"] == "test-project"
    assert params["vertex_location"] == "us-east5"


def test_vertex_with_credentials_file(
    vertex_config: VertexAIProviderConfig, tmp_path: Path
) -> None:
    """Test Vertex AI provider with credentials file."""
    # Create a temporary credentials file
    creds_file = tmp_path / "creds.json"
    creds_file.write_text('{"type": "service_account"}')

    vertex_config.credentials_file = str(creds_file)

    provider = AIProvider(vertex_config)
    model, params = provider._build_vertex_params()

    assert model == "vertex_ai/gemini-2.5-pro"
    assert params["vertex_credentials"] == str(creds_file)


def test_vertex_credentials_file_not_found(
    vertex_config: VertexAIProviderConfig,
) -> None:
    """Test error when Vertex credentials file doesn't exist."""
    vertex_config.credentials_file = "/nonexistent/creds.json"

    provider = AIProvider(vertex_config)

    with pytest.raises(AIProviderError, match="Credentials file not found"):
        provider._build_vertex_params()


def test_vertex_with_max_tokens(vertex_config: VertexAIProviderConfig) -> None:
    """Test Vertex AI provider with max_tokens set."""
    vertex_config.max_tokens = 4096

    provider = AIProvider(vertex_config)
    model, params = provider._build_vertex_params()

    assert model == "vertex_ai/gemini-2.5-pro"
    assert params["max_tokens"] == "4096"


@patch("iptax.ai.provider.litellm.completion")
def test_judge_changes_success(
    mock_completion: Mock, gemini_config: GeminiProviderConfig
) -> None:
    """Test successful AI judgment with mocked LiteLLM."""
    # Mock the LiteLLM response
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content="""```yaml
judgments:
  - change_id: "github.com/org/repo#123"
    decision: INCLUDE
    reasoning: This change adds core product functionality
  - change_id: "github.com/org/repo#124"
    decision: EXCLUDE
    reasoning: This is documentation only
```"""
            )
        )
    ]
    mock_completion.return_value = mock_response

    with patch.dict(os.environ, {"TEST_GEMINI_KEY": "test-key"}):
        provider = AIProvider(gemini_config)
        response = provider.judge_changes("test prompt")

        # Verify LiteLLM was called correctly
        mock_completion.assert_called_once()
        call_args = mock_completion.call_args

        assert call_args.kwargs["model"] == "gemini/gemini-2.5-pro"
        assert call_args.kwargs["messages"] == [
            {"role": "user", "content": "test prompt"}
        ]
        assert call_args.kwargs["api_key"] == "test-key"

        # Verify response parsing
        assert isinstance(response, AIResponse)
        assert len(response.judgments) == 2

        assert response.judgments[0].change_id == "github.com/org/repo#123"
        assert response.judgments[0].decision == AIDecision.INCLUDE
        assert "core product functionality" in response.judgments[0].reasoning

        assert response.judgments[1].change_id == "github.com/org/repo#124"
        assert response.judgments[1].decision == AIDecision.EXCLUDE
        assert "documentation only" in response.judgments[1].reasoning


@patch("iptax.ai.provider.litellm.completion")
def test_judge_changes_api_error(
    mock_completion: Mock, gemini_config: GeminiProviderConfig
) -> None:
    """Test AI judgment with API error."""
    # Mock LiteLLM to raise an exception
    mock_completion.side_effect = Exception("API connection failed")

    with patch.dict(os.environ, {"TEST_GEMINI_KEY": "test-key"}):
        provider = AIProvider(gemini_config)

        with pytest.raises(AIProviderError, match="AI provider error"):
            provider.judge_changes("test prompt")


def test_parse_response_yaml_block(gemini_config: GeminiProviderConfig) -> None:
    """Test parsing YAML from code blocks."""
    with patch.dict(os.environ, {"TEST_GEMINI_KEY": "test-key"}):
        provider = AIProvider(gemini_config)

        response_text = """Here's my analysis:

```yaml
judgments:
  - change_id: "github.com/org/repo#123"
    decision: INCLUDE
    reasoning: Core feature
```

Hope this helps!"""

        response = provider._parse_response(response_text)

        assert isinstance(response, AIResponse)
        assert len(response.judgments) == 1
        assert response.judgments[0].change_id == "github.com/org/repo#123"
        assert response.judgments[0].decision == AIDecision.INCLUDE


def test_parse_response_no_code_block_fails(
    gemini_config: GeminiProviderConfig,
) -> None:
    """Test that parsing fails if no YAML code block is found."""
    with patch.dict(os.environ, {"TEST_GEMINI_KEY": "test-key"}):
        provider = AIProvider(gemini_config)

        response_text = """judgments:
  - change_id: "github.com/org/repo#123"
    decision: EXCLUDE
    reasoning: Not relevant"""

        with pytest.raises(AIProviderError, match="Failed to extract YAML"):
            provider._parse_response(response_text)


def test_parse_response_invalid_yaml(gemini_config: GeminiProviderConfig) -> None:
    """Test error handling for invalid YAML."""
    with patch.dict(os.environ, {"TEST_GEMINI_KEY": "test-key"}):
        provider = AIProvider(gemini_config)

        response_text = """```yaml
invalid: yaml: : content
```"""

        with pytest.raises(AIProviderError, match="Failed to parse YAML response"):
            provider._parse_response(response_text)


def test_parse_response_invalid_structure(
    gemini_config: GeminiProviderConfig,
) -> None:
    """Test error handling for invalid response structure."""
    with patch.dict(os.environ, {"TEST_GEMINI_KEY": "test-key"}):
        provider = AIProvider(gemini_config)

        response_text = """```yaml
wrong_key: value
```"""

        with pytest.raises(AIProviderError, match="Invalid response format"):
            provider._parse_response(response_text)


def test_parse_response_case_insensitive_yaml_marker(
    gemini_config: GeminiProviderConfig,
) -> None:
    """Test that YAML marker is case-insensitive."""
    with patch.dict(os.environ, {"TEST_GEMINI_KEY": "test-key"}):
        provider = AIProvider(gemini_config)

        response_text = """```YAML
judgments:
  - change_id: "test#1"
    decision: UNCERTAIN
    reasoning: Need more info
```"""

        response = provider._parse_response(response_text)

        assert isinstance(response, AIResponse)
        assert len(response.judgments) == 1
        assert response.judgments[0].decision == AIDecision.UNCERTAIN


def test_parse_response_multiple_yaml_blocks(
    gemini_config: GeminiProviderConfig,
) -> None:
    """Test that first YAML block is extracted when multiple exist."""
    with patch.dict(os.environ, {"TEST_GEMINI_KEY": "test-key"}):
        provider = AIProvider(gemini_config)

        response_text = """Here are my judgments:

```yaml
judgments:
  - change_id: "test#1"
    decision: INCLUDE
    reasoning: First one
```

And here's another block:

```yaml
judgments:
  - change_id: "test#2"
    decision: EXCLUDE
    reasoning: Second one
```"""

        response = provider._parse_response(response_text)

        # Should parse the first block
        assert isinstance(response, AIResponse)
        assert len(response.judgments) == 1
        assert response.judgments[0].change_id == "test#1"
