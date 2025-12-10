#!/usr/bin/env python3
"""Generate SHA256 checksums for distribution files."""

import hashlib
import sys
from pathlib import Path

# Get the repository root directory (4 levels up from this script)
REPO_ROOT = Path(__file__).parent.parent.parent.parent
DIST_DIR = REPO_ROOT / "dist"


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with file_path.open("rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def main() -> None:
    """Main entry point."""
    if not DIST_DIR.exists():
        sys.exit(f"Error: Distribution directory not found: {DIST_DIR}")

    # Find all wheel and sdist files
    dist_files = sorted(list(DIST_DIR.glob("*.whl")) + list(DIST_DIR.glob("*.tar.gz")))

    if not dist_files:
        sys.exit("Error: No distribution files found in dist/")

    checksums_file = DIST_DIR / "checksums.txt"

    # Generate checksums
    with checksums_file.open("w") as f:
        for dist_file in dist_files:
            checksum = calculate_sha256(dist_file)
            line = f"{checksum}  {dist_file.name}\n"
            f.write(line)
            print(line.rstrip())

    print(f"\nChecksums written to {checksums_file}")


if __name__ == "__main__":
    main()
