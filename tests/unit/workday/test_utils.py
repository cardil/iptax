"""Unit tests for iptax.workday.utils module."""

from datetime import date

import pytest

from iptax.workday.utils import (
    _is_valid_float,
    _month_to_number,
    _parse_week_range,
    calculate_working_days,
)


class TestCalculateWorkingDays:
    """Test calculate_working_days function."""

    def test_full_week(self):
        """Test calculating working days for a full week."""
        # Monday to Friday
        start = date(2024, 11, 4)  # Monday
        end = date(2024, 11, 8)  # Friday

        result = calculate_working_days(start, end)

        assert result == 5

    def test_includes_weekend(self):
        """Test that weekends are excluded."""
        # Monday to Sunday (7 days, but only 5 working)
        start = date(2024, 11, 4)  # Monday
        end = date(2024, 11, 10)  # Sunday

        result = calculate_working_days(start, end)

        assert result == 5

    def test_full_month_november_2024(self):
        """Test full month calculation for November 2024."""
        start = date(2024, 11, 1)  # Friday
        end = date(2024, 11, 30)  # Saturday

        result = calculate_working_days(start, end)

        # November 2024 has 21 working days
        assert result == 21

    def test_single_weekday(self):
        """Test single weekday."""
        day = date(2024, 11, 6)  # Wednesday

        result = calculate_working_days(day, day)

        assert result == 1

    def test_single_weekend_day(self):
        """Test single weekend day."""
        day = date(2024, 11, 9)  # Saturday

        result = calculate_working_days(day, day)

        assert result == 0

    def test_across_month_boundary(self):
        """Test working days across month boundary."""
        start = date(2024, 10, 28)  # Monday
        end = date(2024, 11, 1)  # Friday

        result = calculate_working_days(start, end)

        assert result == 5

    def test_across_year_boundary(self):
        """Test working days across year boundary."""
        start = date(2024, 12, 30)  # Monday
        end = date(2025, 1, 3)  # Friday

        result = calculate_working_days(start, end)

        # Dec 30 (Mon), 31 (Tue), Jan 1 (Wed), 2 (Thu), 3 (Fri) = 5 days
        assert result == 5


class TestIsValidFloat:
    """Test _is_valid_float helper function."""

    def test_valid_integer(self):
        """Test that integer strings are valid."""
        assert _is_valid_float("42") is True

    def test_valid_float(self):
        """Test that float strings are valid."""
        assert _is_valid_float("168.5") is True

    def test_invalid_string(self):
        """Test that non-numeric strings are invalid."""
        assert _is_valid_float("abc") is False

    def test_empty_string(self):
        """Test that empty string is invalid."""
        assert _is_valid_float("") is False

    def test_negative_float(self):
        """Test that negative floats are valid."""
        assert _is_valid_float("-42.5") is True

    def test_zero(self):
        """Test that zero is valid."""
        assert _is_valid_float("0") is True


class TestParseWeekRange:
    """Test _parse_week_range function."""

    def test_same_month_format(self):
        """Test parsing 'Nov 24 - 30, 2025' format."""
        result = _parse_week_range("Nov 24 - 30, 2025")
        assert result == (date(2025, 11, 24), date(2025, 11, 30))

    def test_different_months_format(self):
        """Test parsing 'Dec 30, 2024 - Jan 5, 2025' format."""
        result = _parse_week_range("Dec 30, 2024 - Jan 5, 2025")
        assert result == (date(2024, 12, 30), date(2025, 1, 5))

    def test_different_months_same_year(self):
        """Test parsing 'Dec 30 - Jan 5, 2025' format (year boundary)."""
        result = _parse_week_range("Dec 30 - Jan 5, 2025")
        # Dec is in previous year when followed by Jan
        assert result == (date(2024, 12, 30), date(2025, 1, 5))

    def test_same_year_no_boundary(self):
        """Test parsing 'Oct 30 - Nov 5, 2025' format (no year boundary)."""
        result = _parse_week_range("Oct 30 - Nov 5, 2025")
        assert result == (date(2025, 10, 30), date(2025, 11, 5))

    def test_with_en_dash(self):
        """Test parsing with en-dash character."""
        result = _parse_week_range("Nov 24 \u2013 30, 2025")
        assert result == (date(2025, 11, 24), date(2025, 11, 30))

    def test_with_em_dash(self):
        """Test parsing with em-dash character."""
        result = _parse_week_range("Nov 24 \u2014 30, 2025")
        assert result == (date(2025, 11, 24), date(2025, 11, 30))

    def test_invalid_format(self):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Could not parse week range"):
            _parse_week_range("Invalid format")

    def test_all_months(self):
        """Test that all month abbreviations work."""
        months = [
            ("Jan", 1),
            ("Feb", 2),
            ("Mar", 3),
            ("Apr", 4),
            ("May", 5),
            ("Jun", 6),
            ("Jul", 7),
            ("Aug", 8),
            ("Sep", 9),
            ("Oct", 10),
            ("Nov", 11),
            ("Dec", 12),
        ]
        for month_str, month_num in months:
            result = _parse_week_range(f"{month_str} 1 - 7, 2025")
            assert result[0].month == month_num


class TestMonthToNumber:
    """Test _month_to_number function."""

    def test_all_months(self):
        """Test all month abbreviations."""
        assert _month_to_number("Jan") == 1
        assert _month_to_number("Feb") == 2
        assert _month_to_number("Mar") == 3
        assert _month_to_number("Apr") == 4
        assert _month_to_number("May") == 5
        assert _month_to_number("Jun") == 6
        assert _month_to_number("Jul") == 7
        assert _month_to_number("Aug") == 8
        assert _month_to_number("Sep") == 9
        assert _month_to_number("Oct") == 10
        assert _month_to_number("Nov") == 11
        assert _month_to_number("Dec") == 12

    def test_lowercase(self):
        """Test that lowercase works."""
        assert _month_to_number("jan") == 1
        assert _month_to_number("dec") == 12

    def test_uppercase(self):
        """Test that uppercase works."""
        assert _month_to_number("JAN") == 1
        assert _month_to_number("DEC") == 12

    def test_full_month_name(self):
        """Test that full month names work (first 3 chars used)."""
        assert _month_to_number("January") == 1
        assert _month_to_number("December") == 12
