"""Judgment cache manager for AI-powered filtering.

This module manages persistent storage and intelligent retrieval of AI judgments
for learning context purposes.
"""

import contextlib
import json
import logging
from pathlib import Path

from iptax.utils.env import get_cache_dir

from .models import Decision, Judgment, JudgmentCache

logger = logging.getLogger(__name__)


def get_ai_cache_path() -> Path:
    """Get path to AI cache file.

    Returns dynamically to respect environment variable changes.
    """
    return get_cache_dir() / "ai_cache.json"


class JudgmentCacheManager:
    """Manages the AI judgment cache with intelligent history selection."""

    def __init__(self, cache_path: Path | None = None) -> None:
        """Initialize cache manager.

        Args:
            cache_path: Custom cache path, defaults to ~/.cache/iptax/ai_cache.json
        """
        self.cache_path = cache_path or get_ai_cache_path()
        self.cache = JudgmentCache()
        self.load()

    def load(self) -> None:
        """Load cache from disk, creating empty cache if not exists."""
        if not self.cache_path.exists():
            logger.debug(
                f"Cache file not found at {self.cache_path}, starting with empty cache"
            )
            return

        try:
            with self.cache_path.open() as f:
                data = json.load(f)
                self.cache = JudgmentCache.model_validate(data)
                logger.debug(f"Loaded {len(self.cache.judgments)} judgments from cache")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Cache file corrupted, starting with empty cache: {e}")
            self.cache = JudgmentCache()

    def save(self) -> None:
        """Persist cache to disk."""
        # Create parent directories if they don't exist
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        with self.cache_path.open("w") as f:
            json.dump(self.cache.model_dump(mode="json"), f, indent=2)
        self.cache_path.chmod(0o600)
        logger.debug(f"Saved {len(self.cache.judgments)} judgments to cache")

    def add_judgment(self, judgment: Judgment) -> None:
        """Add or update a judgment in the cache.

        If an existing judgment has a user decision and the new judgment's
        final decision matches, the existing is preserved (not overwritten).
        If decisions differ, the new judgment is saved.

        Args:
            judgment: The judgment to add
        """
        existing = self.cache.judgments.get(judgment.change_id)
        if existing and existing.user_decision is not None:
            # Check if decisions match - if so, preserve existing
            if existing.final_decision == judgment.final_decision:
                logger.debug(
                    f"Preserving existing judgment for '{judgment.change_id}': "
                    f"user_decision={existing.user_decision.value}, "
                    f"final={existing.final_decision.value}"
                )
                return
            # Decisions differ - log and update
            cached_val = existing.final_decision.value
            new_val = judgment.final_decision.value
            logger.debug(
                f"Updating judgment for '{judgment.change_id}': "
                f"cached={cached_val} → new={new_val}"
            )

        self.cache.judgments[judgment.change_id] = judgment
        self.save()

    def update_with_user_decision(
        self,
        change_id: str,
        user_decision: Decision,
        user_reasoning: str | None = None,
    ) -> bool:
        """Record user's override of an AI decision.

        Args:
            change_id: The change identifier
            user_decision: User's decision
            user_reasoning: Optional user's reasoning

        Returns:
            True if judgment was found and updated, False otherwise
        """
        if change_id not in self.cache.judgments:
            logger.warning(f"Cannot update non-existent judgment: {change_id}")
            return False

        judgment = self.cache.judgments[change_id]
        judgment.user_decision = user_decision
        judgment.user_reasoning = user_reasoning
        self.save()
        return True

    def get_judgment(self, change_id: str) -> Judgment | None:
        """Retrieve a specific judgment by change_id.

        Args:
            change_id: The change identifier

        Returns:
            The judgment if found, None otherwise
        """
        return self.cache.judgments.get(change_id)

    def get_history_for_prompt(
        self,
        product: str,
        max_entries: int = 20,
        correction_ratio: float = 0.75,
    ) -> list[Judgment]:
        """Select optimal history entries for AI prompt context.

        This implements an intelligent selection algorithm that prioritizes
        user corrections (where AI was wrong) while including some correct
        AI decisions for positive reinforcement.

        Args:
            product: Only include judgments for this product
            max_entries: Maximum number of entries to return
            correction_ratio: Target ratio of corrected vs correct entries
                            (0.75 = 75% corrections, 25% correct)

        Returns:
            List of Judgment objects optimized for learning context
        """
        # Step 1: Filter by product
        product_judgments = [
            j for j in self.cache.judgments.values() if j.product == product
        ]

        # Handle empty cache
        if not product_judgments:
            return []

        # Step 2: Separate into pools
        corrected = [j for j in product_judgments if j.was_corrected]
        correct = [j for j in product_judgments if not j.was_corrected]

        # Step 3: Sort each pool by recency (newest first)
        corrected.sort(key=lambda j: j.timestamp, reverse=True)
        correct.sort(key=lambda j: j.timestamp, reverse=True)

        # Step 4: Calculate slot allocation
        target_corrections = int(max_entries * correction_ratio)
        target_correct = max_entries - target_corrections

        # Handle pool size limitations with fallback
        actual_corrections = min(len(corrected), target_corrections)
        actual_correct = min(len(correct), target_correct)

        # If one pool is short, fill from the other
        remaining_slots = max_entries - actual_corrections - actual_correct
        if remaining_slots > 0:
            if actual_corrections < target_corrections:
                # Not enough corrections, take more correct
                extra_correct = min(remaining_slots, len(correct) - actual_correct)
                actual_correct += extra_correct
            else:
                # Not enough correct, take more corrections
                extra_corrections = min(
                    remaining_slots, len(corrected) - actual_corrections
                )
                actual_corrections += extra_corrections

        # Step 5: Select and combine
        selected_corrections = corrected[:actual_corrections]
        selected_correct = correct[:actual_correct]

        # Interleave for variety (correction, correct, correction, ...)
        result: list[Judgment] = []
        corr_iter = iter(selected_corrections)
        correct_iter = iter(selected_correct)

        # Alternate, prioritizing corrections
        while len(result) < max_entries:
            with contextlib.suppress(StopIteration):
                result.append(next(corr_iter))

            if len(result) < max_entries:
                with contextlib.suppress(StopIteration):
                    result.append(next(correct_iter))

            # Break if both exhausted
            if len(result) == actual_corrections + actual_correct:
                break

        return result

    def clear_product(self, product: str) -> int:
        """Remove all judgments for a product.

        Args:
            product: The product name

        Returns:
            Count of judgments removed
        """
        original_count = len(self.cache.judgments)
        self.cache.judgments = {
            k: v for k, v in self.cache.judgments.items() if v.product != product
        }
        removed_count = original_count - len(self.cache.judgments)

        if removed_count > 0:
            self.save()

        return removed_count

    def stats(self, product: str | None = None) -> dict:
        """Get cache statistics.

        Args:
            product: Optional product filter

        Returns:
            Dictionary with cache statistics including:
                - total_judgments: Total count
                - corrected_count: Count of user corrections
                - correct_count: Count of correct AI decisions
                - correction_rate: Ratio of corrections to total
                - products: List of unique products
                - oldest_judgment: Timestamp of oldest judgment
                - newest_judgment: Timestamp of newest judgment
        """
        judgments = list(self.cache.judgments.values())

        if product:
            judgments = [j for j in judgments if j.product == product]

        if not judgments:
            return {
                "total_judgments": 0,
                "corrected_count": 0,
                "correct_count": 0,
                "correction_rate": 0.0,
                "products": [],
                "oldest_judgment": None,
                "newest_judgment": None,
            }

        corrected = [j for j in judgments if j.was_corrected]
        correct = [j for j in judgments if not j.was_corrected]

        timestamps = [j.timestamp for j in judgments]
        all_judgments = list(self.cache.judgments.values())
        products = sorted({j.product for j in all_judgments})

        return {
            "total_judgments": len(judgments),
            "corrected_count": len(corrected),
            "correct_count": len(correct),
            "correction_rate": len(corrected) / len(judgments) if judgments else 0.0,
            "products": products,
            "oldest_judgment": min(timestamps).isoformat() if timestamps else None,
            "newest_judgment": max(timestamps).isoformat() if timestamps else None,
        }
