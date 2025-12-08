"""Unit tests for iptax.report.fonts module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from iptax.report.fonts import (
    FONT_BASE_URL,
    FONT_FAMILY,
    FONT_FILES,
    _download_font,
    ensure_fonts_available,
    generate_font_face_css,
    get_fonts_dir,
)


class TestGetFontsDir:
    """Test get_fonts_dir function."""

    def test_returns_path_object(self, monkeypatch, tmp_path):
        """Test that get_fonts_dir returns a Path."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        result = get_fonts_dir()
        assert isinstance(result, Path)

    def test_returns_fonts_subdir(self, monkeypatch, tmp_path):
        """Test that fonts dir is under cache directory."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        result = get_fonts_dir()
        assert result.name == "fonts"
        assert "iptax" in str(result)


class TestDownloadFont:
    """Test _download_font function."""

    def test_rejects_non_https_url(self, tmp_path):
        """Test that non-HTTPS URLs are rejected."""
        dest = tmp_path / "font.ttf"

        with pytest.raises(ValueError, match="Only HTTPS URLs are allowed"):
            _download_font("http://example.com/font.ttf", dest)

    def test_downloads_font_from_https(self, tmp_path):
        """Test downloading font from HTTPS URL."""
        dest = tmp_path / "font.ttf"
        mock_response = MagicMock()
        mock_response.read.return_value = b"fake font data"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("iptax.report.fonts.urlopen", return_value=mock_response):
            _download_font("https://example.com/font.ttf", dest)

        assert dest.exists()
        assert dest.read_bytes() == b"fake font data"


class TestEnsureFontsAvailable:
    """Test ensure_fonts_available function."""

    def test_creates_fonts_directory(self, monkeypatch, tmp_path):
        """Test that fonts directory is created if it doesn't exist."""
        cache_dir = tmp_path / "cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

        # Mock download to avoid network calls
        with patch("iptax.report.fonts._download_font"):
            result = ensure_fonts_available()

        assert result.exists()
        assert result.is_dir()

    def test_downloads_missing_fonts(self, monkeypatch, tmp_path):
        """Test that missing fonts are downloaded."""
        cache_dir = tmp_path / "cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

        download_calls = []

        def mock_download(url: str, dest: Path) -> None:
            download_calls.append((url, dest))
            dest.write_bytes(b"font data")

        with patch("iptax.report.fonts._download_font", side_effect=mock_download):
            ensure_fonts_available()

        # Should download all 4 font files
        assert len(download_calls) == len(FONT_FILES)
        for url, _ in download_calls:
            assert url.startswith(FONT_BASE_URL)

    def test_skips_existing_fonts(self, monkeypatch, tmp_path):
        """Test that existing fonts are not re-downloaded."""
        cache_dir = tmp_path / "cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

        # Create fonts directory with existing fonts
        fonts_dir = cache_dir / "iptax" / "fonts"
        fonts_dir.mkdir(parents=True)
        for filename in FONT_FILES:
            (fonts_dir / filename).write_bytes(b"existing font")

        download_calls = []

        def mock_download(url: str, dest: Path) -> None:
            download_calls.append((url, dest))

        with patch("iptax.report.fonts._download_font", side_effect=mock_download):
            ensure_fonts_available()

        # Should not download any fonts
        assert len(download_calls) == 0


class TestGenerateFontFaceCss:
    """Test generate_font_face_css function."""

    def test_generates_css_for_all_fonts(self, monkeypatch, tmp_path):
        """Test that CSS is generated for all font files."""
        cache_dir = tmp_path / "cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

        # Create fonts directory with font files
        fonts_dir = cache_dir / "iptax" / "fonts"
        fonts_dir.mkdir(parents=True)
        for filename in FONT_FILES:
            (fonts_dir / filename).write_bytes(b"font data")

        css = generate_font_face_css()

        # Should have @font-face rules for all fonts
        assert css.count("@font-face") == len(FONT_FILES)
        assert f'font-family: "{FONT_FAMILY}"' in css

    def test_includes_font_weights_and_styles(self, monkeypatch, tmp_path):
        """Test that CSS includes correct weights and styles."""
        cache_dir = tmp_path / "cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

        # Create fonts directory with font files
        fonts_dir = cache_dir / "iptax" / "fonts"
        fonts_dir.mkdir(parents=True)
        for filename in FONT_FILES:
            (fonts_dir / filename).write_bytes(b"font data")

        css = generate_font_face_css()

        # Check for expected weights
        assert "font-weight: 400" in css
        assert "font-weight: 700" in css
        # Check for expected styles
        assert "font-style: normal" in css
        assert "font-style: italic" in css

    def test_uses_file_urls(self, monkeypatch, tmp_path):
        """Test that CSS uses file:// URLs."""
        cache_dir = tmp_path / "cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

        # Create fonts directory with font files
        fonts_dir = cache_dir / "iptax" / "fonts"
        fonts_dir.mkdir(parents=True)
        for filename in FONT_FILES:
            (fonts_dir / filename).write_bytes(b"font data")

        css = generate_font_face_css()

        assert "file://" in css
        assert ".ttf" in css
