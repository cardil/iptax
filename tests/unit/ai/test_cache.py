"""Tests for AI judgment cache manager."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from iptax.ai.cache import JudgmentCacheManager, get_ai_cache_path
from iptax.ai.models import Decision, Judgment, JudgmentCache


class TestJudgmentModel:
    """Test Judgment model's was_corrected property."""

    def test_was_corrected_when_user_decision_differs(self):
        """Test was_corrected returns True when user overrides AI decision."""
        judgment = Judgment(
            change_id="test#1",
            decision=Decision.INCLUDE,
            reasoning="AI thinks it's related",
            user_decision=Decision.EXCLUDE,
            user_reasoning="Actually not related",
            product="TestProduct",
        )
        assert judgment.was_corrected is True

    def test_was_corrected_when_user_agrees(self):
        """Test was_corrected returns False when user agrees with AI."""
        judgment = Judgment(
            change_id="test#1",
            decision=Decision.INCLUDE,
            reasoning="AI thinks it's related",
            user_decision=Decision.INCLUDE,
            user_reasoning="Confirmed",
            product="TestProduct",
        )
        assert judgment.was_corrected is False

    def test_was_corrected_when_no_user_decision(self):
        """Test was_corrected returns False when no user decision."""
        judgment = Judgment(
            change_id="test#1",
            decision=Decision.INCLUDE,
            reasoning="AI thinks it's related",
            product="TestProduct",
        )
        assert judgment.was_corrected is False


class TestJudgmentCacheManager:
    """Test JudgmentCacheManager functionality."""

    def test_init_with_default_path(self, tmp_path: Path, monkeypatch):
        """Test initialization with default cache path."""
        # Set XDG_CACHE_HOME to temp path to avoid touching production cache
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        manager = JudgmentCacheManager()
        assert manager.cache_path == get_ai_cache_path()
        assert isinstance(manager.cache, JudgmentCache)

    def test_init_with_custom_path(self, tmp_path: Path):
        """Test initialization with custom cache path."""
        custom_path = tmp_path / "custom_cache.json"
        manager = JudgmentCacheManager(cache_path=custom_path)
        assert manager.cache_path == custom_path

    def test_load_nonexistent_file(self, tmp_path: Path):
        """Test loading when cache file doesn't exist."""
        cache_path = tmp_path / "nonexistent.json"
        manager = JudgmentCacheManager(cache_path=cache_path)
        assert len(manager.cache.judgments) == 0

    def test_load_valid_cache(self, tmp_path: Path):
        """Test loading a valid cache file."""
        cache_path = tmp_path / "cache.json"
        judgment = Judgment(
            change_id="test#1",
            decision=Decision.INCLUDE,
            reasoning="Test",
            product="TestProduct",
        )
        cache_data = {
            "cache_version": "1.0",
            "judgments": {"test#1": judgment.model_dump(mode="json")},
        }
        with cache_path.open("w") as f:
            json.dump(cache_data, f)

        manager = JudgmentCacheManager(cache_path=cache_path)
        assert len(manager.cache.judgments) == 1
        assert "test#1" in manager.cache.judgments

    def test_load_corrupt_json(self, tmp_path: Path):
        """Test loading a corrupted cache file falls back to empty cache."""
        cache_path = tmp_path / "corrupt.json"
        with cache_path.open("w") as f:
            f.write("{ invalid json }")

        manager = JudgmentCacheManager(cache_path=cache_path)
        assert len(manager.cache.judgments) == 0

    def test_save_creates_directories(self, tmp_path: Path):
        """Test save creates parent directories if needed."""
        cache_path = tmp_path / "deep" / "nested" / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)
        judgment = Judgment(
            change_id="test#1",
            decision=Decision.INCLUDE,
            reasoning="Test",
            product="TestProduct",
        )
        manager.add_judgment(judgment)

        assert cache_path.exists()
        assert cache_path.parent.exists()

    def test_add_judgment(self, tmp_path: Path):
        """Test adding a judgment to the cache."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        judgment = Judgment(
            change_id="test#1",
            decision=Decision.INCLUDE,
            reasoning="Test",
            product="TestProduct",
        )
        manager.add_judgment(judgment)

        assert "test#1" in manager.cache.judgments
        assert manager.cache.judgments["test#1"] == judgment
        assert cache_path.exists()

    def test_add_judgment_overwrites_existing(self, tmp_path: Path):
        """Test adding a judgment with same change_id overwrites existing."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        judgment1 = Judgment(
            change_id="test#1",
            decision=Decision.INCLUDE,
            reasoning="First",
            product="TestProduct",
        )
        manager.add_judgment(judgment1)

        judgment2 = Judgment(
            change_id="test#1",
            decision=Decision.EXCLUDE,
            reasoning="Second",
            product="TestProduct",
        )
        manager.add_judgment(judgment2)

        assert len(manager.cache.judgments) == 1
        assert manager.cache.judgments["test#1"].reasoning == "Second"

    def test_get_judgment_exists(self, tmp_path: Path):
        """Test retrieving an existing judgment."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        judgment = Judgment(
            change_id="test#1",
            decision=Decision.INCLUDE,
            reasoning="Test",
            product="TestProduct",
        )
        manager.add_judgment(judgment)

        retrieved = manager.get_judgment("test#1")
        assert retrieved is not None
        assert retrieved.change_id == "test#1"

    def test_get_judgment_not_exists(self, tmp_path: Path):
        """Test retrieving a non-existent judgment returns None."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        retrieved = manager.get_judgment("nonexistent")
        assert retrieved is None

    def test_update_with_user_decision_success(self, tmp_path: Path):
        """Test updating existing judgment with user decision."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        judgment = Judgment(
            change_id="test#1",
            decision=Decision.INCLUDE,
            reasoning="AI decision",
            product="TestProduct",
        )
        manager.add_judgment(judgment)

        success = manager.update_with_user_decision(
            "test#1", Decision.EXCLUDE, "User correction"
        )

        assert success is True
        updated = manager.get_judgment("test#1")
        assert updated.user_decision == Decision.EXCLUDE
        assert updated.user_reasoning == "User correction"
        assert updated.was_corrected is True

    def test_update_with_user_decision_not_found(self, tmp_path: Path):
        """Test updating non-existent judgment returns False."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        success = manager.update_with_user_decision(
            "nonexistent", Decision.EXCLUDE, "User correction"
        )

        assert success is False

    def test_clear_product(self, tmp_path: Path):
        """Test clearing all judgments for a product."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        # Add judgments for multiple products
        for i in range(3):
            manager.add_judgment(
                Judgment(
                    change_id=f"product1#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product1",
                )
            )

        for i in range(2):
            manager.add_judgment(
                Judgment(
                    change_id=f"product2#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product2",
                )
            )

        removed = manager.clear_product("Product1")

        assert removed == 3
        assert len(manager.cache.judgments) == 2
        assert all(j.product == "Product2" for j in manager.cache.judgments.values())

    def test_clear_product_nonexistent(self, tmp_path: Path):
        """Test clearing a non-existent product returns 0."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        removed = manager.clear_product("NonExistent")
        assert removed == 0

    def test_stats_empty_cache(self, tmp_path: Path):
        """Test stats on empty cache."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        stats = manager.stats()

        assert stats["total_judgments"] == 0
        assert stats["corrected_count"] == 0
        assert stats["correct_count"] == 0
        assert stats["correction_rate"] == 0.0
        assert stats["products"] == []
        assert stats["oldest_judgment"] is None
        assert stats["newest_judgment"] is None

    def test_stats_with_data(self, tmp_path: Path):
        """Test stats with mixed corrected and correct judgments."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        base_time = datetime.now(UTC)

        # Add 3 corrected judgments
        for i in range(3):
            j = Judgment(
                change_id=f"test#{i}",
                decision=Decision.INCLUDE,
                reasoning="AI",
                product="TestProduct",
                timestamp=base_time + timedelta(hours=i),
            )
            j.user_decision = Decision.EXCLUDE
            manager.add_judgment(j)

        # Add 2 correct judgments
        for i in range(3, 5):
            manager.add_judgment(
                Judgment(
                    change_id=f"test#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="AI",
                    product="TestProduct",
                    timestamp=base_time + timedelta(hours=i),
                )
            )

        stats = manager.stats()

        assert stats["total_judgments"] == 5
        assert stats["corrected_count"] == 3
        assert stats["correct_count"] == 2
        assert stats["correction_rate"] == 0.6
        assert "TestProduct" in stats["products"]
        assert stats["oldest_judgment"] is not None
        assert stats["newest_judgment"] is not None

    def test_stats_with_product_filter(self, tmp_path: Path):
        """Test stats filtered by product."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        # Add judgments for multiple products
        for i in range(3):
            manager.add_judgment(
                Judgment(
                    change_id=f"p1#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product1",
                )
            )

        for i in range(2):
            manager.add_judgment(
                Judgment(
                    change_id=f"p2#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product2",
                )
            )

        stats = manager.stats(product="Product1")

        assert stats["total_judgments"] == 3
        # Products list includes all products in cache, not just filtered
        assert set(stats["products"]) == {"Product1", "Product2"}

    def test_roundtrip_add_save_load(self, tmp_path: Path):
        """Test full roundtrip: add → save → new manager → load → verify."""
        cache_path = tmp_path / "cache.json"

        # First manager: add judgments
        manager1 = JudgmentCacheManager(cache_path=cache_path)
        judgment = Judgment(
            change_id="test#1",
            decision=Decision.INCLUDE,
            reasoning="Test",
            product="TestProduct",
        )
        manager1.add_judgment(judgment)

        # Second manager: load from same file
        manager2 = JudgmentCacheManager(cache_path=cache_path)

        assert len(manager2.cache.judgments) == 1
        assert "test#1" in manager2.cache.judgments
        loaded = manager2.get_judgment("test#1")
        assert loaded.change_id == judgment.change_id
        assert loaded.decision == judgment.decision
        assert loaded.reasoning == judgment.reasoning


class TestGetHistoryForPrompt:
    """Test the intelligent history selection algorithm."""

    def test_empty_cache_returns_empty_list(self, tmp_path: Path):
        """Test cold start with empty cache returns empty list."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        history = manager.get_history_for_prompt("TestProduct")

        assert history == []

    def test_respects_product_filter(self, tmp_path: Path):
        """Test that only judgments for the specified product are returned."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        # Add judgments for different products
        for i in range(5):
            manager.add_judgment(
                Judgment(
                    change_id=f"p1#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product1",
                )
            )

        for i in range(3):
            manager.add_judgment(
                Judgment(
                    change_id=f"p2#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="Product2",
                )
            )

        history = manager.get_history_for_prompt("Product1", max_entries=10)

        assert len(history) == 5
        assert all(j.product == "Product1" for j in history)

    def test_respects_max_entries_limit(self, tmp_path: Path):
        """Test that max_entries limit is respected."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        # Add 20 judgments
        for i in range(20):
            manager.add_judgment(
                Judgment(
                    change_id=f"test#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="TestProduct",
                )
            )

        history = manager.get_history_for_prompt("TestProduct", max_entries=10)

        assert len(history) == 10

    def test_achieves_75_25_split(self, tmp_path: Path):
        """Test that ~75/25 split between corrected and correct is achieved."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        # Add 20 corrected judgments
        for i in range(20):
            j = Judgment(
                change_id=f"corrected#{i}",
                decision=Decision.INCLUDE,
                reasoning="AI",
                product="TestProduct",
            )
            j.user_decision = Decision.EXCLUDE
            manager.add_judgment(j)

        # Add 20 correct judgments
        for i in range(20):
            manager.add_judgment(
                Judgment(
                    change_id=f"correct#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="AI",
                    product="TestProduct",
                )
            )

        history = manager.get_history_for_prompt(
            "TestProduct", max_entries=20, correction_ratio=0.75
        )

        corrected_count = sum(1 for j in history if j.was_corrected)
        correct_count = sum(1 for j in history if not j.was_corrected)

        # Should get 15 corrected (75%) and 5 correct (25%)
        assert corrected_count == 15
        assert correct_count == 5

    def test_fallback_when_no_corrections(self, tmp_path: Path):
        """Test fallback when corrected pool is empty."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        # Add only correct judgments (no corrections)
        for i in range(30):
            manager.add_judgment(
                Judgment(
                    change_id=f"correct#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="AI",
                    product="TestProduct",
                )
            )

        history = manager.get_history_for_prompt(
            "TestProduct", max_entries=20, correction_ratio=0.75
        )

        # Should fill all 20 slots with correct judgments
        assert len(history) == 20
        assert all(not j.was_corrected for j in history)

    def test_fallback_when_no_correct(self, tmp_path: Path):
        """Test fallback when correct pool is empty."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        # Add only corrected judgments
        for i in range(30):
            j = Judgment(
                change_id=f"corrected#{i}",
                decision=Decision.INCLUDE,
                reasoning="AI",
                product="TestProduct",
            )
            j.user_decision = Decision.EXCLUDE
            manager.add_judgment(j)

        history = manager.get_history_for_prompt(
            "TestProduct", max_entries=20, correction_ratio=0.75
        )

        # Should fill all 20 slots with corrected judgments
        assert len(history) == 20
        assert all(j.was_corrected for j in history)

    def test_most_recent_prioritized(self, tmp_path: Path):
        """Test that most recent entries are prioritized."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        base_time = datetime.now(UTC)

        # Add judgments with different timestamps
        for i in range(30):
            manager.add_judgment(
                Judgment(
                    change_id=f"test#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="Test",
                    product="TestProduct",
                    timestamp=base_time + timedelta(hours=i),
                )
            )

        history = manager.get_history_for_prompt("TestProduct", max_entries=10)

        # Should get the 10 most recent (highest indices)
        timestamps = [j.timestamp for j in history]
        # All timestamps should be from the later entries
        assert all(ts >= base_time + timedelta(hours=20) for ts in timestamps)

    def test_partial_pools_handled_correctly(self, tmp_path: Path):
        """Test handling when one pool has fewer items than target."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        # Add 5 corrected (target is 15)
        for i in range(5):
            j = Judgment(
                change_id=f"corrected#{i}",
                decision=Decision.INCLUDE,
                reasoning="AI",
                product="TestProduct",
            )
            j.user_decision = Decision.EXCLUDE
            manager.add_judgment(j)

        # Add 20 correct (target is 5)
        for i in range(20):
            manager.add_judgment(
                Judgment(
                    change_id=f"correct#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="AI",
                    product="TestProduct",
                )
            )

        history = manager.get_history_for_prompt(
            "TestProduct", max_entries=20, correction_ratio=0.75
        )

        corrected_count = sum(1 for j in history if j.was_corrected)
        correct_count = sum(1 for j in history if not j.was_corrected)

        # Should get 5 corrected (all available) and 15 correct (filling remaining)
        assert corrected_count == 5
        assert correct_count == 15
        assert len(history) == 20

    def test_interleaving_for_variety(self, tmp_path: Path):
        """Test that results are interleaved for variety."""
        cache_path = tmp_path / "cache.json"
        manager = JudgmentCacheManager(cache_path=cache_path)

        # Add enough of each type
        for i in range(10):
            j = Judgment(
                change_id=f"corrected#{i}",
                decision=Decision.INCLUDE,
                reasoning="AI",
                product="TestProduct",
            )
            j.user_decision = Decision.EXCLUDE
            manager.add_judgment(j)

        for i in range(10):
            manager.add_judgment(
                Judgment(
                    change_id=f"correct#{i}",
                    decision=Decision.INCLUDE,
                    reasoning="AI",
                    product="TestProduct",
                )
            )

        history = manager.get_history_for_prompt(
            "TestProduct", max_entries=10, correction_ratio=0.75
        )

        # With 75/25 ratio and 10 entries, we should get approximately:
        # 7-8 corrected and 2-3 correct, interleaved
        # The interleaving pattern should not have all of one type together
        corrected_indices = [i for i, j in enumerate(history) if j.was_corrected]

        # Check that corrected judgments are not all grouped together
        # (they should be somewhat distributed)
        if len(corrected_indices) > 1:
            gaps = [
                corrected_indices[i + 1] - corrected_indices[i]
                for i in range(len(corrected_indices) - 1)
            ]
            # At least some gaps should be > 1 (meaning interleaving)
            assert any(gap > 1 for gap in gaps) or len(corrected_indices) == len(
                history
            )
