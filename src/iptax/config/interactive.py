"""Interactive configuration wizard for iptax.

This module handles the interactive questionnaire-based configuration setup,
separated from the core configuration management logic.
"""

from collections.abc import Callable
from pathlib import Path

import questionary
from questionary.prompts.common import Choice

from iptax.models import (
    MAX_PERCENTAGE,
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
    ).ask()

    default_supervisor = (
        defaults.employee.supervisor if defaults and defaults.employee else ""
    )
    supervisor_name = questionary.text(
        "Supervisor name:",
        default=default_supervisor,
        validate=lambda x: len(x.strip()) > 0 or "Name cannot be empty",
    ).ask()

    return EmployeeInfo(name=employee_name, supervisor=supervisor_name)


def _get_product_config(defaults: Settings | None) -> ProductConfig:
    """Get product configuration interactively."""
    questionary.print("\nProduct Configuration:", style="bold")

    default_product = defaults.product.name if defaults else ""
    product_name = questionary.text(
        "Product name:",
        default=default_product,
        validate=lambda x: len(x.strip()) > 0 or "Product name cannot be empty",
    ).ask()

    return ProductConfig(name=product_name)


def _get_report_config(defaults: Settings | None) -> ReportConfig:
    """Get report configuration interactively."""
    questionary.print("\nReport Settings:", style="bold")

    # Get defaults from model or existing config
    if defaults:
        default_percentage = defaults.report.creative_work_percentage
    else:
        default_percentage = ReportConfig.model_fields[
            "creative_work_percentage"
        ].default

    creative_percentage = questionary.text(
        f"Creative work percentage (0-{MAX_PERCENTAGE}) [{default_percentage}]:",
        default=str(default_percentage),
        validate=lambda x: (x.isdigit() and 0 <= int(x) <= MAX_PERCENTAGE)
        or f"Must be 0-{MAX_PERCENTAGE}",
    ).ask()

    if defaults:
        default_output_dir = str(defaults.report.output_dir)
    else:
        default_output_dir = ReportConfig.model_fields["output_dir"].default

    output_dir = questionary.text(
        f"Output directory [{default_output_dir}]:", default=default_output_dir
    ).ask()

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
    ).ask()

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
    ).ask()

    if provider == "gemini":
        return _configure_gemini(default_config)
    if provider == "vertex":
        return _configure_vertex(default_config)

    questionary.print(
        f"Unknown provider '{provider}', using disabled AI", style="yellow"
    )
    return DisabledAIConfig()


def _configure_gemini(default_config: AIProviderConfig | None) -> GeminiProviderConfig:
    """Configure Gemini API provider."""
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


def _configure_vertex(
    default_config: AIProviderConfig | None,
) -> VertexAIProviderConfig:
    """Configure Vertex AI provider."""
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
        "Credentials file (optional, press Enter to skip):",
        default=default_credentials,
    ).ask()

    return VertexAIProviderConfig(
        model=model,
        project_id=project_id,
        location=location,
        credentials_file=credentials_file if credentials_file else None,
    )


def _get_workday_config(defaults: Settings | None) -> WorkdayConfig:
    """Get Workday configuration interactively."""
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
        return WorkdayConfig(enabled=True, url=workday_url)
    return WorkdayConfig(enabled=False)


def _get_did_config(
    defaults: Settings | None,
    list_providers_fn: Callable[[Path], list[str]],
) -> DidConfig:
    """Get did configuration interactively."""
    questionary.print("\npsss/did Configuration:", style="bold")

    # Get default from model or existing config
    if defaults:
        default_did_path = str(defaults.did.config_path)
    else:
        default_did_path = DidConfig.model_fields["config_path"].default

    did_path = questionary.text(
        f"did config path [{default_did_path}]:", default=default_did_path
    ).ask()

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
    ).ask()

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
