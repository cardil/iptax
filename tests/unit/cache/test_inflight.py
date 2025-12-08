"""Unit tests for in-flight report cache."""

from datetime import date
from pathlib import Path

import pytest

from iptax.ai.models import Decision, Judgment
from iptax.cache.inflight import (
    STATE_COMPLETE,
    STATE_INCOMPLETE,
    STATE_PENDING,
    STATE_SKIPPED,
    InFlightCache,
    ReportState,
)
from iptax.models import InFlightReport


class TestInFlightCache:
    """Test InFlightCache class."""

    def test_init_with_custom_path(self, tmp_path: Path) -> None:
        """Test initialization with custom path."""
        custom_path = tmp_path / "custom_cache"
        cache = InFlightCache(cache_dir=custom_path)

        assert cache.cache_dir == custom_path

    def test_exists_no_report(self, tmp_path: Path) -> None:
        """Test exists returns False when no report exists."""
        cache = InFlightCache(cache_dir=tmp_path)

        assert not cache.exists("2024-11")

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Test saving and loading a report."""
        cache = InFlightCache(cache_dir=tmp_path)

        # Create a report
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )

        # Save
        path = cache.save(report)
        assert path.exists()
        assert cache.exists("2024-11")

        # Load
        loaded = cache.load("2024-11")
        assert loaded is not None
        assert loaded.month == "2024-11"
        assert loaded.workday_start == date(2024, 11, 1)
        assert loaded.workday_end == date(2024, 11, 30)
        assert loaded.changes_since == date(2024, 10, 25)
        assert loaded.changes_until == date(2024, 11, 25)

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        """Test loading non-existent report returns None."""
        cache = InFlightCache(cache_dir=tmp_path)

        loaded = cache.load("2024-11")
        assert loaded is None

    def test_delete(self, tmp_path: Path) -> None:
        """Test deleting a report."""
        cache = InFlightCache(cache_dir=tmp_path)

        # Create and save a report
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        cache.save(report)
        assert cache.exists("2024-11")

        # Delete
        result = cache.delete("2024-11")
        assert result is True
        assert not cache.exists("2024-11")

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        """Test deleting non-existent report returns False."""
        cache = InFlightCache(cache_dir=tmp_path)

        result = cache.delete("2024-11")
        assert result is False

    def test_list_all_empty(self, tmp_path: Path) -> None:
        """Test listing reports when cache is empty."""
        cache = InFlightCache(cache_dir=tmp_path)

        reports = cache.list_all()
        assert reports == []

    def test_list_all_multiple(self, tmp_path: Path) -> None:
        """Test listing multiple reports."""
        cache = InFlightCache(cache_dir=tmp_path)

        # Create multiple reports
        for month in ["2024-10", "2024-11", "2024-12"]:
            report = InFlightReport(
                month=month,
                workday_start=date(2024, 11, 1),
                workday_end=date(2024, 11, 30),
                changes_since=date(2024, 10, 25),
                changes_until=date(2024, 11, 25),
            )
            cache.save(report)

        reports = cache.list_all()
        assert len(reports) == 3
        assert set(reports) == {"2024-10", "2024-11", "2024-12"}

    def test_clear_all(self, tmp_path: Path) -> None:
        """Test clearing all reports."""
        cache = InFlightCache(cache_dir=tmp_path)

        # Create multiple reports
        for month in ["2024-10", "2024-11"]:
            report = InFlightReport(
                month=month,
                workday_start=date(2024, 11, 1),
                workday_end=date(2024, 11, 30),
                changes_since=date(2024, 10, 25),
                changes_until=date(2024, 11, 25),
            )
            cache.save(report)

        # Clear all
        count = cache.clear_all()
        assert count == 2
        assert cache.list_all() == []

    def test_clear_all_empty(self, tmp_path: Path) -> None:
        """Test clearing when cache is empty."""
        cache = InFlightCache(cache_dir=tmp_path)

        count = cache.clear_all()
        assert count == 0

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Test that save creates cache directory if needed."""
        cache_dir = tmp_path / "subdir" / "cache"
        cache = InFlightCache(cache_dir=cache_dir)

        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )

        cache.save(report)
        assert cache_dir.exists()

    def test_invalid_month_format_raises_error(self, tmp_path: Path) -> None:
        """Test that invalid month format raises ValueError."""
        cache = InFlightCache(cache_dir=tmp_path)

        with pytest.raises(ValueError, match="Invalid month format"):
            cache.load("../../../tmp/evil")

    def test_path_traversal_attempt_raises_error(self, tmp_path: Path) -> None:
        """Test that path traversal attempts are rejected."""
        cache = InFlightCache(cache_dir=tmp_path)

        with pytest.raises(ValueError, match="Invalid month format"):
            cache.exists("2024-11/../../../etc/passwd")

    def test_list_all_filters_invalid_files(self, tmp_path: Path) -> None:
        """Test that list_all only returns valid YYYY-MM format files."""
        cache = InFlightCache(cache_dir=tmp_path)

        # Create a valid report
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        cache.save(report)

        # Create an invalid file manually
        (tmp_path / "invalid.json").write_text("{}")
        (tmp_path / "not-a-month.json").write_text("{}")

        # Should only return valid month
        reports = cache.list_all()
        assert reports == ["2024-11"]


class TestReportState:
    """Test ReportState class for state derivation."""

    def _create_report(
        self,
        *,
        with_changes: bool = False,
        with_total_hours: bool = False,
        workday_validated: bool = False,
        with_judgments: bool = False,
        all_reviewed: bool = False,
    ) -> InFlightReport:
        """Create an InFlightReport with specified state."""
        from iptax.models import Change, Repository

        changes = []
        if with_changes:
            changes = [
                Change(
                    title="Test Change",
                    repository=Repository(
                        host="github.com",
                        path="org/repo",
                        provider_type="github",
                    ),
                    number=123,
                )
            ]

        judgments = []
        if with_judgments:
            for change in changes:
                judgment = Judgment(
                    change_id=change.get_change_id(),
                    decision=Decision.INCLUDE,
                    reasoning="Test reasoning",
                    product="Test Product",
                )
                if all_reviewed:
                    judgment.user_decision = Decision.INCLUDE
                judgments.append(judgment)

        return InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
            changes=changes,
            total_hours=10.0 if with_total_hours else None,
            workday_validated=workday_validated,
            judgments=judgments,
        )

    @pytest.mark.unit
    def test_empty_report_state(self) -> None:
        """Test state derivation for empty report."""
        report = self._create_report()
        state = ReportState.from_report(report)

        assert state.did == STATE_PENDING
        assert state.workday == STATE_PENDING
        assert state.ai == STATE_PENDING
        assert state.reviewed == STATE_PENDING
        assert state.status == "Collecting"

    @pytest.mark.unit
    def test_did_collected_state(self) -> None:
        """Test state after Did collection."""
        report = self._create_report(with_changes=True)
        state = ReportState.from_report(report)

        assert state.did == STATE_COMPLETE
        assert state.workday == STATE_PENDING
        assert state.ai == STATE_PENDING
        assert state.reviewed == STATE_PENDING
        assert state.status == "Needs Workday"

    @pytest.mark.unit
    def test_workday_collected_not_validated(self) -> None:
        """Test state when Workday hours collected but not validated."""
        report = self._create_report(
            with_changes=True,
            with_total_hours=True,
            workday_validated=False,
        )
        state = ReportState.from_report(report)

        assert state.did == STATE_COMPLETE
        assert state.workday == STATE_INCOMPLETE
        assert state.status == "Workday incomplete"

    @pytest.mark.unit
    def test_workday_collected_and_validated(self) -> None:
        """Test state when Workday hours validated."""
        report = self._create_report(
            with_changes=True,
            with_total_hours=True,
            workday_validated=True,
        )
        state = ReportState.from_report(report)

        assert state.did == STATE_COMPLETE
        assert state.workday == STATE_COMPLETE
        assert state.ai == STATE_PENDING
        assert state.status == "Needs AI filtering"

    @pytest.mark.unit
    def test_ai_analyzed_state(self) -> None:
        """Test state after AI analysis."""
        report = self._create_report(
            with_changes=True,
            with_total_hours=True,
            workday_validated=True,
            with_judgments=True,
        )
        state = ReportState.from_report(report)

        assert state.did == STATE_COMPLETE
        assert state.workday == STATE_COMPLETE
        assert state.ai == STATE_COMPLETE
        assert state.reviewed == STATE_PENDING
        assert state.status == "Needs review"

    @pytest.mark.unit
    def test_fully_reviewed_state(self) -> None:
        """Test state when fully reviewed."""
        report = self._create_report(
            with_changes=True,
            with_total_hours=True,
            workday_validated=True,
            with_judgments=True,
            all_reviewed=True,
        )
        state = ReportState.from_report(report)

        assert state.did == STATE_COMPLETE
        assert state.workday == STATE_COMPLETE
        assert state.ai == STATE_COMPLETE
        assert state.reviewed == STATE_COMPLETE
        assert state.status == "Ready for dist"

    @pytest.mark.unit
    def test_workday_disabled(self) -> None:
        """Test state when Workday is disabled."""
        report = self._create_report(with_changes=True)
        state = ReportState.from_report(report, workday_enabled=False)

        assert state.workday == STATE_SKIPPED
        assert state.status == "Needs AI filtering"

    @pytest.mark.unit
    def test_ready_for_dist_without_workday(self) -> None:
        """Test ready for dist when Workday is disabled."""
        report = self._create_report(
            with_changes=True,
            with_judgments=True,
            all_reviewed=True,
        )
        state = ReportState.from_report(report, workday_enabled=False)

        assert state.did == STATE_COMPLETE
        assert state.workday == STATE_SKIPPED
        assert state.ai == STATE_COMPLETE
        assert state.reviewed == STATE_COMPLETE
        assert state.status == "Ready for dist"
