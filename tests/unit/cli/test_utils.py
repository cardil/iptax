"""Tests for CLI utils module."""

from datetime import date

import pytest

from iptax.cli import utils


class TestParseMonthKey:
    """Tests for parse_month_key function."""

    @pytest.mark.unit
    def test_valid_month_format(self):
        """Test parsing a valid month format."""
        result = utils.parse_month_key("2024-10")
        assert result == "2024-10"

    @pytest.mark.unit
    def test_normalized_format(self):
        """Test that month is normalized (zero-padded)."""
        result = utils.parse_month_key("2024-01")
        assert result == "2024-01"

    @pytest.mark.unit
    def test_none_returns_current_month(self):
        """Test that None returns current month."""
        result = utils.parse_month_key(None)
        assert len(result) == 7
        assert result[4] == "-"
        year, month = result.split("-")
        assert 2000 <= int(year) <= 2100
        assert 1 <= int(month) <= 12

    @pytest.mark.unit
    def test_invalid_format_raises(self):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError, match=r"time data .* does not match format"):
            utils.parse_month_key("invalid")

    @pytest.mark.unit
    def test_partial_date_raises(self):
        """Test that partial date raises ValueError."""
        with pytest.raises(ValueError, match=r"time data .* does not match format"):
            utils.parse_month_key("2024")


class TestGetDateRange:
    """Tests for get_date_range function."""

    @pytest.mark.unit
    def test_full_month(self):
        """Test date range for a full month."""
        start, end = utils.get_date_range("2024-10")
        assert start == date(2024, 10, 1)
        assert end == date(2024, 10, 31)

    @pytest.mark.unit
    def test_february_non_leap_year(self):
        """Test date range for February in non-leap year."""
        start, end = utils.get_date_range("2023-02")
        assert start == date(2023, 2, 1)
        assert end == date(2023, 2, 28)

    @pytest.mark.unit
    def test_february_leap_year(self):
        """Test date range for February in leap year."""
        start, end = utils.get_date_range("2024-02")
        assert start == date(2024, 2, 1)
        assert end == date(2024, 2, 29)

    @pytest.mark.unit
    def test_january(self):
        """Test date range for January."""
        start, end = utils.get_date_range("2024-01")
        assert start == date(2024, 1, 1)
        assert end == date(2024, 1, 31)

    @pytest.mark.unit
    def test_december(self):
        """Test date range for December."""
        start, end = utils.get_date_range("2024-12")
        assert start == date(2024, 12, 1)
        assert end == date(2024, 12, 31)
