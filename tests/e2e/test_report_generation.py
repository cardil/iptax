"""E2E tests for report generation - generates actual PDF and Markdown files."""

from datetime import date
from pathlib import Path

import pdfplumber
import pytest

from iptax.models import Change, Decision, Judgment, ReportData, Repository
from iptax.report.generator import generate_all


@pytest.fixture
def sample_report_data() -> ReportData:
    """Create sample report data for testing."""
    return ReportData(
        month="2024-11",
        start_date=date(2024, 11, 1),
        end_date=date(2024, 11, 30),
        changes=[
            Change(
                title="Add new feature for parsing",
                repository=Repository(
                    host="github.com",
                    path="acme/parser-core",
                    provider_type="github",
                ),
                number=101,
                url="https://github.com/acme/parser-core/pull/101",
            ),
            Change(
                title="Fix bug in analyzer",
                repository=Repository(
                    host="gitlab.com",
                    path="acme/analyzer",
                    provider_type="gitlab",
                ),
                number=42,
                url="https://gitlab.com/acme/analyzer/-/merge_requests/42",
            ),
        ],
        repositories=[
            Repository(
                host="github.com",
                path="acme/parser-core",
                provider_type="github",
            ),
            Repository(
                host="gitlab.com",
                path="acme/analyzer",
                provider_type="gitlab",
            ),
        ],
        total_hours=160.0,
        creative_hours=128.0,
        creative_percentage=80,
        employee_name="Jan Kowalski",
        supervisor_name="Anna Nowak",
        product_name="Acme Code Analysis Suite",
    )


@pytest.fixture
def sample_judgments(sample_report_data: ReportData) -> list[Judgment]:
    """Create sample judgments matching the report data changes."""
    return [
        Judgment(
            change_id=sample_report_data.changes[0].get_change_id(),
            decision=Decision.INCLUDE,
            reasoning="Core product feature",
            product=sample_report_data.product_name,
            user_decision=Decision.INCLUDE,
        ),
        Judgment(
            change_id=sample_report_data.changes[1].get_change_id(),
            decision=Decision.INCLUDE,
            reasoning="Bug fix for core component",
            product=sample_report_data.product_name,
            user_decision=Decision.INCLUDE,
        ),
    ]


@pytest.mark.e2e
class TestReportGeneration:
    """E2E tests for full report generation workflow."""

    def test_generates_all_output_files(
        self, tmp_path: Path, sample_report_data: ReportData
    ):
        """Test that all three output files (MD + 2 PDFs) are generated."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        generated_files = generate_all(
            sample_report_data,
            output_dir,
            format_type="all",
        )

        assert len(generated_files) == 3

        # Check file names match expected pattern
        file_names = {f.name for f in generated_files}
        assert "2024-11 IP TAX Report.md" in file_names
        assert "2024-11 IP TAX Work Card.pdf" in file_names
        assert "2024-11 IP TAX Raport.pdf" in file_names

        # Check all files exist and have content
        for file_path in generated_files:
            assert file_path.exists(), f"{file_path} should exist"
            assert file_path.stat().st_size > 0, f"{file_path} should not be empty"

    def test_markdown_contains_expected_content(
        self, tmp_path: Path, sample_report_data: ReportData
    ):
        """Test that Markdown report contains expected sections and content."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        generate_all(sample_report_data, output_dir, format_type="md")

        md_file = output_dir / "2024-11 IP TAX Report.md"
        assert md_file.exists()

        content = md_file.read_text()

        # Check for Changes section with links
        assert "## Changes" in content
        assert "Add new feature for parsing" in content
        assert "Fix bug in analyzer" in content
        # Format is owner/repo#number (GitHub) or owner/repo!number (GitLab)
        assert "acme/parser-core#101" in content
        assert "acme/analyzer!42" in content

        # Check for Projects section
        assert "## Projects" in content
        assert "acme / parser-core" in content
        assert "acme / analyzer" in content

    def test_pdf_files_are_valid(self, tmp_path: Path, sample_report_data: ReportData):
        """Test that generated PDFs are valid PDF files."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        generate_all(sample_report_data, output_dir, format_type="pdf")

        work_card = output_dir / "2024-11 IP TAX Work Card.pdf"
        tax_report = output_dir / "2024-11 IP TAX Raport.pdf"

        # Check PDF magic bytes
        assert work_card.read_bytes()[:4] == b"%PDF"
        assert tax_report.read_bytes()[:4] == b"%PDF"

        # Minimum size check (PDFs should be at least a few KB)
        assert work_card.stat().st_size > 1000
        assert tax_report.stat().st_size > 1000

    def test_only_markdown_format(self, tmp_path: Path, sample_report_data: ReportData):
        """Test generating only Markdown output."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        generated_files = generate_all(sample_report_data, output_dir, format_type="md")

        assert len(generated_files) == 1
        assert generated_files[0].suffix == ".md"

    def test_only_pdf_format(self, tmp_path: Path, sample_report_data: ReportData):
        """Test generating only PDF outputs."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        generated_files = generate_all(
            sample_report_data, output_dir, format_type="pdf"
        )

        assert len(generated_files) == 2
        assert all(f.suffix == ".pdf" for f in generated_files)

    def test_bilingual_content_in_pdfs(
        self, tmp_path: Path, sample_report_data: ReportData
    ):
        """Test that PDFs contain bilingual (Polish/English) content."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        generate_all(sample_report_data, output_dir, format_type="pdf")

        work_card = output_dir / "2024-11 IP TAX Work Card.pdf"
        tax_report = output_dir / "2024-11 IP TAX Raport.pdf"

        # Extract text from PDFs using pdfplumber
        with pdfplumber.open(work_card) as pdf:
            work_card_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        with pdfplumber.open(tax_report) as pdf:
            tax_report_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        # Work card should contain bilingual headers (Polish / English format)
        assert "Nr Karty Utworu" in work_card_text  # Polish
        assert "Work Card" in work_card_text  # English

        # Tax report should contain bilingual content
        assert "Raport" in tax_report_text  # Polish
        assert "Report" in tax_report_text  # English

    def test_work_card_number_format(
        self, tmp_path: Path, sample_report_data: ReportData
    ):
        """Test that work card number is correctly formatted."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        generate_all(sample_report_data, output_dir, format_type="pdf")

        work_card = output_dir / "2024-11 IP TAX Work Card.pdf"

        # Extract text from PDF using pdfplumber
        with pdfplumber.open(work_card) as pdf:
            work_card_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        # Work card number should be #1-YYYYMM format
        assert "#1-202411" in work_card_text

    def test_hours_in_tax_report(self, tmp_path: Path, sample_report_data: ReportData):
        """Test that hours appear correctly in tax report PDF."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        generate_all(sample_report_data, output_dir, format_type="pdf")

        tax_report = output_dir / "2024-11 IP TAX Raport.pdf"

        # Extract text from PDF using pdfplumber
        with pdfplumber.open(tax_report) as pdf:
            tax_report_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        # Tax report should contain the hours values
        assert "160" in tax_report_text  # total_hours
        assert "128" in tax_report_text  # creative_hours

    def test_different_month_formats(
        self, tmp_path: Path, sample_report_data: ReportData
    ):
        """Test report generation for different months."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        # Test with different month
        sample_report_data.month = "2025-01"
        sample_report_data.start_date = date(2025, 1, 1)
        sample_report_data.end_date = date(2025, 1, 31)

        generated_files = generate_all(
            sample_report_data, output_dir, format_type="all"
        )

        file_names = {f.name for f in generated_files}
        assert "2025-01 IP TAX Report.md" in file_names
        assert "2025-01 IP TAX Work Card.pdf" in file_names
        assert "2025-01 IP TAX Raport.pdf" in file_names

    def test_force_overwrite(self, tmp_path: Path, sample_report_data: ReportData):
        """Test that force flag allows overwriting existing files."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        # Generate files first time
        generate_all(sample_report_data, output_dir, format_type="all")

        md_file = output_dir / "2024-11 IP TAX Report.md"

        # Generate again with force=True
        generate_all(sample_report_data, output_dir, format_type="all", force=True)

        # File should still exist and have content
        assert md_file.exists()
        assert md_file.stat().st_size > 0

    def test_fails_without_force_on_existing(
        self, tmp_path: Path, sample_report_data: ReportData
    ):
        """Test that generation fails without force on existing files."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        # Generate files first time
        generate_all(sample_report_data, output_dir, format_type="all")

        # Try to generate again without force
        with pytest.raises(FileExistsError):
            generate_all(sample_report_data, output_dir, format_type="all")
