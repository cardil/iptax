#!/usr/bin/env python3
"""Update version in pyproject.toml."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from version_utils import update_version  # noqa: E402

if len(sys.argv) != 2:
    sys.exit("Usage: update_version.py <version>")

update_version(sys.argv[1])
print(f"Updated pyproject.toml to version {sys.argv[1]}")
