"""Integration with psss/did SDK for fetching merged code contributions.

This module provides integration with the did SDK to fetch merged pull requests
and merge requests from GitHub and GitLab for IP tax reporting purposes.
"""

import io
import re
from contextlib import redirect_stdout
from datetime import date

import did.base
import did.cli

from iptax.models import Change, Repository, Settings


class DidIntegrationError(Exception):
    """Error during did integration."""

    pass


def fetch_changes(
    settings: Settings,
    start_date: date,
    end_date: date,
) -> list[Change]:
    """Fetch changes from did SDK for the given date range.

    Args:
        settings: User settings including did configuration
        start_date: Start of reporting period (inclusive)
        end_date: End of reporting period (inclusive)

    Returns:
        List of Change objects

    Raises:
        DidIntegrationError: If fetching fails
    """
    try:
        # Load did configuration
        config_path = str(settings.did.get_config_path())
        did.base.Config(path=config_path)
    except Exception as e:
        raise DidIntegrationError(
            f"Failed to load did config from {config_path}: {e}"
        ) from e

    # Fetch changes from all configured providers
    all_changes: list[Change] = []

    for provider_name in settings.did.providers:
        try:
            changes = _fetch_provider_changes(provider_name, start_date, end_date)
            all_changes.extend(changes)
        except Exception as e:
            raise DidIntegrationError(
                f"Failed to fetch changes from provider '{provider_name}': {e}"
            ) from e

    return all_changes


def _fetch_provider_changes(
    provider_name: str,
    start_date: date,
    end_date: date,
) -> list[Change]:
    """Fetch changes from a specific provider using did.cli.main().

    This replicates what did.cli.main() does but returns POPOs instead of
    printing to screen. Suppresses did's stdout output.

    Args:
        provider_name: Provider name from did config (e.g., "github.com", "gitlab.cee")
        start_date: Start of reporting period (inclusive)
        end_date: End of reporting period (inclusive)

    Returns:
        List of Change objects from this provider

    Raises:
        DidIntegrationError: If provider is not found or fetching fails
    """
    # Build the did command-line options
    # Use the section name directly as did uses it as the option prefix

    # Determine the correct option name based on provider type
    provider_type = _determine_provider_type(provider_name)
    if provider_type == "github":
        option_suffix = "pull-requests-merged"
    else:  # gitlab
        option_suffix = "merge-requests-merged"

    option = (
        f"--{provider_name}-{option_suffix} "
        f"--since {start_date.isoformat()} "
        f"--until {end_date.isoformat()}"
    )

    try:
        # Suppress did's stdout output (it prints the report)
        # but still get the POPOs it returns
        with redirect_stdout(io.StringIO()):
            # Call did.cli.main() to get stats (POPOs)
            result = did.cli.main(option.split())

        if not result or not result[0]:
            return []

        user_stats = result[0][0]
        if not hasattr(user_stats, "stats") or not user_stats.stats:
            return []

        # Get the provider stats group
        provider_stats_group = user_stats.stats[0]
        if not hasattr(provider_stats_group, "stats") or not provider_stats_group.stats:
            return []

        # Find the merged PRs/MRs stats
        merged_stats = None
        for stat in provider_stats_group.stats:
            if (
                hasattr(stat, "stats")
                and "merged" in stat.__class__.__name__.lower()
                and (
                    "pull" in stat.__class__.__name__.lower()
                    or "merge" in stat.__class__.__name__.lower()
                )
            ):
                merged_stats = stat.stats
                break

        if not merged_stats:
            return []

        # Convert did stats to Change objects
        changes: list[Change] = []
        for stat in merged_stats:
            change = _convert_to_change(stat, provider_name)
            if change:
                changes.append(change)
    except Exception as e:
        raise DidIntegrationError(f"Failed to call did.cli.main(): {e}") from e
    else:
        return changes


def _convert_to_change(stat: object, provider_name: str) -> Change | None:
    """Convert a did stat object into a Change object.

    Args:
        stat: A did stat object (Issue or MergeRequest from did plugins)
        provider_name: Provider name for host determination

    Returns:
        Change object or None if conversion fails
    """
    try:
        # Access object attributes directly (no parsing!)
        # did's Issue/MergeRequest objects have: owner, project, id, title, data
        owner = getattr(stat, "owner", None)
        project = getattr(stat, "project", None)
        number = int(getattr(stat, "id", 0))
        title = getattr(stat, "title", "")

        if not all([owner, project, number, title]):
            return None

        # Clean emoji from title
        title = _clean_emoji(title)

        # Build repository path
        repo_path = f"{owner}/{project}"

        # Determine provider type from host
        provider_type = _determine_provider_type(provider_name)

        # Create Repository object
        repository = Repository(
            host=provider_name,
            path=repo_path,
            provider_type=provider_type,
        )

        # Create Change object (merged_at not available from did stats)
        return Change(
            title=title,
            repository=repository,
            number=number,
            merged_at=None,
        )

    except Exception:
        return None


def _clean_emoji(title: str) -> str:
    """Remove GitHub emoji codes from title.

    Removes patterns like :rocket:, :bug:, etc.

    Args:
        title: Original title with potential emoji codes

    Returns:
        Title with emoji codes removed and whitespace cleaned
    """
    # Remove emoji codes (e.g., :rocket:, :bug:, :sparkles:)
    cleaned = re.sub(r":[a-z_]+:", "", title)

    # Strip leading/trailing whitespace and collapse multiple spaces
    return " ".join(cleaned.split())


def _determine_provider_type(host: str) -> str:
    """Determine provider type from host name.

    Args:
        host: Repository host (e.g., "github.com", "gitlab.example.org")

    Returns:
        Provider type: "github" or "gitlab"
    """
    host_lower = host.lower()
    if "github" in host_lower:
        return "github"
    if "gitlab" in host_lower:
        return "gitlab"
    # Default to gitlab if can't determine
    return "gitlab"
