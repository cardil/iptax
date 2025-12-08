"""Font management for PDF report generation.

Downloads and caches Red Hat Text font for consistent PDF rendering.
"""

import logging
from pathlib import Path
from urllib.request import urlopen

from iptax.utils.env import get_cache_dir

logger = logging.getLogger(__name__)

# Font configuration
FONT_FAMILY = "Red Hat Text"

# GitHub raw URLs for Red Hat Text fonts
FONT_BASE_URL = (
    "https://raw.githubusercontent.com/RedHatOfficial/RedHatFont/"
    "master/fonts/Proportional/RedHatText/ttf"
)

# Font files to download (filename -> weight, style)
FONT_FILES = {
    "RedHatText-Regular.ttf": ("400", "normal"),
    "RedHatText-Bold.ttf": ("700", "normal"),
    "RedHatText-Italic.ttf": ("400", "italic"),
    "RedHatText-BoldItalic.ttf": ("700", "italic"),
}


def get_fonts_dir() -> Path:
    """Get the fonts cache directory."""
    return get_cache_dir() / "fonts"


def _download_font(url: str, dest_path: Path) -> None:
    """Download a font file from URL."""
    # Security check: only allow HTTPS URLs
    if not url.startswith("https://"):
        raise ValueError(f"Only HTTPS URLs are allowed: {url}")
    logger.debug("Downloading font: %s", dest_path.name)
    # S310: URL scheme validated above, only HTTPS allowed
    with urlopen(url, timeout=30) as response:  # noqa: S310
        content = response.read()
    dest_path.write_bytes(content)


def ensure_fonts_available() -> Path:
    """Ensure fonts are downloaded and available.

    Downloads Red Hat Text font files if not already cached.

    Returns:
        Path to fonts directory
    """
    fonts_dir = get_fonts_dir()
    fonts_dir.mkdir(parents=True, exist_ok=True)

    for filename in FONT_FILES:
        font_path = fonts_dir / filename
        if not font_path.exists():
            url = f"{FONT_BASE_URL}/{filename}"
            _download_font(url, font_path)

    return fonts_dir


def generate_font_face_css() -> str:
    """Generate @font-face CSS rules for cached fonts.

    Ensures fonts are downloaded first, then generates CSS rules
    with file:// URLs pointing to the cached font files.

    Returns:
        CSS @font-face rules as string
    """
    fonts_dir = ensure_fonts_available()

    css_rules = []
    for filename, (weight, style) in FONT_FILES.items():
        font_path = fonts_dir / filename
        if font_path.exists():
            font_url = font_path.as_uri()
            css_rules.append(
                f"@font-face {{\n"
                f'  font-family: "{FONT_FAMILY}";\n'
                f'  src: url("{font_url}") format("truetype");\n'
                f"  font-weight: {weight};\n"
                f"  font-style: {style};\n"
                f"}}"
            )

    return "\n\n".join(css_rules)
