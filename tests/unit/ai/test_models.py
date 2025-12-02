"""Unit tests for iptax.ai.models module.

Tests all AI-related Pydantic models including validation, serialization,
and business logic.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from iptax.ai.models import (
    AIDecision,
    AIResponse,
    AIResponseItem,
    Judgment,
    JudgmentCache,
)


class TestAIDecision:
    """Test AIDecision enum."""

    def test_enum_value_count(self):
        """Test that there are exactly 3 decision types."""
        assert len(AIDecision) == 3

    def test_enum_membership(self):
        """Test that values can be checked for membership."""
        assert AIDecision("INCLUDE") == AIDecision.INCLUDE
        assert AIDecision("EXCLUDE") == AIDecision.EXCLUDE
        assert AIDecision("UNCERTAIN") == AIDecision.UNCERTAIN
        with pytest.raises(ValueError):
            AIDecision("ERROR")


class TestJudgment:
    """Test Judgment model."""

    def test_basic_creation(self):
        """Test creating a Judgment with required fields."""
        judgment = Judgment(
            change_id="github.com/owner/repo#123",
            decision=AIDecision.INCLUDE,
            reasoning="This change implements core product functionality",
            product="Test Product",
        )

        assert judgment.change_id == "github.com/owner/repo#123"
        assert judgment.decision == AIDecision.INCLUDE
        assert judgment.reasoning == "This change implements core product functionality"
        assert judgment.product == "Test Product"
        assert judgment.user_decision is None
        assert judgment.user_reasoning is None
        assert isinstance(judgment.timestamp, datetime)

    def test_timestamp_is_utc(self):
        """Test that timestamp is in UTC."""
        judgment = Judgment(
            change_id="test#1",
            decision=AIDecision.INCLUDE,
            reasoning="Test",
            product="Test",
        )

        # Timestamp should have UTC timezone
        assert judgment.timestamp.tzinfo == UTC

    def test_with_user_override(self):
        """Test creating a Judgment with user override."""
        judgment = Judgment(
            change_id="github.com/owner/repo#123",
            decision=AIDecision.INCLUDE,
            reasoning="AI thinks this is relevant",
            user_decision=AIDecision.EXCLUDE,
            user_reasoning="Actually not related to our product",
            product="Test Product",
        )

        assert judgment.decision == AIDecision.INCLUDE
        assert judgment.user_decision == AIDecision.EXCLUDE
        assert judgment.user_reasoning == "Actually not related to our product"

    def test_final_decision_without_user_override(self):
        """Test final_decision property returns AI decision when no override."""
        judgment = Judgment(
            change_id="test#1",
            decision=AIDecision.INCLUDE,
            reasoning="Test",
            product="Test",
        )

        assert judgment.final_decision == AIDecision.INCLUDE

    def test_final_decision_with_user_override(self):
        """Test final_decision property returns user decision when overridden."""
        judgment = Judgment(
            change_id="test#1",
            decision=AIDecision.INCLUDE,
            reasoning="AI reasoning",
            user_decision=AIDecision.EXCLUDE,
            product="Test",
        )

        assert judgment.final_decision == AIDecision.EXCLUDE

    def test_final_decision_with_uncertain_to_include(self):
        """Test user can override UNCERTAIN to INCLUDE."""
        judgment = Judgment(
            change_id="test#1",
            decision=AIDecision.UNCERTAIN,
            reasoning="Not enough context",
            user_decision=AIDecision.INCLUDE,
            product="Test",
        )

        assert judgment.final_decision == AIDecision.INCLUDE

    def test_change_id_required(self):
        """Test that change_id is required."""
        with pytest.raises(ValidationError) as exc_info:
            Judgment(
                decision=AIDecision.INCLUDE,
                reasoning="Test",
                product="Test",
            )

        assert "change_id" in str(exc_info.value)

    def test_decision_required(self):
        """Test that decision is required."""
        with pytest.raises(ValidationError) as exc_info:
            Judgment(
                change_id="test#1",
                reasoning="Test",
                product="Test",
            )

        assert "decision" in str(exc_info.value)

    def test_reasoning_required(self):
        """Test that reasoning is required."""
        with pytest.raises(ValidationError) as exc_info:
            Judgment(
                change_id="test#1",
                decision=AIDecision.INCLUDE,
                product="Test",
            )

        assert "reasoning" in str(exc_info.value)

    def test_product_required(self):
        """Test that product is required."""
        with pytest.raises(ValidationError) as exc_info:
            Judgment(
                change_id="test#1",
                decision=AIDecision.INCLUDE,
                reasoning="Test",
            )

        assert "product" in str(exc_info.value)

    def test_invalid_decision_type(self):
        """Test that invalid decision type raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Judgment(
                change_id="test#1",
                decision="INVALID",
                reasoning="Test",
                product="Test",
            )

        assert "decision" in str(exc_info.value).lower()

    def test_serialization_and_deserialization(self):
        """Test Judgment can be serialized and deserialized."""
        original = Judgment(
            change_id="github.com/owner/repo#123",
            decision=AIDecision.INCLUDE,
            reasoning="Test reasoning",
            product="Test Product",
        )

        # Serialize to dict
        data = original.model_dump(mode="python")

        # Deserialize from dict
        restored = Judgment(**data)

        assert restored.change_id == original.change_id
        assert restored.decision == original.decision
        assert restored.reasoning == original.reasoning
        assert restored.product == original.product


class TestJudgmentCache:
    """Test JudgmentCache model."""

    def test_empty_cache_creation(self):
        """Test creating an empty cache."""
        cache = JudgmentCache()

        assert cache.cache_version == "1.0"
        assert cache.judgments == {}

    def test_cache_with_judgments(self):
        """Test creating cache with judgments."""
        judgment1 = Judgment(
            change_id="test#1",
            decision=AIDecision.INCLUDE,
            reasoning="Test 1",
            product="Product",
        )
        judgment2 = Judgment(
            change_id="test#2",
            decision=AIDecision.EXCLUDE,
            reasoning="Test 2",
            product="Product",
        )

        cache = JudgmentCache(
            judgments={
                "test#1": judgment1,
                "test#2": judgment2,
            }
        )

        assert len(cache.judgments) == 2
        assert "test#1" in cache.judgments
        assert "test#2" in cache.judgments

    def test_cache_version_has_default(self):
        """Test that cache_version has a default value of '1.0'."""
        cache = JudgmentCache()
        assert cache.cache_version == "1.0"

    def test_serialization_and_deserialization(self):
        """Test cache can be serialized and deserialized."""
        judgment = Judgment(
            change_id="test#1",
            decision=AIDecision.INCLUDE,
            reasoning="Test",
            product="Product",
        )

        original = JudgmentCache(judgments={"test#1": judgment})

        # Serialize to dict
        data = original.model_dump(mode="python")

        # Deserialize from dict
        restored = JudgmentCache(**data)

        assert restored.cache_version == original.cache_version
        assert len(restored.judgments) == len(original.judgments)
        assert "test#1" in restored.judgments

    def test_adding_judgment_to_cache(self):
        """Test adding judgment to existing cache."""
        cache = JudgmentCache()

        judgment = Judgment(
            change_id="test#1",
            decision=AIDecision.INCLUDE,
            reasoning="Test",
            product="Product",
        )

        cache.judgments["test#1"] = judgment

        assert len(cache.judgments) == 1
        assert cache.judgments["test#1"].change_id == "test#1"


class TestAIResponseItem:
    """Test AIResponseItem model."""

    def test_basic_creation(self):
        """Test creating an AIResponseItem."""
        item = AIResponseItem(
            change_id="github.com/owner/repo#123",
            decision=AIDecision.INCLUDE,
            reasoning="This implements core functionality",
        )

        assert item.change_id == "github.com/owner/repo#123"
        assert item.decision == AIDecision.INCLUDE
        assert item.reasoning == "This implements core functionality"

    def test_all_fields_required(self):
        """Test that all fields are required."""
        with pytest.raises(ValidationError) as exc_info:
            AIResponseItem(
                change_id="test#1",
                decision=AIDecision.INCLUDE,
            )

        assert "reasoning" in str(exc_info.value)


class TestAIResponse:
    """Test AIResponse model."""

    def test_empty_response(self):
        """Test creating an empty AI response."""
        response = AIResponse(judgments=[])

        assert response.judgments == []

    def test_response_with_single_judgment(self):
        """Test creating response with single judgment."""
        item = AIResponseItem(
            change_id="test#1",
            decision=AIDecision.INCLUDE,
            reasoning="Test",
        )

        response = AIResponse(judgments=[item])

        assert len(response.judgments) == 1
        assert response.judgments[0].change_id == "test#1"

    def test_response_with_multiple_judgments(self):
        """Test creating response with multiple judgments."""
        items = [
            AIResponseItem(
                change_id="test#1",
                decision=AIDecision.INCLUDE,
                reasoning="Relevant",
            ),
            AIResponseItem(
                change_id="test#2",
                decision=AIDecision.EXCLUDE,
                reasoning="Not relevant",
            ),
            AIResponseItem(
                change_id="test#3",
                decision=AIDecision.UNCERTAIN,
                reasoning="Need more context",
            ),
        ]

        response = AIResponse(judgments=items)

        assert len(response.judgments) == 3
        assert response.judgments[0].decision == AIDecision.INCLUDE
        assert response.judgments[1].decision == AIDecision.EXCLUDE
        assert response.judgments[2].decision == AIDecision.UNCERTAIN

    def test_parsing_from_dict(self):
        """Test parsing AIResponse from dictionary."""
        data = {
            "judgments": [
                {
                    "change_id": "test#1",
                    "decision": "INCLUDE",
                    "reasoning": "Relevant change",
                },
                {
                    "change_id": "test#2",
                    "decision": "EXCLUDE",
                    "reasoning": "Infrastructure change",
                },
            ]
        }

        response = AIResponse(**data)

        assert len(response.judgments) == 2
        assert response.judgments[0].change_id == "test#1"
        assert response.judgments[0].decision == AIDecision.INCLUDE
        assert response.judgments[1].change_id == "test#2"
        assert response.judgments[1].decision == AIDecision.EXCLUDE

    def test_judgments_field_required(self):
        """Test that judgments field is required."""
        with pytest.raises(ValidationError) as exc_info:
            AIResponse()

        assert "judgments" in str(exc_info.value)

    def test_invalid_judgment_in_response(self):
        """Test that invalid judgment data raises error."""
        data = {
            "judgments": [
                {
                    "change_id": "test#1",
                    "decision": "INVALID_DECISION",
                    "reasoning": "Test",
                }
            ]
        }

        with pytest.raises(ValidationError) as exc_info:
            AIResponse(**data)

        assert "decision" in str(exc_info.value).lower()

    def test_serialization_and_deserialization(self):
        """Test response can be serialized and deserialized."""
        original = AIResponse(
            judgments=[
                AIResponseItem(
                    change_id="test#1",
                    decision=AIDecision.INCLUDE,
                    reasoning="Test",
                )
            ]
        )

        # Serialize to dict
        data = original.model_dump(mode="python")

        # Deserialize from dict
        restored = AIResponse(**data)

        assert len(restored.judgments) == len(original.judgments)
        assert restored.judgments[0].change_id == original.judgments[0].change_id
