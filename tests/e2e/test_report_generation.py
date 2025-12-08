"""E2E tests for report generation - validates actual PDF content using pdfplumber.

Corner case tests (format filtering, force overwrite, etc.) are covered by unit tests.
This file only contains e2e tests that validate actual PDF text extraction.
"""

from datetime import date
from pathlib import Path

import pdfplumber
import pytest

from iptax.models import Change, ReportData, Repository
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


@pytest.mark.e2e
class TestReportGeneration:
    """E2E tests for full report generation workflow with PDF content validation."""

    def test_full_report_generation_and_pdf_content(
        self, tmp_path: Path, sample_report_data: ReportData
    ):
        """
        Comprehensive test validating full report generation workflow.

        Validates:
        - All 3 files (MD + 2 PDFs) are generated
        - PDFs are valid PDF files
        - Markdown contains expected sections and content
        - Work Card PDF has bilingual content and correct work card number
        - Tax Report PDF has bilingual content and correct hours
        """
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        # Generate all output files
        generated_files = generate_all(
            sample_report_data,
            output_dir,
            format_type="all",
        )

        # 1. Verify all files generated
        assert len(generated_files) == 3
        file_names = {f.name for f in generated_files}
        assert "2024-11 IP TAX Report.md" in file_names
        assert "2024-11 IP TAX Work Card.pdf" in file_names
        assert "2024-11 IP TAX Raport.pdf" in file_names

        # 2. Verify all files exist and have content
        for file_path in generated_files:
            assert file_path.exists(), f"{file_path} should exist"
            assert file_path.stat().st_size > 0, f"{file_path} should not be empty"

        # 3. Verify PDF magic bytes
        work_card = output_dir / "2024-11 IP TAX Work Card.pdf"
        tax_report = output_dir / "2024-11 IP TAX Raport.pdf"
        assert work_card.read_bytes()[:4] == b"%PDF"
        assert tax_report.read_bytes()[:4] == b"%PDF"

        # 4. Verify Markdown content
        md_file = output_dir / "2024-11 IP TAX Report.md"
        md_content = md_file.read_text()
        assert "## Changes" in md_content
        assert "## Projects" in md_content
        assert "Add new feature for parsing" in md_content
        assert "acme/parser-core#101" in md_content  # GitHub format
        assert "acme/analyzer!42" in md_content  # GitLab format

        # 5. Extract and validate Work Card PDF content
        with pdfplumber.open(work_card) as pdf:
            work_card_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        # Bilingual headers
        assert "Nr Karty Utworu" in work_card_text  # Polish
        assert "Work Card" in work_card_text  # English

        # Work card number format: #1-YYYYMM
        assert "#1-202411" in work_card_text

        # Employee name
        assert "Jan Kowalski" in work_card_text

        # 6. Extract and validate Tax Report PDF content
        with pdfplumber.open(tax_report) as pdf:
            tax_report_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        # Bilingual content
        assert "Raport" in tax_report_text  # Polish
        assert "Report" in tax_report_text  # English

        # Hours values
        assert "160" in tax_report_text  # total_hours
        assert "128" in tax_report_text  # creative_hours

        # Employee name
        assert "Jan Kowalski" in tax_report_text
