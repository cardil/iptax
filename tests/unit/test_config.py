"""Unit tests for iptax.config module.

Tests configuration management including path resolution, loading,
validation, and creation.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

from iptax.config import (
    ConfigError,
    Configurator,
    DidConfigError,
    create_default_config,
    get_config_path,
    get_did_config_path,
    list_did_providers,
    load_settings,
    validate_did_config,
)
from iptax.models import (
    DisabledAIConfig,
    GeminiProviderConfig,
    Settings,
    VertexAIProviderConfig,
)


class TestPathResolution:
    """Test path resolution functions."""

    def test_get_config_path_with_xdg_config_home(self, tmp_path, monkeypatch):
        """Test get_config_path() respects XDG_CONFIG_HOME environment variable."""
        xdg_home = tmp_path / "config"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))

        config_path = get_config_path()

        assert config_path == xdg_home / "iptax" / "settings.yaml"

    def test_get_config_path_without_xdg_config_home(self, monkeypatch):
        """Test get_config_path() uses ~/.config when XDG_CONFIG_HOME not set."""
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

        config_path = get_config_path()

        assert config_path == Path.home() / ".config" / "iptax" / "settings.yaml"

    def test_get_did_config_path(self):
        """Test get_did_config_path() returns ~/.did/config."""
        did_path = get_did_config_path()

        assert did_path == Path.home() / ".did" / "config"


class TestConfiguratorInitialization:
    """Test Configurator class initialization."""

    def test_init_with_default_paths(self):
        """Test Configurator initialization with default paths."""
        configurator = Configurator()

        assert configurator.settings_path == Path.home() / ".config" / "iptax" / "settings.yaml"
        assert configurator.did_config_path == Path.home() / ".did" / "config"

    def test_init_with_custom_settings_path(self, tmp_path):
        """Test Configurator initialization with custom settings path."""
        custom_path = tmp_path / "custom-settings.yaml"

        configurator = Configurator(settings_path=custom_path)

        assert configurator.settings_path == custom_path

    def test_init_with_custom_did_config_path(self, tmp_path):
        """Test Configurator initialization with custom did config path."""
        custom_did = tmp_path / "custom-did-config"

        configurator = Configurator(did_config_path=custom_did)

        assert configurator.did_config_path == custom_did

    def test_init_with_string_paths(self, tmp_path):
        """Test Configurator accepts string paths."""
        settings_str = str(tmp_path / "settings.yaml")
        did_str = str(tmp_path / "did-config")

        configurator = Configurator(
            settings_path=settings_str,
            did_config_path=did_str,
        )

        assert configurator.settings_path == Path(settings_str)
        assert configurator.did_config_path == Path(did_str)


class TestConfigurationLoading:
    """Test configuration loading functionality."""

    def test_load_settings_with_valid_config(self, tmp_path):
        """Test loading settings from a valid YAML configuration file."""
        # Create did config
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\n[github]\ntype = github\n")

        # Create settings file
        settings_file = tmp_path / "settings.yaml"
        settings_data = {
            "employee": {
                "name": "John Doe",
                "supervisor": "Jane Smith",
            },
            "product": {
                "name": "Test Product",
            },
            "report": {
                "creative_work_percentage": 75,
            },
            "ai": {
                "provider": "disabled",
            },
            "did": {
                "config_path": str(did_config_file),
                "providers": ["github"],
            },
        }
        settings_file.write_text(yaml.safe_dump(settings_data))

        configurator = Configurator(settings_path=settings_file)
        settings = configurator.load()

        assert settings.employee.name == "John Doe"
        assert settings.employee.supervisor == "Jane Smith"
        assert settings.product.name == "Test Product"
        assert settings.report.creative_work_percentage == 75
        assert isinstance(settings.ai, DisabledAIConfig)

    def test_load_settings_with_missing_config(self, tmp_path):
        """Test that loading missing config raises ConfigError."""
        missing_file = tmp_path / "nonexistent.yaml"

        configurator = Configurator(settings_path=missing_file)

        with pytest.raises(ConfigError) as exc_info:
            configurator.load()

        assert "Configuration file not found" in str(exc_info.value)
        assert "iptax config" in str(exc_info.value)

    def test_load_settings_with_invalid_yaml(self, tmp_path):
        """Test that invalid YAML raises ConfigError."""
        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text("invalid: yaml: content: [")

        configurator = Configurator(settings_path=settings_file)

        with pytest.raises(ConfigError) as exc_info:
            configurator.load()

        assert "Invalid YAML" in str(exc_info.value)

    def test_load_settings_with_validation_error(self, tmp_path):
        """Test that Pydantic validation errors raise ConfigError."""
        settings_file = tmp_path / "settings.yaml"
        settings_data = {
            "employee": {
                "name": "",  # Empty name should fail validation
                "supervisor": "Jane Smith",
            },
            "product": {
                "name": "Test Product",
            },
        }
        settings_file.write_text(yaml.safe_dump(settings_data))

        configurator = Configurator(settings_path=settings_file)

        with pytest.raises(ConfigError) as exc_info:
            configurator.load()

        assert "Invalid configuration" in str(exc_info.value)

    def test_load_settings_convenience_function(self, tmp_path, monkeypatch):
        """Test load_settings() convenience function."""
        # Create did config
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\n")

        # Create settings file
        config_dir = tmp_path / "config" / "iptax"
        config_dir.mkdir(parents=True)
        settings_file = config_dir / "settings.yaml"

        settings_data = {
            "employee": {
                "name": "John Doe",
                "supervisor": "Jane Smith",
            },
            "product": {
                "name": "Test Product",
            },
            "did": {
                "config_path": str(did_config_file),
                "providers": ["github"],
            },
        }
        settings_file.write_text(yaml.safe_dump(settings_data))

        # Set XDG_CONFIG_HOME to use temp directory
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        settings = load_settings()

        assert settings.employee.name == "John Doe"


class TestDidConfigValidation:
    """Test did configuration validation."""

    def test_validate_did_config_with_existing_file(self, tmp_path):
        """Test validate_did_config() succeeds when file exists."""
        did_config = tmp_path / "did-config"
        did_config.write_text("[general]\n")

        configurator = Configurator(did_config_path=did_config)

        result = configurator.validate_did_config()

        assert result is True

    def test_validate_did_config_with_missing_file(self, tmp_path):
        """Test validate_did_config() raises DidConfigError when file missing."""
        missing_file = tmp_path / "nonexistent"

        configurator = Configurator(did_config_path=missing_file)

        with pytest.raises(DidConfigError) as exc_info:
            configurator.validate_did_config()

        assert "did config file not found" in str(exc_info.value)
        assert "https://github.com/psss/did#setup" in str(exc_info.value)

    def test_validate_did_config_with_directory_instead_of_file(self, tmp_path):
        """Test validate_did_config() raises error when path is directory."""
        directory = tmp_path / "did-dir"
        directory.mkdir()

        configurator = Configurator(did_config_path=directory)

        with pytest.raises(DidConfigError) as exc_info:
            configurator.validate_did_config()

        assert "is not a file" in str(exc_info.value)

    def test_validate_did_config_with_unreadable_file(self, tmp_path):
        """Test validate_did_config() raises error for unreadable file."""
        did_config = tmp_path / "did-config"
        did_config.write_text("[general]\n")
        did_config.chmod(0o000)

        configurator = Configurator(did_config_path=did_config)

        try:
            with pytest.raises(DidConfigError) as exc_info:
                configurator.validate_did_config()

            assert "not readable" in str(exc_info.value)
        finally:
            # Restore permissions for cleanup
            did_config.chmod(0o600)

    def test_validate_did_config_convenience_function(self, isolated_home):
        """Test validate_did_config() convenience function."""
        did_config = isolated_home / ".did" / "config"
        did_config.parent.mkdir(parents=True)
        did_config.write_text("[general]\n")

        result = validate_did_config()

        assert result is True


class TestListDidProviders:
    """Test listing did providers."""

    def test_list_did_providers_with_did_sdk(self, tmp_path):
        """Test list_did_providers() using did SDK."""
        did_config_file = tmp_path / "did-config"
        config_content = """[general]
email = test@example.com

[github]
type = github
url = https://github.com

[gitlab]
type = gitlab
url = https://gitlab.com
"""
        did_config_file.write_text(config_content)

        configurator = Configurator(did_config_path=did_config_file)

        providers = configurator.list_did_providers()

        assert "github" in providers
        assert "gitlab" in providers
        assert "general" not in providers

    def test_list_did_providers_without_did_sdk(self, tmp_path):
        """Test list_did_providers() falls back to manual parsing."""
        did_config_file = tmp_path / "did-config"
        config_content = """[general]
email = test@example.com

[github]
type = github

[gitlab.cee]
type = gitlab
"""
        did_config_file.write_text(config_content)

        configurator = Configurator(did_config_path=did_config_file)

        providers = configurator.list_did_providers()

        assert "github" in providers
        assert "gitlab.cee" in providers
        assert "general" not in providers

    def test_list_did_providers_with_no_providers(self, tmp_path):
        """Test list_did_providers() raises error when no providers configured."""
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\nemail = test@example.com\n")

        configurator = Configurator(did_config_path=did_config_file)

        with pytest.raises(DidConfigError) as exc_info:
            configurator.list_did_providers()

        assert "No providers configured" in str(exc_info.value)

    def test_list_did_providers_with_invalid_config(self, tmp_path):
        """Test list_did_providers() raises error for invalid config."""
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("invalid [config syntax")

        configurator = Configurator(did_config_path=did_config_file)

        with pytest.raises(DidConfigError) as exc_info:
            configurator.list_did_providers()

        assert "Failed to parse did config" in str(exc_info.value)

    def test_list_did_providers_convenience_function(self, isolated_home):
        """Test list_did_providers() convenience function."""
        did_config_file = isolated_home / ".did" / "config"
        did_config_file.parent.mkdir(parents=True)
        config_content = """[general]
[github]
type = github
"""
        did_config_file.write_text(config_content)

        providers = list_did_providers()

        assert "github" in providers


class TestCreateMinimalConfig:
    """Test minimal configuration creation."""

    def test_create_minimal_config(self, tmp_path):
        """Test creating minimal configuration in non-interactive mode."""
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\n[github]\ntype = github\n")

        settings_file = tmp_path / "settings.yaml"

        configurator = Configurator(
            settings_path=settings_file,
            did_config_path=did_config_file,
        )

        configurator.create(interactive=False)

        assert settings_file.exists()

        # Verify content
        settings = Settings.from_yaml_file(settings_file)
        assert settings.employee.name == "Your Name"
        assert settings.employee.supervisor == "Supervisor Name"
        assert settings.product.name == "Your Product Name"
        assert isinstance(settings.ai, DisabledAIConfig)
        assert settings.workday.enabled is False

    def test_create_minimal_config_creates_directory(self, tmp_path):
        """Test that create() creates parent directories."""
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\n[github]\ntype = github\n")

        settings_file = tmp_path / "nested" / "dir" / "settings.yaml"

        configurator = Configurator(
            settings_path=settings_file,
            did_config_path=did_config_file,
        )

        configurator.create(interactive=False)

        assert settings_file.parent.exists()
        assert settings_file.exists()

    def test_create_minimal_config_without_did(self, tmp_path):
        """Test creating config when did is not configured."""
        settings_file = tmp_path / "settings.yaml"
        missing_did = tmp_path / "nonexistent-did"

        configurator = Configurator(
            settings_path=settings_file,
            did_config_path=missing_did,
        )

        # Should exit with error
        with pytest.raises(SystemExit):
            configurator.create(interactive=False)


class TestCreateInteractiveConfig:
    """Test interactive configuration creation."""

    def test_interactive_config_with_minimal_inputs(self, tmp_path):
        """Test interactive configuration with minimal inputs."""
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\n[github]\ntype = github\n")

        settings_file = tmp_path / "settings.yaml"

        configurator = Configurator(
            settings_path=settings_file,
            did_config_path=did_config_file,
        )

        # Mock questionary inputs
        mock_responses = {
            "Employee name:": "John Doe",
            "Supervisor name:": "Jane Smith",
            "Product name:": "Test Product",
            "Creative work percentage (0-100) [80]:": "80",
            "Output directory [~/Documents/iptax/{year}/]:": "~/Documents/iptax/{year}/",
            "Enable AI filtering?": False,
            "Enable Workday integration?": False,
            "did config path [~/.did/config]:": str(did_config_file),
        }

        with (
            patch("iptax.config.questionary.text") as mock_text,
            patch("iptax.config.questionary.confirm") as mock_confirm,
            patch("iptax.config.questionary.checkbox") as mock_checkbox,
            patch("iptax.config.questionary.print"),
        ):

            # Setup text mock
            def text_side_effect(prompt, **kwargs):
                mock = Mock()
                for key, value in mock_responses.items():
                    if key in prompt:
                        mock.ask.return_value = value
                        return mock
                # Default return
                mock.ask.return_value = kwargs.get("default", "")
                return mock

            mock_text.side_effect = text_side_effect

            # Setup confirm mock
            def confirm_side_effect(prompt, **kwargs):
                mock = Mock()
                for key, value in mock_responses.items():
                    if key in prompt:
                        mock.ask.return_value = value
                        return mock
                mock.ask.return_value = kwargs.get("default", False)
                return mock

            mock_confirm.side_effect = confirm_side_effect

            # Setup checkbox mock
            mock_checkbox_instance = Mock()
            mock_checkbox_instance.ask.return_value = ["github.com"]
            mock_checkbox.return_value = mock_checkbox_instance

            configurator.create(interactive=True)

        assert settings_file.exists()

        # Verify content
        settings = Settings.from_yaml_file(settings_file)
        assert settings.employee.name == "John Doe"
        assert settings.product.name == "Test Product"

    def test_interactive_config_with_gemini_ai(self, tmp_path):
        """Test interactive configuration with Gemini AI provider."""
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\n[github]\ntype = github\n")

        settings_file = tmp_path / "settings.yaml"

        configurator = Configurator(
            settings_path=settings_file,
            did_config_path=did_config_file,
        )

        with (
            patch("iptax.config.questionary.text") as mock_text,
            patch("iptax.config.questionary.confirm") as mock_confirm,
            patch("iptax.config.questionary.select") as mock_select,
            patch("iptax.config.questionary.checkbox") as mock_checkbox,
            patch("iptax.config.questionary.print"),
        ):

            # Mock text inputs
            mock_text_instance = Mock()
            mock_text_instance.ask.side_effect = [
                "John Doe",  # Employee name
                "Jane Smith",  # Supervisor name
                "Test Product",  # Product name
                "80",  # Creative percentage
                "~/Documents/iptax/{year}/",  # Output dir
                "gemini-1.5-pro",  # AI model
                "GEMINI_API_KEY",  # API key env
                str(did_config_file),  # did config path
            ]
            mock_text.return_value = mock_text_instance

            # Mock confirm inputs
            mock_confirm_instance = Mock()
            mock_confirm_instance.ask.side_effect = [
                True,  # Enable AI
                False,  # Use .env file
                False,  # Enable Workday
            ]
            mock_confirm.return_value = mock_confirm_instance

            # Mock select (AI provider)
            mock_select_instance = Mock()
            mock_select_instance.ask.return_value = "gemini"
            mock_select.return_value = mock_select_instance

            # Mock checkbox
            mock_checkbox_instance = Mock()
            mock_checkbox_instance.ask.return_value = ["github.com"]
            mock_checkbox.return_value = mock_checkbox_instance

            configurator.create(interactive=True)

        settings = Settings.from_yaml_file(settings_file)
        assert isinstance(settings.ai, GeminiProviderConfig)

    def test_interactive_config_with_vertex_ai(self, tmp_path):
        """Test interactive configuration with Vertex AI provider."""
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\n[github]\ntype = github\n")

        settings_file = tmp_path / "settings.yaml"

        configurator = Configurator(
            settings_path=settings_file,
            did_config_path=did_config_file,
        )

        with (
            patch("iptax.config.questionary.text") as mock_text,
            patch("iptax.config.questionary.confirm") as mock_confirm,
            patch("iptax.config.questionary.select") as mock_select,
            patch("iptax.config.questionary.checkbox") as mock_checkbox,
            patch("iptax.config.questionary.print"),
        ):

            # Mock text inputs
            mock_text_instance = Mock()
            mock_text_instance.ask.side_effect = [
                "John Doe",  # Employee name
                "Jane Smith",  # Supervisor name
                "Test Product",  # Product name
                "80",  # Creative percentage
                "~/Documents/iptax/{year}/",  # Output dir
                "gemini-1.5-pro",  # AI model
                "my-gcp-project",  # Project ID
                "us-central1",  # Location
                "",  # Credentials file (empty)
                str(did_config_file),  # did config path
            ]
            mock_text.return_value = mock_text_instance

            # Mock confirm inputs
            mock_confirm_instance = Mock()
            mock_confirm_instance.ask.side_effect = [
                True,  # Enable AI
                False,  # Enable Workday
            ]
            mock_confirm.return_value = mock_confirm_instance

            # Mock select (AI provider)
            mock_select_instance = Mock()
            mock_select_instance.ask.return_value = "vertex"
            mock_select.return_value = mock_select_instance

            # Mock checkbox
            mock_checkbox_instance = Mock()
            mock_checkbox_instance.ask.return_value = ["github.com"]
            mock_checkbox.return_value = mock_checkbox_instance

            configurator.create(interactive=True)

        settings = Settings.from_yaml_file(settings_file)
        assert isinstance(settings.ai, VertexAIProviderConfig)
        assert settings.ai.project_id == "my-gcp-project"

    def test_interactive_config_with_workday(self, tmp_path):
        """Test interactive configuration with Workday enabled."""
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\n[github.com]\ntype = github\n")

        settings_file = tmp_path / "settings.yaml"

        configurator = Configurator(
            settings_path=settings_file,
            did_config_path=did_config_file,
        )

        with (
            patch("iptax.config.questionary.text") as mock_text,
            patch("iptax.config.questionary.confirm") as mock_confirm,
            patch("iptax.config.questionary.checkbox") as mock_checkbox,
            patch("iptax.config.questionary.print"),
        ):

            # Mock text inputs
            mock_text_instance = Mock()
            mock_text_instance.ask.side_effect = [
                "John Doe",
                "Jane Smith",
                "Test Product",
                "80",
                "~/Documents/iptax/{year}/",
                "https://company.workday.com",  # Workday URL
                str(did_config_file),
            ]
            mock_text.return_value = mock_text_instance

            # Mock confirm inputs
            mock_confirm_instance = Mock()
            mock_confirm_instance.ask.side_effect = [
                False,  # Disable AI
                True,  # Enable Workday
            ]
            mock_confirm.return_value = mock_confirm_instance

            # Mock checkbox
            mock_checkbox_instance = Mock()
            mock_checkbox_instance.ask.return_value = ["github.com"]
            mock_checkbox.return_value = mock_checkbox_instance

            configurator.create(interactive=True)

        settings = Settings.from_yaml_file(settings_file)
        assert settings.workday.enabled is True
        assert settings.workday.url == "https://company.workday.com"


class TestCreateDefaultConfig:
    """Test create_default_config convenience function."""

    def test_create_default_config_non_interactive(self, isolated_home):
        """Test create_default_config() in non-interactive mode."""
        # Setup paths
        did_config_file = isolated_home / ".did" / "config"
        did_config_file.parent.mkdir(parents=True)
        did_config_file.write_text("[general]\n[github]\ntype = github\n")

        config_dir = isolated_home / ".config" / "iptax"

        create_default_config(interactive=False)

        settings_file = config_dir / "settings.yaml"
        assert settings_file.exists()

    def test_create_default_config_without_did(self, isolated_home):
        """Test create_default_config() exits when did not configured."""
        with pytest.raises(SystemExit):
            create_default_config(interactive=False)


class TestConfiguratorErrorMessages:
    """Test Configurator error message formatting."""

    def test_load_error_message_includes_help_text(self, tmp_path):
        """Test that load errors include helpful setup instructions."""
        missing_file = tmp_path / "nonexistent.yaml"

        configurator = Configurator(settings_path=missing_file)

        with pytest.raises(ConfigError) as exc_info:
            configurator.load()

        error_msg = str(exc_info.value)
        assert "Configuration file not found" in error_msg
        assert "iptax config" in error_msg

    def test_did_error_message_includes_setup_link(self, tmp_path):
        """Test that did errors include setup documentation link."""
        missing_did = tmp_path / "nonexistent"

        configurator = Configurator(did_config_path=missing_did)

        with pytest.raises(DidConfigError) as exc_info:
            configurator.validate_did_config()

        error_msg = str(exc_info.value)
        assert "did config file not found" in error_msg
        assert "https://github.com/psss/did#setup" in error_msg

    def test_yaml_error_message_includes_file_path(self, tmp_path):
        """Test that YAML errors include the config file path."""
        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text("invalid: [yaml")

        configurator = Configurator(settings_path=settings_file)

        with pytest.raises(ConfigError) as exc_info:
            configurator.load()

        error_msg = str(exc_info.value)
        assert "Invalid YAML" in error_msg
        assert str(settings_file) in error_msg

    def test_validation_error_message_includes_suggestion(self, tmp_path):
        """Test that validation errors suggest running config."""
        settings_file = tmp_path / "settings.yaml"
        settings_data = {"employee": {"name": "", "supervisor": "Test"}}
        settings_file.write_text(yaml.safe_dump(settings_data))

        configurator = Configurator(settings_path=settings_file)

        with pytest.raises(ConfigError) as exc_info:
            configurator.load()

        error_msg = str(exc_info.value)
        assert "Invalid configuration" in error_msg
        assert "iptax config" in error_msg


class TestConfigFilePermissions:
    """Test configuration file permission handling."""

    def test_created_config_has_restricted_permissions(self, tmp_path):
        """Test that created config files have 600 permissions."""
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\n[github]\ntype = github\n")

        settings_file = tmp_path / "settings.yaml"

        configurator = Configurator(
            settings_path=settings_file,
            did_config_path=did_config_file,
        )

        configurator.create(interactive=False)

        import stat

        mode = settings_file.stat().st_mode
        assert stat.S_IMODE(mode) == 0o600


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_configurator_handles_none_paths_gracefully(self):
        """Test that None paths default to standard locations."""
        configurator = Configurator(settings_path=None, did_config_path=None)

        assert configurator.settings_path is not None
        assert configurator.did_config_path is not None

    def test_list_providers_handles_empty_sections(self, tmp_path):
        """Test list_did_providers handles config with only [general]."""
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\nemail = test@example.com\n")

        configurator = Configurator(did_config_path=did_config_file)

        with pytest.raises(DidConfigError) as exc_info:
            configurator.list_did_providers()

        assert "No providers configured" in str(exc_info.value)

    def test_create_handles_existing_config_file(self, tmp_path):
        """Test that create() overwrites existing config file."""
        did_config_file = tmp_path / "did-config"
        did_config_file.write_text("[general]\n[github.com]\ntype = github\n")

        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text("old: config")

        configurator = Configurator(
            settings_path=settings_file,
            did_config_path=did_config_file,
        )

        configurator.create(interactive=False)

        # Should overwrite
        settings = Settings.from_yaml_file(settings_file)
        assert settings.employee.name == "Your Name"
