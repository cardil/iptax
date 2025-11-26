"""Integration with psss/did SDK for fetching merged code contributions.

This module provides integration with the did SDK to fetch merged pull requests
and merge requests from GitHub and GitLab for IP tax reporting purposes.
"""

import io
import logging
import re
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from typing import Literal, cast

import did.base
import did.cli
from did.plugins.github import Issue

from iptax.models import Change, Repository, Settings

logger = logging.getLogger(__name__)

# Constants for stat detection
MERGED_STAT_KEYWORDS = ("merged", "pull", "merge")


class DidIntegrationError(Exception):
    """Error during did integration."""


class InvalidStatDataError(Exception):
    """Data validation error when converting did stat to Change object."""


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
    provider_type = _determine_provider_type(provider_name)
    option_suffix = (
        "pull-requests-merged" if provider_type == "github" else "merge-requests-merged"
    )

    option = (
        f"--{provider_name}-{option_suffix} "
        f"--since {start_date.isoformat()} "
        f"--until {end_date.isoformat()}"
    )

    try:
        # Capture did's stdout and stderr (it prints the report and errors)
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        # Redirect both stdout and stderr
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Call did.cli.main() to get stats (POPOs)
            result = did.cli.main(option.split())

        # Check for errors in stderr
        _check_did_stderr(
            stderr_content=stderr_capture.getvalue(), provider_name=provider_name
        )

        # Extract merged stats from result
        merged_stats = _extract_merged_stats(result)

        # Convert did stats to Change objects
        return _convert_stats_to_changes(merged_stats, provider_name)

    except DidIntegrationError:
        # Re-raise our own exceptions
        raise
    except Exception as e:
        raise DidIntegrationError(f"Failed to call did.cli.main(): {e}") from e


def _extract_merged_stats(result: object) -> list[Issue]:
    """Extract merged PR/MR stats from did CLI result.

    Uses object type with strict runtime validation. Returns empty list ONLY when
    input is an empty list. All other cases raise exceptions.

    Args:
        result: Result from did.cli.main()

    Returns:
        List of Issue objects from did SDK (empty list only if input is empty list)

    Raises:
        DidIntegrationError: For any unexpected structure or None values
    """
    # Validate and extract user stats
    user_stats = _validate_and_extract_user_stats(result)

    # Validate user stats structure
    if not hasattr(user_stats, "stats"):
        raise DidIntegrationError(
            f"User stats object (type: {type(user_stats).__name__}) "
            "missing 'stats' attribute"
        )

    if not isinstance(user_stats.stats, list):
        raise DidIntegrationError(
            f"User stats.stats is not a list (type: {type(user_stats.stats).__name__})"
        )

    # Empty user stats means no activity in the period - this is valid
    if len(user_stats.stats) == 0:
        return []

    # Validate and extract provider stats
    provider_stats_group = user_stats.stats[0]
    if not hasattr(provider_stats_group, "stats"):
        raise DidIntegrationError("Provider stats group missing 'stats' attribute")

    if not isinstance(provider_stats_group.stats, list):
        raise DidIntegrationError("Provider stats.stats is not a list")

    if len(provider_stats_group.stats) == 0:
        return []

    # Find the merged PRs/MRs stats - MUST exist since we requested it
    for stat in provider_stats_group.stats:
        if _is_merged_stat(stat):
            if not hasattr(stat, "stats"):
                raise DidIntegrationError(
                    "Merged stat object missing 'stats' attribute"
                )
            # Cast to list[Issue] - did SDK uses Issue type for both PRs and MRs
            return cast(list[Issue], stat.stats)

    # We requested merged stats in CLI but didn't find them - error
    raise DidIntegrationError(
        "Merged stats section not found in did result - "
        "expected pull-requests-merged or merge-requests-merged"
    )


def _validate_and_extract_user_stats(result: object) -> object:
    """Validate did result structure and extract user stats.

    Args:
        result: Result from did.cli.main()

    Returns:
        User stats object

    Raises:
        DidIntegrationError: For any invalid structure
    """
    # Validate result is a tuple (did.cli.main returns a tuple)
    if not isinstance(result, tuple):
        raise DidIntegrationError(
            f"Expected tuple from did.cli.main(), got {type(result).__name__}"
        )

    # Empty tuple means did CLI failed - should always have structure
    if len(result) == 0:
        raise DidIntegrationError(
            "Empty result from did.cli.main() - did execution may have failed"
        )

    # Validate first element
    if not result[0]:
        raise DidIntegrationError("First element of did result is None or falsy")

    # Extract users list - first element should be a list
    try:
        users_list = result[0] if isinstance(result[0], list) else list(result[0])
    except TypeError as e:
        raise DidIntegrationError(
            f"First element of did result is not iterable: {type(result[0]).__name__}"
        ) from e
    if len(users_list) == 0:
        raise DidIntegrationError("Users list in did result is empty")

    return users_list[0]


def _is_merged_stat(stat: object) -> bool:
    """Check if a stat object represents merged PRs/MRs.

    Args:
        stat: Stat object to check

    Returns:
        True if this is a merged PR/MR stat
    """
    if not hasattr(stat, "stats"):
        return False

    class_name_lower = stat.__class__.__name__.lower()
    return MERGED_STAT_KEYWORDS[0] in class_name_lower and (
        MERGED_STAT_KEYWORDS[1] in class_name_lower
        or MERGED_STAT_KEYWORDS[2] in class_name_lower
    )


def _convert_stats_to_changes(stats: list[Issue], provider_name: str) -> list[Change]:
    """Convert did stats to Change objects.

    Args:
        stats: List of Issue objects from did SDK (used for both PRs and MRs)
        provider_name: Provider name for changes

    Returns:
        List of successfully converted Change objects
    """
    changes: list[Change] = []
    for stat in stats:
        try:
            change = _convert_to_change(stat, provider_name)
            changes.append(change)
        except InvalidStatDataError as e:
            # Log expected data validation issues as warnings
            stat_type = type(stat).__name__
            logger.warning(
                "Skipping invalid stat from %s: %s (stat type: %s, repr: %r)",
                provider_name,
                e,
                stat_type,
                stat,
            )
            continue
    return changes


def _check_did_stderr(stderr_content: str, provider_name: str) -> None:
    """Check did's stderr output for errors.

    Args:
        stderr_content: Content from stderr
        provider_name: Provider name for error messages

    Raises:
        DidIntegrationError: If stderr contains error indicators
    """
    if not stderr_content:
        return

    logger.warning(
        "did CLI produced stderr output for provider %s: %s",
        provider_name,
        stderr_content,
    )

    # If stderr contains error indicators, raise exception
    if any(
        keyword in stderr_content.lower() for keyword in ["error", "fail", "exception"]
    ):
        raise DidIntegrationError(
            f"did CLI reported errors for provider '{provider_name}': {stderr_content}"
        )


def _convert_to_change(stat: object, provider_name: str) -> Change:
    """Convert a did stat object into a Change object.

    Args:
        stat: A did stat object (Issue or MergeRequest from did plugins)
        provider_name: Provider name for host determination

    Returns:
        Change object

    Raises:
        InvalidStatDataError: If required data is missing or invalid
    """
    # Access object attributes directly (no parsing!)
    # did's Issue/MergeRequest objects have: owner, project, id, title, data
    owner = getattr(stat, "owner", None)
    project = getattr(stat, "project", None)
    id_value = getattr(stat, "id", None)
    title = getattr(stat, "title", "")

    # Validate required fields
    if not owner:
        raise InvalidStatDataError("Missing owner field")
    if not project:
        raise InvalidStatDataError(f"Missing project field for owner '{owner}'")
    if not id_value:
        raise InvalidStatDataError(f"Missing id field for {owner}/{project}")
    if not title:
        raise InvalidStatDataError(
            f"Missing title field for {owner}/{project}#{id_value}"
        )

    # Convert id to integer
    try:
        number = int(id_value)
    except (ValueError, TypeError) as e:
        raise InvalidStatDataError(
            f"Invalid id '{id_value}' for {owner}/{project}: {e}"
        ) from e

    if number <= 0:
        raise InvalidStatDataError(f"Non-positive id {number} for {owner}/{project}")

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


def _clean_emoji(title: str) -> str:
    """Remove GitHub emoji codes from title.

    Removes patterns like :rocket:, :bug:, :100:, :+1:, etc.

    Args:
        title: Original title with potential emoji codes

    Returns:
        Title with emoji codes removed and whitespace cleaned
    """
    # Remove emoji codes (e.g., :rocket:, :bug:, :sparkles:, :100:, :+1:)
    # Matches word characters, digits, plus signs, and hyphens
    cleaned = re.sub(r":[\w+-]+:", "", title, flags=re.IGNORECASE)

    # Strip leading/trailing whitespace and collapse multiple spaces
    return " ".join(cleaned.split())


def _determine_provider_type(host: str) -> Literal["github", "gitlab"]:
    """Determine provider type from host name.

    Args:
        host: Repository host (e.g., "github.com", "gitlab.example.org")

    Returns:
        Provider type: "github" or "gitlab"

    Raises:
        DidIntegrationError: If provider type cannot be determined from host
    """
    host_lower = host.lower()
    if "github" in host_lower:
        return "github"
    if "gitlab" in host_lower:
        return "gitlab"

    # Cannot determine provider type - raise error to avoid silent misconfigurations
    raise DidIntegrationError(
        f"Cannot determine provider type from host '{host}'. "
        f"Host name must contain 'github' or 'gitlab'"
    )
