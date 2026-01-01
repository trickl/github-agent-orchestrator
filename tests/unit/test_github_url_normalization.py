"""Regression tests for GitHub API URL construction.

We previously emitted a trailing slash for repo-root REST endpoints, which can
cause 404s depending on the GitHub deployment / routing layer.

These tests ensure our URL builders do not generate trailing slashes for repo
root calls and normalize user-provided base URLs and repository strings.
"""

from __future__ import annotations

from unittest.mock import Mock

from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard_router import _repo_api_url


def test_dashboard_repo_api_url_repo_root_has_no_trailing_slash() -> None:
    settings = ServerSettings(github_base_url="https://api.github.com/")

    assert (
        _repo_api_url(settings, repository="trickl/breadboard-lab", path="")
        == "https://api.github.com/repos/trickl/breadboard-lab"
    )


def test_orchestrator_repo_url_repo_root_has_no_trailing_slash() -> None:
    # Inject a repo to avoid any network calls during construction.
    client = GitHubClient(
        token="test-token",
        repository="trickl/breadboard-lab/",  # intentionally includes trailing slash
        base_url="https://api.github.com/",  # intentionally includes trailing slash
        repo=Mock(),
    )

    assert (
        client._repo_url(repository="trickl/breadboard-lab/", path="")
        == "https://api.github.com/repos/trickl/breadboard-lab"
    )

    assert (
        client._repo_url(repository="trickl/breadboard-lab", path="issues")
        == "https://api.github.com/repos/trickl/breadboard-lab/issues"
    )
