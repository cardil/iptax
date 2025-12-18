"""Unit tests for GitHub Actions release scripts."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add release scripts directory to path
RELEASE_SCRIPTS_DIR = Path(__file__).parents[2] / ".github" / "workflows" / "release"
sys.path.insert(0, str(RELEASE_SCRIPTS_DIR))

# Import modules after path modification
from version_utils import (  # noqa: E402
    DEFAULT_PYPROJECT,
    get_version,
    update_version,
)


class TestVersionUtils:
    """Tests for version_utils module."""

    def test_get_version(self) -> None:
        """Test extracting version from pyproject.toml."""
        mock_content = 'version = "1.2.3"\n'
        with patch("pathlib.Path.read_text", return_value=mock_content):
            version = get_version()
            assert version == "1.2.3"

    def test_get_version_with_dev(self) -> None:
        """Test extracting version with .dev suffix."""
        mock_content = 'version = "1.2.3.dev0"\n'
        with patch("pathlib.Path.read_text", return_value=mock_content):
            version = get_version()
            assert version == "1.2.3.dev0"

    def test_get_version_not_found(self) -> None:
        """Test error when version not found."""
        mock_content = "no version here\n"
        with (
            patch("pathlib.Path.read_text", return_value=mock_content),
            pytest.raises(SystemExit),
        ):
            get_version()

    def test_update_version(self) -> None:
        """Test updating version in pyproject.toml."""
        mock_content = 'version = "1.2.3"\nother = "content"\n'
        expected = 'version = "2.0.0"\nother = "content"\n'

        with (
            patch("pathlib.Path.read_text", return_value=mock_content),
            patch("pathlib.Path.write_text") as mock_write,
        ):
            update_version("2.0.0")
            mock_write.assert_called_once_with(expected)

    def test_default_pyproject_path(self) -> None:
        """Test that DEFAULT_PYPROJECT points to pyproject.toml."""
        assert DEFAULT_PYPROJECT.name == "pyproject.toml"
        # Verify the path exists and contains the .github directory
        assert (DEFAULT_PYPROJECT.parent / ".github").exists()


class TestCheckDevVersion:
    """Tests for check_dev_version script."""

    def test_has_dev_suffix_true(self) -> None:
        """Test detecting .dev suffix."""
        from check_dev_version import has_dev_suffix

        assert has_dev_suffix("1.2.3.dev0") is True
        assert has_dev_suffix("1.2.3.dev1") is True

    def test_has_dev_suffix_false(self) -> None:
        """Test detecting absence of .dev suffix."""
        from check_dev_version import has_dev_suffix

        assert has_dev_suffix("1.2.3") is False
        assert has_dev_suffix("1.0.0") is False


class TestStripDevVersion:
    """Tests for strip_dev_version script."""

    def test_strip_dev(self) -> None:
        """Test stripping .dev suffix."""
        from strip_dev_version import strip_dev

        assert strip_dev("1.2.3.dev0") == "1.2.3"
        assert strip_dev("1.2.3.dev1") == "1.2.3"
        assert strip_dev("1.2.3") == "1.2.3"


class TestBumpMainDev:
    """Tests for bump_main_dev script."""

    def test_parse_version(self) -> None:
        """Test parsing version string."""
        from bump_main_dev import parse_version

        assert parse_version("1.2.3") == (1, 2, 3)
        assert parse_version("10.20.30") == (10, 20, 30)
        assert parse_version("0.1.0") == (0, 1, 0)

    def test_parse_version_invalid(self) -> None:
        """Test parsing invalid version."""
        from bump_main_dev import parse_version

        with pytest.raises(SystemExit):
            parse_version("1.2")
        with pytest.raises(SystemExit):
            parse_version("invalid")

    def test_get_next_dev_version(self) -> None:
        """Test calculating next dev version."""
        from bump_main_dev import get_next_dev_version

        assert get_next_dev_version("1.0.0") == "1.1.0.dev0"
        assert get_next_dev_version("1.5.0") == "1.6.0.dev0"
        assert get_next_dev_version("2.10.0") == "2.11.0.dev0"


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
