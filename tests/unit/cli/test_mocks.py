"""Tests for CLI mocks module."""

import pytest

from iptax.ai.models import Decision
from iptax.cli import mocks


class TestGenerateMockChanges:
    """Tests for generate_mock_changes function."""

    @pytest.mark.unit
    def test_default_count(self):
        """Test default count generates 15 changes."""
        changes = mocks.generate_mock_changes()
        assert len(changes) == 15

    @pytest.mark.unit
    def test_custom_count(self):
        """Test custom count generates correct number."""
        changes = mocks.generate_mock_changes(count=5)
        assert len(changes) == 5

    @pytest.mark.unit
    def test_changes_have_titles(self):
        """Test that changes have non-empty titles."""
        changes = mocks.generate_mock_changes(count=3)
        for change in changes:
            assert change.title
            assert len(change.title) > 10

    @pytest.mark.unit
    def test_changes_have_repositories(self):
        """Test that changes have valid repositories."""
        changes = mocks.generate_mock_changes(count=3)
        for change in changes:
            assert change.repository
            assert change.repository.host == "github.com"
            assert change.repository.path

    @pytest.mark.unit
    def test_changes_have_numbers(self):
        """Test that changes have PR numbers."""
        changes = mocks.generate_mock_changes(count=3)
        for change in changes:
            assert change.number >= 1000

    @pytest.mark.unit
    def test_changes_unique_change_ids(self):
        """Test that all changes have unique IDs."""
        changes = mocks.generate_mock_changes(count=10)
        change_ids = [c.get_change_id() for c in changes]
        assert len(set(change_ids)) == len(change_ids)


class TestGenerateMockJudgments:
    """Tests for generate_mock_judgments function."""

    @pytest.mark.unit
    def test_matches_change_count(self):
        """Test that judgment count matches change count."""
        changes = mocks.generate_mock_changes(count=5)
        judgments = mocks.generate_mock_judgments(changes)
        assert len(judgments) == 5

    @pytest.mark.unit
    def test_default_product_name(self):
        """Test that default product name is used."""
        changes = mocks.generate_mock_changes(count=1)
        judgments = mocks.generate_mock_judgments(changes)
        assert judgments[0].product == "Test Product"

    @pytest.mark.unit
    def test_custom_product_name(self):
        """Test that custom product name is used."""
        changes = mocks.generate_mock_changes(count=1)
        judgments = mocks.generate_mock_judgments(changes, product="Custom Product")
        assert judgments[0].product == "Custom Product"

    @pytest.mark.unit
    def test_variety_of_decisions(self):
        """Test that judgments include variety of decisions."""
        changes = mocks.generate_mock_changes(count=15)
        judgments = mocks.generate_mock_judgments(changes)

        decisions = {j.decision for j in judgments}
        # Should include all three types
        assert Decision.INCLUDE in decisions
        assert Decision.EXCLUDE in decisions
        assert Decision.UNCERTAIN in decisions

    @pytest.mark.unit
    def test_uncertain_every_fifth(self):
        """Test that every 5th change is UNCERTAIN."""
        changes = mocks.generate_mock_changes(count=10)
        judgments = mocks.generate_mock_judgments(changes)

        # Index 4 and 9 should be UNCERTAIN (0-indexed, every 5th)
        assert judgments[4].decision == Decision.UNCERTAIN
        assert judgments[9].decision == Decision.UNCERTAIN

    @pytest.mark.unit
    def test_judgments_have_reasoning(self):
        """Test that judgments have reasoning."""
        changes = mocks.generate_mock_changes(count=3)
        judgments = mocks.generate_mock_judgments(changes)

        for j in judgments:
            assert j.reasoning
            assert len(j.reasoning) > 5

    @pytest.mark.unit
    def test_change_ids_match(self):
        """Test that judgment change_ids match actual changes."""
        changes = mocks.generate_mock_changes(count=5)
        judgments = mocks.generate_mock_judgments(changes)

        for change, judgment in zip(changes, judgments, strict=True):
            assert judgment.change_id == change.get_change_id()
