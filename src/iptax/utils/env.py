"""Environment-aware path resolution utilities.

This module provides centralized functions for resolving application directories
that respect XDG Base Directory specification and HOME environment variable.
"""

import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def _validate_xdg_path(
    xdg_var_name: str, xdg_value: str, fallback_subdir: str
) -> Path | None:
    """Validate XDG path per XDG Base Directory specification.

    Args:
        xdg_var_name: Name of the XDG environment variable
        xdg_value: Value from the environment variable
        fallback_subdir: Subdirectory to append (e.g., "iptax")

    Returns:
        Path object if valid absolute path, None if invalid (should use fallback)
    """
    xdg_path = Path(xdg_value)
    if not xdg_path.is_absolute():
        logger.warning(
            "%s contains relative path '%s' which violates "
            "XDG Base Directory specification. Ignoring and using default.",
            xdg_var_name,
            xdg_value,
        )
        return None
    return xdg_path / fallback_subdir


def get_home_dir() -> Path:
    """Get the user's home directory.

    Respects HOME environment variable, falls back to Path.home().

    Returns:
        Path to the user's home directory
    """
    home = os.environ.get("HOME")
    return Path(home) if home else Path.home()


def get_config_dir() -> Path:
    """Get the application's configuration directory.

    Respects XDG_CONFIG_HOME and HOME environment variables.
    Falls back to ~/.config/iptax if environment variables are not set.
    Per XDG spec, relative paths in XDG_CONFIG_HOME are ignored.

    Returns:
        Path to the iptax configuration directory
    """
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")

    if xdg_config_home:
        validated_path = _validate_xdg_path("XDG_CONFIG_HOME", xdg_config_home, "iptax")
        if validated_path:
            return validated_path

    return get_home_dir() / ".config" / "iptax"


def get_cache_dir() -> Path:
    """Get the application's cache directory.

    Respects XDG_CACHE_HOME and HOME environment variables.
    Falls back to ~/.cache/iptax if environment variables are not set.
    Per XDG spec, relative paths in XDG_CACHE_HOME are ignored.

    Returns:
        Path to the iptax cache directory
    """
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")

    if xdg_cache_home:
        validated_path = _validate_xdg_path("XDG_CACHE_HOME", xdg_cache_home, "iptax")
        if validated_path:
            return validated_path

    return get_home_dir() / ".cache" / "iptax"


def get_month_end_date(year: int, month: int) -> date:
    """Get the last day of a given month.

    Args:
        year: Year (e.g., 2024)
        month: Month number (1-12)

    Returns:
        Date representing the last day of the month
    """
    DECEMBER = 12
    if month == DECEMBER:
        return date(year, DECEMBER, 31)

    # Get first day of next month, then subtract one day
    next_month = datetime(year, month + 1, 1).date()
    return next_month - timedelta(days=1)


def get_did_config_path() -> Path:
    """Get the default path for did config file.

    Did uses ~/.did/config by default and doesn't support XDG variables.
    This function respects DID_CONFIG and HOME environment variables.

    Checks DID_CONFIG environment variable first, then falls back to
    ~/.did/config (respecting HOME environment variable).

    Returns:
        Path to did config file
    """
    # Check DID_CONFIG environment variable first
    did_config = os.environ.get("DID_CONFIG")
    if did_config:
        return Path(did_config).expanduser()

    # Fall back to default ~/.did/config
    return get_home_dir() / ".did" / "config"
