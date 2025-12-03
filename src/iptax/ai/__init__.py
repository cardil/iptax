"""AI-powered filtering and decision making for IP tax changes.

This module provides AI-based filtering of merged PRs/MRs to determine
which changes are relevant to the product for IP tax reporting purposes.
"""

from .cache import DEFAULT_CACHE_PATH, JudgmentCacheManager
from .models import AIResponse, AIResponseItem, Decision, Judgment, JudgmentCache
from .prompts import build_judgment_prompt
from .provider import AIDisabledError, AIProvider, AIProviderError
from .review import (
    COLORS,
    ICONS,
    ReviewResult,
    needs_review,
    review_judgments,
)
from .tui import ai_progress

__all__ = [
    "COLORS",
    "DEFAULT_CACHE_PATH",
    "ICONS",
    "AIDisabledError",
    "AIProvider",
    "AIProviderError",
    "AIResponse",
    "AIResponseItem",
    "Decision",
    "Judgment",
    "JudgmentCache",
    "JudgmentCacheManager",
    "ReviewResult",
    "ai_progress",
    "build_judgment_prompt",
    "needs_review",
    "review_judgments",
]
