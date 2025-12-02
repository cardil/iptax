# AI Judgment Cache Design - Intelligent History Selection

## Table of Contents

1. [Purpose & Philosophy](#purpose--philosophy)
2. [Selection Algorithm](#selection-algorithm)
3. [Model Updates](#model-updates)
4. [Cache Manager API](#cache-manager-api)
5. [Edge Cases](#edge-cases)
6. [Implementation Notes](#implementation-notes)

---

## Purpose & Philosophy

### What the Cache Is NOT For

The AI judgment cache is **NOT** designed for:

- **Deduplication** - Each monthly report has different PRs/MRs; we don't need to avoid re-judging the same changes.
- **Cost Reduction via Skipping** - We perform ONE batch request per run anyway, so skipping individual judgments doesn't save API calls.

### What the Cache IS For

The cache provides **learning context** to the AI. By including past decisions (especially user corrections) in the prompt, we help the AI:

1. **Learn from Mistakes** - When the AI was wrong and the user corrected it, the AI sees what it misunderstood.
2. **Reinforce Good Patterns** - When the AI was correct, it sees patterns that worked well.
3. **Understand Product Scope** - Past decisions help define what "related to product X" actually means for this specific user.

### Key Insight

User corrections are **more valuable** than correct AI decisions because they teach the AI what it got wrong. A prompt full of correct decisions provides less learning signal than one with corrections and explanations.

---

## Selection Algorithm

### Overview

We can't naively include all past judgments - this wastes context tokens and may include irrelevant or outdated decisions. Instead, we use an intelligent selection strategy:

```
┌─────────────────────────────────────────────────────────────┐
│                    Selection Parameters                      │
├─────────────────────────────────────────────────────────────┤
│  max_entries: 20         # Total entries to include         │
│  correction_ratio: 0.75  # Target 75% corrected decisions   │
│  product: "Acme Fungear" # Filter by product                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │  Step 1: Filter by Product    │
              │  Only same-product judgments  │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │  Step 2: Separate Pools       │
              │  - Corrected decisions        │
              │  - Correct AI decisions       │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │  Step 3: Sort by Recency      │
              │  Newest first in each pool    │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │  Step 4: Allocate Slots       │
              │  - 75% for corrections        │
              │  - 25% for correct AI         │
              │  - Fallback if pool too small │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │  Step 5: Final Selection      │
              │  Interleave for variety       │
              └───────────────────────────────┘
```

### Detailed Algorithm

```python
def get_history_for_prompt(
    self,
    product: str,
    max_entries: int = 20,
    correction_ratio: float = 0.75
) -> list[Judgment]:
    """
    Select optimal history entries for AI prompt context.

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
        j for j in self.judgments.values()
        if j.product == product
    ]

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
            extra_corrections = min(remaining_slots, len(corrected) - actual_corrections)
            actual_corrections += extra_corrections

    # Step 5: Select and combine
    selected_corrections = corrected[:actual_corrections]
    selected_correct = correct[:actual_correct]

    # Interleave for variety (correction, correct, correction, ...)
    result = []
    corr_iter = iter(selected_corrections)
    correct_iter = iter(selected_correct)

    # Alternate, prioritizing corrections
    while len(result) < max_entries:
        try:
            result.append(next(corr_iter))
        except StopIteration:
            pass

        if len(result) < max_entries:
            try:
                result.append(next(correct_iter))
            except StopIteration:
                pass

        # Break if both exhausted
        if len(result) == actual_corrections + actual_correct:
            break

    return result
```

### Rationale for 75/25 Split

| Ratio | Corrections | Correct AI | Rationale |
|-------|-------------|------------|-----------|
| 100/0 | 20 | 0 | Only errors - AI may become too conservative |
| 75/25 | 15 | 5 | **Balanced** - Strong learning signal with positive reinforcement |
| 50/50 | 10 | 10 | Even split - Dilutes correction signal |
| 25/75 | 5 | 15 | Mostly correct - Limited learning from mistakes |

The 75/25 split provides:
- **Strong correction signal** - AI sees many examples of what it got wrong
- **Positive reinforcement** - AI also sees patterns that worked
- **Balanced perspective** - Avoids making AI overly conservative or liberal

---

## Model Updates

### Current Model Analysis

The existing [`Judgment`](../src/iptax/ai/models.py:21) model already tracks:

```python
class Judgment(BaseModel):
    change_id: str          # e.g., "owner/repo#123"
    decision: AIDecision    # AI's original decision
    reasoning: str          # AI's reasoning
    user_decision: AIDecision | None   # User override (if any)
    user_reasoning: str | None         # User's reasoning for override
    product: str            # Product name
    timestamp: datetime     # When judgment was made
```

### Proposed Addition: `was_corrected` Property

Add a computed property to detect if the AI was corrected:

```python
@property
def was_corrected(self) -> bool:
    """Return True if user overrode the AI's decision."""
    return self.user_decision is not None and self.user_decision != self.decision
```

This property:
- Returns `True` if user provided a different decision than AI
- Returns `False` if user agreed (same decision) or didn't override (None)
- Is computed, not stored, so no schema migration needed

### No Schema Changes Required

The current schema already supports all needed data:
- **Correction detection** via comparing `decision` vs `user_decision`
- **Product filtering** via `product` field
- **Recency sorting** via `timestamp` field

The only change is adding the `was_corrected` property for convenience.

---

## Cache Manager API

### JudgmentCacheManager Class

```python
class JudgmentCacheManager:
    """Manages the AI judgment cache with intelligent history selection."""

    def __init__(self, cache_path: Path | None = None):
        """
        Initialize cache manager.

        Args:
            cache_path: Custom cache path, defaults to ~/.cache/iptax/ai_cache.json
        """
        ...

    def load(self) -> JudgmentCache:
        """Load cache from disk, creating empty cache if not exists."""
        ...

    def save(self, cache: JudgmentCache) -> None:
        """Persist cache to disk."""
        ...

    def get_history_for_prompt(
        self,
        product: str,
        max_entries: int = 20,
        correction_ratio: float = 0.75
    ) -> list[Judgment]:
        """
        Select optimal history for AI prompt context.

        Args:
            product: Filter by product name
            max_entries: Maximum entries to return (default: 20)
            correction_ratio: Target ratio of corrections vs correct (default: 0.75)

        Returns:
            List of Judgment objects optimized for learning
        """
        ...

    def add_judgment(self, judgment: Judgment) -> None:
        """Add or update a judgment in the cache."""
        ...

    def update_with_user_decision(
        self,
        change_id: str,
        user_decision: AIDecision,
        user_reasoning: str | None = None
    ) -> None:
        """Record user's override of an AI decision."""
        ...

    def get_judgment(self, change_id: str) -> Judgment | None:
        """Retrieve a specific judgment by change_id."""
        ...

    def clear_product(self, product: str) -> int:
        """Remove all judgments for a product. Returns count removed."""
        ...

    def stats(self, product: str | None = None) -> dict:
        """
        Get cache statistics.

        Returns:
            {
                "total_judgments": 150,
                "corrected_count": 45,
                "correct_count": 105,
                "correction_rate": 0.30,
                "products": ["Acme Fungear", "Other Product"],
                "oldest_judgment": "2024-01-15T...",
                "newest_judgment": "2024-12-01T..."
            }
        """
        ...
```

### Usage Example

```python
from iptax.ai.cache import JudgmentCacheManager
from iptax.ai.models import Judgment, AIDecision

# Initialize manager
cache_mgr = JudgmentCacheManager()

# Get history for prompt building
history = cache_mgr.get_history_for_prompt(
    product="Acme Fungear",
    max_entries=20,
    correction_ratio=0.75
)

# Build prompt with history
prompt = build_ai_prompt(
    product="Acme Fungear",
    history=history,
    current_changes=changes_to_judge
)

# After AI response, record judgments
for item in ai_response.judgments:
    judgment = Judgment(
        change_id=item.change_id,
        decision=item.decision,
        reasoning=item.reasoning,
        product="Acme Fungear"
    )
    cache_mgr.add_judgment(judgment)

# After user review, record corrections
for change_id, user_choice in user_overrides.items():
    cache_mgr.update_with_user_decision(
        change_id=change_id,
        user_decision=user_choice.decision,
        user_reasoning=user_choice.reasoning
    )
```

---

## Edge Cases

### 1. Cold Start (No History)

**Scenario:** First run, cache is empty.

**Behavior:**
- `get_history_for_prompt()` returns empty list `[]`
- AI makes decisions without historical context
- Prompt includes note: "No previous judgments available"
- All decisions are recorded for future runs

**Mitigation:** The AI prompt template should handle empty history gracefully.

### 2. All AI Decisions Were Correct

**Scenario:** User never corrected any AI decisions.

**Behavior:**
- `corrected` pool is empty
- `correction_ratio` cannot be satisfied
- Algorithm falls back to using all slots for `correct` pool
- Returns up to `max_entries` correct decisions

**Example:** With `max_entries=20` and `correction_ratio=0.75`:
- Target: 15 corrections, 5 correct
- Available: 0 corrections, 50 correct
- Result: 0 corrections, 20 correct (fill remaining slots)

### 3. All AI Decisions Were Wrong

**Scenario:** User corrected every AI decision.

**Behavior:**
- `correct` pool is empty
- All slots filled with corrections
- This is actually ideal for learning!

**Example:** With `max_entries=20` and `correction_ratio=0.75`:
- Target: 15 corrections, 5 correct
- Available: 100 corrections, 0 correct
- Result: 20 corrections, 0 correct (fill remaining slots)

### 4. Very Old Entries vs Recent

**Scenario:** Cache has entries spanning years.

**Behavior:**
- Algorithm sorts by `timestamp` descending (newest first)
- Old entries naturally deprioritized
- No explicit age cutoff (recency sorting sufficient)

**Rationale:** Recent decisions are more relevant because:
- Product scope may have evolved
- User's understanding may have changed
- Coding patterns may have shifted

### 5. Multi-Product Cache

**Scenario:** User works on multiple products.

**Behavior:**
- History is always filtered by `product` parameter
- Each product has independent history
- No cross-product contamination

**Example:**
```python
# Only returns "Acme Fungear" judgments
history = cache_mgr.get_history_for_prompt(product="Acme Fungear")
```

### 6. User Agrees with AI (Same Decision)

**Scenario:** User reviews AI decision and explicitly confirms it's correct.

**Behavior:**
- If `user_decision == decision`, `was_corrected` returns `False`
- Explicit confirmation counts as "correct AI decision"
- This is intentional - we only want actual corrections to be prioritized

### 7. Cache Corruption or Version Mismatch

**Scenario:** Cache file is corrupted or from incompatible version.

**Behavior:**
- `load()` catches parsing errors
- Falls back to empty cache with warning
- `cache_version` field allows future migrations

---

## Implementation Notes

### File Format

Use JSON for cache storage (already defined in architecture):

```json
{
  "cache_version": "1.0",
  "judgments": {
    "github.com/owner/repo#123": {
      "change_id": "github.com/owner/repo#123",
      "decision": "INCLUDE",
      "reasoning": "Implements core feature",
      "user_decision": "EXCLUDE",
      "user_reasoning": "Actually internal tooling",
      "product": "Acme Fungear",
      "timestamp": "2024-11-15T10:30:00Z"
    }
  }
}
```

### Cache Location

- **Default:** `~/.cache/iptax/ai_cache.json`
- **Configurable:** Via `cache_path` parameter

### Performance Considerations

- Cache is loaded once at startup
- Selection algorithm is O(n log n) due to sorting
- For typical cache sizes (<1000 entries), this is negligible

---

## Summary

| Component | Description |
|-----------|-------------|
| **Purpose** | Provide learning context to AI, NOT deduplication |
| **Selection Strategy** | 75% corrections / 25% correct, recency-weighted |
| **Model Change** | Add `was_corrected` property (no schema change) |
| **Key Method** | `get_history_for_prompt(product, max_entries, correction_ratio)` |
| **Edge Case Handling** | Graceful fallback for empty pools, cold start, etc. |
