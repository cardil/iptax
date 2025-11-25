"""Configuration management for iptax.

This module handles loading, validating, and creating configuration files
for the iptax application. It manages both the iptax settings and integration
with the did configuration.
"""

import os
from pathlib import Path

import questionary
import yaml
from questionary.prompts.common import Choice

from iptax.models import (
    AIProviderConfig,
    DidConfig,
    DisabledAIConfig,
    EmployeeInfo,
    GeminiProviderConfig,
    ProductConfig,
    ReportConfig,
    Settings,
    VertexAIProviderConfig,
    WorkdayConfig,
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
    ):
        """Initialize configuration manager.

        Args:
            settings_path: Path to iptax settings.yaml. If None, uses default
                          location (~/.config/iptax/settings.yaml or
                          $XDG_CONFIG_HOME/iptax/settings.yaml)
            did_config_path: Path to did config. If None, uses default
                            location (~/.did/config)
        """
        self.settings_path = (
            Path(settings_path) if settings_path else self._get_default_settings_path()
        )
        self.did_config_path = (
            Path(did_config_path) if did_config_path else self._get_default_did_config_path()
        )

    @staticmethod
    def _get_default_settings_path() -> Path:
        """Get default path for iptax settings.yaml.

        Respects XDG_CONFIG_HOME and HOME environment variables.

        Returns:
            Path to settings.yaml
        """
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")

        if xdg_config_home:
            config_dir = Path(xdg_config_home) / "iptax"
        else:
            # Respect HOME environment variable, fall back to Path.home()
            home = os.environ.get("HOME")
            home_path = Path(home) if home else Path.home()
            config_dir = home_path / ".config" / "iptax"

        return config_dir / "settings.yaml"

    @staticmethod
    def _get_default_did_config_path() -> Path:
        """Get default path for did config.

        Respects HOME environment variable, falls back to Path.home().

        Returns:
            Path to ~/.did/config
        """
        # Respect HOME environment variable, fall back to Path.home()
        home = os.environ.get("HOME")
        home_path = Path(home) if home else Path.home()
        return home_path / ".did" / "config"

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
                f"{self.did_config_path} is not readable. Please check file permissions."
            )

        return True

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
            # Try to import did SDK
            try:
                from did.base import Config as DidConfig
            except ImportError:
                # did SDK not available - fall back to manual parsing
                return self._parse_did_config_manual()

            # Load did config using the SDK (pass path as keyword argument)
            did_config = DidConfig(path=str(self.did_config_path))

            # Extract provider names from sections
            # did config uses INI format with sections like [github], [gitlab]
            providers = []

            # Get all sections except 'general'
            for section in did_config.parser.sections():
                if section.lower() != "general":
                    providers.append(section)

            if not providers:
                raise DidConfigError(
                    f"No providers configured in {self.did_config_path}\n\n"
                    "Please enable at least one provider in your did config:\n"
                    "  [github]\n"
                    "  type = github\n"
                    "  url = https://github.com\n"
                    "  ...\n\n"
                    "Then run 'iptax config' again."
                )

            return providers

        except Exception as e:
            if isinstance(e, DidConfigError):
                raise
            raise DidConfigError(
                f"Failed to parse did config: {e}\n\n"
                f"Please check {self.did_config_path} for syntax errors."
            ) from e

    def _parse_did_config_manual(self) -> list[str]:
        """Manually parse did config to extract provider names.

        Fallback method when did SDK is not available. Parses the INI-style
        config file to extract section names.

        Returns:
            List of provider names
        """
        import configparser

        try:
            parser = configparser.ConfigParser()
            parser.read(self.did_config_path)

            providers = [section for section in parser.sections() if section.lower() != "general"]

            if not providers:
                raise DidConfigError(f"No providers configured in {self.did_config_path}")

            return providers

        except configparser.Error as e:
            raise DidConfigError(f"Failed to parse did config: {e}") from e

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
            try:
                current_settings = self.load()
            except ConfigError:
                # If config is invalid, we'll just use standard defaults
                pass

        if interactive:
            settings = self._interactive_config_wizard(defaults=current_settings)
        else:
            settings = self._create_minimal_config()

        # Save configuration
        try:
            settings.to_yaml_file(self.settings_path)
            print(f"\n✓ Configuration saved to {self.settings_path}")
        except Exception as e:
            raise ConfigError(f"Failed to save configuration: {e}") from e

    def _interactive_config_wizard(self, defaults: Settings | None = None) -> Settings:
        """Run interactive configuration wizard using questionary.

        Guides the user through setting up their iptax configuration by
        asking a series of questions about their employee info, product,
        AI provider, did providers, etc.

        Args:
            defaults: Optional existing settings to use as defaults

        Returns:
            Configured Settings instance
        """
        questionary.print("Welcome to iptax configuration!", style="bold")
        questionary.print("")

        # Employee Information
        questionary.print("Employee Information:", style="bold")

        default_name = defaults.employee.name if defaults and defaults.employee else ""
        employee_name = questionary.text(
            "Employee name:",
            default=default_name,
            validate=lambda x: len(x.strip()) > 0 or "Name cannot be empty",
        ).ask()

        default_supervisor = defaults.employee.supervisor if defaults and defaults.employee else ""
        supervisor_name = questionary.text(
            "Supervisor name:",
            default=default_supervisor,
            validate=lambda x: len(x.strip()) > 0 or "Name cannot be empty",
        ).ask()

        employee = EmployeeInfo(
            name=employee_name,
            supervisor=supervisor_name,
        )

        # Product Configuration
        questionary.print("\nProduct Configuration:", style="bold")

        default_product = defaults.product.name if defaults else ""
        product_name = questionary.text(
            "Product name:",
            default=default_product,
            validate=lambda x: len(x.strip()) > 0 or "Product name cannot be empty",
        ).ask()

        product = ProductConfig(name=product_name)

        # Report Settings
        questionary.print("\nReport Settings:", style="bold")

        # Get defaults from model or existing config
        if defaults:
            default_percentage = defaults.report.creative_work_percentage
        else:
            default_percentage = ReportConfig.model_fields["creative_work_percentage"].default

        creative_percentage = questionary.text(
            f"Creative work percentage (0-100) [{default_percentage}]:",
            default=str(default_percentage),
            validate=lambda x: (x.isdigit() and 0 <= int(x) <= 100) or "Must be 0-100",
        ).ask()

        if defaults:
            default_output_dir = str(defaults.report.output_dir)
        else:
            default_output_dir = ReportConfig.model_fields["output_dir"].default

        output_dir = questionary.text(
            f"Output directory [{default_output_dir}]:", default=default_output_dir
        ).ask()

        report = ReportConfig(
            output_dir=output_dir,
            creative_work_percentage=int(creative_percentage),
        )

        # AI Provider
        questionary.print("\nAI Provider Configuration:", style="bold")

        default_enable_ai = not isinstance(defaults.ai, DisabledAIConfig) if defaults else True
        enable_ai = questionary.confirm("Enable AI filtering?", default=default_enable_ai).ask()

        if enable_ai:
            default_ai_config = defaults.ai if defaults else None
            ai = self._configure_ai_provider(default_ai_config)
        else:
            ai = DisabledAIConfig()

        # Workday Integration
        questionary.print("\nWorkday Integration:", style="bold")

        default_enable_workday = defaults.workday.enabled if defaults else True
        enable_workday = questionary.confirm(
            "Enable Workday integration?", default=default_enable_workday
        ).ask()

        if enable_workday:
            default_url = defaults.workday.url if defaults and defaults.workday.url else ""
            workday_url = questionary.text(
                "Workday URL:",
                default=default_url,
                validate=lambda x: len(x.strip()) > 0 or "URL cannot be empty",
            ).ask()
            workday = WorkdayConfig(enabled=True, url=workday_url)
        else:
            workday = WorkdayConfig(enabled=False)

        # did Configuration
        questionary.print("\npsss/did Configuration:", style="bold")

        # Get default from model or existing config
        if defaults:
            default_did_path = str(defaults.did.config_path)
        else:
            default_did_path = DidConfig.model_fields["config_path"].default

        did_config_path = questionary.text(
            f"did config path [{default_did_path}]:", default=default_did_path
        ).ask()

        # List available providers from did config
        questionary.print("\nReading did config...", style="italic")
        original_path = self.did_config_path
        try:
            # Temporarily update did_config_path to read providers
            self.did_config_path = Path(did_config_path).expanduser()
            available_providers = self.list_did_providers()
        finally:
            # Always restore original path
            self.did_config_path = original_path

        questionary.print("Found providers:", style="bold")

        # Determine checked state
        checked_providers = set(available_providers)
        if defaults:
            checked_providers = set(defaults.did.providers)

        # Let user select providers using checkbox
        # Use Choice objects with checked=True/False
        choices = []
        for p in available_providers:
            is_checked = p in checked_providers
            choices.append(Choice(title=p, checked=is_checked))

        selected_providers = questionary.checkbox(
            "Select providers to use:",
            choices=choices,
        ).ask()

        if not selected_providers:
            questionary.print("⚠ At least one provider must be selected", style="bold red")
            selected_providers = available_providers

        questionary.print("\nSelected providers:", style="bold")
        for provider in selected_providers:
            questionary.print(f"  ✓ {provider}", style="green")

        did = DidConfig(
            config_path=did_config_path,
            providers=selected_providers,
        )

        # Create and return settings
        return Settings(
            employee=employee,
            product=product,
            report=report,
            ai=ai,
            workday=workday,
            did=did,
        )

    def _configure_ai_provider(
        self, default_config: AIProviderConfig | None = None
    ) -> AIProviderConfig:
        """Configure AI provider interactively using questionary.

        Args:
            default_config: Optional existing AI config to use for defaults

        Returns:
            Configured AI provider (Gemini or Vertex AI)
        """
        default_provider = "gemini"
        if isinstance(default_config, GeminiProviderConfig):
            default_provider = "gemini"
        elif isinstance(default_config, VertexAIProviderConfig):
            default_provider = "vertex"

        provider = questionary.select(
            "Select AI provider:",
            choices=[
                questionary.Choice("Google Gemini API", value="gemini"),
                questionary.Choice("Google Vertex AI", value="vertex"),
            ],
            default=default_provider,
        ).ask()

        if provider == "gemini":
            # Get defaults
            default_model = (
                default_config.model
                if isinstance(default_config, GeminiProviderConfig)
                else GeminiProviderConfig.model_fields["model"].default
            )
            default_api_key_env = (
                default_config.api_key_env
                if isinstance(default_config, GeminiProviderConfig)
                else GeminiProviderConfig.model_fields["api_key_env"].default
            )

            model = questionary.text(f"Model [{default_model}]:", default=default_model).ask()

            api_key_env = questionary.text(
                f"API key environment variable [{default_api_key_env}]:",
                default=default_api_key_env,
            ).ask()

            default_use_env_file = (
                bool(default_config.api_key_file)
                if isinstance(default_config, GeminiProviderConfig)
                else False
            )

            use_env_file = questionary.confirm(
                "Use .env file for API key? (default: use system environment)",
                default=default_use_env_file,
            ).ask()

            api_key_file = None
            if use_env_file:
                default_path = (
                    str(default_config.api_key_file)
                    if isinstance(default_config, GeminiProviderConfig)
                    and default_config.api_key_file
                    else ""
                )
                api_key_file = questionary.text(
                    "Path to .env file:",
                    default=default_path,
                    validate=lambda x: len(x.strip()) > 0 or "Path cannot be empty",
                ).ask()

            return GeminiProviderConfig(
                model=model,
                api_key_env=api_key_env,
                api_key_file=api_key_file,
            )

        elif provider == "vertex":
            # Get defaults
            default_model = (
                default_config.model
                if isinstance(default_config, VertexAIProviderConfig)
                else VertexAIProviderConfig.model_fields["model"].default
            )
            default_location = (
                default_config.location
                if isinstance(default_config, VertexAIProviderConfig)
                else VertexAIProviderConfig.model_fields["location"].default
            )
            default_project_id = (
                default_config.project_id
                if isinstance(default_config, VertexAIProviderConfig)
                else ""
            )

            model = questionary.text(f"Model [{default_model}]:", default=default_model).ask()

            project_id = questionary.text(
                "GCP Project ID:",
                default=default_project_id,
                validate=lambda x: len(x.strip()) > 0 or "Project ID cannot be empty",
            ).ask()

            location = questionary.text(
                f"GCP Location [{default_location}]:", default=default_location
            ).ask()

            default_credentials = (
                str(default_config.credentials_file)
                if isinstance(default_config, VertexAIProviderConfig)
                and default_config.credentials_file
                else ""
            )

            credentials_file = questionary.text(
                "Credentials file (optional, press Enter to skip):", default=default_credentials
            ).ask()

            return VertexAIProviderConfig(
                model=model,
                project_id=project_id,
                location=location,
                credentials_file=credentials_file if credentials_file else None,
            )

        else:
            questionary.print(f"Unknown provider '{provider}', using disabled AI", style="yellow")
            return DisabledAIConfig()

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
