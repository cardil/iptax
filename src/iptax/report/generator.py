"""Report generators for iptax.

Generates output files (Markdown and PDFs) from compiled ReportData.
"""

from datetime import date
from importlib import resources
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from iptax.models import ReportData
from iptax.report.fonts import generate_font_face_css
from iptax.workday.validation import validate_workday_coverage

# Template directory path
TEMPLATES_DIR = resources.files("iptax.report") / "templates"


def generate_markdown(report: ReportData) -> str:
    """Generate markdown report content.

    Creates a markdown document with three sections:
    1. Summary: Report statistics (period, hours, changes, workday coverage)
    2. Changes: List of included changes with links
    3. Projects: List of unique repositories

    Args:
        report: Compiled report data

    Returns:
        Markdown content as string
    """
    lines = []

    # Summary section - use list format for better rendering
    lines.append("## Summary\n")
    lines.append(f"- **Product:** {report.product_name}")
    lines.append(f"- **Employee:** {report.employee_name}")
    lines.append(f"- **Supervisor:** {report.supervisor_name}")
    lines.append(f"- **Report Period:** {report.month}")
    lines.append(
        f"- **Changes Range:** {report.changes_since} to {report.changes_until}"
    )

    # Calculate working days from total hours (assuming 8-hour days)
    working_days = report.total_hours // 8
    lines.append(f"- **Work Time:** {working_days} days, {report.total_hours} hours")
    lines.append(
        f"- **Creative Work:** {report.creative_hours} hours "
        f"({report.creative_percentage}%)"
    )

    # Check for missing workday coverage
    if report.workday_entries:
        missing = validate_workday_coverage(
            report.workday_entries, report.start_date, report.end_date
        )
        if missing:
            lines.append(
                f"- **⚠ Work Time Coverage:** INCOMPLETE ({len(missing)} "
                f"day{'s' if len(missing) != 1 else ''} missing)"
            )
            for day in missing:
                day_str = day.strftime("%Y-%m-%d (%A)")
                lines.append(f"  - {day_str}")

    lines.append("")  # Empty line between sections

    # Changes section
    lines.append("## Changes\n")
    for change in report.changes:
        # Format: * [Title (owner/repo#number)](url)
        ref = change.get_display_reference()
        url = change.get_url()
        lines.append(f"* [{change.title} ({ref})]({url})")

    lines.append("")  # Empty line between sections

    # Projects section
    lines.append("## Projects\n")
    for repo in report.repositories:
        # Format: * [owner / repo](url)
        display_name = repo.get_display_name()
        url = repo.get_url()
        lines.append(f"* [{display_name}]({url})")

    # Ensure file ends with newline
    lines.append("")

    return "\n".join(lines)


def _load_styles() -> str:
    """Load CSS styles from templates directory with embedded fonts.

    Prepends @font-face rules for Red Hat Text font (auto-downloaded to cache)
    to the base styles. This ensures consistent font rendering in PDFs.

    Returns:
        CSS content with font-face rules and base styles
    """
    styles_path = TEMPLATES_DIR / "styles.css"
    base_styles = styles_path.read_text(encoding="utf-8")

    # Prepend font-face CSS rules
    font_css = generate_font_face_css()
    return f"{font_css}\n\n{base_styles}"


def _create_jinja_env() -> Environment:
    """Create Jinja2 environment configured for templates.

    Returns:
        Configured Jinja2 environment
    """
    # Use a traversable-compatible loader
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )


def _render_html(template_name: str, context: dict) -> str:
    """Render HTML from a template.

    Args:
        template_name: Name of the template file
        context: Template context dictionary

    Returns:
        Rendered HTML string
    """
    env = _create_jinja_env()
    template = env.get_template(template_name)
    return template.render(**context)


def _html_to_pdf(html_content: str, output_path: Path) -> None:
    """Convert HTML to PDF using WeasyPrint.

    Args:
        html_content: Rendered HTML string
        output_path: Path where PDF should be saved
    """
    html = HTML(string=html_content)
    html.write_pdf(output_path)


def generate_work_card_html(
    report: ReportData,
    preparation_date: date | None = None,
) -> str:
    """Generate Work Card HTML for debugging/preview.

    Args:
        report: Compiled report data
        preparation_date: Date of preparation (defaults to today)

    Returns:
        Rendered HTML string
    """
    if preparation_date is None:
        preparation_date = date.today()

    formatted_date = preparation_date.strftime("%b %d, %Y")
    styles = _load_styles()

    context = {
        "report": report,
        "preparation_date": formatted_date,
        "styles": styles,
    }

    return _render_html("work_card.html", context)


def generate_tax_report_html(report: ReportData) -> str:
    """Generate Tax Report HTML for debugging/preview.

    Args:
        report: Compiled report data

    Returns:
        Rendered HTML string
    """
    month_name_en, month_name_pl = report.get_month_name_bilingual()
    hours_per_day = 8
    working_days = int(report.total_hours / hours_per_day)
    styles = _load_styles()

    context = {
        "report": report,
        "month_name_en": month_name_en,
        "month_name_pl": month_name_pl,
        "working_days": working_days,
        "creative_percentage": report.creative_percentage,
        "styles": styles,
    }

    return _render_html("tax_report.html", context)


def generate_work_card_pdf(
    report: ReportData,
    output_path: Path,
    preparation_date: date | None = None,
) -> None:
    """Generate Work Card PDF.

    Creates a bilingual (English/Polish) work card document containing:
    - Work card number and preparation date
    - Author information
    - Co-authors (repository list)
    - Title and description of work
    - List of changes

    Args:
        report: Compiled report data
        output_path: Path where PDF should be saved
        preparation_date: Date of preparation (defaults to today)
    """
    html_content = generate_work_card_html(report, preparation_date)
    _html_to_pdf(html_content, output_path)


def generate_tax_report_pdf(
    report: ReportData,
    output_path: Path,
) -> None:
    """Generate Tax Report PDF.

    Creates a bilingual (English/Polish) tax report document containing:
    - Report period (month/year)
    - Employee and supervisor information
    - Work hours breakdown (total and creative)
    - Co-authors (repository list)
    - Declaration and acceptance sections

    Args:
        report: Compiled report data
        output_path: Path where PDF should be saved
    """
    html_content = generate_tax_report_html(report)
    _html_to_pdf(html_content, output_path)


# Valid format types for output generation
VALID_FORMAT_TYPES = ("all", "md", "pdf")


def generate_all(
    report: ReportData,
    output_dir: Path,
    force: bool = False,
    format_type: str = "all",
) -> list[Path]:
    """Generate all report files (MD + PDFs).

    Creates output directory if it doesn't exist. Generates:
    - Markdown report (format: "all" or "md")
    - Work Card PDF (format: "all" or "pdf")
    - Tax Report PDF (format: "all" or "pdf")

    Args:
        report: Compiled report data
        output_dir: Directory where files should be saved
        force: If True, overwrite existing files. If False, raise error if files exist.
        format_type: Output format - "all", "md", or "pdf"

    Returns:
        List of paths to generated files

    Raises:
        ValueError: If format_type is not valid
        FileExistsError: If files exist and force=False
    """
    # Validate format_type
    if format_type not in VALID_FORMAT_TYPES:
        raise ValueError(
            f"Invalid format_type '{format_type}'. "
            f"Must be one of: {', '.join(VALID_FORMAT_TYPES)}"
        )

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filenames based on report month
    month_part = report.month  # Format: YYYY-MM

    # Collect all file paths that will be generated
    files_to_generate: list[tuple[Path, str]] = []

    if format_type in ("all", "md"):
        md_path = output_dir / f"{month_part} IP TAX Report.md"
        files_to_generate.append((md_path, "Markdown report"))

    if format_type in ("all", "pdf"):
        work_card_path = output_dir / f"{month_part} IP TAX Work Card.pdf"
        tax_report_path = output_dir / f"{month_part} IP TAX Raport.pdf"
        files_to_generate.append((work_card_path, "Work Card PDF"))
        files_to_generate.append((tax_report_path, "Tax Report PDF"))

    # Check all files BEFORE writing any (fail-fast for partial output prevention)
    if not force:
        for path, description in files_to_generate:
            if path.exists():
                raise FileExistsError(
                    f"{description} already exists: {path}. Use --force to overwrite."
                )

    # Now generate all files
    generated_files: list[Path] = []

    if format_type in ("all", "md"):
        md_path = output_dir / f"{month_part} IP TAX Report.md"
        md_content = generate_markdown(report)
        md_path.write_text(md_content, encoding="utf-8")
        generated_files.append(md_path)

    if format_type in ("all", "pdf"):
        work_card_path = output_dir / f"{month_part} IP TAX Work Card.pdf"
        generate_work_card_pdf(report, work_card_path)
        generated_files.append(work_card_path)

        tax_report_path = output_dir / f"{month_part} IP TAX Raport.pdf"
        generate_tax_report_pdf(report, tax_report_path)
        generated_files.append(tax_report_path)

    return generated_files
