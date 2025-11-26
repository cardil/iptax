#!/usr/bin/env python3
"""Setup minimal did configuration for CI testing.

This script creates a minimal did config file that allows e2e tests to run
in CI environment. It uses GitHub's GITHUB_TOKEN for authentication and
requires DID_LOGIN to specify which user's PRs to fetch.
"""

import os
import sys
from pathlib import Path


def create_test_did_config(
    config_path: Path, github_token: str, github_login: str, github_email: str
) -> None:
    """Create a minimal test did config file.

    Args:
        config_path: Path where the did config should be created
        github_token: GitHub token for authentication
        github_login: GitHub username whose PRs should be fetched
        github_email: Email address for did general config
    """
    # Create parent directory if it doesn't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Create minimal did config with github.com section
    config_content = f"""[general]
email = {github_email}
width = 79

[github.com]
type = github
url = https://api.github.com/
token = {github_token}
login = {github_login}
"""

    # Write the config file
    config_path.write_text(config_content, encoding="utf-8")

    # Set file permissions to 600 (owner read/write only)
    config_path.chmod(0o600)

    print(f"✓ Created test did config at {config_path}")
    print(f"✓ Config will fetch PRs for GitHub user: {github_login}")
    print(f"✓ Config contains [github.com] section for e2e tests")


def main() -> int:
    """Main entry point."""
    # Get GitHub token from environment
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("ERROR: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        print(
            "This script requires a GitHub token for did authentication",
            file=sys.stderr,
        )
        return 1

    # Get GitHub login - required to know which user's PRs to fetch
    github_login = os.environ.get("DID_LOGIN")
    if not github_login:
        print("ERROR: DID_LOGIN environment variable not set", file=sys.stderr)
        print(
            "This variable must specify the GitHub username whose PRs to fetch",
            file=sys.stderr,
        )
        print("\nExample: export DID_LOGIN=cardil", file=sys.stderr)
        return 1

    # Get email (optional, defaults to login@users.noreply.github.com)
    github_email = os.environ.get(
        "DID_EMAIL", f"{github_login}@users.noreply.github.com"
    )

    # Determine config path (allow override via DID_CONFIG env var)
    config_path_str = os.environ.get("DID_CONFIG")
    if config_path_str:
        config_path = Path(config_path_str).expanduser()
    else:
        config_path = Path.home() / ".did" / "config"

    # Create the config
    try:
        create_test_did_config(config_path, github_token, github_login, github_email)
        print(f"\n✓ E2E tests can now use did config at: {config_path}")
        return 0
    except Exception as e:
        print(f"ERROR: Failed to create did config: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
