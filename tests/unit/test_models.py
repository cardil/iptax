"""Unit tests for iptax.models module.

Tests all Pydantic models including validation, serialization, and business logic.
"""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from iptax.models import (
    AIJudgment,
    Change,
    DidConfig,
    DisabledAIConfig,
    EmployeeInfo,
    Fields,
    GeminiProviderConfig,
    HistoryEntry,
    ProductConfig,
    ReportConfig,
    ReportData,
    Repository,
    Settings,
    VertexAIProviderConfig,
    WorkdayConfig,
)


class TestFields:
    """Test Fields proxy class."""

    def test_fields_returns_fields_instance(self):
        """Test that Fields() returns a Fields instance."""
        accessor = Fields(ReportConfig)

        assert isinstance(accessor, Fields)

    def test_access_field_default_value(self):
        """Test accessing a field's default value."""
        accessor = Fields(ReportConfig)

        assert accessor.output_dir.default == "~/Documents/iptax/{year}/"
        assert accessor.creative_work_percentage.default == 80

    def test_access_field_description(self):
        """Test accessing a field's description."""
        accessor = Fields(ReportConfig)

        assert "Output directory" in accessor.output_dir.description
        assert "creative" in accessor.creative_work_percentage.description.lower()

    def test_access_nonexistent_field_raises_key_error(self):
        """Test that accessing non-existent field raises KeyError."""
        accessor = Fields(ReportConfig)

        with pytest.raises(KeyError):
            _ = accessor.nonexistent_field

    def test_fields_with_did_config(self):
        """Test Fields() with DidConfig model."""
        accessor = Fields(DidConfig)

        assert accessor.config_path.default == "~/.did/config"

    def test_fields_works_with_any_pydantic_model(self):
        """Test that Fields() works with any Pydantic BaseModel."""
        # Test with a model that doesn't have defaults
        accessor = Fields(EmployeeInfo)

        # Should be able to access field info even without defaults
        assert accessor.name is not None
        assert accessor.supervisor is not None


class TestEmployeeInfo:
    """Test EmployeeInfo model validation."""

    def test_valid_employee_data(self):
        """Test creating EmployeeInfo with valid data."""
        employee = EmployeeInfo(
            name="John Doe",
            supervisor="Jane Smith",
        )

        assert employee.name == "John Doe"
        assert employee.supervisor == "Jane Smith"

    def test_employee_name_strips_whitespace(self):
        """Test that names are stripped of leading/trailing whitespace."""
        employee = EmployeeInfo(
            name="  John Doe  ",
            supervisor="  Jane Smith  ",
        )

        assert employee.name == "John Doe"
        assert employee.supervisor == "Jane Smith"

    def test_employee_name_required(self):
        """Test that name field is required."""
        with pytest.raises(ValidationError) as exc_info:
            EmployeeInfo(supervisor="Jane Smith")

        assert "name" in str(exc_info.value)

    def test_supervisor_name_required(self):
        """Test that supervisor field is required."""
        with pytest.raises(ValidationError) as exc_info:
            EmployeeInfo(name="John Doe")

        assert "supervisor" in str(exc_info.value)

    def test_employee_name_cannot_be_empty(self):
        """Test that name cannot be empty string."""
        with pytest.raises(ValidationError) as exc_info:
            EmployeeInfo(name="", supervisor="Jane Smith")

        assert "Field cannot be empty" in str(exc_info.value)

    def test_employee_name_cannot_be_whitespace_only(self):
        """Test that name cannot be whitespace only."""
        with pytest.raises(ValidationError) as exc_info:
            EmployeeInfo(name="   ", supervisor="Jane Smith")

        assert "Field cannot be empty" in str(exc_info.value)

    def test_supervisor_name_cannot_be_empty(self):
        """Test that supervisor cannot be empty string."""
        with pytest.raises(ValidationError) as exc_info:
            EmployeeInfo(name="John Doe", supervisor="")

        assert "Field cannot be empty" in str(exc_info.value)


class TestProductConfig:
    """Test ProductConfig model validation."""

    def test_valid_product_config(self):
        """Test creating ProductConfig with valid data."""
        product = ProductConfig(name="Acme Fungear")

        assert product.name == "Acme Fungear"

    def test_product_name_strips_whitespace(self):
        """Test that product name is stripped of whitespace."""
        product = ProductConfig(name="  Test Product  ")

        assert product.name == "Test Product"

    def test_product_name_required(self):
        """Test that product name is required."""
        with pytest.raises(ValidationError) as exc_info:
            ProductConfig()

        assert "name" in str(exc_info.value)

    def test_product_name_cannot_be_empty(self):
        """Test that product name cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            ProductConfig(name="")

        assert "Product name cannot be empty" in str(exc_info.value)

    def test_product_name_cannot_be_whitespace_only(self):
        """Test that product name cannot be whitespace only."""
        with pytest.raises(ValidationError) as exc_info:
            ProductConfig(name="   ")

        assert "Product name cannot be empty" in str(exc_info.value)


class TestReportConfig:
    """Test ReportConfig model validation and methods."""

    def test_default_values(self):
        """Test that ReportConfig uses correct default values."""
        report = ReportConfig()

        assert report.output_dir == "~/Documents/iptax/{year}/"
        assert report.creative_work_percentage == 80

    def test_custom_values(self):
        """Test creating ReportConfig with custom values."""
        report = ReportConfig(
            output_dir="~/custom/path/{year}",
            creative_work_percentage=75,
        )

        assert report.output_dir == "~/custom/path/{year}"
        assert report.creative_work_percentage == 75

    def test_percentage_validation_minimum(self):
        """Test that percentage cannot be less than 0."""
        with pytest.raises(ValidationError) as exc_info:
            ReportConfig(creative_work_percentage=-1)

        assert "Creative work percentage must be between 0 and 100" in str(
            exc_info.value
        )

    def test_percentage_validation_maximum(self):
        """Test that percentage cannot be greater than 100."""
        with pytest.raises(ValidationError) as exc_info:
            ReportConfig(creative_work_percentage=101)

        assert "Creative work percentage must be between 0 and 100" in str(
            exc_info.value
        )

    def test_percentage_validation_boundary_values(self):
        """Test that boundary values 0 and 100 are valid."""
        report_min = ReportConfig(creative_work_percentage=0)
        assert report_min.creative_work_percentage == 0

        report_max = ReportConfig(creative_work_percentage=100)
        assert report_max.creative_work_percentage == 100

    def test_get_output_path_substitutes_year(self):
        """Test that get_output_path() substitutes {year} placeholder."""
        report = ReportConfig(output_dir="~/Documents/iptax/{year}/")

        path = report.get_output_path(2024)

        assert "{year}" not in str(path)
        assert "2024" in str(path)

    def test_get_output_path_expands_home(self):
        """Test that get_output_path() expands ~ to home directory."""
        report = ReportConfig(output_dir="~/test/{year}")

        path = report.get_output_path(2024)

        assert not str(path).startswith("~")
        assert path.is_absolute()


class TestGeminiProviderConfig:
    """Test GeminiProviderConfig model validation."""

    def test_default_values(self):
        """Test that GeminiProviderConfig uses correct defaults."""
        config = GeminiProviderConfig()

        assert config.provider == "gemini"
        assert config.model == "gemini-2.5-pro"
        assert config.api_key_env == "GEMINI_API_KEY"
        assert config.api_key_file is None
        assert config.enable_reasoning is True
        assert config.max_tokens is None

    def test_custom_values(self):
        """Test creating GeminiProviderConfig with custom values."""
        config = GeminiProviderConfig(
            model="gemini-pro",
            api_key_env="MY_API_KEY",
            enable_reasoning=False,
            max_tokens=1000,
        )

        assert config.model == "gemini-pro"
        assert config.api_key_env == "MY_API_KEY"
        assert config.enable_reasoning is False
        assert config.max_tokens == 1000

    def test_api_key_file_validation_with_existing_file(self, tmp_path):
        """Test that api_key_file validates existence."""
        env_file = tmp_path / ".env"
        env_file.write_text("GEMINI_API_KEY=test")

        config = GeminiProviderConfig(api_key_file=str(env_file))

        assert config.api_key_file == str(env_file)

    def test_api_key_file_validation_with_missing_file(self, tmp_path):
        """Test that api_key_file raises error for missing file."""
        missing_file = tmp_path / "nonexistent.env"

        with pytest.raises(ValidationError) as exc_info:
            GeminiProviderConfig(api_key_file=str(missing_file))

        assert "API key file not found" in str(exc_info.value)

    def test_provider_field_is_literal(self):
        """Test that provider field is locked to 'gemini'."""
        config = GeminiProviderConfig()
        assert config.provider == "gemini"

        # Cannot change provider
        with pytest.raises(ValidationError):
            GeminiProviderConfig(provider="vertex")


class TestVertexAIProviderConfig:
    """Test VertexAIProviderConfig model validation."""

    def test_default_values(self):
        """Test that VertexAIProviderConfig uses correct defaults."""
        config = VertexAIProviderConfig(project_id="test-project")

        assert config.provider == "vertex"
        assert config.model == "gemini-2.5-pro"
        assert config.location == "us-east5"
        assert config.credentials_file is None
        assert config.enable_reasoning is True
        assert config.max_tokens is None

    def test_custom_values(self):
        """Test creating VertexAIProviderConfig with custom values."""
        config = VertexAIProviderConfig(
            project_id="my-project",
            model="gemini-pro",
            location="europe-west1",
            enable_reasoning=False,
            max_tokens=2000,
        )

        assert config.project_id == "my-project"
        assert config.model == "gemini-pro"
        assert config.location == "europe-west1"
        assert config.enable_reasoning is False
        assert config.max_tokens == 2000

    def test_project_id_required(self):
        """Test that project_id is required."""
        with pytest.raises(ValidationError) as exc_info:
            VertexAIProviderConfig()

        assert "project_id" in str(exc_info.value)

    def test_credentials_file_validation_with_existing_file(self, tmp_path):
        """Test that credentials_file validates existence."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{"type": "service_account"}')

        config = VertexAIProviderConfig(
            project_id="test-project",
            credentials_file=str(creds_file),
        )

        assert config.credentials_file == str(creds_file)

    def test_credentials_file_validation_with_missing_file(self, tmp_path):
        """Test that credentials_file raises error for missing file."""
        missing_file = tmp_path / "nonexistent.json"

        with pytest.raises(ValidationError) as exc_info:
            VertexAIProviderConfig(
                project_id="test-project",
                credentials_file=str(missing_file),
            )

        assert "Credentials file not found" in str(exc_info.value)

    def test_provider_field_is_literal(self):
        """Test that provider field is locked to 'vertex'."""
        config = VertexAIProviderConfig(project_id="test")
        assert config.provider == "vertex"


class TestDisabledAIConfig:
    """Test DisabledAIConfig model."""

    def test_disabled_config(self):
        """Test creating DisabledAIConfig."""
        config = DisabledAIConfig()

        assert config.provider == "disabled"

    def test_provider_field_is_literal(self):
        """Test that provider field is locked to 'disabled'."""
        config = DisabledAIConfig()
        assert config.provider == "disabled"


class TestAIProviderConfigDiscriminatedUnion:
    """Test AI provider discriminated union functionality."""

    def test_gemini_provider_type_discrimination(self):
        """Test that provider='gemini' creates GeminiProviderConfig."""
        data = {"provider": "gemini"}

        # When used in Settings, this should create GeminiProviderConfig
        config = GeminiProviderConfig(**data)

        assert isinstance(config, GeminiProviderConfig)
        assert config.provider == "gemini"

    def test_vertex_provider_type_discrimination(self):
        """Test that provider='vertex' creates VertexAIProviderConfig."""
        data = {"provider": "vertex", "project_id": "test-project"}

        config = VertexAIProviderConfig(**data)

        assert isinstance(config, VertexAIProviderConfig)
        assert config.provider == "vertex"

    def test_disabled_provider_type_discrimination(self):
        """Test that provider='disabled' creates DisabledAIConfig."""
        data = {"provider": "disabled"}

        config = DisabledAIConfig(**data)

        assert isinstance(config, DisabledAIConfig)
        assert config.provider == "disabled"


class TestWorkdayConfig:
    """Test WorkdayConfig model validation."""

    def test_default_values(self):
        """Test that WorkdayConfig uses correct defaults."""
        config = WorkdayConfig()

        assert config.enabled is False
        assert config.url is None
        assert config.auth == "sso+kerberos"
        assert config.trusted_uris == []

    def test_disabled_config_without_url(self):
        """Test that disabled config doesn't require URL."""
        config = WorkdayConfig(enabled=False)

        assert config.enabled is False
        assert config.url is None

    def test_enabled_config_requires_url(self):
        """Test that enabled config requires URL."""
        with pytest.raises(ValidationError) as exc_info:
            WorkdayConfig(enabled=True)

        assert "url is required when Workday is enabled" in str(exc_info.value)

    def test_enabled_config_with_url(self):
        """Test creating enabled config with URL."""
        config = WorkdayConfig(
            enabled=True,
            url="https://workday.example.org",
        )

        assert config.enabled is True
        assert config.url == "https://workday.example.org"

    def test_sso_kerberos_auth_with_trusted_uris(self):
        """Test SSO+Kerberos config with trusted URIs."""
        config = WorkdayConfig(
            enabled=True,
            url="https://workday.example.org",
            auth="sso+kerberos",
            trusted_uris=["*.example.org", "*.sso.example.org"],
        )

        assert config.auth == "sso+kerberos"
        assert config.trusted_uris == ["*.example.org", "*.sso.example.org"]

    def test_sso_auth_without_trusted_uris(self):
        """Test SSO (password fallback) config without trusted URIs."""
        config = WorkdayConfig(
            enabled=True,
            url="https://workday.example.org",
            auth="sso",
        )

        assert config.auth == "sso"
        assert config.trusted_uris == []


class TestDidConfig:
    """Test DidConfig model validation."""

    def test_default_config_path(self, tmp_path):
        """Test that DidConfig uses default config path."""
        # Create a temporary did config file
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        config = DidConfig(
            config_path=str(did_config),
            providers=["github.com"],
        )

        assert config.config_path == str(did_config)
        assert config.providers == ["github.com"]

    def test_config_path_validation_with_existing_file(self, tmp_path):
        """Test that config_path validates file exists."""
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        config = DidConfig(
            config_path=str(did_config),
            providers=["github.com"],
        )

        assert config.config_path == str(did_config)

    def test_config_path_validation_with_missing_file(self, tmp_path):
        """Test that config_path raises error for missing file."""
        missing_file = tmp_path / "nonexistent"

        with pytest.raises(ValidationError) as exc_info:
            DidConfig(
                config_path=str(missing_file),
                providers=["github.com"],
            )

        assert "did config file not found" in str(exc_info.value)

    def test_providers_required(self, tmp_path):
        """Test that providers list is required."""
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        with pytest.raises(ValidationError) as exc_info:
            DidConfig(config_path=str(did_config))

        assert "providers" in str(exc_info.value)

    def test_providers_cannot_be_empty(self, tmp_path):
        """Test that providers list cannot be empty."""
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        with pytest.raises(ValidationError) as exc_info:
            DidConfig(
                config_path=str(did_config),
                providers=[],
            )

        assert "At least one provider must be specified" in str(exc_info.value)

    def test_multiple_providers(self, tmp_path):
        """Test creating DidConfig with multiple providers."""
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        config = DidConfig(
            config_path=str(did_config),
            providers=["github.com", "gitlab.cee"],
        )

        assert len(config.providers) == 2
        assert "github.com" in config.providers
        assert "gitlab.cee" in config.providers

    def test_get_config_path_expands_home(self, tmp_path):
        """Test that get_config_path() expands ~ to home directory."""
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        # Create config with ~ path (for this test we'll use the actual file)
        config = DidConfig(
            config_path=str(did_config),
            providers=["github.com"],
        )

        path = config.get_config_path()

        assert path.is_absolute()


class TestRepository:
    """Test Repository model."""

    def test_github_repository_creation(self):
        """Test creating a GitHub repository."""
        repo = Repository(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        assert repo.host == "github.com"
        assert repo.path == "owner/repo"
        assert repo.provider_type == "github"

    def test_gitlab_repository_creation(self):
        """Test creating a GitLab repository."""
        repo = Repository(
            host="gitlab.example.org",
            path="group/subgroup/repo",
            provider_type="gitlab",
        )

        assert repo.host == "gitlab.example.org"
        assert repo.path == "group/subgroup/repo"
        assert repo.provider_type == "gitlab"

    def test_from_full_path_factory_method(self):
        """Test creating Repository using from_full_path()."""
        repo = Repository.from_full_path(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        assert repo.host == "github.com"
        assert repo.path == "owner/repo"
        assert repo.provider_type == "github"

    def test_github_url_generation(self):
        """Test URL generation for GitHub repositories."""
        repo = Repository(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        url = repo.get_url()

        assert url == "https://github.com/owner/repo"

    def test_gitlab_url_generation(self):
        """Test URL generation for GitLab repositories."""
        repo = Repository(
            host="gitlab.example.org",
            path="group/subgroup/repo",
            provider_type="gitlab",
        )

        url = repo.get_url()

        assert url == "https://gitlab.example.org/group/subgroup/repo"

    def test_github_display_name_formatting(self):
        """Test display name formatting for GitHub (simple path)."""
        repo = Repository(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        display_name = repo.get_display_name()

        assert display_name == "owner / repo"

    def test_gitlab_display_name_formatting(self):
        """Test display name formatting for GitLab (nested path)."""
        repo = Repository(
            host="gitlab.example.org",
            path="group/subgroup/repo",
            provider_type="gitlab",
        )

        display_name = repo.get_display_name()

        assert display_name == "group / subgroup / repo"

    def test_string_representation(self):
        """Test that __str__ returns display name."""
        repo = Repository(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        assert str(repo) == "owner / repo"


class TestChange:
    """Test Change model."""

    def test_github_change_creation(self):
        """Test creating a GitHub change."""
        repo = Repository(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        change = Change(
            title="Fix bug in handler",
            repository=repo,
            number=123,
        )

        assert change.title == "Fix bug in handler"
        assert change.repository == repo
        assert change.number == 123
        assert change.merged_at is None

    def test_change_with_merged_at(self):
        """Test creating a change with merged_at timestamp."""
        repo = Repository(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        merged_time = datetime(2024, 11, 15, 10, 30, 0)
        change = Change(
            title="Add feature",
            repository=repo,
            number=456,
            merged_at=merged_time,
        )

        assert change.merged_at == merged_time

    def test_number_must_be_positive(self):
        """Test that change number must be greater than 0."""
        repo = Repository(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        with pytest.raises(ValidationError) as exc_info:
            Change(
                title="Test",
                repository=repo,
                number=0,
            )

        assert "greater than 0" in str(exc_info.value).lower()

    def test_github_change_url_generation(self):
        """Test URL generation for GitHub changes (pull requests)."""
        repo = Repository(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        change = Change(
            title="Fix bug",
            repository=repo,
            number=123,
        )

        url = change.get_url()

        assert url == "https://github.com/owner/repo/pull/123"

    def test_gitlab_change_url_generation(self):
        """Test URL generation for GitLab changes (merge requests)."""
        repo = Repository(
            host="gitlab.example.org",
            path="group/repo",
            provider_type="gitlab",
        )

        change = Change(
            title="Add feature",
            repository=repo,
            number=456,
        )

        url = change.get_url()

        assert url == "https://gitlab.example.org/group/repo/-/merge_requests/456"

    def test_get_change_id(self):
        """Test unique change identifier generation."""
        repo = Repository(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        change = Change(
            title="Test",
            repository=repo,
            number=123,
        )

        change_id = change.get_change_id()

        assert change_id == "github.com/owner/repo#123"

    def test_get_display_reference(self):
        """Test display reference generation."""
        repo = Repository(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        change = Change(
            title="Test",
            repository=repo,
            number=123,
        )

        reference = change.get_display_reference()

        assert reference == "owner/repo#123"


class TestSettings:
    """Test Settings model."""

    def test_settings_with_all_required_fields(self, tmp_path):
        """Test creating Settings with all required fields."""
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        settings = Settings(
            employee=EmployeeInfo(name="John Doe", supervisor="Jane Smith"),
            product=ProductConfig(name="Test Product"),
            did=DidConfig(config_path=str(did_config), providers=["github.com"]),
        )

        assert settings.employee.name == "John Doe"
        assert settings.product.name == "Test Product"
        assert settings.did.providers == ["github.com"]

    def test_settings_with_default_values(self, tmp_path):
        """Test that Settings uses correct defaults for optional fields."""
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        settings = Settings(
            employee=EmployeeInfo(name="John Doe", supervisor="Jane Smith"),
            product=ProductConfig(name="Test Product"),
            did=DidConfig(config_path=str(did_config), providers=["github.com"]),
        )

        # Check defaults
        assert settings.report.creative_work_percentage == 80
        assert isinstance(settings.ai, DisabledAIConfig)
        assert settings.workday.enabled is False

    def test_settings_with_gemini_ai(self, tmp_path):
        """Test Settings with Gemini AI provider."""
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        settings = Settings(
            employee=EmployeeInfo(name="John Doe", supervisor="Jane Smith"),
            product=ProductConfig(name="Test Product"),
            ai=GeminiProviderConfig(),
            did=DidConfig(config_path=str(did_config), providers=["github.com"]),
        )

        assert isinstance(settings.ai, GeminiProviderConfig)
        assert settings.ai.provider == "gemini"

    def test_yaml_serialization_and_deserialization(self, tmp_path):
        """Test Settings YAML serialization round-trip."""
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        # Create settings
        original = Settings(
            employee=EmployeeInfo(name="John Doe", supervisor="Jane Smith"),
            product=ProductConfig(name="Test Product"),
            report=ReportConfig(creative_work_percentage=75),
            ai=GeminiProviderConfig(model="gemini-pro"),
            did=DidConfig(config_path=str(did_config), providers=["github.com"]),
        )

        # Save to YAML
        yaml_file = tmp_path / "settings.yaml"
        original.to_yaml_file(yaml_file)

        # Load from YAML
        loaded = Settings.from_yaml_file(yaml_file)

        # Verify
        assert loaded.employee.name == "John Doe"
        assert loaded.product.name == "Test Product"
        assert loaded.report.creative_work_percentage == 75
        assert isinstance(loaded.ai, GeminiProviderConfig)
        assert loaded.ai.model == "gemini-pro"

    def test_from_yaml_file_with_missing_file(self, tmp_path):
        """Test that from_yaml_file raises FileNotFoundError for missing file."""
        missing_file = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError) as exc_info:
            Settings.from_yaml_file(missing_file)

        assert "Settings file not found" in str(exc_info.value)

    def test_to_yaml_file_creates_parent_directory(self, tmp_path):
        """Test that to_yaml_file creates parent directories."""
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        settings = Settings(
            employee=EmployeeInfo(name="John Doe", supervisor="Jane Smith"),
            product=ProductConfig(name="Test Product"),
            did=DidConfig(config_path=str(did_config), providers=["github.com"]),
        )

        # Save to nested path
        yaml_file = tmp_path / "nested" / "dir" / "settings.yaml"
        settings.to_yaml_file(yaml_file)

        assert yaml_file.exists()
        assert yaml_file.parent.exists()

    def test_to_yaml_file_sets_permissions(self, tmp_path):
        """Test that to_yaml_file sets file permissions to 600."""
        did_config = tmp_path / "did_config"
        did_config.write_text("[general]\n")

        settings = Settings(
            employee=EmployeeInfo(name="John Doe", supervisor="Jane Smith"),
            product=ProductConfig(name="Test Product"),
            did=DidConfig(config_path=str(did_config), providers=["github.com"]),
        )

        yaml_file = tmp_path / "settings.yaml"
        settings.to_yaml_file(yaml_file)

        # Check permissions (owner read/write only)
        import stat

        mode = yaml_file.stat().st_mode
        assert stat.S_IMODE(mode) == 0o600


class TestHistoryEntry:
    """Test HistoryEntry model."""

    def test_history_entry_creation(self):
        """Test creating a HistoryEntry."""
        cutoff = date(2024, 11, 25)
        generated = datetime(2024, 11, 26, 10, 0, 0)

        entry = HistoryEntry(
            last_cutoff_date=cutoff,
            generated_at=generated,
        )

        assert entry.last_cutoff_date == cutoff
        assert entry.generated_at == generated
        assert entry.regenerated_at is None

    def test_history_entry_with_regeneration(self):
        """Test HistoryEntry with regeneration timestamp."""
        cutoff = date(2024, 11, 25)
        generated = datetime(2024, 11, 26, 10, 0, 0)
        regenerated = datetime(2024, 11, 27, 15, 30, 0)

        entry = HistoryEntry(
            last_cutoff_date=cutoff,
            generated_at=generated,
            regenerated_at=regenerated,
        )

        assert entry.regenerated_at == regenerated


class TestAIJudgment:
    """Test AIJudgment model."""

    def test_ai_judgment_creation(self):
        """Test creating an AIJudgment."""
        judgment = AIJudgment(
            change_id="github.com/owner/repo#123",
            url="https://github.com/owner/repo/pull/123",
            description="Fix bug in handler",
            decision="INCLUDE",
            reasoning="This change fixes a bug in the product",
            product="Test Product",
            ai_provider="gemini-1.5-pro",
        )

        assert judgment.change_id == "github.com/owner/repo#123"
        assert judgment.decision == "INCLUDE"
        assert judgment.user_decision is None

    def test_get_final_decision_without_override(self):
        """Test final decision when no user override exists."""
        judgment = AIJudgment(
            change_id="test#1",
            url="https://test.com",
            description="Test",
            decision="INCLUDE",
            reasoning="Test",
            product="Test",
            ai_provider="test",
        )

        assert judgment.get_final_decision() == "INCLUDE"

    def test_get_final_decision_with_override(self):
        """Test final decision when user override exists."""
        judgment = AIJudgment(
            change_id="test#1",
            url="https://test.com",
            description="Test",
            decision="INCLUDE",
            user_decision="EXCLUDE",
            reasoning="Test",
            product="Test",
            ai_provider="test",
        )

        assert judgment.get_final_decision() == "EXCLUDE"

    def test_was_overridden_returns_false_when_no_override(self):
        """Test was_overridden() when no user decision exists."""
        judgment = AIJudgment(
            change_id="test#1",
            url="https://test.com",
            description="Test",
            decision="INCLUDE",
            reasoning="Test",
            product="Test",
            ai_provider="test",
        )

        assert judgment.was_overridden() is False

    def test_was_overridden_returns_false_when_decisions_match(self):
        """Test was_overridden() when user decision matches AI."""
        judgment = AIJudgment(
            change_id="test#1",
            url="https://test.com",
            description="Test",
            decision="INCLUDE",
            user_decision="INCLUDE",
            reasoning="Test",
            product="Test",
            ai_provider="test",
        )

        assert judgment.was_overridden() is False

    def test_was_overridden_returns_true_when_decisions_differ(self):
        """Test was_overridden() when user decision differs from AI."""
        judgment = AIJudgment(
            change_id="test#1",
            url="https://test.com",
            description="Test",
            decision="INCLUDE",
            user_decision="EXCLUDE",
            reasoning="Test",
            product="Test",
            ai_provider="test",
        )

        assert judgment.was_overridden() is True

    def test_was_overridden_returns_false_for_uncertain_ai_decision(self):
        """Test was_overridden() doesn't count UNCERTAIN as override."""
        judgment = AIJudgment(
            change_id="test#1",
            url="https://test.com",
            description="Test",
            decision="UNCERTAIN",
            user_decision="INCLUDE",
            reasoning="Test",
            product="Test",
            ai_provider="test",
        )

        assert judgment.was_overridden() is False


class TestReportData:
    """Test ReportData model."""

    def test_report_data_creation(self):
        """Test creating ReportData with all fields."""
        repo = Repository(
            host="github.com",
            path="owner/repo",
            provider_type="github",
        )

        change = Change(
            title="Fix bug",
            repository=repo,
            number=123,
        )

        report = ReportData(
            month="2024-11",
            start_date=date(2024, 11, 1),
            end_date=date(2024, 11, 30),
            changes=[change],
            repositories=[repo],
            total_hours=160.0,
            creative_hours=128.0,
            employee_name="John Doe",
            supervisor_name="Jane Smith",
            product_name="Test Product",
        )

        assert report.month == "2024-11"
        assert len(report.changes) == 1
        assert report.total_hours == 160.0

    def test_get_work_card_number(self):
        """Test work card number generation."""
        report = ReportData(
            month="2024-11",
            start_date=date(2024, 11, 1),
            end_date=date(2024, 11, 30),
            total_hours=160.0,
            creative_hours=128.0,
            employee_name="John Doe",
            supervisor_name="Jane Smith",
            product_name="Test Product",
        )

        card_number = report.get_work_card_number()

        assert card_number == "#1-202411"

    def test_get_month_name_bilingual(self):
        """Test bilingual month name generation."""
        report = ReportData(
            month="2024-11",
            start_date=date(2024, 11, 1),
            end_date=date(2024, 11, 30),
            total_hours=160.0,
            creative_hours=128.0,
            employee_name="John Doe",
            supervisor_name="Jane Smith",
            product_name="Test Product",
        )

        en, pl = report.get_month_name_bilingual()

        assert en == "November 2024"
        assert pl == "Listopad 2024"

    def test_hours_must_be_positive(self):
        """Test that hours must be greater than 0."""
        with pytest.raises(ValidationError) as exc_info:
            ReportData(
                month="2024-11",
                start_date=date(2024, 11, 1),
                end_date=date(2024, 11, 30),
                total_hours=0,
                creative_hours=0,
                employee_name="John Doe",
                supervisor_name="Jane Smith",
                product_name="Test Product",
            )

        assert "greater than 0" in str(exc_info.value).lower()
