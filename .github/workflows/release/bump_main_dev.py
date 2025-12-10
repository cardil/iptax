#!/usr/bin/env python3
"""Bump main branch to next development version after a minor release."""

import subprocess
import sys
from pathlib import Path

# Add the release directory to the path for local module imports
sys.path.insert(0, str(Path(__file__).parent))

# Import after path modification (E402: module level import not at top of file)
from version_utils import update_version  # noqa: E402


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse semantic version into (major, minor, patch)."""
    parts = version.split(".")
    if len(parts) != 3:
        sys.exit(f"Error: Invalid version format: {version}")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        sys.exit(f"Error: Invalid version format: {version}")


def get_next_dev_version(version: str) -> str:
    """Get the next development version."""
    major, minor, _ = parse_version(version)
    next_minor = minor + 1
    return f"{major}.{next_minor}.0.dev0"


def git_commit_and_push(version: str, next_dev_version: str) -> None:
    """Configure git, commit, and push changes to main."""
    print(f"Bumping main from {version} to {next_dev_version}")

    # Checkout main
    subprocess.run(["git", "fetch", "origin", "main"], check=True)
    subprocess.run(["git", "checkout", "main"], check=True)

    # Update version in pyproject.toml
    update_version(next_dev_version)

    # Configure git
    subprocess.run(
        ["git", "config", "--global", "user.name", "github-actions[bot]"], check=True
    )
    subprocess.run(
        [
            "git",
            "config",
            "--global",
            "user.email",
            "github-actions[bot]@users.noreply.github.com",
        ],
        check=True,
    )

    # Commit and push
    subprocess.run(["git", "add", "pyproject.toml"], check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            f"chore: bump version to {next_dev_version} for development",
        ],
        check=True,
    )
    subprocess.run(["git", "push", "origin", "main"], check=True)


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 2:
        sys.exit("Usage: bump_main_dev.py <current_version>")

    version = sys.argv[1]
    next_dev_version = get_next_dev_version(version)
    git_commit_and_push(version, next_dev_version)


if __name__ == "__main__":
    main()
