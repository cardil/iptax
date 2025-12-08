"""Report compiler for iptax.

Compiles InFlightReport and Settings into final ReportData ready for generation.
"""

from iptax.models import (
    Decision,
    DisabledAIConfig,
    InFlightReport,
    ReportData,
    Repository,
    Settings,
)


def compile_report(inflight: InFlightReport, settings: Settings) -> ReportData:
    """Compile a ReportData from in-flight report and settings.

    Filters changes to include only those accepted (either explicitly by user
    or by AI). All changes must have judgments (unless AI is disabled), and
    all UNCERTAIN judgments must be resolved by user.

    Args:
        inflight: In-flight report with changes, judgments, and hours data
        settings: Application settings with employee info and report config

    Returns:
        Compiled ReportData ready for report generation

    Raises:
        ValueError: If required data is missing or inconsistent
    """
    # Validate required data
    if inflight.total_hours is None:
        raise ValueError("Cannot compile report: total_hours is missing")

    if not inflight.changes:
        raise ValueError("Cannot compile report: no changes found")

    # Build judgment lookup map
    judgment_map = {j.change_id: j for j in inflight.judgments}

    # Check if AI is enabled
    ai_enabled = not isinstance(settings.ai, DisabledAIConfig)

    # Validate and filter changes
    included_changes = []
    for change in inflight.changes:
        change_id = change.get_change_id()
        judgment = judgment_map.get(change_id)

        if judgment is None:
            if ai_enabled:
                # AI is enabled but no judgment exists - this is an error
                raise ValueError(
                    f"Change {change_id} has no judgment. "
                    "Run AI filtering or review before compiling report."
                )
            # AI disabled: include all changes
            included_changes.append(change)
            continue

        # Check if UNCERTAIN is unresolved
        if judgment.final_decision == Decision.UNCERTAIN:
            raise ValueError(
                f"Change {change_id} has UNCERTAIN judgment without user decision. "
                "Complete review before compiling report."
            )

        # Include only INCLUDE decisions
        if judgment.final_decision == Decision.INCLUDE:
            included_changes.append(change)
        # EXCLUDE: skip (not an error)

    if not included_changes:
        raise ValueError(
            "Cannot compile report: no changes were included after filtering. "
            "Review judgments or add changes."
        )

    # Extract unique repositories from included changes
    repo_map: dict[str, Repository] = {}
    for change in included_changes:
        repo_key = f"{change.repository.host}/{change.repository.path}"
        if repo_key not in repo_map:
            repo_map[repo_key] = change.repository

    repositories = sorted(
        repo_map.values(),
        key=lambda r: (r.host, r.path),
    )

    # Calculate creative hours
    creative_percentage = settings.report.creative_work_percentage
    creative_hours = inflight.total_hours * (creative_percentage / 100.0)

    # Build ReportData
    return ReportData(
        month=inflight.month,
        start_date=inflight.workday_start,
        end_date=inflight.workday_end,
        changes=included_changes,
        repositories=repositories,
        total_hours=inflight.total_hours,
        creative_hours=creative_hours,
        creative_percentage=creative_percentage,
        employee_name=settings.employee.name,
        supervisor_name=settings.employee.supervisor,
        product_name=settings.product.name,
    )
