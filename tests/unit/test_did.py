"""Unit tests for did integration module."""

import logging
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from did.plugins.github import Issue
from did.plugins.gitlab import MergedRequest
from pydantic import ValidationError

from iptax.did import (
    DidIntegrationError,
    InvalidStatDataError,
    _clean_emoji,
    _convert_github_pr,
    _convert_to_change,
    _determine_provider_type,
    _fetch_provider_changes,
    fetch_changes,
)
from iptax.models import DidConfig, EmployeeInfo, ProductConfig, Settings


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

    def test_unknown_raises_error(self) -> None:
        """Test unknown hosts raise DidIntegrationError."""
        with pytest.raises(
            DidIntegrationError,
            match=r"Cannot determine provider type from host 'git\.example\.com'",
        ):
            _determine_provider_type("git.example.com")

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


class TestInvalidStatDataError:
    """Test InvalidStatDataError exception."""

    def test_error_creation(self) -> None:
        """Test creating InvalidStatDataError."""
        error = InvalidStatDataError("Missing field")
        assert str(error) == "Missing field"

    def test_error_with_cause(self) -> None:
        """Test creating InvalidStatDataError with cause."""

        def raise_with_cause() -> None:
            cause = ValueError("Bad value")
            raise InvalidStatDataError("Invalid data") from cause

        try:
            raise_with_cause()
        except InvalidStatDataError as error:
            assert str(error) == "Invalid data"
            assert isinstance(error.__cause__, ValueError)
            assert str(error.__cause__) == "Bad value"


def _create_github_issue_mock(
    owner: str | None = "owner",
    project: str | None = "repo",
    id_val: int | str | None = 1,
    title: str | None = "Title",
    url: str | None = None,
) -> Mock:
    """Create a mock that acts like a GitHub Issue."""
    mock = Mock(spec=Issue)
    mock.owner = owner
    mock.project = project
    mock.id = id_val
    mock.title = title
    # Create data dict with html_url (like real did SDK)
    if url is None and owner and project:
        html_url = f"https://github.com/{owner}/{project}/pull/{id_val}"
    else:
        html_url = url
    mock.data = {"html_url": html_url, "title": title}
    return mock


def _create_gitlab_mr_mock(
    path_with_namespace: str = "group/project",
    iid: int | None = 1,
    title: str | None = "Title",
    url: str | None = None,
) -> Mock:
    """Create a mock that acts like a GitLab MergedRequest."""
    mock = Mock(spec=MergedRequest)
    mock.project = {"path_with_namespace": path_with_namespace}
    mock.data = {"title": title}
    mock.iid = Mock(return_value=iid)
    # Create gitlabapi mock with URL
    gitlabapi_mock = Mock()
    if url is None:
        # Default to gitlab.com with standard MR path
        gitlabapi_mock.url = (
            f"https://gitlab.com/{path_with_namespace}/-/merge_requests/{iid}"
        )
    else:
        gitlabapi_mock.url = url
    mock.gitlabapi = gitlabapi_mock
    return mock


class TestConvertToChange:
    """Test _convert_to_change function."""

    def test_convert_valid_github_stat(self) -> None:
        """Test converting valid GitHub stat to Change."""
        stat = _create_github_issue_mock(
            owner="octocat",
            project="hello-world",
            id_val=123,
            title="Add new feature",
        )

        change = _convert_to_change(stat)

        assert change.title == "Add new feature"
        assert change.repository.host == "github.com"
        assert change.repository.path == "octocat/hello-world"
        assert change.repository.provider_type == "github"
        assert change.number == 123
        assert change.merged_at is None

    def test_convert_valid_gitlab_stat(self) -> None:
        """Test converting valid GitLab stat to Change."""
        stat = _create_gitlab_mr_mock(
            path_with_namespace="gitlab-org/gitlab",
            iid=456,
            title="Fix bug",
        )

        change = _convert_to_change(stat)

        assert change.title == "Fix bug"
        assert change.repository.host == "gitlab.com"
        assert change.repository.path == "gitlab-org/gitlab"
        assert change.repository.provider_type == "gitlab"
        assert change.number == 456

    def test_convert_with_emoji_in_title(self) -> None:
        """Test converting stat with emoji in title."""
        stat = _create_github_issue_mock(
            owner="user",
            project="repo",
            id_val=1,
            title=":rocket: Add feature :sparkles:",
        )

        change = _convert_to_change(stat)

        assert change.title == "Add feature"

    def test_convert_missing_owner(self) -> None:
        """Test converting stat with missing owner raises error."""
        stat = _create_github_issue_mock(owner=None)

        with pytest.raises(InvalidStatDataError, match="Missing owner"):
            _convert_github_pr(stat)

    def test_convert_missing_project(self) -> None:
        """Test converting stat with missing project raises error."""
        stat = _create_github_issue_mock(project=None)

        with pytest.raises(InvalidStatDataError, match="Missing project"):
            _convert_github_pr(stat)

    def test_convert_missing_id(self) -> None:
        """Test converting stat with missing id raises error."""
        stat = _create_github_issue_mock(id_val=None)

        with pytest.raises(InvalidStatDataError, match="Missing id"):
            _convert_github_pr(stat)

    def test_convert_missing_title(self) -> None:
        """Test converting stat with missing title raises error."""
        stat = _create_github_issue_mock(title=None)

        with pytest.raises(InvalidStatDataError, match="Missing title"):
            _convert_github_pr(stat)

    def test_convert_empty_title(self) -> None:
        """Test converting stat with empty title raises error."""
        stat = _create_github_issue_mock(title="")

        with pytest.raises(InvalidStatDataError, match="Missing title"):
            _convert_github_pr(stat)

    def test_convert_invalid_id_type(self) -> None:
        """Test converting stat with non-numeric id raises Pydantic error."""
        stat = _create_github_issue_mock(id_val="not-a-number")

        # Pydantic validates the Change model and raises ValidationError
        with pytest.raises(ValidationError, match="int_parsing"):
            _convert_github_pr(stat)

    def test_convert_zero_id(self) -> None:
        """Test converting stat with zero id raises error."""
        stat = _create_github_issue_mock(id_val=0)

        with pytest.raises(InvalidStatDataError, match="Missing id"):
            _convert_github_pr(stat)

    def test_convert_negative_id(self) -> None:
        """Test converting stat with negative id raises Pydantic error."""
        stat = _create_github_issue_mock(id_val=-5)

        # Pydantic validates the Change model and raises ValidationError for negative
        with pytest.raises(ValidationError, match="greater_than"):
            _convert_github_pr(stat)

    def test_convert_unknown_type_raises_error(self) -> None:
        """Test converting unknown stat type raises error."""
        stat = Mock()  # Generic mock, not Issue or MergedRequest

        with pytest.raises(InvalidStatDataError, match="Unknown stat type"):
            _convert_to_change(stat)


class TestFetchProviderChanges:
    """Test _fetch_provider_changes function."""

    @patch("iptax.did.did.cli.main")
    def test_fetch_github_provider(self, mock_did_main: Mock) -> None:
        """Test fetching changes from GitHub provider."""
        mock_stat = _create_github_issue_mock(
            owner="owner", project="repo", id_val=1, title="PR title"
        )

        mock_merged_stats = Mock()
        mock_merged_stats.__class__.__name__ = "PullRequestsMerged"
        mock_merged_stats.stats = [mock_stat]

        mock_provider_group = Mock()
        mock_provider_group.__class__.__name__ = "GitHubStats"
        mock_provider_group.stats = [mock_merged_stats]

        mock_user = Mock()
        mock_user.stats = [mock_provider_group]

        mock_did_main.return_value = ([mock_user],)

        changes = _fetch_provider_changes(
            "github.com",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        assert len(changes) == 1
        assert changes[0].title == "PR title"
        assert changes[0].repository.provider_type == "github"

    @patch("iptax.did.did.cli.main")
    def test_fetch_gitlab_provider(self, mock_did_main: Mock) -> None:
        """Test fetching changes from GitLab provider."""
        mock_stat = _create_gitlab_mr_mock(
            path_with_namespace="group/project",
            iid=2,
            title="MR title",
        )

        mock_merged_stats = Mock()
        mock_merged_stats.__class__.__name__ = "MergeRequestsMerged"
        mock_merged_stats.stats = [mock_stat]

        mock_provider_group = Mock()
        mock_provider_group.__class__.__name__ = "GitLabStats"
        mock_provider_group.stats = [mock_merged_stats]

        mock_user = Mock()
        mock_user.stats = [mock_provider_group]

        mock_did_main.return_value = ([mock_user],)

        changes = _fetch_provider_changes(
            "gitlab.example.com",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        assert len(changes) == 1
        assert changes[0].title == "MR title"
        assert changes[0].repository.provider_type == "gitlab"

    @patch("iptax.did.did.cli.main")
    def test_fetch_empty_result(self, mock_did_main: Mock) -> None:
        """Test fetching with empty result raises error."""
        mock_did_main.return_value = ()

        with pytest.raises(DidIntegrationError, match="Empty result"):
            _fetch_provider_changes(
                "github.com",
                date(2024, 1, 1),
                date(2024, 1, 31),
            )

    @patch("iptax.did.did.cli.main")
    def test_fetch_no_user_stats(self, mock_did_main: Mock) -> None:
        """Test fetching with no user stats raises error."""
        mock_did_main.return_value = ([],)

        with pytest.raises(DidIntegrationError, match="None or falsy"):
            _fetch_provider_changes(
                "github.com",
                date(2024, 1, 1),
                date(2024, 1, 31),
            )

    @patch("iptax.did.did.cli.main")
    def test_fetch_no_provider_stats(self, mock_did_main: Mock) -> None:
        """Test fetching with no provider stats."""
        mock_user = Mock()
        mock_user.stats = []

        mock_did_main.return_value = ([mock_user],)

        changes = _fetch_provider_changes(
            "github.com",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        assert changes == []

    @patch("iptax.did.did.cli.main")
    def test_fetch_no_merged_stats(self, mock_did_main: Mock) -> None:
        """Test fetching with no merged stats raises error."""
        mock_other_stats = Mock()
        mock_other_stats.__class__.__name__ = "IssuesCreated"

        mock_provider_group = Mock()
        mock_provider_group.__class__.__name__ = "GitHubStats"
        mock_provider_group.stats = [mock_other_stats]

        mock_user = Mock()
        mock_user.stats = [mock_provider_group]

        mock_did_main.return_value = ([mock_user],)

        with pytest.raises(DidIntegrationError, match="Merged stats section not found"):
            _fetch_provider_changes(
                "github.com",
                date(2024, 1, 1),
                date(2024, 1, 31),
            )

    @patch("iptax.did.did.cli.main")
    def test_fetch_multiple_changes(self, mock_did_main: Mock) -> None:
        """Test fetching multiple changes."""
        mock_stat1 = _create_github_issue_mock(
            owner="owner", project="repo1", id_val=1, title="First PR"
        )
        mock_stat2 = _create_github_issue_mock(
            owner="owner", project="repo2", id_val=2, title="Second PR"
        )

        mock_merged_stats = Mock()
        mock_merged_stats.__class__.__name__ = "PullRequestsMerged"
        mock_merged_stats.stats = [mock_stat1, mock_stat2]

        mock_provider_group = Mock()
        mock_provider_group.__class__.__name__ = "GitHubStats"
        mock_provider_group.stats = [mock_merged_stats]

        mock_user = Mock()
        mock_user.stats = [mock_provider_group]

        mock_did_main.return_value = ([mock_user],)

        changes = _fetch_provider_changes(
            "github.com",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        assert len(changes) == 2
        assert changes[0].title == "First PR"
        assert changes[1].title == "Second PR"

    @patch("iptax.did.did.cli.main")
    def test_fetch_filters_invalid_stats(self, mock_did_main: Mock) -> None:
        """Test that invalid stats are filtered out with logging."""
        # Valid GitHub Issue mock
        mock_valid = _create_github_issue_mock(
            owner="owner", project="repo", id_val=1, title="Valid PR"
        )
        # Invalid: generic mock (not Issue or MergedRequest type)
        mock_invalid = Mock()

        mock_merged_stats = Mock()
        mock_merged_stats.__class__.__name__ = "PullRequestsMerged"
        mock_merged_stats.stats = [mock_valid, mock_invalid]

        mock_provider_group = Mock()
        mock_provider_group.__class__.__name__ = "GitHubStats"
        mock_provider_group.stats = [mock_merged_stats]

        mock_user = Mock()
        mock_user.stats = [mock_provider_group]

        mock_did_main.return_value = ([mock_user],)

        changes = _fetch_provider_changes(
            "github.com",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        assert len(changes) == 1
        assert changes[0].title == "Valid PR"

    @patch("iptax.did.did.cli.main")
    def test_fetch_did_cli_exception(self, mock_did_main: Mock) -> None:
        """Test handling exception from did.cli.main."""
        mock_did_main.side_effect = RuntimeError("Did CLI error")

        with pytest.raises(DidIntegrationError) as exc_info:
            _fetch_provider_changes(
                "github.com",
                date(2024, 1, 1),
                date(2024, 1, 31),
            )

        assert "Failed to call did.cli.main()" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, RuntimeError)


class TestExtractMergedStats:
    """Test _extract_merged_stats function."""

    def test_extract_user_stats_missing_stats_attribute(self) -> None:
        """Test error when user stats object missing stats attribute."""
        from iptax.did import _extract_merged_stats

        mock_user = Mock(spec=[])  # No 'stats' attribute
        result = ([mock_user],)

        with pytest.raises(
            DidIntegrationError,
            match=r"Object \(type: .*\) missing 'stats' attribute",
        ):
            _extract_merged_stats(result, "github.com")

    def test_extract_user_stats_stats_not_list(self) -> None:
        """Test error when user stats.stats is not a list."""
        from iptax.did import _extract_merged_stats

        mock_user = Mock()
        mock_user.stats = "not a list"
        result = ([mock_user],)

        with pytest.raises(DidIntegrationError, match=r"stats is not a list"):
            _extract_merged_stats(result, "github.com")

    def test_extract_provider_stats_missing_stats_attribute(self) -> None:
        """Test error when provider stats group missing stats attribute."""
        from iptax.did import _extract_merged_stats

        mock_provider_group = Mock(spec=[])  # No 'stats' attribute
        mock_provider_group.__class__.__name__ = "GitHubStats"
        mock_user = Mock()
        mock_user.stats = [mock_provider_group]
        result = ([mock_user],)

        with pytest.raises(
            DidIntegrationError, match=r"Object \(type: .*\) missing 'stats' attribute"
        ):
            _extract_merged_stats(result, "github.com")

    def test_extract_provider_stats_stats_not_list(self) -> None:
        """Test error when provider stats.stats is not a list."""
        from iptax.did import _extract_merged_stats

        mock_provider_group = Mock()
        mock_provider_group.__class__.__name__ = "GitHubStats"
        mock_provider_group.stats = "not a list"
        mock_user = Mock()
        mock_user.stats = [mock_provider_group]
        result = ([mock_user],)

        with pytest.raises(DidIntegrationError, match=r"stats is not a list"):
            _extract_merged_stats(result, "github.com")

    def test_extract_provider_stats_empty_list(self) -> None:
        """Test empty provider stats returns empty list."""
        from iptax.did import _extract_merged_stats

        mock_provider_group = Mock()
        mock_provider_group.__class__.__name__ = "GitHubStats"
        mock_provider_group.stats = []
        mock_user = Mock()
        mock_user.stats = [mock_provider_group]
        result = ([mock_user],)

        assert _extract_merged_stats(result, "github.com") == []

    def test_extract_merged_stat_missing_stats_attribute(self) -> None:
        """Test error when merged stat object missing stats attribute."""
        from iptax.did import _extract_merged_stats

        mock_merged_stat = Mock(spec=[])  # No 'stats' attribute
        mock_merged_stat.__class__.__name__ = "PullRequestsMerged"

        mock_provider_group = Mock()
        mock_provider_group.__class__.__name__ = "GitHubStats"
        mock_provider_group.stats = [mock_merged_stat]
        mock_user = Mock()
        mock_user.stats = [mock_provider_group]
        result = ([mock_user],)

        # Mock without 'stats' won't pass _is_merged_stat check, falls through to end
        with pytest.raises(
            DidIntegrationError,
            match="Merged stats section not found in did result",
        ):
            _extract_merged_stats(result, "github.com")


class TestValidateAndExtractUserStats:
    """Test _validate_and_extract_user_stats function."""

    def test_validate_non_tuple_result(self) -> None:
        """Test error when result is not a tuple."""
        from iptax.did import _validate_and_extract_user_stats

        with pytest.raises(DidIntegrationError, match="Expected tuple"):
            _validate_and_extract_user_stats([])  # List instead of tuple

    def test_validate_empty_users_list(self) -> None:
        """Test error when users list is empty."""
        from iptax.did import _validate_and_extract_user_stats

        result = ([],)  # Empty list is falsy

        # Empty list is falsy, caught by line 220 check
        with pytest.raises(
            DidIntegrationError, match="First element of did result is None or falsy"
        ):
            _validate_and_extract_user_stats(result)


class TestIsMergedStat:
    """Test _is_merged_stat function."""

    def test_is_merged_stat_no_stats_attribute(self) -> None:
        """Test returns False when stat has no stats attribute."""
        from iptax.did import _is_merged_stat

        mock_stat = Mock(spec=[])  # No 'stats' attribute
        assert _is_merged_stat(mock_stat) is False


class TestCheckDidStderr:
    """Test _check_did_stderr function."""

    def test_check_stderr_with_error_keyword(self) -> None:
        """Test raises error when stderr contains 'error' keyword."""
        from iptax.did import _check_did_stderr

        with pytest.raises(DidIntegrationError, match="did CLI reported errors"):
            _check_did_stderr("Error: something went wrong", "github.com")

    def test_check_stderr_with_fail_keyword(self) -> None:
        """Test raises error when stderr contains 'fail' keyword."""
        from iptax.did import _check_did_stderr

        with pytest.raises(DidIntegrationError, match="did CLI reported errors"):
            _check_did_stderr("Failed to connect", "github.com")

    def test_check_stderr_with_exception_keyword(self) -> None:
        """Test raises error when stderr contains 'exception' keyword."""
        from iptax.did import _check_did_stderr

        with pytest.raises(DidIntegrationError, match="did CLI reported errors"):
            _check_did_stderr("Exception occurred", "github.com")

    def test_check_stderr_with_warning_only(self, caplog) -> None:
        """Test logs warning but doesn't raise when stderr has no error keywords."""
        from iptax.did import _check_did_stderr

        with caplog.at_level(logging.WARNING):
            _check_did_stderr("Some warning message", "github.com")

        assert "did CLI produced stderr output" in caplog.text
        assert "github.com" in caplog.text


class TestFetchChanges:
    """Test fetch_changes function."""

    @patch("iptax.did._fetch_provider_changes")
    @patch("iptax.did.did.base.Config")
    def test_fetch_changes_single_provider(
        self,
        _mock_config: Mock,
        mock_fetch_provider: Mock,
        tmp_path: Path,
    ) -> None:
        """Test fetching changes from single provider."""
        config_path = tmp_path / "did.conf"
        config_path.write_text("[general]\nemail = test@example.com\n")

        settings = Settings(
            employee=EmployeeInfo(name="Test User", supervisor="Manager"),
            product=ProductConfig(name="Product"),
            did=DidConfig(
                config_path=str(config_path),
                providers=["github.com"],
            ),
        )

        mock_change = Mock()
        mock_fetch_provider.return_value = [mock_change]

        changes = fetch_changes(settings, date(2024, 1, 1), date(2024, 1, 31))

        assert len(changes) == 1
        assert changes[0] == mock_change
        mock_fetch_provider.assert_called_once()

    @patch("iptax.did._fetch_provider_changes")
    @patch("iptax.did.did.base.Config")
    def test_fetch_changes_multiple_providers(
        self,
        _mock_config: Mock,
        mock_fetch_provider: Mock,
        tmp_path: Path,
    ) -> None:
        """Test fetching changes from multiple providers."""
        config_path = tmp_path / "did.conf"
        config_path.write_text("[general]\nemail = test@example.com\n")

        settings = Settings(
            employee=EmployeeInfo(name="Test User", supervisor="Manager"),
            product=ProductConfig(name="Product"),
            did=DidConfig(
                config_path=str(config_path),
                providers=["github.com", "gitlab.com"],
            ),
        )

        mock_change1 = Mock()
        mock_change2 = Mock()
        mock_fetch_provider.side_effect = [[mock_change1], [mock_change2]]

        changes = fetch_changes(settings, date(2024, 1, 1), date(2024, 1, 31))

        assert len(changes) == 2
        assert changes[0] == mock_change1
        assert changes[1] == mock_change2
        assert mock_fetch_provider.call_count == 2

    @patch("iptax.did.did.base.Config")
    def test_fetch_changes_config_load_error(
        self, mock_config: Mock, tmp_path: Path
    ) -> None:
        """Test error when loading did config fails."""
        config_path = tmp_path / "did.conf"
        config_path.write_text("[general]\nemail = test@example.com\n")

        settings = Settings(
            employee=EmployeeInfo(name="Test User", supervisor="Manager"),
            product=ProductConfig(name="Product"),
            did=DidConfig(
                config_path=str(config_path),
                providers=["github.com"],
            ),
        )

        mock_config.side_effect = Exception("Config error")

        with pytest.raises(DidIntegrationError) as exc_info:
            fetch_changes(settings, date(2024, 1, 1), date(2024, 1, 31))

        assert "Failed to load did config" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, Exception)

    @patch("iptax.did._fetch_provider_changes")
    @patch("iptax.did.did.base.Config")
    def test_fetch_changes_provider_error(
        self,
        _mock_config: Mock,
        mock_fetch_provider: Mock,
        tmp_path: Path,
    ) -> None:
        """Test error when fetching from provider fails."""
        config_path = tmp_path / "did.conf"
        config_path.write_text("[general]\nemail = test@example.com\n")

        settings = Settings(
            employee=EmployeeInfo(name="Test User", supervisor="Manager"),
            product=ProductConfig(name="Product"),
            did=DidConfig(
                config_path=str(config_path),
                providers=["github.com"],
            ),
        )

        mock_fetch_provider.side_effect = RuntimeError("Provider error")

        with pytest.raises(DidIntegrationError) as exc_info:
            fetch_changes(settings, date(2024, 1, 1), date(2024, 1, 31))

        assert "Failed to fetch changes from provider 'github.com'" in str(
            exc_info.value
        )
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    @patch("iptax.did._fetch_provider_changes")
    @patch("iptax.did.did.base.Config")
    def test_fetch_changes_empty_results(
        self,
        _mock_config: Mock,
        mock_fetch_provider: Mock,
        tmp_path: Path,
    ) -> None:
        """Test fetching with no changes."""
        config_path = tmp_path / "did.conf"
        config_path.write_text("[general]\nemail = test@example.com\n")

        settings = Settings(
            employee=EmployeeInfo(name="Test User", supervisor="Manager"),
            product=ProductConfig(name="Product"),
            did=DidConfig(
                config_path=str(config_path),
                providers=["github.com"],
            ),
        )

        mock_fetch_provider.return_value = []

        changes = fetch_changes(settings, date(2024, 1, 1), date(2024, 1, 31))

        assert changes == []
