"""Pydantic data models for AI-powered filtering and decisions.

This module defines all data models used for AI-based filtering of merged
PRs/MRs, including decisions, judgments, and cache structures.
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class AIDecision(str, Enum):
    """AI decision for a change."""

    INCLUDE = "INCLUDE"  # Change directly contributes to the product
    EXCLUDE = "EXCLUDE"  # Change is unrelated to the product
    UNCERTAIN = "UNCERTAIN"  # Cannot determine with confidence


class Judgment(BaseModel):
    """AI judgment for a single change."""

    change_id: str = Field(..., description="Unique identifier: owner/repo#number")
    decision: AIDecision
    reasoning: str = Field(..., description="AI's reasoning for the decision")
    user_decision: AIDecision | None = Field(None, description="User override decision")
    user_reasoning: str | None = Field(
        None, description="User's reasoning for override"
    )
    product: str = Field(..., description="Product name this judgment is for")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this judgment was made (UTC)",
    )

    @property
    def final_decision(self) -> AIDecision:
        """Return user decision if set, otherwise AI decision."""
        return self.user_decision if self.user_decision else self.decision


class JudgmentCache(BaseModel):
    """Cache schema for AI judgments."""

    cache_version: str = "1.0"
    judgments: dict[str, Judgment] = Field(default_factory=dict)


class AIResponseItem(BaseModel):
    """Single item in AI response."""

    change_id: str
    decision: AIDecision
    reasoning: str


class AIResponse(BaseModel):
    """Parsed AI response."""

    judgments: list[AIResponseItem]
