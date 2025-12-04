"""AI provider integration using LiteLLM.

This module provides the AIProvider class that handles communication with
various AI providers (Gemini, Vertex AI) through the LiteLLM library.
"""

import contextlib
import logging
import os
import re
import warnings
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic.warnings import PydanticDeprecatedSince20

from iptax.models import (
    AIProviderConfig,
    DisabledAIConfig,
    GeminiProviderConfig,
    VertexAIProviderConfig,
)

from .models import AIResponse

# Filter litellm's Pydantic deprecation warnings before importing litellm.
# litellm uses deprecated Pydantic class-based config that emits warnings
# during import, and we cannot fix this in external library code.
warnings.filterwarnings(
    "ignore",
    message=r"Support for class-based .config. is deprecated",
    category=PydanticDeprecatedSince20,
    module="litellm.types.llms.anthropic",
)
# litellm has internal Pydantic serialization issues at runtime
warnings.filterwarnings(
    "ignore",
    message=r"Pydantic serializer warnings",
    category=UserWarning,
)

# E402: litellm must be imported AFTER the warning filters above because
# it emits deprecation warnings during import.
import litellm  # noqa: E402

logger = logging.getLogger(__name__)


def cleanup_litellm_clients() -> None:
    """Clean up cached litellm HTTP clients.

    LiteLLM caches HTTP clients in `litellm.in_memory_llm_clients_cache`.
    These should be cleaned up after use to prevent "I/O operation on
    closed file" errors during Python interpreter shutdown (the clients'
    __del__ methods try to log after stderr is closed).

    Call this function when done with AI operations, typically at the end
    of a CLI command or test session.
    """
    with contextlib.suppress(Exception):
        cache = getattr(litellm, "in_memory_llm_clients_cache", None)
        if cache is None:
            return

        cache_dict = getattr(cache, "cache_dict", None)
        if cache_dict is None:
            return

        for key in list(cache_dict.keys()):
            if key.startswith("httpx_client"):
                with contextlib.suppress(Exception):
                    item = cache_dict.get(key)
                    if item is not None:
                        client = getattr(item, "value", item)
                        if hasattr(client, "close"):
                            client.close()
                        # Remove from cache to prevent __del__ from running
                        with contextlib.suppress(Exception):
                            del cache_dict[key]


class AIProviderError(Exception):
    """Error during AI provider operation."""

    pass


class AIDisabledError(Exception):
    """AI is disabled in configuration."""

    pass


# Default max retries for parsing errors
DEFAULT_MAX_RETRIES = 2


class AIProvider:
    """AI provider for judging code changes.

    Handles communication with AI providers through LiteLLM and parses
    responses into structured judgments. Includes retry logic for parsing
    errors.

    Examples:
        >>> from iptax.models import GeminiProviderConfig
        >>> config = GeminiProviderConfig(
        ...     provider="gemini",
        ...     model="gemini-2.5-pro",
        ...     api_key_env="GEMINI_API_KEY"
        ... )
        >>> provider = AIProvider(config)
        >>> prompt = "..."
        >>> response = provider.judge_changes(prompt)
    """

    def __init__(
        self, config: AIProviderConfig, max_retries: int = DEFAULT_MAX_RETRIES
    ) -> None:
        """Initialize AI provider with configuration.

        Args:
            config: AI provider configuration (discriminated union)
            max_retries: Maximum retries when AI response can't be parsed

        Raises:
            AIDisabledError: If AI is disabled in configuration
        """
        if isinstance(config, DisabledAIConfig):
            raise AIDisabledError("AI is disabled in configuration")

        self.config = config
        self.max_retries = max_retries

    def judge_changes(self, prompt: str) -> AIResponse:
        """Send prompt to AI and parse the response.

        Includes retry logic: if the response cannot be parsed, the AI is
        asked to correct its response with the error details.

        Args:
            prompt: The prompt to send to the AI

        Returns:
            Parsed AI response with judgments

        Raises:
            AIProviderError: If the API call fails or response is invalid
                after all retries
        """
        try:
            return self._judge_changes_impl(prompt)
        finally:
            # Clean up litellm HTTP clients to prevent "I/O operation on
            # closed file" errors during Python interpreter shutdown
            cleanup_litellm_clients()

    def _judge_changes_impl(self, prompt: str) -> AIResponse:
        """Internal implementation of judge_changes.

        Args:
            prompt: The prompt to send to the AI

        Returns:
            Parsed AI response with judgments
        """
        # Build parameters for LiteLLM
        model, api_params = self._build_llm_params()

        logger.debug("Sending prompt to AI model: %s", model)
        logger.debug("Prompt:\n%s", prompt)

        # Build conversation messages
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                # Call LiteLLM
                response = litellm.completion(
                    model=model,
                    messages=messages,
                    **api_params,
                )
            except Exception as e:
                raise AIProviderError(f"AI provider error: {e}") from e

            # Extract response text
            response_text = response.choices[0].message.content
            if not response_text:
                raise AIProviderError("AI returned empty response")
            logger.debug("AI response (attempt %d):\n%s", attempt + 1, response_text)

            try:
                return self._parse_response(response_text, prompt)
            except AIProviderError as e:
                last_error = e
                if attempt < self.max_retries:
                    # Add the AI's response and error correction request
                    logger.info(
                        "Parse error on attempt %d, retrying: %s", attempt + 1, e
                    )
                    messages.append({"role": "assistant", "content": response_text})
                    messages.append(
                        {
                            "role": "user",
                            "content": self._build_correction_prompt(str(e)),
                        }
                    )
                else:
                    logger.warning("Parse failed after %d attempts: %s", attempt + 1, e)

        # All retries exhausted
        assert last_error is not None
        raise last_error

    def _build_correction_prompt(self, error_message: str) -> str:
        """Build a prompt asking the AI to correct its response.

        Args:
            error_message: The parsing error message

        Returns:
            Correction prompt string
        """
        return (
            f"Your response could not be parsed. Error: {error_message}\n\n"
            "Please provide your response again in valid YAML format, "
            "wrapped in ```yaml and ``` code blocks. "
            "Make sure the YAML structure matches the expected format with "
            "'judgments' as the top-level key containing a list of items, "
            "each with 'change_id', 'decision', and 'reasoning' fields."
        )

    def _build_llm_params(self) -> tuple[str, dict[str, Any]]:
        """Build model name and API parameters for LiteLLM.

        Returns:
            Tuple of (model_name, api_params_dict)

        Raises:
            AIProviderError: If configuration is invalid or credentials are missing
        """
        match self.config:
            case GeminiProviderConfig():
                return self._build_gemini_params()
            case VertexAIProviderConfig():
                return self._build_vertex_params()
            case _:
                raise AIProviderError(f"Unknown provider type: {self.config.provider}")

    def _build_gemini_params(self) -> tuple[str, dict[str, Any]]:
        """Build parameters for Gemini provider.

        Returns:
            Tuple of (model_name, api_params_dict)

        Raises:
            AIProviderError: If API key is not found
        """
        assert isinstance(self.config, GeminiProviderConfig)

        # Load API key from file if specified
        if self.config.api_key_file:
            env_file = Path(self.config.api_key_file).expanduser()
            if not env_file.exists():
                raise AIProviderError(f"API key file not found: {env_file}")
            load_dotenv(env_file)

        # Get API key from environment
        api_key = os.getenv(self.config.api_key_env)
        if not api_key:
            raise AIProviderError(
                f"API key not found in environment variable: {self.config.api_key_env}"
            )

        # Build model name in LiteLLM format
        model = f"gemini/{self.config.model}"

        # Build API params
        api_params: dict[str, Any] = {"api_key": api_key}

        if self.config.max_tokens:
            api_params["max_tokens"] = self.config.max_tokens

        return model, api_params

    def _build_vertex_params(self) -> tuple[str, dict[str, Any]]:
        """Build parameters for Vertex AI provider.

        Returns:
            Tuple of (model_name, api_params_dict)

        Raises:
            AIProviderError: If required configuration is missing
        """
        assert isinstance(self.config, VertexAIProviderConfig)

        # Build model name in LiteLLM format
        model = f"vertex_ai/{self.config.model}"

        # Build API params
        api_params: dict[str, Any] = {
            "vertex_project": self.config.project_id,
            "vertex_location": self.config.location,
        }

        # Add credentials file if specified
        if self.config.credentials_file:
            creds_file = Path(self.config.credentials_file).expanduser()
            if not creds_file.exists():
                raise AIProviderError(f"Credentials file not found: {creds_file}")
            api_params["vertex_credentials"] = str(creds_file)

        if self.config.max_tokens:
            api_params["max_tokens"] = self.config.max_tokens

        return model, api_params

    def _parse_response(self, response_text: str, prompt: str = "") -> AIResponse:
        """Parse AI response text into structured data.

        First tries to extract YAML from code blocks (```yaml ... ```).
        If no code block is found, attempts to parse the entire response as YAML.

        Args:
            response_text: Raw response text from AI
            prompt: Original prompt (for debugging)

        Returns:
            Parsed AIResponse

        Raises:
            AIProviderError: If response cannot be parsed
        """
        # Try to extract YAML from code blocks first
        yaml_match = re.search(
            r"```yaml\s*\n(.*?)\n```", response_text, re.DOTALL | re.IGNORECASE
        )

        if yaml_match:
            yaml_text = yaml_match.group(1)
            logger.debug("Extracted YAML from code block")
        else:
            # Fallback: try to parse the entire response as YAML
            logger.debug("No YAML code block found, trying to parse entire response")
            yaml_text = response_text.strip()

        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            logger.debug("Failed to parse YAML")
            logger.debug("Prompt was:\n%s", prompt)
            logger.debug("YAML text was:\n%s", yaml_text)
            raise AIProviderError(f"Failed to parse YAML response: {e}") from e

        if data is None:
            raise AIProviderError("Empty YAML response")

        try:
            return AIResponse(**data)
        except Exception as e:
            logger.debug("Invalid response format")
            logger.debug("Prompt was:\n%s", prompt)
            logger.debug("Data was: %s", data)
            raise AIProviderError(f"Invalid response format: {e}") from e
