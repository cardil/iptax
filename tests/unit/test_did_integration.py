"""Unit tests for did integration module."""

from iptax.did_integration import (
    DidIntegrationError,
    _clean_emoji,
    _determine_provider_type,
)


class TestCleanEmoji:
    """Test emoji cleaning functionality."""

    def test_clean_simple_emoji(self) -> None:
        """Test removing simple emoji code."""
        assert _clean_emoji(":rocket: Add feature") == "Add feature"

    def test_clean_multiple_emojis(self) -> None:
        """Test removing multiple emoji codes."""
        assert (
            _clean_emoji(":bug: :rocket: Fix and add feature") == "Fix and add feature"
        )

    def test_clean_emoji_at_end(self) -> None:
        """Test removing emoji at end of title."""
        assert _clean_emoji("Add feature :sparkles:") == "Add feature"

    def test_clean_no_emoji(self) -> None:
        """Test title without emoji codes."""
        assert _clean_emoji("Regular title") == "Regular title"

    def test_clean_emoji_with_extra_spaces(self) -> None:
        """Test removing emoji and collapsing spaces."""
        assert _clean_emoji(":rocket:  Add   feature  :bug:") == "Add feature"

    def test_clean_empty_after_emoji_removal(self) -> None:
        """Test title that becomes empty after emoji removal."""
        assert _clean_emoji(":rocket: :bug:") == ""

    def test_clean_unicode_emoji_preserved(self) -> None:
        """Test that actual unicode emoji are preserved."""
        assert _clean_emoji("Add feature 🚀") == "Add feature 🚀"


class TestDetermineProviderType:
    """Test provider type determination."""

    def test_github_com(self) -> None:
        """Test identifying github.com."""
        assert _determine_provider_type("github.com") == "github"

    def test_github_enterprise(self) -> None:
        """Test identifying GitHub Enterprise."""
        assert _determine_provider_type("github.example.com") == "github"

    def test_gitlab_com(self) -> None:
        """Test identifying gitlab.com."""
        assert _determine_provider_type("gitlab.com") == "gitlab"

    def test_gitlab_self_hosted(self) -> None:
        """Test identifying self-hosted GitLab."""
        assert _determine_provider_type("gitlab.example.org") == "gitlab"

    def test_unknown_defaults_to_gitlab(self) -> None:
        """Test unknown hosts default to GitLab."""
        assert _determine_provider_type("git.example.com") == "gitlab"

    def test_case_insensitive(self) -> None:
        """Test host matching is case insensitive."""
        assert _determine_provider_type("GitHub.Com") == "github"
        assert _determine_provider_type("GitLab.Com") == "gitlab"


class TestDidIntegrationError:
    """Test DidIntegrationError exception."""

    def test_error_creation(self) -> None:
        """Test creating DidIntegrationError."""
        error = DidIntegrationError("Test error message")
        assert str(error) == "Test error message"

    def test_error_with_cause(self) -> None:
        """Test creating DidIntegrationError with cause."""

        def raise_with_cause() -> None:
            cause = ValueError("Original error")
            raise DidIntegrationError("Wrapper error") from cause

        try:
            raise_with_cause()
        except DidIntegrationError as error:
            assert str(error) == "Wrapper error"
            assert isinstance(error.__cause__, ValueError)
            assert str(error.__cause__) == "Original error"
