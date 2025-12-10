#!/usr/bin/env python3
"""Strip .dev suffix from version in pyproject.toml."""

import re
import subprocess
import sys
from pathlib import Path

# Add the release directory to the path for local module imports
sys.path.insert(0, str(Path(__file__).parent))

# Import after path modification (E402: module level import not at top of file)
from version_utils import get_version, update_version  # noqa: E402


def strip_dev(version: str) -> str:
    """Remove .dev suffix from version."""
    return re.sub(r"\.dev.*$", "", version)


def git_commit_and_push(version: str, clean_version: str) -> None:
    """Configure git, commit, and push changes."""
    print(f"Stripping .dev from version: {version} -> {clean_version}")

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
        ["git", "commit", "-m", "chore: strip dev version for release"], check=True
    )
    subprocess.run(["git", "push"], check=True)

    print("Dev version stripped. Workflow will re-run with clean version.")


def main() -> None:
    """Main entry point."""
    version = get_version()
    clean_version = strip_dev(version)

    if version == clean_version:
        sys.exit("Error: Version does not contain .dev suffix")

    update_version(clean_version)
    git_commit_and_push(version, clean_version)


if __name__ == "__main__":
    main()
