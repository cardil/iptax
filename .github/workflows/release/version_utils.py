"""Common utilities for version management in release scripts."""

import re
import sys
from pathlib import Path

# Get the repository root directory (3 levels up from this script)
REPO_ROOT = Path(__file__).parent.parent.parent.parent
DEFAULT_PYPROJECT = REPO_ROOT / "pyproject.toml"


def get_version(pyproject_path: Path = DEFAULT_PYPROJECT) -> str:
    """Extract version from pyproject.toml."""
    content = pyproject_path.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        sys.exit("Error: Could not find version in pyproject.toml")
    return match.group(1)


def update_version(
    new_version: str, pyproject_path: Path = DEFAULT_PYPROJECT
) -> None:
    """Update version in pyproject.toml."""
    content = pyproject_path.read_text()
    updated = re.sub(
        r'^version\s*=\s*"[^"]+"',
        f'version = "{new_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    pyproject_path.write_text(updated)
