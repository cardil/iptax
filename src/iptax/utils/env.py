"""Environment-aware path resolution utilities.

This module provides centralized functions for resolving application directories
that respect XDG Base Directory specification and HOME environment variable.
"""

import os
from pathlib import Path


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

    Returns:
        Path to the iptax configuration directory
    """
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")

    if xdg_config_home:
        return Path(xdg_config_home) / "iptax"

    return get_home_dir() / ".config" / "iptax"


def get_cache_dir() -> Path:
    """Get the application's cache directory.

    Respects XDG_CACHE_HOME and HOME environment variables.
    Falls back to ~/.cache/iptax if environment variables are not set.

    Returns:
        Path to the iptax cache directory
    """
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")

    if xdg_cache_home:
        return Path(xdg_cache_home) / "iptax"

    return get_home_dir() / ".cache" / "iptax"


def get_did_config_path() -> Path:
    """Get the default path for did config file.

    Did uses ~/.did/config by default and doesn't support XDG variables.
    This function respects HOME environment variable.

    Returns:
        Path to ~/.did/config
    """
    return get_home_dir() / ".did" / "config"
