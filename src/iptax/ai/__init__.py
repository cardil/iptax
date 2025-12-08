"""AI-powered filtering and decision making for IP tax changes.

This module provides AI-based filtering of merged PRs/MRs to determine
which changes are relevant to the product for IP tax reporting purposes.
"""

from .cache import JudgmentCacheManager, get_ai_cache_path
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
    "get_ai_cache_path",
    "needs_review",
    "review_judgments",
]
