"""Prompt building for AI judgment requests.

This module provides functions to build prompts for AI-based filtering of
code changes (PRs/MRs) to determine relevance to a product.
"""

from iptax.models import Change

from .models import Judgment


def build_judgment_prompt(
    product: str,
    changes: list[Change],
    history: list[Judgment],
) -> str:
    """Build the batch prompt for AI judgment.

    Creates a prompt that asks the AI to judge whether code changes belong
    to the specified product. Includes previous judgment history to help the
    AI learn from past decisions and corrections.

    Args:
        product: The product name to judge changes against
        changes: List of changes to evaluate
        history: Previous judgments (including corrected ones) for context

    Returns:
        Formatted prompt with YAML delimiters for easy extraction

    Example:
        >>> from iptax.models import Change, Repository
        >>> changes = [
        ...     Change(
        ...         title="Fix memory leak",
        ...         repository=Repository(
        ...             host="github.com",
        ...             path="org/repo",
        ...             provider_type="github"
        ...         ),
        ...         number=123,
        ...     )
        ... ]
        >>> prompt = build_judgment_prompt("MyProduct", changes, [])
    """
    prompt_parts = [
        f"You are judging whether code changes belong to the product: {product}",
        "",
    ]

    # Add history section if available
    if history:
        prompt_parts.extend(
            [
                "## Previous Judgment History (for learning)",
                "",
                "These are examples of past decisions, including corrections. "
                "Use them to understand what belongs to this product:",
                "",
            ]
        )

        for judgment in history:
            decision_marker = ""
            if judgment.was_corrected:
                decision_marker = (
                    f" (corrected from {judgment.decision.value} to "
                    f"{judgment.final_decision.value})"
                )
            else:
                decision_marker = f" (confirmed {judgment.final_decision.value})"

            prompt_parts.extend(
                [
                    f"- {judgment.change_id}{decision_marker}",
                    f"  Decision: {judgment.final_decision.value}",
                ]
            )

            # Show both AI reasoning and user reasoning for corrections
            if judgment.was_corrected and judgment.user_reasoning:
                prompt_parts.extend(
                    [
                        f"  AI reasoning: {judgment.reasoning}",
                        f"  User correction: {judgment.user_reasoning}",
                    ]
                )
            else:
                # Just show the final reasoning (either user's or AI's)
                prompt_parts.append(
                    f"  Reasoning: {judgment.user_reasoning or judgment.reasoning}"
                )

            prompt_parts.append("")

    # Add changes to judge
    prompt_parts.extend(
        [
            "## Current Changes to Judge",
            "",
            "Evaluate each change and decide if it belongs to the product:",
            "",
        ]
    )

    for change in changes:
        prompt_parts.extend(
            [
                f"- {change.get_change_id()}",
                f"  Title: {change.title}",
                f"  URL: {change.get_url()}",
                "",
            ]
        )

    # Add response format
    prompt_parts.extend(
        [
            "## Response Format",
            "",
            "Respond with YAML inside code blocks:",
            "",
            "```yaml",
            "judgments:",
            '    - change_id: "host.com/owner/repo#123"  # EXACT from above',
            "      decision: INCLUDE  # or EXCLUDE or UNCERTAIN",
            "      reasoning: Brief explanation",
            "```",
            "",
            "IMPORTANT: The change_id must match EXACTLY as shown above",
            "(including host/path#number).",
            "",
            "Decisions:",
            "- INCLUDE: Change directly contributes to the product",
            "- EXCLUDE: Change is unrelated to the product",
            "- UNCERTAIN: Cannot determine with confidence",
        ]
    )

    return "\n".join(prompt_parts)
