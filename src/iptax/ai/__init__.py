"""AI-powered filtering and decision making for IP tax changes.

This module provides AI-based filtering of merged PRs/MRs to determine
which changes are relevant to the product for IP tax reporting purposes.
"""

from .cache import DEFAULT_CACHE_PATH, JudgmentCacheManager
from .models import AIDecision, AIResponse, AIResponseItem, Judgment, JudgmentCache
from .prompts import build_judgment_prompt
from .provider import AIDisabledError, AIProvider, AIProviderError

__all__ = [
    "DEFAULT_CACHE_PATH",
    "AIDecision",
    "AIDisabledError",
    "AIProvider",
    "AIProviderError",
    "AIResponse",
    "AIResponseItem",
    "Judgment",
    "JudgmentCache",
    "JudgmentCacheManager",
    "build_judgment_prompt",
]
