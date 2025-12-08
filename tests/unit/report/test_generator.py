"""Unit tests for iptax.report.generator module."""

from datetime import date

import pytest

from iptax.models import Change, ReportData, Repository
from iptax.report.generator import (
    generate_all,
    generate_markdown,
    generate_tax_report_pdf,
    generate_work_card_pdf,
)


@pytest.fixture
def github_repo():
    """Create a GitHub repository for testing."""
    return Repository(
        host="github.com",
        path="owner/repo",
        provider_type="github",
    )


@pytest.fixture
def gitlab_repo():
    """Create a GitLab repository for testing."""
    return Repository(
        host="gitlab.example.org",
        path="group/subgroup/project",
        provider_type="gitlab",
    )


@pytest.fixture
def basic_report(github_repo):
    """Create a basic ReportData for testing."""
    change = Change(
        title="Fix bug in handler",
        repository=github_repo,
        number=123,
    )

    return ReportData(
        month="2024-11",
        start_date=date(2024, 11, 1),
        end_date=date(2024, 11, 30),
        changes=[change],
        repositories=[github_repo],
        total_hours=160.0,
        creative_hours=128.0,
        creative_percentage=80,
        employee_name="John Doe",
        supervisor_name="Jane Smith",
        product_name="Test Product",
    )


class TestGenerateMarkdown:
    """Test generate_markdown function."""

    def test_generates_valid_markdown_structure(self, basic_report):
        """Test that markdown has correct structure with sections."""
        md = generate_markdown(basic_report)

        assert "## Changes" in md
        assert "## Projects" in md

    def test_formats_change_correctly(self, basic_report):
        """Test that change is formatted with title, reference, and URL."""
        md = generate_markdown(basic_report)

        # Should contain: * [Title (owner/repo#number)](url)
        assert "* [Fix bug in handler (owner/repo#123)]" in md
        assert "(https://github.com/owner/repo/pull/123)" in md

    def test_formats_repository_correctly(self, basic_report):
        """Test that repository is formatted with display name and URL."""
        md = generate_markdown(basic_report)

        # Should contain: * [owner / repo](url)
        assert "* [owner / repo](https://github.com/owner/repo)" in md

    def test_handles_multiple_changes(self, github_repo):
        """Test formatting with multiple changes."""
        changes = [
            Change(title="Fix bug A", repository=github_repo, number=1),
            Change(title="Add feature B", repository=github_repo, number=2),
            Change(title="Update docs C", repository=github_repo, number=3),
        ]

        report = ReportData(
            month="2024-11",
            start_date=date(2024, 11, 1),
            end_date=date(2024, 11, 30),
            changes=changes,
            repositories=[github_repo],
            total_hours=160.0,
            creative_hours=128.0,
            creative_percentage=80,
            employee_name="John Doe",
            supervisor_name="Jane Smith",
            product_name="Test Product",
        )

        md = generate_markdown(report)

        # All changes should be listed
        assert "Fix bug A (owner/repo#1)" in md
        assert "Add feature B (owner/repo#2)" in md
        assert "Update docs C (owner/repo#3)" in md

    def test_handles_multiple_repositories(self, github_repo, gitlab_repo):
        """Test formatting with multiple repositories."""
        change1 = Change(title="Change 1", repository=github_repo, number=1)
        change2 = Change(title="Change 2", repository=gitlab_repo, number=2)

        report = ReportData(
            month="2024-11",
            start_date=date(2024, 11, 1),
            end_date=date(2024, 11, 30),
            changes=[change1, change2],
            repositories=[github_repo, gitlab_repo],
            total_hours=160.0,
            creative_hours=128.0,
            creative_percentage=80,
            employee_name="John Doe",
            supervisor_name="Jane Smith",
            product_name="Test Product",
        )

        md = generate_markdown(report)

        # Both repositories should be listed
        assert "[owner / repo](https://github.com/owner/repo)" in md
        gitlab_url = "https://gitlab.example.org/group/subgroup/project"
        assert f"[group / subgroup / project]({gitlab_url})" in md

    def test_gitlab_merge_request_url_format(self, gitlab_repo):
        """Test that GitLab URLs use merge_requests format."""
        change = Change(title="Test MR", repository=gitlab_repo, number=456)

        report = ReportData(
            month="2024-11",
            start_date=date(2024, 11, 1),
            end_date=date(2024, 11, 30),
            changes=[change],
            repositories=[gitlab_repo],
            total_hours=160.0,
            creative_hours=128.0,
            creative_percentage=80,
            employee_name="John Doe",
            supervisor_name="Jane Smith",
            product_name="Test Product",
        )

        md = generate_markdown(report)

        # Should use GitLab MR URL format
        assert "/-/merge_requests/456" in md

    def test_ends_with_newline(self, basic_report):
        """Test that markdown content ends with newline."""
        md = generate_markdown(basic_report)

        assert md.endswith("\n")

    def test_empty_line_between_sections(self, basic_report):
        """Test that there's an empty line between Changes and Projects."""
        md = generate_markdown(basic_report)

        # Should have blank line between sections
        assert "## Changes\n\n" in md or "\n\n## Projects" in md


class TestGenerateWorkCardPdf:
    """Test generate_work_card_pdf function."""

    def test_generates_pdf_file(self, basic_report, tmp_path):
        """Test that Work Card PDF is generated."""
        output_path = tmp_path / "work_card.pdf"

        generate_work_card_pdf(basic_report, output_path)

        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_pdf_is_valid_pdf(self, basic_report, tmp_path):
        """Test that generated file is a valid PDF."""
        output_path = tmp_path / "work_card.pdf"

        generate_work_card_pdf(basic_report, output_path)

        # PDF files start with %PDF
        content = output_path.read_bytes()
        assert content.startswith(b"%PDF")


class TestGenerateTaxReportPdf:
    """Test generate_tax_report_pdf function."""

    def test_generates_pdf_file(self, basic_report, tmp_path):
        """Test that Tax Report PDF is generated."""
        output_path = tmp_path / "tax_report.pdf"

        generate_tax_report_pdf(basic_report, output_path)

        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_pdf_is_valid_pdf(self, basic_report, tmp_path):
        """Test that generated file is a valid PDF."""
        output_path = tmp_path / "tax_report.pdf"

        generate_tax_report_pdf(basic_report, output_path)

        # PDF files start with %PDF
        content = output_path.read_bytes()
        assert content.startswith(b"%PDF")


class TestGenerateAll:
    """Test generate_all function."""

    def test_creates_output_directory(self, basic_report, tmp_path):
        """Test that output directory is created if it doesn't exist."""
        output_dir = tmp_path / "reports" / "2024"
        assert not output_dir.exists()

        generate_all(basic_report, output_dir)

        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_generates_all_files(self, basic_report, tmp_path):
        """Test that all report files are generated."""
        output_dir = tmp_path / "reports"

        files = generate_all(basic_report, output_dir)

        # Should return list with all three files
        assert len(files) == 3
        filenames = [f.name for f in files]
        assert "2024-11 IP TAX Report.md" in filenames
        assert "2024-11 IP TAX Work Card.pdf" in filenames
        assert "2024-11 IP TAX Raport.pdf" in filenames
        assert all(f.exists() for f in files)

    def test_markdown_file_has_correct_content(self, basic_report, tmp_path):
        """Test that generated markdown file has correct content."""
        output_dir = tmp_path / "reports"

        files = generate_all(basic_report, output_dir)

        # Read and verify content
        md_content = files[0].read_text(encoding="utf-8")
        assert "## Changes" in md_content
        assert "## Projects" in md_content
        assert "Fix bug in handler" in md_content

    def test_fails_if_file_exists_without_force(self, basic_report, tmp_path):
        """Test that generation fails if file exists and force=False."""
        output_dir = tmp_path / "reports"

        # Generate first time
        generate_all(basic_report, output_dir)

        # Try to generate again without force
        with pytest.raises(FileExistsError, match="already exists"):
            generate_all(basic_report, output_dir, force=False)

    def test_overwrites_if_force_is_true(self, basic_report, tmp_path):
        """Test that file is overwritten if force=True."""
        output_dir = tmp_path / "reports"

        # Generate first time
        files1 = generate_all(basic_report, output_dir)

        # Modify the file
        files1[0].write_text("Modified content", encoding="utf-8")

        # Generate again with force
        files2 = generate_all(basic_report, output_dir, force=True)

        # Should succeed and overwrite
        assert files2[0] == files1[0]
        content = files2[0].read_text(encoding="utf-8")
        assert "Modified content" not in content
        assert "## Changes" in content

    def test_filename_format_for_different_months(self, basic_report, tmp_path):
        """Test filename format for different report months."""
        output_dir = tmp_path / "reports"

        # Test November 2024
        basic_report.month = "2024-11"
        files = generate_all(basic_report, output_dir)
        assert files[0].name == "2024-11 IP TAX Report.md"

        # Test January 2025
        basic_report.month = "2025-01"
        files = generate_all(basic_report, output_dir, force=True)
        assert files[0].name == "2025-01 IP TAX Report.md"
