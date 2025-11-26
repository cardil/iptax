"""Configuration management for iptax.

This module handles loading, validating, and creating configuration files
for the iptax application. It manages both the iptax settings and integration
with the did configuration.
"""

import contextlib
import os
from pathlib import Path
from typing import NoReturn

import questionary
import yaml
from did.base import Config as DidSdkConfig

from iptax.config.interactive import run_interactive_wizard
from iptax.models import (
    DidConfig,
    DisabledAIConfig,
    EmployeeInfo,
    ProductConfig,
    ReportConfig,
    Settings,
    WorkdayConfig,
)
from iptax.utils.env import (
    get_config_dir,
)
from iptax.utils.env import (
    get_did_config_path as get_did_config_path_util,
)


class ConfigError(Exception):
    """Configuration-related error."""

    pass


class DidConfigError(ConfigError):
    """Did configuration error."""

    pass


class Configurator:
    """Configuration manager for iptax.

    Handles loading, validating, and creating iptax configuration.
    Similar to did's Config class, allows passing custom paths via constructor.

    Examples:
        # Use default paths
        config = Configurator()
        settings = config.load()

        # Use custom paths (useful for testing)
        config = Configurator(
            settings_path="/tmp/test-settings.yaml",
            did_config_path="/tmp/test-did-config"
        )
        settings = config.load()
    """

    def __init__(
        self,
        settings_path: Path | str | None = None,
        did_config_path: Path | str | None = None,
    ) -> None:
        """Initialize configuration manager.

        Args:
            settings_path: Path to iptax settings.yaml. If None, uses
                default location (~/.config/iptax/settings.yaml
                or $XDG_CONFIG_HOME/iptax/settings.yaml)
            did_config_path: Path to did config. If None, uses default
                location (~/.did/config)
        """
        self.settings_path = (
            Path(settings_path) if settings_path else self._get_default_settings_path()
        )
        self.did_config_path = (
            Path(did_config_path)
            if did_config_path
            else self._get_default_did_config_path()
        )

    @staticmethod
    def _get_default_settings_path() -> Path:
        """Get default path for iptax settings.yaml.

        Respects XDG_CONFIG_HOME and HOME environment variables.

        Returns:
            Path to settings.yaml
        """
        return get_config_dir() / "settings.yaml"

    @staticmethod
    def _get_default_did_config_path() -> Path:
        """Get default path for did config.

        Respects HOME environment variable, falls back to Path.home().

        Returns:
            Path to ~/.did/config
        """
        return get_did_config_path_util()

    def load(self) -> Settings:
        """Load and validate settings from config file.

        Returns:
            Validated Settings instance

        Raises:
            ConfigError: If config file doesn't exist or is invalid
        """
        if not self.settings_path.exists():
            raise ConfigError(
                f"Configuration file not found: {self.settings_path}\n\n"
                "Please run 'iptax config' to set up your configuration."
            )

        try:
            return Settings.from_yaml_file(self.settings_path)
        except FileNotFoundError as e:
            raise ConfigError(
                f"Configuration file not found: {self.settings_path}\n\n"
                "Please run 'iptax config' to set up your configuration."
            ) from e
        except yaml.YAMLError as e:
            raise ConfigError(
                f"Invalid YAML in configuration file:\n{e}\n\n"
                f"Please check {self.settings_path} for syntax errors."
            ) from e
        except ValueError as e:
            raise ConfigError(
                f"Invalid configuration:\n{e}\n\n"
                f"Please run 'iptax config' to update your configuration."
            ) from e

    def validate_did_config(self) -> bool:
        """Check if did config exists and is valid.

        Validates that:
        - did config file exists
        - File is readable

        Returns:
            True if did config exists and is readable

        Raises:
            DidConfigError: If did config doesn't exist or is not readable
        """
        if not self.did_config_path.exists():
            raise DidConfigError(
                f"did config file not found at {self.did_config_path}\n\n"
                "Please configure did first:\n"
                "  https://github.com/psss/did#setup\n\n"
                "Then run 'iptax config' to configure iptax."
            )

        if not self.did_config_path.is_file():
            raise DidConfigError(f"{self.did_config_path} exists but is not a file")

        if not os.access(self.did_config_path, os.R_OK):
            raise DidConfigError(
                f"{self.did_config_path} is not readable. "
                "Please check file permissions."
            )

        return True

    def _raise_no_providers_error(self) -> NoReturn:
        """Raise error when no providers are configured.

        Raises:
            DidConfigError: Always raised
        """
        raise DidConfigError(
            f"No providers configured in {self.did_config_path}\n\n"
            "Please enable at least one provider in your did config:\n"
            "  [github]\n"
            "  type = github\n"
            "  url = https://github.com\n"
            "  ...\n\n"
            "Then run 'iptax config' again."
        )

    def list_did_providers(self) -> list[str]:
        """List available providers from did config.

        Parses the did config file to extract configured provider names.
        Uses the did SDK to read the configuration properly.

        Returns:
            List of provider names (e.g., ['github.com', 'gitlab.cee'])

        Raises:
            DidConfigError: If did config is invalid or cannot be parsed
        """
        # First validate that the config exists
        self.validate_did_config()

        try:
            # Load did config using the SDK (pass path as keyword argument)
            did_config = DidSdkConfig(path=str(self.did_config_path))

            # Get all sections except 'general'
            # (did config uses INI format with sections like [github], [gitlab])
            providers = [
                section
                for section in did_config.parser.sections()
                if section.lower() != "general"
            ]

            if providers:
                return providers

            # No providers configured
            self._raise_no_providers_error()

        except DidConfigError:
            raise
        except Exception as e:
            raise DidConfigError(
                f"Failed to parse did config: {e}\n\n"
                f"Please check {self.did_config_path} for syntax errors."
            ) from e

    def create(self, interactive: bool = True) -> None:
        """Create configuration file, optionally with interactive wizard.

        Creates the iptax configuration file. If interactive is True,
        runs an interactive questionnaire to gather configuration values.
        Otherwise, creates a minimal configuration that requires manual editing.

        Args:
            interactive: If True, run interactive setup wizard. If False,
                        create minimal template configuration.

        Raises:
            DidConfigError: If did config doesn't exist or is invalid
            ConfigError: If configuration creation fails
        """
        # First validate that did is configured
        self.validate_did_config()

        # Create config directory if it doesn't exist
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)

        # Try to load existing settings for defaults
        current_settings = None
        if self.settings_path.exists():
            with contextlib.suppress(ConfigError):
                current_settings = self.load()

        if interactive:
            settings = self._interactive_config_wizard(defaults=current_settings)
        else:
            settings = self._create_minimal_config()

        # Save configuration
        try:
            settings.to_yaml_file(self.settings_path)
            questionary.print(
                f"\n✓ Configuration saved to {self.settings_path}", style="green"
            )
        except Exception as e:
            raise ConfigError(f"Failed to save configuration: {e}") from e

    def _list_providers_for_path(self, path: Path) -> list[str]:
        """List providers for a given did config path.

        Helper method to provide a compatible interface for the interactive wizard.

        Args:
            path: Path to did config file

        Returns:
            List of provider names
        """
        original_path = self.did_config_path
        try:
            self.did_config_path = path
            return self.list_did_providers()
        finally:
            self.did_config_path = original_path

    def _interactive_config_wizard(self, defaults: Settings | None = None) -> Settings:
        """Run interactive configuration wizard using questionary.

        Args:
            defaults: Optional existing settings to use as defaults

        Returns:
            Configured Settings instance
        """
        return run_interactive_wizard(
            defaults=defaults,
            list_providers_fn=self._list_providers_for_path,
        )

    def _create_minimal_config(self) -> Settings:
        """Create minimal configuration template.

        Creates a basic configuration with placeholder values that requires
        manual editing. Used when interactive mode is disabled.

        Returns:
            Minimal Settings instance
        """
        # Get available providers from did config
        try:
            available_providers = self.list_did_providers()
        except DidConfigError:
            available_providers = ["github.com"]

        return Settings(
            employee=EmployeeInfo(
                name="Your Name",
                supervisor="Supervisor Name",
            ),
            product=ProductConfig(
                name="Your Product Name",
            ),
            report=ReportConfig(),  # Uses defaults from model
            ai=DisabledAIConfig(),
            workday=WorkdayConfig(enabled=False),
            did=DidConfig(
                config_path=str(self.did_config_path),
                providers=available_providers,
            ),
        )


# Convenience functions that use default paths


def load_settings() -> Settings:
    """Load and validate settings from default config file.

    Convenience function that uses default paths.
    For custom paths, use Configurator class directly.

    Returns:
        Validated Settings instance

    Raises:
        ConfigError: If config file doesn't exist or is invalid
    """
    config = Configurator()
    return config.load()


def get_config_path() -> Path:
    """Return path to default settings.yaml file.

    Returns:
        Path to the settings.yaml file (may not exist yet)
    """
    return Configurator._get_default_settings_path()


def get_did_config_path() -> Path:
    """Return path to default did config file.

    Returns:
        Path to ~/.did/config
    """
    return Configurator._get_default_did_config_path()


def validate_did_config() -> bool:
    """Check if default did config exists and is valid.

    Convenience function that uses default paths.
    For custom paths, use Configurator class directly.

    Returns:
        True if did config exists and is readable

    Raises:
        DidConfigError: If did config doesn't exist or is not readable
    """
    config = Configurator()
    return config.validate_did_config()


def list_did_providers() -> list[str]:
    """List available providers from default did config.

    Convenience function that uses default paths.
    For custom paths, use Configurator class directly.

    Returns:
        List of provider names (e.g., ['github.com', 'gitlab.cee'])

    Raises:
        DidConfigError: If did config is invalid or cannot be parsed
    """
    config = Configurator()
    return config.list_did_providers()


def create_default_config(interactive: bool = True) -> None:
    """Create configuration file at default location.

    Convenience function that uses default paths.
    For custom paths, use Configurator class directly.

    Args:
        interactive: If True, run interactive setup wizard. If False,
                    create minimal template configuration.

    Raises:
        DidConfigError: If did config doesn't exist or is invalid
        ConfigError: If configuration creation fails
    """
    config = Configurator()
    config.create(interactive=interactive)
