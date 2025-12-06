"""Pydantic data models for AI-powered filtering and decisions.

This module defines AI-specific cache and response structures.
Core types like Decision and Judgment are in iptax.models.
"""

from pydantic import BaseModel, Field

from iptax.models import Decision, Judgment


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
