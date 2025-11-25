"""Pydantic data models for iptax configuration and data structures.

This module defines all data models used throughout the iptax application,
including configuration settings, report data, and AI filtering structures.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    Discriminator,
    Field,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

# Constants
MAX_PERCENTAGE = 100


def _validate_not_empty_string(v: str) -> str:
    """Validate string is not empty or whitespace only."""
    if not v or not v.strip():
        raise ValueError("Field cannot be empty")
    return v.strip()


NonEmptyStr = Annotated[str, BeforeValidator(_validate_not_empty_string)]


class EmployeeInfo(BaseModel):
    """Employee information for report generation.

    Contains basic employee details used in generated reports,
    including the employee's name and their supervisor's name.
    """

    name: NonEmptyStr = Field(
        ...,
        description="Full name of the employee",
    )
    supervisor: NonEmptyStr = Field(
        ...,
        description="Full name of the employee's supervisor",
    )


def _validate_product_name(v: str) -> str:
    """Validate product name is not empty."""
    if not v or not v.strip():
        raise ValueError("Product name cannot be empty")
    return v.strip()


NonEmptyProductName = Annotated[str, BeforeValidator(_validate_product_name)]


class ProductConfig(BaseModel):
    """Product configuration for filtering changes.

    Defines the product name used by AI filtering to determine
    which code changes are relevant to the IP tax report.
    """

    name: NonEmptyProductName = Field(
        ...,
        description="Name of the product (e.g., 'Red Hat OpenShift Serverless')",
    )


class ReportConfig(BaseModel):
    """Report generation settings.

    Controls where reports are saved and what percentage of work
    is considered creative for tax calculation purposes.
    """

    output_dir: str = Field(
        default="~/Documents/iptax/{year}/",
        description=(
            "Output directory for reports. "
            "{year} will be replaced with report year"
        ),
    )
    creative_work_percentage: int = Field(
        default=80,
        description=f"Percentage of work considered creative (0-{MAX_PERCENTAGE})",
    )

    @field_validator("creative_work_percentage")
    @classmethod
    def validate_percentage(cls, v: int) -> int:
        """Validate percentage is in valid range."""
        if not 0 <= v <= MAX_PERCENTAGE:
            raise ValueError(
                f"Creative work percentage must be between 0 and {MAX_PERCENTAGE}"
            )
        return v

    def get_output_path(self, year: int) -> Path:
        """Get the resolved output path for a specific year.

        Args:
            year: The year to use for path substitution

        Returns:
            Resolved Path object with {year} placeholder replaced
        """
        path_str = self.output_dir.replace("{year}", str(year))
        return Path(path_str).expanduser()


class AIProviderConfigBase(BaseModel):
    """Base AI provider configuration.

    Common settings for all AI providers. Specific providers
    inherit from this class and add their own required fields.
    """

    provider: str = Field(
        ...,
        description="AI provider identifier (e.g., 'gemini', 'vertex')",
    )
    model: str = Field(
        ...,
        description="Model name to use for the provider",
    )
    enable_reasoning: bool = Field(
        default=True,
        description="Enable reasoning/explanation for AI decisions",
    )
    max_tokens: int | None = Field(
        default=None,
        description=(
            "Maximum tokens for AI responses "
            "(provider-specific defaults if None)"
        ),
    )


class GeminiProviderConfig(AIProviderConfigBase):
    """Google Gemini API provider configuration.

    Configuration for using Google's Gemini API directly.
    Requires an API key from Google AI Studio. The API key can be loaded from
    either an environment variable or a .env file.
    """

    provider: Literal["gemini"] = "gemini"
    model: str = Field(
        default="gemini-2.5-pro",
        description="Gemini model name",
    )
    api_key_env: str = Field(
        default="GEMINI_API_KEY",
        description="Environment variable name containing the API key",
    )
    api_key_file: str | None = Field(
        default=None,
        description=(
            "Path to .env file containing the API key "
            "(optional, uses system env if not specified)"
        ),
    )

    @field_validator("api_key_file")
    @classmethod
    def validate_api_key_file(cls, v: str | None) -> str | None:
        """Validate that API key file exists if specified."""
        if v is not None:
            path = Path(v).expanduser()
            if not path.exists():
                raise ValueError(f"API key file not found: {path}")
        return v


class VertexAIProviderConfig(AIProviderConfigBase):
    """Google Vertex AI provider configuration.

    Configuration for using Google's Vertex AI service on GCP.
    Requires GCP project ID and optionally a credentials file.
    """

    provider: Literal["vertex"] = "vertex"
    model: str = Field(
        default="gemini-2.5-pro",
        description="Vertex AI model name",
    )
    project_id: str = Field(
        ...,
        description="GCP project ID where Vertex AI is enabled",
    )
    location: str = Field(
        default="us-east5",
        description="GCP location/region for Vertex AI",
    )
    credentials_file: str | None = Field(
        default=None,
        description=(
            "Path to GCP service account credentials JSON file "
            "(uses default credentials if None)"
        ),
    )

    @field_validator("credentials_file")
    @classmethod
    def validate_credentials_file(cls, v: str | None) -> str | None:
        """Validate that credentials file exists if specified."""
        if v is not None:
            path = Path(v).expanduser()
            if not path.exists():
                raise ValueError(f"Credentials file not found: {path}")
        return v


class DisabledAIConfig(BaseModel):
    """Disabled AI configuration.

    Used when AI filtering is explicitly disabled.
    All changes will require manual review.
    """

    provider: Literal["disabled"] = "disabled"


# Discriminated union for AI provider configs
AIProviderConfig = Annotated[
    GeminiProviderConfig | VertexAIProviderConfig | DisabledAIConfig,
    Discriminator("provider"),
]


class WorkdayConfig(BaseModel):
    """Workday integration configuration.

    Settings for automated retrieval of work hours from Workday.
    Falls back to manual input if disabled or if automation fails.
    """

    enabled: bool = Field(
        default=False,
        description="Whether to enable Workday integration",
    )
    url: str | None = Field(
        default=None,
        description="Company Workday URL",
    )
    auth: Literal["saml"] = Field(
        default="saml",
        description="Authentication method (only SAML supported)",
    )

    @model_validator(mode="after")
    def validate_url_if_enabled(self) -> "WorkdayConfig":
        """Validate that URL is provided if Workday is enabled."""
        if self.enabled and not self.url:
            raise ValueError("url is required when Workday is enabled")
        return self


class DidConfig(BaseModel):
    """psss/did integration configuration.

    Settings for fetching merged PRs/MRs using the did SDK.
    Requires a configured ~/.did/config file with provider credentials.
    """

    config_path: str = Field(
        default="~/.did/config",
        description="Path to did config file",
    )
    providers: list[str] = Field(
        ...,  # Required, no default
        description="List of provider names to use (e.g., github.com, gitlab.cee)",
    )

    @field_validator("config_path", mode="wrap")
    @classmethod
    def validate_config_path_exists(
        cls, v: str, handler: ValidatorFunctionWrapHandler
    ) -> str:
        """Validate that did config file exists."""
        path = Path(v).expanduser()
        if not path.exists():
            raise ValueError(
                f"did config file not found at {path}. "
                "Please configure did first: https://github.com/psss/did#setup"
            )
        result: str = handler(v)
        return result

    @field_validator("providers", mode="wrap")
    @classmethod
    def validate_providers_not_empty(
        cls, v: list[str], handler: ValidatorFunctionWrapHandler
    ) -> list[str]:
        """Validate that at least one provider is specified."""
        if not v:
            raise ValueError("At least one provider must be specified")
        result: list[str] = handler(v)
        return result

    def get_config_path(self) -> Path:
        """Get the resolved config file path.

        Returns:
            Resolved Path object with ~ expanded
        """
        return Path(self.config_path).expanduser()


class Settings(BaseModel):
    """Main configuration settings for iptax.

    This is the root configuration model loaded from ~/.config/iptax/settings.yaml.
    It contains all settings needed for report generation including employee info,
    AI provider configuration, and integration settings.
    """

    employee: EmployeeInfo = Field(
        ...,
        description="Employee information",
    )
    product: ProductConfig = Field(
        ...,
        description="Product configuration",
    )
    report: ReportConfig = Field(
        default_factory=ReportConfig,
        description="Report generation settings",
    )
    ai: AIProviderConfig = Field(
        default=DisabledAIConfig(),
        description=(
            "AI provider configuration "
            "(use discriminated union based on provider type)"
        ),
    )
    workday: WorkdayConfig = Field(
        default_factory=WorkdayConfig,
        description="Workday integration configuration",
    )
    did: DidConfig = Field(
        ...,
        description="did integration configuration",
    )

    @classmethod
    def from_yaml_file(cls, path: Path) -> "Settings":
        """Load settings from a YAML file.

        Args:
            path: Path to the YAML settings file

        Returns:
            Settings instance loaded from the file

        Raises:
            FileNotFoundError: If the settings file doesn't exist
            TypeError: If the YAML is invalid or validation fails
        """
        if not path.exists():
            raise FileNotFoundError(f"Settings file not found: {path}")

        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise TypeError(
                f"Invalid settings file format in {path}: expected a mapping"
            )

        return cls(**data)

    def to_yaml_file(self, path: Path) -> None:
        """Save settings to a YAML file.

        Args:
            path: Path where the settings file should be saved
        """
        # Create parent directory if it doesn't exist
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and write to file
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                self.model_dump(mode="python", exclude_none=True),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        # Set file permissions to 600 (owner read/write only)
        path.chmod(0o600)


class HistoryEntry(BaseModel):
    """History entry for a single monthly report.

    Tracks when a report was generated and what cutoff date was used.
    This prevents duplicate or missing changes between reports.
    """

    last_cutoff_date: date = Field(
        ...,
        description=(
            "The end date used for this report "
            "(start date for next report will be this + 1 day)"
        ),
    )
    generated_at: datetime = Field(
        ...,
        description="When the report was first generated (UTC)",
    )
    regenerated_at: datetime | None = Field(
        default=None,
        description="When the report was last regenerated (UTC), if applicable",
    )


class Repository(BaseModel):
    """Repository information.

    Represents a code repository that can be formatted nicely
    and handles both GitHub (owner/repo) and GitLab (nested) formats.
    """

    host: str = Field(
        ...,
        description="Repository host (e.g., github.com, gitlab.cee.redhat.com)",
    )
    path: str = Field(
        ...,
        description=(
            "Repository path "
            "(e.g., 'owner/repo' or 'group/subgroup/repo' for GitLab)"
        ),
    )
    provider_type: Literal["github", "gitlab"] = Field(
        ...,
        description="Provider type (github or gitlab)",
    )

    @classmethod
    def from_full_path(
        cls, host: str, path: str, provider_type: Literal["github", "gitlab"]
    ) -> "Repository":
        """Create a Repository from host and path.

        Args:
            host: Repository host
            path: Repository path
            provider_type: Type of provider (github or gitlab)

        Returns:
            Repository instance
        """
        return cls(host=host, path=path, provider_type=provider_type)

    def get_display_name(self) -> str:
        """Get formatted display name for the repository.

        For GitHub: "owner / repo"
        For GitLab: "group / ... / repo" (shows full nested path)

        Returns:
            Formatted repository name with spaces around slashes
        """
        return " / ".join(self.path.split("/"))

    def get_url(self) -> str:
        """Get the base URL for the repository.

        Returns:
            Full repository URL
        """
        protocol = "https"
        return f"{protocol}://{self.host}/{self.path}"

    def __str__(self) -> str:
        """String representation."""
        return self.get_display_name()


class Change(BaseModel):
    """A code change (PR/MR) from the did SDK.

    Represents a single merged pull request or merge request
    that may be included in the report. Stores minimal information
    to avoid redundancy while allowing proper URL construction.
    """

    title: str = Field(
        ...,
        description="PR/MR title (cleaned of emoji)",
    )
    repository: Repository = Field(
        ...,
        description="Repository information",
    )
    number: int = Field(
        ...,
        description="PR/MR number",
        gt=0,
    )
    merged_at: datetime | None = Field(
        default=None,
        description="When the change was merged",
    )

    def get_change_id(self) -> str:
        """Get a unique identifier for this change.

        Returns:
            String in format "host/path#number" (e.g., "github.com/owner/repo#123")
        """
        return f"{self.repository.host}/{self.repository.path}#{self.number}"

    def get_url(self) -> str:
        """Get the full URL to the PR/MR.

        Constructs the correct URL based on provider type:
        - GitHub: https://host/owner/repo/pull/number
        - GitLab: https://host/path/-/merge_requests/number

        Returns:
            Full URL to the change
        """
        base_url = self.repository.get_url()

        if self.repository.provider_type == "github":
            return f"{base_url}/pull/{self.number}"
        # gitlab
        return f"{base_url}/-/merge_requests/{self.number}"

    def get_display_reference(self) -> str:
        """Get a short display reference for the change.

        Returns:
            String in format "repo#number" (e.g., "owner/repo#123")
        """
        return f"{self.repository.path}#{self.number}"


class AIJudgment(BaseModel):
    """AI judgment for a single code change.

    Stores the AI's decision about whether a change is relevant to the product,
    along with the reasoning and any user overrides.
    """

    change_id: str = Field(
        ...,
        description="Unique change identifier (host/path#number)",
    )
    url: str = Field(
        ...,
        description="Full PR/MR URL",
    )
    description: str = Field(
        ...,
        description="Full PR/MR description",
    )
    decision: Literal["INCLUDE", "EXCLUDE", "UNCERTAIN", "ERROR"] = Field(
        ...,
        description="AI's initial decision",
    )
    user_decision: Literal["INCLUDE", "EXCLUDE"] | None = Field(
        default=None,
        description="Final decision after user review (may differ from AI)",
    )
    reasoning: str = Field(
        ...,
        description="AI's explanation for the decision",
    )
    user_reasoning: str | None = Field(
        default=None,
        description="Optional human explanation when overriding",
    )
    product: str = Field(
        ...,
        description="Product name this judgment is for",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this judgment was made (UTC)",
    )
    ai_provider: str = Field(
        ...,
        description="AI provider and model used (e.g., 'gemini-1.5-pro')",
    )

    def get_final_decision(self) -> Literal["INCLUDE", "EXCLUDE", "UNCERTAIN", "ERROR"]:
        """Get the final decision, considering user override.

        Returns:
            The user's decision if provided, otherwise the AI's decision
        """
        return self.user_decision or self.decision

    def was_overridden(self) -> bool:
        """Check if the user overrode the AI's decision.

        Returns:
            True if user decision differs from AI decision
        """
        return (
            self.user_decision is not None
            and self.decision not in ("UNCERTAIN", "ERROR")
            and self.user_decision != self.decision
        )


class ReportData(BaseModel):
    """Compiled report data ready for generation.

    Contains all the information needed to generate the markdown
    and PDF reports for a specific month.
    """

    month: str = Field(
        ...,
        description="Report month in YYYY-MM format",
    )
    start_date: date = Field(
        ...,
        description="Start date of reporting period",
    )
    end_date: date = Field(
        ...,
        description="End date of reporting period",
    )
    changes: list[Change] = Field(
        default_factory=list,
        description="List of included changes",
    )
    repositories: list[Repository] = Field(
        default_factory=list,
        description="List of unique repositories",
    )
    total_hours: float = Field(
        ...,
        description="Total working hours in period",
        gt=0,
    )
    creative_hours: float = Field(
        ...,
        description="Creative work hours (calculated from total and percentage)",
        gt=0,
    )
    employee_name: str = Field(
        ...,
        description="Employee name",
    )
    supervisor_name: str = Field(
        ...,
        description="Supervisor name",
    )
    product_name: str = Field(
        ...,
        description="Product name",
    )

    def get_work_card_number(self) -> str:
        """Generate work card number for this report.

        Returns:
            Work card number in format #1-YYYYMM
        """
        month_numeric = self.month.replace("-", "")
        return f"#1-{month_numeric}"

    def get_month_name_bilingual(self) -> tuple[str, str]:
        """Get bilingual month name for the report.

        Returns:
            Tuple of (English name, Polish name)

        Note:
            This file must be saved with UTF-8 encoding to properly handle
            Polish characters in month names.
        """
        month_names = {
            "01": ("January", "Styczeń"),
            "02": ("February", "Luty"),
            "03": ("March", "Marzec"),
            "04": ("April", "Kwiecień"),
            "05": ("May", "Maj"),
            "06": ("June", "Czerwiec"),
            "07": ("July", "Lipiec"),
            "08": ("August", "Sierpień"),
            "09": ("September", "Wrzesień"),
            "10": ("October", "Październik"),
            "11": ("November", "Listopad"),
            "12": ("December", "Grudzień"),
        }

        year, month = self.month.split("-")
        en, pl = month_names.get(month, ("Unknown", "Nieznany"))
        return f"{en} {year}", f"{pl} {year}"
