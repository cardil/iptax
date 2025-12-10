#!/usr/bin/env python3
"""Check if the version in pyproject.toml contains .dev suffix."""

import sys
from pathlib import Path

# Add the release directory to the path for local module imports
sys.path.insert(0, str(Path(__file__).parent))

# Import after path modification (E402: module level import not at top of file)
from version_utils import get_version  # noqa: E402


def has_dev_suffix(version: str) -> bool:
    """Check if version has .dev suffix."""
    return ".dev" in version


def main() -> None:
    """Main entry point."""
    version = get_version()
    has_dev = has_dev_suffix(version)

    # Output for GitHub Actions
    print(f"current_version={version}")
    print(f"has_dev={'true' if has_dev else 'false'}")


if __name__ == "__main__":
    main()
