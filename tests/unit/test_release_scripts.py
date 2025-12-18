"""Unit tests for GitHub Actions release scripts."""

import sys
from pathlib import Path

# Add release scripts directory to path
RELEASE_SCRIPTS_DIR = Path(__file__).parents[2] / ".github" / "workflows" / "release"
sys.path.insert(0, str(RELEASE_SCRIPTS_DIR))


class TestGenerateChecksums:
    """Tests for generate_checksums script."""

    def test_calculate_sha256(self, tmp_path: Path) -> None:
        """Test SHA256 calculation."""
        from generate_checksums import calculate_sha256

        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        # Known SHA256 for "Hello, World!"
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        assert calculate_sha256(test_file) == expected
