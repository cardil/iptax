"""Interactive configuration wizard for iptax.

This module handles the interactive questionnaire-based configuration setup,
separated from the core configuration management logic.
"""

from collections.abc import Callable
from pathlib import Path

import questionary
from questionary.prompts.common import Choice

# All prompts use unsafe_ask() to propagate KeyboardInterrupt
# instead of returning None, allowing clean exit on Ctrl+C
from iptax.models import (
    MAX_PERCENTAGE,
    AIProviderConfig,
    AIProviderConfigBase,
    DidConfig,
    DisabledAIConfig,
    EmployeeInfo,
    Fields,
    GeminiProviderConfig,
    ProductConfig,
    ReportConfig,
    Settings,
    VertexAIProviderConfig,
    WorkdayConfig,
)


def run_interactive_wizard(
    defaults: Settings | None,
    list_providers_fn: Callable[[Path], list[str]],
) -> Settings:
    """Run interactive configuration wizard.

    Args:
        defaults: Optional existing settings to use as defaults
        list_providers_fn: Function to list did providers (callable)

    Returns:
        Configured Settings instance
    """
    questionary.print("Welcome to iptax configuration!", style="bold")
    questionary.print("")

    employee = _get_employee_info(defaults)
    product = _get_product_config(defaults)
    report = _get_report_config(defaults)
    ai = _get_ai_config(defaults)
    workday = _get_workday_config(defaults)
    did = _get_did_config(defaults, list_providers_fn)

    return Settings(
        employee=employee,
        product=product,
        report=report,
        ai=ai,
        workday=workday,
        did=did,
    )


def _get_employee_info(defaults: Settings | None) -> EmployeeInfo:
    """Get employee information interactively."""
    questionary.print("Employee Information:", style="bold")

    default_name = defaults.employee.name if defaults and defaults.employee else ""
    employee_name = questionary.text(
        "Employee name:",
        default=default_name,
        validate=lambda x: len(x.strip()) > 0 or "Name cannot be empty",
    ).unsafe_ask()

    default_supervisor = (
        defaults.employee.supervisor if defaults and defaults.employee else ""
    )
    supervisor_name = questionary.text(
        "Supervisor name:",
        default=default_supervisor,
        validate=lambda x: len(x.strip()) > 0 or "Name cannot be empty",
    ).unsafe_ask()

    return EmployeeInfo(name=employee_name, supervisor=supervisor_name)


def _get_product_config(defaults: Settings | None) -> ProductConfig:
    """Get product configuration interactively."""
    questionary.print("\nProduct Configuration:", style="bold")

    default_product = defaults.product.name if defaults else ""
    product_name = questionary.text(
        "Product name:",
        default=default_product,
        validate=lambda x: len(x.strip()) > 0 or "Product name cannot be empty",
    ).unsafe_ask()

    return ProductConfig(name=product_name)


def _get_report_config(defaults: Settings | None) -> ReportConfig:
    """Get report configuration interactively."""
    questionary.print("\nReport Settings:", style="bold")

    # Get defaults from model or existing config
    default_percentage = (
        defaults.report.creative_work_percentage
        if defaults
        else Fields(ReportConfig).creative_work_percentage.default
    )

    creative_percentage = questionary.text(
        f"Creative work percentage (0-{MAX_PERCENTAGE}) [{default_percentage}]:",
        default=str(default_percentage),
        validate=lambda x: (x.isdigit() and 0 <= int(x) <= MAX_PERCENTAGE)
        or f"Must be 0-{MAX_PERCENTAGE}",
    ).unsafe_ask()

    default_output_dir = (
        str(defaults.report.output_dir)
        if defaults
        else Fields(ReportConfig).output_dir.default
    )

    output_dir = questionary.text(
        f"Output directory [{default_output_dir}]:", default=default_output_dir
    ).unsafe_ask()

    return ReportConfig(
        output_dir=output_dir,
        creative_work_percentage=int(creative_percentage),
    )


def _get_ai_config(defaults: Settings | None) -> AIProviderConfig:
    """Get AI configuration interactively."""
    questionary.print("\nAI Provider Configuration:", style="bold")

    default_enable_ai = (
        not isinstance(defaults.ai, DisabledAIConfig) if defaults else True
    )
    enable_ai = questionary.confirm(
        "Enable AI filtering?", default=default_enable_ai
    ).unsafe_ask()

    if enable_ai:
        default_ai_config = defaults.ai if defaults else None
        return _configure_ai_provider(default_ai_config)
    return DisabledAIConfig()


def _configure_ai_provider(
    default_config: AIProviderConfig | None = None,
) -> AIProviderConfig:
    """Configure AI provider interactively.

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
    ).unsafe_ask()

    if provider == "gemini":
        return _configure_gemini(default_config)
    if provider == "vertex":
        return _configure_vertex(default_config)

    questionary.print(
        f"Unknown provider '{provider}', using disabled AI", style="yellow"
    )
    return DisabledAIConfig()


def _get_hints_list(default_config: AIProviderConfig | None) -> list[str]:
    """Get hints one at a time until empty input."""
    default_hints: list[str] = []
    if isinstance(default_config, AIProviderConfigBase):
        default_hints = list(default_config.hints)

    hints: list[str] = []

    questionary.print("Enter AI evaluation hints (empty to finish):", style="italic")

    hint_num = 1
    while True:
        # Pre-fill from defaults if available
        default_value = (
            default_hints[hint_num - 1] if hint_num <= len(default_hints) else ""
        )

        hint = questionary.text(
            f"  Hint {hint_num}:",
            default=default_value,
        ).unsafe_ask()

        if not hint.strip():
            break

        hints.append(hint.strip())
        hint_num += 1

    if hints:
        questionary.print(f"  ✓ {len(hints)} hint(s) configured", style="green")

    return hints


def _get_ai_advanced_options(
    default_config: AIProviderConfig | None,
) -> tuple[list[str], int, float]:
    """Get advanced AI options interactively.

    Args:
        default_config: Optional existing AI config for defaults

    Returns:
        Tuple of (hints, max_learnings, correction_ratio)
    """
    # Get default values from model
    default_max_learnings = Fields(AIProviderConfigBase).max_learnings.default
    default_correction_ratio = Fields(AIProviderConfigBase).correction_ratio.default

    questionary.print("\nAdvanced AI Options:", style="bold")

    # Default to True if any advanced options are already configured
    has_advanced_options = False
    if isinstance(default_config, AIProviderConfigBase):
        has_hints = bool(default_config.hints)
        has_custom_learnings = default_config.max_learnings != default_max_learnings
        has_custom_ratio = default_config.correction_ratio != default_correction_ratio
        has_advanced_options = has_hints or has_custom_learnings or has_custom_ratio

    configure_advanced = questionary.confirm(
        "Configure advanced AI options? (hints, learning settings)",
        default=has_advanced_options,
    ).unsafe_ask()

    if not configure_advanced:
        # Return current values or defaults
        if isinstance(default_config, AIProviderConfigBase):
            return (
                default_config.hints,
                default_config.max_learnings,
                default_config.correction_ratio,
            )
        return ([], default_max_learnings, default_correction_ratio)

    # Hints configuration - one at a time
    hints = _get_hints_list(default_config)

    # Max learnings
    current_max = (
        default_config.max_learnings
        if isinstance(default_config, AIProviderConfigBase)
        else default_max_learnings
    )
    max_learnings_input = questionary.text(
        f"Max learning entries for AI context (0-{MAX_PERCENTAGE}) [{current_max}]:",
        default=str(current_max),
        validate=lambda x: (x.isdigit() and 0 <= int(x) <= MAX_PERCENTAGE)
        or f"Must be 0-{MAX_PERCENTAGE}",
    ).unsafe_ask()
    max_learnings = int(max_learnings_input)

    # Correction ratio (as percentage for user-friendliness)
    current_ratio = (
        default_config.correction_ratio
        if isinstance(default_config, AIProviderConfigBase)
        else default_correction_ratio
    )
    current_percent = int(current_ratio * MAX_PERCENTAGE)
    ratio_input = questionary.text(
        f"Correction ratio % (0-{MAX_PERCENTAGE}) [{current_percent}]:",
        default=str(current_percent),
        validate=lambda x: (x.isdigit() and 0 <= int(x) <= MAX_PERCENTAGE)
        or f"Must be 0-{MAX_PERCENTAGE}",
    ).unsafe_ask()
    correction_ratio = int(ratio_input) / float(MAX_PERCENTAGE)

    return hints, max_learnings, correction_ratio


def _configure_gemini(default_config: AIProviderConfig | None) -> GeminiProviderConfig:
    """Configure Gemini API provider."""
    default_model = (
        default_config.model
        if isinstance(default_config, GeminiProviderConfig)
        else Fields(GeminiProviderConfig).model.default
    )
    default_api_key_env = (
        default_config.api_key_env
        if isinstance(default_config, GeminiProviderConfig)
        else Fields(GeminiProviderConfig).api_key_env.default
    )

    model = questionary.text(
        f"Model [{default_model}]:", default=default_model
    ).unsafe_ask()

    api_key_env = questionary.text(
        f"API key environment variable [{default_api_key_env}]:",
        default=default_api_key_env,
    ).unsafe_ask()

    default_use_env_file = (
        bool(default_config.api_key_file)
        if isinstance(default_config, GeminiProviderConfig)
        else False
    )

    use_env_file = questionary.confirm(
        "Use .env file for API key? (default: use system environment)",
        default=default_use_env_file,
    ).unsafe_ask()

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
        ).unsafe_ask()

    # Get advanced options
    hints, max_learnings, correction_ratio = _get_ai_advanced_options(default_config)

    return GeminiProviderConfig(
        model=model,
        api_key_env=api_key_env,
        api_key_file=api_key_file,
        hints=hints,
        max_learnings=max_learnings,
        correction_ratio=correction_ratio,
    )


def _configure_vertex(
    default_config: AIProviderConfig | None,
) -> VertexAIProviderConfig:
    """Configure Vertex AI provider."""
    default_model = (
        default_config.model
        if isinstance(default_config, VertexAIProviderConfig)
        else Fields(VertexAIProviderConfig).model.default
    )
    default_location = (
        default_config.location
        if isinstance(default_config, VertexAIProviderConfig)
        else Fields(VertexAIProviderConfig).location.default
    )
    default_project_id = (
        default_config.project_id
        if isinstance(default_config, VertexAIProviderConfig)
        else ""
    )

    model = questionary.text(
        f"Model [{default_model}]:", default=default_model
    ).unsafe_ask()

    project_id = questionary.text(
        "GCP Project ID:",
        default=default_project_id,
        validate=lambda x: len(x.strip()) > 0 or "Project ID cannot be empty",
    ).unsafe_ask()

    location = questionary.text(
        f"GCP Location [{default_location}]:", default=default_location
    ).unsafe_ask()

    default_credentials = (
        str(default_config.credentials_file)
        if isinstance(default_config, VertexAIProviderConfig)
        and default_config.credentials_file
        else ""
    )

    credentials_file = questionary.text(
        "Credentials file (optional, press Enter to skip):",
        default=default_credentials,
    ).unsafe_ask()

    # Get advanced options
    hints, max_learnings, correction_ratio = _get_ai_advanced_options(default_config)

    return VertexAIProviderConfig(
        model=model,
        project_id=project_id,
        location=location,
        credentials_file=credentials_file if credentials_file else None,
        hints=hints,
        max_learnings=max_learnings,
        correction_ratio=correction_ratio,
    )


def _get_workday_config(defaults: Settings | None) -> WorkdayConfig:
    """Get Workday configuration interactively."""
    questionary.print("\nWorkday Integration:", style="bold")

    default_enable_workday = defaults.workday.enabled if defaults else True
    enable_workday = questionary.confirm(
        "Enable Workday integration?", default=default_enable_workday
    ).unsafe_ask()

    if enable_workday:
        default_url = defaults.workday.url if defaults and defaults.workday.url else ""
        workday_url = questionary.text(
            "Workday URL (e.g., https://workday.example.org):",
            default=default_url,
            validate=lambda x: len(x.strip()) > 0 or "URL cannot be empty",
        ).unsafe_ask()

        default_auth = defaults.workday.auth if defaults else "sso+kerberos"
        auth_method = questionary.select(
            "Authentication method:",
            choices=[
                questionary.Choice(
                    "SSO with Kerberos (automatic, requires valid ticket)",
                    value="sso+kerberos",
                ),
                questionary.Choice(
                    "SSO with username/password (prompts for credentials)",
                    value="sso",
                ),
            ],
            default=default_auth,
        ).unsafe_ask()

        trusted_uris: list[str] = []
        if auth_method == "sso+kerberos":
            default_uris = (
                ",".join(defaults.workday.trusted_uris)
                if defaults and defaults.workday.trusted_uris
                else ""
            )
            uris_input = questionary.text(
                "Trusted URIs for Kerberos/SPNEGO (comma-separated, "
                "e.g., *.example.org,*.sso.example.org):",
                default=default_uris,
            ).unsafe_ask()
            if uris_input and uris_input.strip():
                trusted_uris = [u.strip() for u in uris_input.split(",") if u.strip()]

        return WorkdayConfig(
            enabled=True,
            url=workday_url,
            auth=auth_method,
            trusted_uris=trusted_uris,
        )
    return WorkdayConfig(enabled=False)


def _get_did_config(
    defaults: Settings | None,
    list_providers_fn: Callable[[Path], list[str]],
) -> DidConfig:
    """Get did configuration interactively."""
    questionary.print("\npsss/did Configuration:", style="bold")

    # Get default from model or existing config
    default_did_path = (
        str(defaults.did.config_path)
        if defaults
        else Fields(DidConfig).config_path.default
    )

    did_path = questionary.text(
        f"did config path [{default_did_path}]:", default=default_did_path
    ).unsafe_ask()

    # List available providers
    questionary.print("\nReading did config...", style="italic")
    available_providers = list_providers_fn(Path(did_path).expanduser())

    questionary.print("Found providers:", style="bold")

    # Determine checked state
    checked_providers = set(available_providers)
    if defaults:
        checked_providers = set(defaults.did.providers)

    # Let user select providers
    choices = [
        Choice(title=p, checked=p in checked_providers) for p in available_providers
    ]

    selected_providers = questionary.checkbox(
        "Select providers to use:",
        choices=choices,
    ).unsafe_ask()

    if not selected_providers:
        questionary.print("⚠ At least one provider must be selected", style="bold red")
        selected_providers = available_providers

    questionary.print("\nSelected providers:", style="bold")
    for provider in selected_providers:
        questionary.print(f"  ✓ {provider}", style="green")

    return DidConfig(
        config_path=did_path,
        providers=selected_providers,
    )
