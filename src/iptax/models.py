"""Pydantic data models for iptax configuration and data structures.

This module defines all data models used throughout the iptax application,
including configuration settings, report data, and AI filtering structures.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
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
from pydantic.fields import FieldInfo


class Fields:
    """Proxy class for accessing Pydantic model field info via attributes.

    Enables syntax like `Fields(ReportConfig).output_dir.default` instead of
    `ReportConfig.model_fields["output_dir"].default`.

    This avoids conflicts with Pydantic's metaclass which intercepts
    class-level attribute access.

    Example:
        class MyConfig(BaseModel):
            name: str = Field(default="default_name")

        # Access default value
        default_name = Fields(MyConfig).name.default  # Returns "default_name"
    """

    def __init__(self, model_class: type[BaseModel]) -> None:
        """Initialize the accessor with a Pydantic model class."""
        self._model_class = model_class

    def __getattr__(self, name: str) -> FieldInfo:
        """Provide access to field info via attribute access."""
        return self._model_class.model_fields[name]


# Constants
MAX_PERCENTAGE = 100

# Bilingual month names for report generation
MONTH_NAMES_BILINGUAL = {
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


@dataclass(frozen=True)
class ReportDateRanges:
    """Date ranges for a report.

    Separates Workday (full month) and Did (skewed) date ranges.
    """

    workday_start: date
    workday_end: date
    did_start: date
    did_end: date

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"ReportDateRanges("
            f"workday={self.workday_start} to {self.workday_end}, "
            f"did={self.did_start} to {self.did_end})"
        )


def _validate_not_empty_string(v: str) -> str:
    """Validate string is not empty or whitespace only."""
    if not v or not v.strip():
        raise ValueError("Field cannot be empty")
    return v.strip()


NonEmptyStr = Annotated[str, BeforeValidator(_validate_not_empty_string)]


def _validate_product_name(v: str) -> str:
    """Validate product name is not empty."""
    if not v or not v.strip():
        raise ValueError("Product name cannot be empty")
    return v.strip()


NonEmptyProductName = Annotated[str, BeforeValidator(_validate_product_name)]


def _validate_file_exists(v: str | None, field_name: str) -> str | None:
    """Validate that file exists if path is specified.

    Args:
        v: File path or None
        field_name: Name of the field for error messages

    Returns:
        The original value (None if None was passed, str if valid path)

    Raises:
        ValueError: If file path is specified but doesn't exist
    """
    if v is not None:
        path = Path(v).expanduser()
        if not path.exists():
            raise ValueError(f"{field_name} not found: {path}")
    return v


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


class ProductConfig(BaseModel):
    """Product configuration for filtering changes.

    Defines the product name used by AI filtering to determine
    which code changes are relevant to the IP tax report.
    """

    name: NonEmptyProductName = Field(
        ...,
        description="Name of the product (e.g., 'Acme Fungear')",
    )


class ReportConfig(BaseModel):
    """Report generation settings.

    Controls where reports are saved and what percentage of work
    is considered creative for tax calculation purposes.
    """

    output_dir: str = Field(
        default="~/Documents/iptax/{year}/",
        description=(
            "Output directory for reports. " "{year} will be replaced with report year"
        ),
    )
    creative_work_percentage: int = Field(
        default=80,
        description=f"Percentage of work considered creative (0-{MAX_PERCENTAGE})",
    )

    @field_validator("creative_work_percentage")
    @classmethod
    def validate_percentage(cls, v: int) -> int:
        """Validate percentage is in valid range (1-100).

        Note: 0% is not allowed because IP tax reports require creative work.
        A report with 0% creative work defeats the purpose of IP tax deductions.
        """
        if not 1 <= v <= MAX_PERCENTAGE:
            raise ValueError(
                f"Creative work percentage must be between 1 and {MAX_PERCENTAGE}. "
                "IP tax reports require at least some creative work."
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
            "Maximum tokens for AI responses " "(provider-specific defaults if None)"
        ),
    )
    hints: list[str] = Field(
        default_factory=list,
        description="Optional hints to provide context to AI for evaluation",
    )
    max_learnings: int = Field(
        default=20,
        ge=0,
        le=100,
        description="Maximum number of learning entries for AI context",
    )
    correction_ratio: float = Field(
        default=0.75,
        description="Target ratio of corrections vs correct entries (0.0-1.0)",
    )

    @field_validator("correction_ratio")
    @classmethod
    def validate_correction_ratio(cls, v: float) -> float:
        """Validate correction ratio is in valid range."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Correction ratio must be between 0.0 and 1.0")
        return v


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
        return _validate_file_exists(v, "API key file")


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
        return _validate_file_exists(v, "Credentials file")


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

    Supported authentication methods:

    - "sso+kerberos": Fully automatic SSO with Kerberos/SPNEGO. Requires valid
        Kerberos ticket. The authentication flow is:
        1. Browser navigates to Workday
        2. Workday redirects via SAML to SSO/IdP (like Keycloak)
        3. SSO/IdP uses SPNEGO to authenticate with browser's Kerberos ticket
        4. SSO/IdP returns SAML assertion to Workday
        5. Session established
        Playwright needs Chromium args (--auth-server-allowlist,
        --auth-negotiate-delegate-allowlist) to enable SPNEGO for SSO domains
        specified in trusted_uris.

    - "sso": SSO with username/password fallback. Prompts for credentials
        in command-line which are then entered into the SSO login form.
        Use this if Kerberos tickets are not available or not accepted.
    """

    enabled: bool = Field(
        default=False,
        description="Whether to enable Workday integration",
    )
    url: str | None = Field(
        default=None,
        description="Company Workday URL (e.g., https://workday.example.org)",
    )
    auth: Literal["sso+kerberos", "sso"] = Field(
        default="sso+kerberos",
        description=(
            "Authentication method: "
            "'sso+kerberos' for automatic Kerberos/SPNEGO, "
            "'sso' for username/password prompt"
        ),
    )
    trusted_uris: list[str] = Field(
        default_factory=list,
        description=(
            "Trusted URIs for SPNEGO/Kerberos auth (used with 'sso+kerberos'). "
            "Used in Chromium's --auth-server-allowlist. "
            "Example: ['*.example.org', '*.sso.example.org']"
        ),
    )

    @model_validator(mode="after")
    def validate_url_if_enabled(self) -> "WorkdayConfig":
        """Validate that URL is provided if Workday is enabled."""
        if self.enabled and not self.url:
            raise ValueError("url is required when Workday is enabled")
        return self


class WorkdayCalendarEntry(BaseModel):
    """A single calendar entry from Workday.

    Represents one entry that was extracted from Workday's calendar API.
    Can be work hours, PTO, or holiday.
    """

    entry_date: date = Field(
        ...,
        description="Date of the entry",
    )
    title: str = Field(
        ...,
        description="Entry title (e.g., 'Work', 'Paid Holiday')",
    )
    entry_type: str = Field(
        ...,
        description=(
            "Entry type (e.g., 'Time Tracking', 'Time Off', "
            "'Holiday Calendar Entry Type')"
        ),
    )
    hours: float = Field(
        ...,
        description="Hours for this entry",
        ge=0,
    )


class WorkHours(BaseModel):
    """Work hours data from Workday.

    Contains working days, absence information, and total hours
    for a reporting period. Used for calculating creative work hours.
    """

    working_days: int = Field(
        ...,
        description="Number of working days in the period",
        ge=0,
    )
    absence_days: int = Field(
        default=0,
        description="Vacation, sick leave, holidays",
        ge=0,
    )
    total_hours: float = Field(
        ...,
        description="Total working hours",
        ge=0,
    )
    calendar_entries: list[WorkdayCalendarEntry] = Field(
        default_factory=list,
        description="Individual calendar entries from Workday (for validation)",
    )

    @property
    def effective_days(self) -> int:
        """Days actually worked."""
        return self.working_days - self.absence_days

    @property
    def effective_hours(self) -> float:
        """Hours actually worked (assuming 8h/day for absences)."""
        return self.total_hours - (self.absence_days * 8.0)


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

        # Convert to dict, excluding defaults but preserving discriminator fields
        data = self.model_dump(mode="python", exclude_none=True, exclude_defaults=True)

        # Ensure AI provider discriminator is preserved
        if "ai" in data and isinstance(
            self.ai, (GeminiProviderConfig, VertexAIProviderConfig)
        ):
            data["ai"]["provider"] = self.ai.provider

        # Convert to dict and write to file
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
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
        description="Repository host (e.g., github.com, gitlab.example.org)",
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
            String in format "repo#number" for GitHub (e.g., "owner/repo#123")
            or "repo!number" for GitLab (e.g., "group/repo!456")
        """
        symbol = "!" if self.repository.provider_type == "gitlab" else "#"
        return f"{self.repository.path}{symbol}{self.number}"


class Decision(str, Enum):
    """Decision for a change (from AI or user)."""

    INCLUDE = "INCLUDE"  # Change directly contributes to the product
    EXCLUDE = "EXCLUDE"  # Change is unrelated to the product
    UNCERTAIN = "UNCERTAIN"  # Cannot determine with confidence


class Judgment(BaseModel):
    """AI judgment for a single change.

    Complete judgment with all metadata for storage and review.
    """

    change_id: str = Field(..., description="Unique identifier: owner/repo#number")
    url: str = Field(
        default="",
        description="Full PR/MR URL",
    )
    description: str = Field(
        default="",
        description="Full PR/MR description",
    )
    decision: Decision = Field(
        ...,
        description="AI's initial decision",
    )
    user_decision: Decision | None = Field(None, description="User override decision")
    reasoning: str = Field(..., description="AI's reasoning for the decision")
    user_reasoning: str | None = Field(
        None, description="User's reasoning for override"
    )
    product: str = Field(..., description="Product name this judgment is for")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this judgment was made (UTC)",
    )
    ai_provider: str = Field(
        default="",
        description="AI provider and model used (e.g., 'gemini/gemini-2.5-pro')",
    )

    @property
    def was_corrected(self) -> bool:
        """Return True if user overrode the AI's decision."""
        return self.final_decision != self.decision

    @property
    def final_decision(self) -> Decision:
        """Return user decision if set, otherwise AI decision."""
        return self.user_decision if self.user_decision is not None else self.decision

    def was_overridden(self) -> bool:
        """Check if the user overrode the AI's decision.

        Returns:
            True if user decision differs from AI decision
        """
        if self.user_decision is None:
            return False
        if self.decision == Decision.UNCERTAIN:
            return False
        return self.user_decision != self.decision


class InFlightReport(BaseModel):
    """In-flight report data being collected and reviewed.

    Stores all data needed for a monthly report while it's being
    prepared, before final generation. Allows users to collect data,
    run AI filtering, and review across multiple sessions.
    """

    month: str = Field(
        ...,
        description="Report month in YYYY-MM format",
    )
    workday_start: date = Field(
        ...,
        description="Start date for Workday data collection",
    )
    workday_end: date = Field(
        ...,
        description="End date for Workday data collection",
    )
    changes_since: date = Field(
        ...,
        description="Start date for Did changes (skewed based on last report)",
    )
    changes_until: date = Field(
        ...,
        description="End date for Did changes (typically today)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this in-flight report was created (UTC)",
    )
    changes: list[Change] = Field(
        default_factory=list,
        description="Did changes (PRs/MRs) collected",
    )
    judgments: list[Judgment] = Field(
        default_factory=list,
        description="AI judgments for changes (empty until AI runs)",
    )
    workday_entries: list[WorkdayCalendarEntry] = Field(
        default_factory=list,
        description="Workday calendar entries for validation",
    )
    workday_validated: bool = Field(
        default=False,
        description="Whether Workday data has been validated for completeness",
    )
    total_hours: float | None = Field(
        default=None,
        description="Total work hours from Workday (if collected)",
    )
    working_days: int | None = Field(
        default=None,
        description="Working days from Workday (if collected)",
    )
    absence_days: int | None = Field(
        default=None,
        description="Absence days from Workday (if collected)",
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
    total_hours: int = Field(
        ...,
        description="Total working hours in period (rounded to whole hours)",
        gt=0,
    )
    creative_hours: int = Field(
        ...,
        description="Creative work hours (calculated from total and percentage)",
        gt=0,
    )
    creative_percentage: int = Field(
        ...,
        description="Percentage of work considered creative",
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
        year, month = self.month.split("-")
        en, pl = MONTH_NAMES_BILINGUAL.get(month, ("Unknown", "Nieznany"))
        return f"{en} {year}", f"{pl} {year}"


# Cache statistics models


@dataclass
class AICacheStats:
    """AI judgment cache statistics for display."""

    total_judgments: int
    corrected_count: int
    correct_count: int
    correction_rate: float
    products: list[str]
    oldest_judgment: str | None
    newest_judgment: str | None
    cache_path: Path
    cache_size_bytes: int


@dataclass
class HistoryCacheStats:
    """Report history statistics for display."""

    total_reports: int
    entries: dict[str, HistoryEntry]
    history_path: Path
    history_size_bytes: int


@dataclass
class InflightCacheStats:
    """In-flight cache statistics for display."""

    active_reports: int
    months: list[str]
    cache_dir: Path
