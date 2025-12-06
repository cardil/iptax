"""Mock data generators for testing CLI flows.

TODO(ksuszyns): DELETE this file when AI review is integrated into report command.
"""

from iptax.models import Change, Decision, Judgment, Repository


def generate_mock_changes(count: int = 15) -> list[Change]:
    """Generate mock changes for testing.

    Args:
        count: Number of mock changes to generate

    Returns:
        List of mock changes with realistic titles
    """
    mock_titles = [
        "Fix memory leak in parser module when processing large JSON documents",
        "Add Go 1.22 support and update all dependencies to latest versions",
        "Implement feature flag system for gradual rollout of new authentication",
        "Refactor database connection pooling to improve performance under load",
        "Add comprehensive logging for debugging authentication failures",
        "Update CI/CD pipeline to use new build system and caching strategy",
        "Fix race condition in concurrent worker pool initialization",
        "Implement retry logic with exponential backoff for API calls",
        "Add metrics collection and monitoring dashboard for system health",
        "Refactor error handling to provide better user feedback messages",
        "Migrate legacy API endpoints to new GraphQL schema",
        "Add unit tests for authentication middleware components",
        "Optimize SQL queries in reporting module for large datasets",
        "Implement WebSocket support for real-time notifications",
        "Add dark mode support to admin dashboard interface",
    ]

    return [
        Change(
            title=mock_titles[i % len(mock_titles)],
            repository=Repository(
                host="github.com",
                path="knative/serving" if i % 2 == 0 else "internal/tooling",
                provider_type="github",
            ),
            number=1000 + i * 10,
        )
        for i in range(count)
    ]


def generate_mock_judgments(
    changes: list[Change],
    product: str = "Test Product",
) -> list[Judgment]:
    """Generate mock judgments for testing.

    Generates a variety of decisions:
    - Every 5th change is UNCERTAIN
    - Every 3rd change (not uncertain) is EXCLUDE
    - Rest are INCLUDE

    Args:
        changes: List of changes to generate judgments for
        product: Product name for judgments

    Returns:
        List of mock judgments
    """
    judgments = []
    uncertain_interval = 5
    exclude_interval = 3

    for i, change in enumerate(changes):
        if i % uncertain_interval == uncertain_interval - 1:
            decision = Decision.UNCERTAIN
            reasoning = "Cannot determine if this belongs to the product"
        elif i % exclude_interval == 0:
            decision = Decision.EXCLUDE
            reasoning = "Unrelated to the product"
        else:
            decision = Decision.INCLUDE
            reasoning = "Directly contributes to the product"

        judgments.append(
            Judgment(
                change_id=change.get_change_id(),
                decision=decision,
                reasoning=reasoning,
                product=product,
                url=change.get_url(),
                description=change.title,
                ai_provider="mock/test",
            )
        )

    return judgments
