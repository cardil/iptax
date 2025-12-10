#!/usr/bin/env python3
"""Get release information after semantic-release."""

import re
import sys
from pathlib import Path

# Add the release directory to the path for local module imports
sys.path.insert(0, str(Path(__file__).parent))

# Import after path modification (E402: module level import not at top of file)
from version_utils import get_version  # noqa: E402


def is_minor_release(version: str) -> bool:
    """Check if this is a minor release (X.Y.0)."""
    pattern = r"^\d+\.\d+\.0$"
    return bool(re.match(pattern, version))


def main() -> None:
    """Main entry point."""
    version = get_version()
    is_minor = is_minor_release(version)

    # Output for GitHub Actions
    print(f"version={version}")
    print(f"is_minor={'true' if is_minor else 'false'}")


if __name__ == "__main__":
    main()
