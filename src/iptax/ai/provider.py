"""AI provider integration using LiteLLM.

This module provides the AIProvider class that handles communication with
various AI providers (Gemini, Vertex AI) through the LiteLLM library.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any

import litellm
import yaml
from dotenv import load_dotenv

from iptax.models import (
    AIProviderConfig,
    DisabledAIConfig,
    GeminiProviderConfig,
    VertexAIProviderConfig,
)

from .models import AIResponse

logger = logging.getLogger(__name__)


class AIProviderError(Exception):
    """Error during AI provider operation."""

    pass


class AIDisabledError(Exception):
    """AI is disabled in configuration."""

    pass


class AIProvider:
    """AI provider for judging code changes.

    Handles communication with AI providers through LiteLLM and parses
    responses into structured judgments.

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

    def __init__(self, config: AIProviderConfig) -> None:
        """Initialize AI provider with configuration.

        Args:
            config: AI provider configuration (discriminated union)

        Raises:
            AIDisabledError: If AI is disabled in configuration
        """
        if isinstance(config, DisabledAIConfig):
            raise AIDisabledError("AI is disabled in configuration")

        self.config = config

    def judge_changes(self, prompt: str) -> AIResponse:
        """Send prompt to AI and parse the response.

        Args:
            prompt: The prompt to send to the AI

        Returns:
            Parsed AI response with judgments

        Raises:
            AIProviderError: If the API call fails or response is invalid
        """
        # Build parameters for LiteLLM
        model, api_params = self._build_llm_params()

        logger.debug("Sending prompt to AI model: %s", model)
        logger.debug("Prompt:\n%s", prompt)

        try:
            # Call LiteLLM
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                **api_params,
            )
        except Exception as e:
            raise AIProviderError(f"AI provider error: {e}") from e

        # Extract response text
        response_text = response.choices[0].message.content
        if not response_text:
            raise AIProviderError("AI returned empty response")
        logger.debug("AI response:\n%s", response_text)

        # Parse YAML from response
        return self._parse_response(response_text, prompt)

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

        Extracts YAML from code blocks (```yaml ... ```).

        Args:
            response_text: Raw response text from AI
            prompt: Original prompt (for debugging)

        Returns:
            Parsed AIResponse

        Raises:
            AIProviderError: If response cannot be parsed
        """
        # Extract YAML from code blocks
        yaml_match = re.search(
            r"```yaml\s*\n(.*?)\n```", response_text, re.DOTALL | re.IGNORECASE
        )

        if not yaml_match:
            logger.debug("Failed to extract YAML from response")
            logger.debug("Prompt was:\n%s", prompt)
            logger.debug("Response was:\n%s", response_text)
            raise AIProviderError(
                "Failed to extract YAML from response. "
                "Expected ```yaml ... ``` code block."
            )

        yaml_text = yaml_match.group(1)

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
