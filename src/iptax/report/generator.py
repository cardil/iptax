"""Report generators for iptax.

Generates output files (Markdown and PDFs) from compiled ReportData.
"""

from pathlib import Path

from iptax.models import ReportData


def generate_markdown(report: ReportData) -> str:
    """Generate markdown report content.

    Creates a markdown document with two sections:
    1. Changes: List of included changes with links
    2. Projects: List of unique repositories

    Args:
        report: Compiled report data

    Returns:
        Markdown content as string
    """
    lines = []

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


def generate_work_card_pdf(report: ReportData, output_path: Path) -> None:
    """Generate Work Card PDF.

    Args:
        report: Compiled report data
        output_path: Path where PDF should be saved

    Raises:
        NotImplementedError: This functionality is not yet implemented
    """
    raise NotImplementedError("Work Card PDF generation not yet implemented")


def generate_tax_report_pdf(report: ReportData, output_path: Path) -> None:
    """Generate Tax Report PDF.

    Args:
        report: Compiled report data
        output_path: Path where PDF should be saved

    Raises:
        NotImplementedError: This functionality is not yet implemented
    """
    raise NotImplementedError("Tax Report PDF generation not yet implemented")


def generate_all(
    report: ReportData,
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Generate all report files (MD + PDFs).

    Creates output directory if it doesn't exist. Generates:
    - Markdown report
    - Work Card PDF (when implemented)
    - Tax Report PDF (when implemented)

    Args:
        report: Compiled report data
        output_dir: Directory where files should be saved
        force: If True, overwrite existing files. If False, raise error if files exist.

    Returns:
        List of paths to generated files

    Raises:
        FileExistsError: If files exist and force=False
        NotImplementedError: PDF generation not yet implemented
    """
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filenames based on report month
    month_part = report.month  # Format: YYYY-MM
    md_filename = f"{month_part} IP TAX Report.md"
    md_path = output_dir / md_filename

    # Check if file exists
    if md_path.exists() and not force:
        raise FileExistsError(
            f"Markdown report already exists: {md_path}. Use --force to overwrite."
        )

    # Generate markdown
    md_content = generate_markdown(report)
    md_path.write_text(md_content, encoding="utf-8")

    # PDF generation will be added in future tasks
    # For now, return just the markdown file
    return [md_path]
