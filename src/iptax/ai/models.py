"""Pydantic data models for AI-powered filtering and decisions.

This module re-exports core types from iptax.models and defines
AI-specific cache structures.
"""

from pydantic import BaseModel, Field

# Re-export core types from models
from iptax.models import Decision, Judgment

__all__ = ["AIResponse", "AIResponseItem", "Decision", "Judgment", "JudgmentCache"]


class JudgmentCache(BaseModel):
    """Cache schema for AI judgments."""

    cache_version: str = "1.0"
    judgments: dict[str, Judgment] = Field(default_factory=dict)


class AIResponseItem(BaseModel):
    """Single item in AI response."""

    change_id: str
    decision: Decision
    reasoning: str


class AIResponse(BaseModel):
    """Parsed AI response."""

    judgments: list[AIResponseItem]
