"""Tests for auto-mark-ready automation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from github_agent_orchestrator.server.dashboard.automation_auto_mark_ready import (
    maybe_auto_mark_focused_pr_ready,
)


def _make_settings(*, enabled: bool = True, token: str = "ghp_test") -> MagicMock:
    settings = MagicMock()
    settings.auto_mark_draft_pr_ready = enabled
    settings.github_token = token
    settings.github_base_url = "https://api.github.com"
    return settings


def test_noop_when_disabled() -> None:
    settings = _make_settings(enabled=False)
    result = maybe_auto_mark_focused_pr_ready(
        settings=settings,
        repository="acme/repo",
        focus={"pullNumber": 42},
        pr_cache={42: {"draft": True, "node_id": "PR_abc"}},
    )
    assert result is None


def test_noop_when_no_token() -> None:
    settings = _make_settings(token="")
    result = maybe_auto_mark_focused_pr_ready(
        settings=settings,
        repository="acme/repo",
        focus={"pullNumber": 42},
        pr_cache={42: {"draft": True, "node_id": "PR_abc"}},
    )
    assert result is None


def test_noop_when_no_pull_number_in_focus() -> None:
    settings = _make_settings()
    result = maybe_auto_mark_focused_pr_ready(
        settings=settings,
        repository="acme/repo",
        focus={"issueNumber": 10},
        pr_cache={},
    )
    assert result is None


def test_noop_when_pr_not_draft() -> None:
    settings = _make_settings()
    result = maybe_auto_mark_focused_pr_ready(
        settings=settings,
        repository="acme/repo",
        focus={"pullNumber": 42},
        pr_cache={42: {"draft": False, "node_id": "PR_abc"}},
    )
    assert result is None


def test_noop_when_pr_not_in_cache() -> None:
    settings = _make_settings()
    result = maybe_auto_mark_focused_pr_ready(
        settings=settings,
        repository="acme/repo",
        focus={"pullNumber": 42},
        pr_cache={},
    )
    assert result is None


def test_noop_when_no_node_id() -> None:
    settings = _make_settings()
    result = maybe_auto_mark_focused_pr_ready(
        settings=settings,
        repository="acme/repo",
        focus={"pullNumber": 42},
        pr_cache={42: {"draft": True}},
    )
    assert result is None


def test_marks_draft_pr_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings()
    pr_data = {"draft": True, "node_id": "PR_abc123"}
    pr_cache = {42: pr_data}

    from github_agent_orchestrator.server.dashboard import automation_auto_mark_ready

    graphql_called = {}

    def fake_graphql_post(_settings, *, query: str, variables: dict) -> dict:
        graphql_called["query"] = query
        graphql_called["variables"] = variables
        return {
            "data": {
                "markPullRequestReadyForReview": {
                    "pullRequest": {"isDraft": False}
                }
            }
        }

    monkeypatch.setattr(automation_auto_mark_ready, "_github_graphql_post", fake_graphql_post)
    monkeypatch.setattr(
        automation_auto_mark_ready, "_graphql_errors_as_message", lambda payload: None
    )

    result = maybe_auto_mark_focused_pr_ready(
        settings=settings,
        repository="acme/repo",
        focus={"pullNumber": 42},
        pr_cache=pr_cache,
    )

    assert result is not None
    assert "Auto-marked PR #42" in result
    assert graphql_called["variables"]["pullRequestId"] == "PR_abc123"
    # Verify cache was updated
    assert pr_data["draft"] is False


def test_returns_error_message_on_graphql_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings()
    pr_data = {"draft": True, "node_id": "PR_abc123"}
    pr_cache = {42: pr_data}

    from github_agent_orchestrator.server.dashboard import automation_auto_mark_ready

    def fake_graphql_post(_settings, *, query: str, variables: dict) -> dict:
        return {"errors": [{"message": "Something went wrong"}]}

    monkeypatch.setattr(automation_auto_mark_ready, "_github_graphql_post", fake_graphql_post)
    monkeypatch.setattr(
        automation_auto_mark_ready,
        "_graphql_errors_as_message",
        lambda payload: "Something went wrong",
    )

    result = maybe_auto_mark_focused_pr_ready(
        settings=settings,
        repository="acme/repo",
        focus={"pullNumber": 42},
        pr_cache=pr_cache,
    )

    assert result is not None
    assert "failed" in result.lower()
