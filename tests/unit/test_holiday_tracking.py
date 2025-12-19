"""Tests for holiday tracking feature.

This test module follows TDD approach for the holiday tracking fix.
Issue: Holidays are lumped with PTO instead of being tracked separately.
"""

from datetime import date

import pytest

from iptax.models import (
    HOURS_PER_DAY,
    INFLIGHT_SCHEMA_VERSION,
    InFlightReport,
    WorkdayCalendarEntry,
    WorkHours,
)
from iptax.workday.models import CalendarEntriesCollector


class TestInflightSchemaVersion:
    """Test schema versioning for InFlightReport."""

    @pytest.mark.unit
    def test_schema_version_constant_exists(self) -> None:
        """Test that INFLIGHT_SCHEMA_VERSION constant is defined."""
        assert INFLIGHT_SCHEMA_VERSION == 2

    @pytest.mark.unit
    def test_inflight_report_has_schema_version_field(self) -> None:
        """Test that InFlightReport has schema_version field."""
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        assert hasattr(report, "schema_version")

    @pytest.mark.unit
    def test_inflight_report_schema_version_defaults_to_none(self) -> None:
        """Test that schema_version defaults to None (for detecting old cached data)."""
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        # Default is None so old cached reports without this field are detected
        assert report.schema_version is None


class TestWorkHoursHolidayDays:
    """Test holiday_days field in WorkHours model."""

    @pytest.mark.unit
    def test_work_hours_has_holiday_days_field(self) -> None:
        """Test that WorkHours has holiday_days field."""
        work_hours = WorkHours(
            working_days=21,
            total_hours=168.0,
        )
        assert hasattr(work_hours, "holiday_days")
        assert work_hours.holiday_days == 0

    @pytest.mark.unit
    def test_work_hours_with_holiday_days(self) -> None:
        """Test creating WorkHours with holiday_days."""
        work_hours = WorkHours(
            working_days=23,
            absence_days=5,
            holiday_days=3,
            total_hours=184.0,
        )
        assert work_hours.holiday_days == 3

    @pytest.mark.unit
    def test_effective_hours_excludes_holidays(self) -> None:
        """Test that effective_hours excludes both PTO and holidays."""
        work_hours = WorkHours(
            working_days=23,
            absence_days=5,  # 5 PTO days
            holiday_days=3,  # 3 holiday days
            total_hours=184.0,  # 23 days * 8h
        )
        # effective_hours = total - (absence + holidays) * 8
        expected = 184.0 - (5 + 3) * HOURS_PER_DAY
        assert work_hours.effective_hours == expected
        assert work_hours.effective_hours == 120.0

    @pytest.mark.unit
    def test_effective_days_excludes_holidays(self) -> None:
        """Test that effective_days excludes both PTO and holidays."""
        work_hours = WorkHours(
            working_days=23,
            absence_days=5,
            holiday_days=3,
            total_hours=184.0,
        )
        # effective_days = effective_hours / 8
        assert work_hours.effective_days == 15

    @pytest.mark.unit
    def test_holiday_days_cannot_be_negative(self) -> None:
        """Test that holiday_days cannot be negative."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            WorkHours(
                working_days=21,
                holiday_days=-1,
                total_hours=168.0,
            )


class TestInFlightReportHolidayDays:
    """Test holiday_days field in InFlightReport model."""

    @pytest.mark.unit
    def test_inflight_report_has_holiday_days_field(self) -> None:
        """Test that InFlightReport has holiday_days field."""
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        assert hasattr(report, "holiday_days")
        assert report.holiday_days is None

    @pytest.mark.unit
    def test_inflight_report_with_holiday_days(self) -> None:
        """Test creating InFlightReport with holiday_days."""
        report = InFlightReport(
            month="2024-12",
            workday_start=date(2024, 12, 1),
            workday_end=date(2024, 12, 31),
            changes_since=date(2024, 11, 25),
            changes_until=date(2024, 12, 25),
            total_hours=184.0,
            working_days=23,
            absence_days=5,
            holiday_days=3,
        )
        assert report.holiday_days == 3

    @pytest.mark.unit
    def test_inflight_effective_hours_excludes_holidays(self) -> None:
        """Test that InFlightReport.effective_hours excludes holidays."""
        report = InFlightReport(
            month="2024-12",
            workday_start=date(2024, 12, 1),
            workday_end=date(2024, 12, 31),
            changes_since=date(2024, 11, 25),
            changes_until=date(2024, 12, 25),
            total_hours=184.0,
            working_days=23,
            absence_days=5,
            holiday_days=3,
        )
        # effective_hours = total - (absence + holidays) * 8
        expected = 184.0 - (5 + 3) * HOURS_PER_DAY
        assert report.effective_hours == expected
        assert report.effective_hours == 120.0


class TestCalendarEntriesCollectorHolidays:
    """Test CalendarEntriesCollector.get_hours_for_month with holidays."""

    @pytest.mark.unit
    def test_get_hours_for_month_separates_holidays(self) -> None:
        """Test that get_hours_for_month returns holidays separately."""
        collector = CalendarEntriesCollector()
        collector.entries = [
            # Work entry
            WorkdayCalendarEntry(
                entry_date=date(2024, 12, 2),
                title="Regular/Time Worked",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            # PTO entry
            WorkdayCalendarEntry(
                entry_date=date(2024, 12, 23),
                title="Paid Time Off in Hours",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            # Holiday entry (Paid Holiday in Time Tracking type)
            WorkdayCalendarEntry(
                entry_date=date(2024, 12, 25),
                title="Paid Holiday",
                entry_type="Time Tracking",
                hours=8.0,
            ),
        ]

        result = collector.get_hours_for_month(2024, 12)

        # Should return 4-tuple: (working, pto, holiday, total)
        assert len(result) == 4
        working, pto, holiday, total = result
        assert working == 8.0  # 1 work day
        assert pto == 8.0  # 1 PTO day
        assert holiday == 8.0  # 1 holiday
        assert total == 24.0

    @pytest.mark.unit
    def test_get_hours_for_month_counts_time_off_entries(self) -> None:
        """Test that Time Off entries are counted when no Time Tracking exists."""
        collector = CalendarEntriesCollector()
        collector.entries = [
            # Work entry
            WorkdayCalendarEntry(
                entry_date=date(2024, 12, 2),
                title="Regular/Time Worked",
                entry_type="Time Tracking",
                hours=8.0,
            ),
            # Time Off entry only (no corresponding Time Tracking)
            # This happens for future PTO entries
            WorkdayCalendarEntry(
                entry_date=date(2024, 12, 30),
                title="Annual Leave",
                entry_type="Time Off",
                hours=8.0,
            ),
        ]

        result = collector.get_hours_for_month(2024, 12)
        working, pto, holiday, total = result

        assert working == 8.0
        assert pto == 8.0  # Time Off entry should be counted
        assert holiday == 0.0
        assert total == 16.0

    @pytest.mark.unit
    def test_get_hours_deduplicates_time_off_with_time_tracking(self) -> None:
        """Test that Time Off entries are NOT double-counted with Time Tracking."""
        collector = CalendarEntriesCollector()
        collector.entries = [
            # Time Off marker entry
            WorkdayCalendarEntry(
                entry_date=date(2024, 12, 23),
                title="Annual Leave",
                entry_type="Time Off",
                hours=8.0,
            ),
            # Corresponding Time Tracking entry (same date)
            WorkdayCalendarEntry(
                entry_date=date(2024, 12, 23),
                title="Paid Time Off in Hours",
                entry_type="Time Tracking",
                hours=8.0,
            ),
        ]

        result = collector.get_hours_for_month(2024, 12)
        _working, pto, _holiday, total = result

        # Should only count once (8h, not 16h)
        assert pto == 8.0
        assert total == 8.0


class TestCacheSchemaVersionInvalidation:
    """Test that cache invalidates old schema versions."""

    @pytest.mark.unit
    def test_load_rejects_missing_schema_version(self, tmp_path) -> None:
        """Test that loading report without schema_version returns None."""
        import json

        from iptax.cache.inflight import InFlightCache

        cache = InFlightCache(cache_dir=tmp_path)

        # Create a report without schema_version (old format)
        old_report_data = {
            "month": "2024-11",
            "workday_start": "2024-11-01",
            "workday_end": "2024-11-30",
            "changes_since": "2024-10-25",
            "changes_until": "2024-11-25",
        }

        cache_file = tmp_path / "2024-11.json"
        with cache_file.open("w") as f:
            json.dump(old_report_data, f)

        # Load should return None (file is ignored but not deleted for safety)
        result = cache.load("2024-11")
        assert result is None
        # File stays on disk but is ignored - safer than auto-deletion
        assert cache_file.exists()

    @pytest.mark.unit
    def test_load_rejects_old_schema_version(self, tmp_path) -> None:
        """Test that loading report with old schema version returns None."""
        import json

        from iptax.cache.inflight import InFlightCache

        cache = InFlightCache(cache_dir=tmp_path)

        # Create a report with old schema version (v1)
        old_report_data = {
            "schema_version": 1,
            "month": "2024-11",
            "workday_start": "2024-11-01",
            "workday_end": "2024-11-30",
            "changes_since": "2024-10-25",
            "changes_until": "2024-11-25",
        }

        cache_file = tmp_path / "2024-11.json"
        with cache_file.open("w") as f:
            json.dump(old_report_data, f)

        # Load should return None (file is ignored but not deleted for safety)
        result = cache.load("2024-11")
        assert result is None
        # File stays on disk but is ignored - safer than auto-deletion
        assert cache_file.exists()

    @pytest.mark.unit
    def test_load_accepts_current_schema_version(self, tmp_path) -> None:
        """Test that loading report with current schema version works."""
        from iptax.cache.inflight import InFlightCache

        cache = InFlightCache(cache_dir=tmp_path)

        # Create and save a report with current schema version
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        cache.save(report)

        # Load should work
        loaded = cache.load("2024-11")
        assert loaded is not None
        assert loaded.schema_version == INFLIGHT_SCHEMA_VERSION

    @pytest.mark.unit
    def test_save_sets_schema_version(self, tmp_path) -> None:
        """Test that save() sets schema_version to current."""
        import json

        from iptax.cache.inflight import InFlightCache

        cache = InFlightCache(cache_dir=tmp_path)

        # Create report (schema_version is None by default)
        report = InFlightReport(
            month="2024-11",
            workday_start=date(2024, 11, 1),
            workday_end=date(2024, 11, 30),
            changes_since=date(2024, 10, 25),
            changes_until=date(2024, 11, 25),
        )
        assert report.schema_version is None

        # Save it
        cache.save(report)

        # Check saved file has schema_version
        cache_file = tmp_path / "2024-11.json"
        with cache_file.open() as f:
            saved_data = json.load(f)
        assert saved_data["schema_version"] == INFLIGHT_SCHEMA_VERSION
