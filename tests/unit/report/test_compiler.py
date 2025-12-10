"""Unit tests for iptax.report.compiler module."""

from datetime import UTC, date, datetime

import pytest

from iptax.models import (
    Change,
    Decision,
    DidConfig,
    DisabledAIConfig,
    EmployeeInfo,
    GeminiProviderConfig,
    InFlightReport,
    Judgment,
    ProductConfig,
    ReportConfig,
    Repository,
    Settings,
)
from iptax.report.compiler import compile_report


@pytest.fixture
def basic_settings(tmp_path):
    """Create basic Settings for testing."""
    did_config = tmp_path / "did_config"
    did_config.write_text("[general]\n")

    return Settings(
        employee=EmployeeInfo(name="John Doe", supervisor="Jane Smith"),
        product=ProductConfig(name="Test Product"),
        report=ReportConfig(creative_work_percentage=80),
        ai=GeminiProviderConfig(),
        did=DidConfig(config_path=str(did_config), providers=["github.com"]),
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
        path="group/repo",
        provider_type="gitlab",
    )


@pytest.fixture
def basic_change(github_repo):
    """Create a basic change for testing."""
    return Change(
        title="Fix bug in handler",
        repository=github_repo,
        number=123,
        merged_at=datetime(2024, 11, 15, 10, 30, 0, tzinfo=UTC),
    )


@pytest.fixture
def basic_inflight(basic_change):
    """Create a basic InFlightReport for testing."""
    return InFlightReport(
        month="2024-11",
        workday_start=date(2024, 11, 1),
        workday_end=date(2024, 11, 30),
        changes_since=date(2024, 10, 26),
        changes_until=date(2024, 11, 25),
        changes=[basic_change],
        total_hours=160.0,
        working_days=21,
        absence_days=0,
    )


class TestCompileReport:
    """Test compile_report function."""

    def test_successful_compilation_with_ai_enabled(
        self, basic_inflight, basic_change, basic_settings
    ):
        """Test successful compilation with AI enabled and judgments."""
        # Add judgment for the change
        judgment = Judgment(
            change_id=basic_change.get_change_id(),
            url=basic_change.get_url(),
            description=basic_change.title,
            decision=Decision.INCLUDE,
            reasoning="Relevant to product",
            product="Test Product",
            ai_provider="gemini/gemini-2.5-pro",
        )
        basic_inflight.judgments = [judgment]

        report = compile_report(basic_inflight, basic_settings)

        assert report.month == "2024-11"
        assert report.start_date == date(2024, 11, 1)
        assert report.end_date == date(2024, 11, 30)
        assert len(report.changes) == 1
        assert report.changes[0] == basic_change
        assert len(report.repositories) == 1
        assert report.total_hours == 160.0
        assert report.creative_hours == 128.0  # 80% of 160
        assert report.employee_name == "John Doe"
        assert report.supervisor_name == "Jane Smith"
        assert report.product_name == "Test Product"

    def test_successful_compilation_with_ai_disabled(
        self, basic_inflight, basic_change, basic_settings
    ):
        """Test successful compilation with AI disabled (no judgments needed)."""
        # Disable AI
        basic_settings.ai = DisabledAIConfig()

        # No judgments provided
        basic_inflight.judgments = []

        report = compile_report(basic_inflight, basic_settings)

        # All changes should be included when AI is disabled
        assert len(report.changes) == 1
        assert report.changes[0] == basic_change

    def test_fails_with_missing_total_hours(self, basic_inflight, basic_settings):
        """Test that compilation fails if total_hours is missing."""
        basic_inflight.total_hours = None

        with pytest.raises(ValueError, match="total_hours is missing"):
            compile_report(basic_inflight, basic_settings)

    def test_fails_with_missing_working_days(self, basic_inflight, basic_settings):
        """Test that compilation fails if working_days is missing."""
        basic_inflight.working_days = None

        with pytest.raises(ValueError, match="working_days is missing"):
            compile_report(basic_inflight, basic_settings)

    def test_fails_with_no_changes(self, basic_inflight, basic_settings):
        """Test that compilation fails if no changes exist."""
        basic_inflight.changes = []

        with pytest.raises(ValueError, match="no changes found"):
            compile_report(basic_inflight, basic_settings)

    def test_fails_with_missing_judgment_when_ai_enabled(
        self, basic_inflight, basic_settings
    ):
        """Test that compilation fails if AI enabled but change has no judgment."""
        # AI enabled by default in basic_settings
        # No judgments provided
        basic_inflight.judgments = []

        with pytest.raises(ValueError, match="has no judgment"):
            compile_report(basic_inflight, basic_settings)

    def test_fails_with_unresolved_uncertain_judgment(
        self, basic_inflight, basic_change, basic_settings
    ):
        """Test that compilation fails if UNCERTAIN judgment is not resolved."""
        judgment = Judgment(
            change_id=basic_change.get_change_id(),
            url=basic_change.get_url(),
            description=basic_change.title,
            decision=Decision.UNCERTAIN,
            reasoning="Cannot determine relevance",
            product="Test Product",
            ai_provider="gemini/gemini-2.5-pro",
        )
        basic_inflight.judgments = [judgment]

        with pytest.raises(
            ValueError, match="UNCERTAIN judgment without user decision"
        ):
            compile_report(basic_inflight, basic_settings)

    def test_fails_with_no_included_changes(
        self, basic_inflight, basic_change, basic_settings
    ):
        """Test that compilation fails if all changes are excluded."""
        judgment = Judgment(
            change_id=basic_change.get_change_id(),
            url=basic_change.get_url(),
            description=basic_change.title,
            decision=Decision.EXCLUDE,
            reasoning="Not relevant to product",
            product="Test Product",
            ai_provider="gemini/gemini-2.5-pro",
        )
        basic_inflight.judgments = [judgment]

        with pytest.raises(ValueError, match="no changes were included"):
            compile_report(basic_inflight, basic_settings)

    def test_includes_only_accepted_changes(
        self, basic_inflight, github_repo, basic_settings
    ):
        """Test that only INCLUDE decisions are included in report."""
        change1 = Change(title="Feature A", repository=github_repo, number=1)
        change2 = Change(title="Feature B", repository=github_repo, number=2)
        change3 = Change(title="Feature C", repository=github_repo, number=3)

        basic_inflight.changes = [change1, change2, change3]

        # Create judgments: INCLUDE, EXCLUDE, INCLUDE
        basic_inflight.judgments = [
            Judgment(
                change_id=change1.get_change_id(),
                url=change1.get_url(),
                description=change1.title,
                decision=Decision.INCLUDE,
                reasoning="Relevant",
                product="Test Product",
                ai_provider="test",
            ),
            Judgment(
                change_id=change2.get_change_id(),
                url=change2.get_url(),
                description=change2.title,
                decision=Decision.EXCLUDE,
                reasoning="Not relevant",
                product="Test Product",
                ai_provider="test",
            ),
            Judgment(
                change_id=change3.get_change_id(),
                url=change3.get_url(),
                description=change3.title,
                decision=Decision.INCLUDE,
                reasoning="Relevant",
                product="Test Product",
                ai_provider="test",
            ),
        ]

        report = compile_report(basic_inflight, basic_settings)

        assert len(report.changes) == 2
        assert change1 in report.changes
        assert change2 not in report.changes
        assert change3 in report.changes

    def test_user_decision_overrides_ai_decision(
        self, basic_inflight, basic_change, basic_settings
    ):
        """Test that user decision overrides AI decision."""
        # AI says EXCLUDE, user overrides to INCLUDE
        judgment = Judgment(
            change_id=basic_change.get_change_id(),
            url=basic_change.get_url(),
            description=basic_change.title,
            decision=Decision.EXCLUDE,
            user_decision=Decision.INCLUDE,
            reasoning="AI thinks not relevant",
            user_reasoning="Actually is relevant",
            product="Test Product",
            ai_provider="test",
        )
        basic_inflight.judgments = [judgment]

        report = compile_report(basic_inflight, basic_settings)

        # Change should be included based on user decision
        assert len(report.changes) == 1
        assert report.changes[0] == basic_change

    def test_resolved_uncertain_judgment_with_include(
        self, basic_inflight, basic_change, basic_settings
    ):
        """Test that resolved UNCERTAIN judgment (user=INCLUDE) works."""
        judgment = Judgment(
            change_id=basic_change.get_change_id(),
            url=basic_change.get_url(),
            description=basic_change.title,
            decision=Decision.UNCERTAIN,
            user_decision=Decision.INCLUDE,
            reasoning="Cannot determine",
            user_reasoning="User confirms relevance",
            product="Test Product",
            ai_provider="test",
        )
        basic_inflight.judgments = [judgment]

        report = compile_report(basic_inflight, basic_settings)

        assert len(report.changes) == 1
        assert report.changes[0] == basic_change

    def test_resolved_uncertain_judgment_with_exclude(
        self, basic_inflight, basic_change, basic_settings
    ):
        """Test that resolved UNCERTAIN judgment (user=EXCLUDE) works."""
        judgment = Judgment(
            change_id=basic_change.get_change_id(),
            url=basic_change.get_url(),
            description=basic_change.title,
            decision=Decision.UNCERTAIN,
            user_decision=Decision.EXCLUDE,
            reasoning="Cannot determine",
            user_reasoning="User confirms not relevant",
            product="Test Product",
            ai_provider="test",
        )
        basic_inflight.judgments = [judgment]

        with pytest.raises(ValueError, match="no changes were included"):
            compile_report(basic_inflight, basic_settings)

    def test_extracts_unique_repositories(
        self, basic_inflight, github_repo, gitlab_repo, basic_settings
    ):
        """Test that unique repositories are extracted correctly."""
        change1 = Change(title="Change 1", repository=github_repo, number=1)
        change2 = Change(title="Change 2", repository=github_repo, number=2)
        change3 = Change(title="Change 3", repository=gitlab_repo, number=3)

        basic_inflight.changes = [change1, change2, change3]
        basic_inflight.judgments = [
            Judgment(
                change_id=c.get_change_id(),
                url=c.get_url(),
                description=c.title,
                decision=Decision.INCLUDE,
                reasoning="Test",
                product="Test Product",
                ai_provider="test",
            )
            for c in [change1, change2, change3]
        ]

        report = compile_report(basic_inflight, basic_settings)

        # Should have 2 unique repos (github and gitlab)
        assert len(report.repositories) == 2
        # Repositories should be sorted by host then path
        assert report.repositories[0].host == "github.com"
        assert report.repositories[1].host == "gitlab.example.org"

    def test_calculates_creative_hours_correctly(
        self, basic_inflight, basic_change, basic_settings
    ):
        """Test creative hours calculation with different percentages."""
        judgment = Judgment(
            change_id=basic_change.get_change_id(),
            url=basic_change.get_url(),
            description=basic_change.title,
            decision=Decision.INCLUDE,
            reasoning="Relevant",
            product="Test Product",
            ai_provider="test",
        )
        basic_inflight.judgments = [judgment]

        # Test with 80% (default)
        basic_settings.report.creative_work_percentage = 80
        report = compile_report(basic_inflight, basic_settings)
        assert report.creative_hours == 128.0  # 80% of 160

        # Test with 100%
        basic_settings.report.creative_work_percentage = 100
        report = compile_report(basic_inflight, basic_settings)
        assert report.creative_hours == 160.0  # 100% of 160

        # Test with 50%
        basic_settings.report.creative_work_percentage = 50
        report = compile_report(basic_inflight, basic_settings)
        assert report.creative_hours == 80.0  # 50% of 160

    def test_uses_employee_and_product_info_from_settings(
        self, basic_inflight, basic_change, basic_settings
    ):
        """Test that employee and product info comes from settings."""
        judgment = Judgment(
            change_id=basic_change.get_change_id(),
            url=basic_change.get_url(),
            description=basic_change.title,
            decision=Decision.INCLUDE,
            reasoning="Relevant",
            product="Test Product",
            ai_provider="test",
        )
        basic_inflight.judgments = [judgment]

        # Modify settings
        basic_settings.employee.name = "Alice Johnson"
        basic_settings.employee.supervisor = "Bob Wilson"
        basic_settings.product.name = "Custom Product"

        report = compile_report(basic_inflight, basic_settings)

        assert report.employee_name == "Alice Johnson"
        assert report.supervisor_name == "Bob Wilson"
        assert report.product_name == "Custom Product"

    def test_uses_workday_dates_for_report_period(
        self, basic_inflight, basic_change, basic_settings
    ):
        """Test that report period uses workday dates."""
        judgment = Judgment(
            change_id=basic_change.get_change_id(),
            url=basic_change.get_url(),
            description=basic_change.title,
            decision=Decision.INCLUDE,
            reasoning="Relevant",
            product="Test Product",
            ai_provider="test",
        )
        basic_inflight.judgments = [judgment]

        report = compile_report(basic_inflight, basic_settings)

        assert report.start_date == basic_inflight.workday_start
        assert report.end_date == basic_inflight.workday_end
        # Note: changes_since and changes_until are different (skewed)
        assert basic_inflight.changes_since != basic_inflight.workday_start
