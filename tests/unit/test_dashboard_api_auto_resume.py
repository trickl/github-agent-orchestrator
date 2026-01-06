"""Tests for dashboard auto-resume functionality."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from github_agent_orchestrator.server.app import create_app


def test_loop_status_auto_resumes_copilot_from_issue_events_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ORCHESTRATOR_AUTO_RESUME_COPILOT_ON_RATE_LIMIT", "true")
    monkeypatch.setenv("ORCHESTRATOR_AUTO_RESUME_COPILOT_ON_RATE_LIMIT_DELAY_MINUTES", "45")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router
    from github_agent_orchestrator.server.dashboard import loop_status

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return []
        if dir_path == "planning/issue_queue/processed":
            return ["planning/issue_queue/processed/dev-1.md"]
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)
    monkeypatch.setattr(loop_status, "_list_repo_markdown_files_under", fake_list_repo_md)
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        loop_status,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(
        loop_status,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(loop_status, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(
        dashboard_router,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 5, "pull_request": {}}},
            }
        ],
    )
    monkeypatch.setattr(
        loop_status,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 5, "pull_request": {}}},
            }
        ],
    )
    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "title": "Dev: One",
            "requested_reviewers": [],
            "requested_teams": [],
            "mergeable_state": "clean",
            "html_url": "https://github.com/acme/repo/pull/5",
        },
    )
    monkeypatch.setattr(
        loop_status,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "title": "Dev: One",
            "requested_reviewers": [],
            "requested_teams": [],
            "mergeable_state": "clean",
            "html_url": "https://github.com/acme/repo/pull/5",
        },
    )

    # No comments: the implementation relies on issue events as the stop signal.
    monkeypatch.setattr(dashboard_router, "_list_issue_comments_raw", lambda *_a, **_k: [])

    # Issue events show a Copilot work failure at t=00:00Z.
    monkeypatch.setattr(
        dashboard_router,
        "_list_issue_events_raw",
        lambda *_a, **_k: [
            {
                "event": "copilot_work_started",
                "created_at": "2026-01-03T00:00:00Z",
                "performed_via_github_app": {"slug": "copilot-swe-agent"},
            },
            {
                "event": "copilot_work_finished_failure",
                "created_at": "2026-01-03T00:00:00Z",
                "performed_via_github_app": {"slug": "copilot-swe-agent"},
            },
        ],
    )

    monkeypatch.setattr(
        dashboard_router,
        "_utc_now",
        lambda: dashboard_router._dt_from_iso("2026-01-03T00:46:00Z"),
    )

    posted: dict[str, object] = {}

    def fake_post_json(_settings, *, url: str, payload: dict[str, object]):
        posted["url"] = url
        posted["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)

    client = TestClient(create_app())
    _loop = client.get("/api/loop").json()

    assert posted["url"].endswith("/repos/acme/repo/issues/5/comments")
    assert posted["payload"] == {"body": "@copilot please can you attempt to resume this work now?"}


def test_loop_status_auto_resume_copilot_respects_nudge_budget(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ORCHESTRATOR_AUTO_RESUME_COPILOT_ON_RATE_LIMIT", "true")
    monkeypatch.setenv("ORCHESTRATOR_AUTO_RESUME_COPILOT_ON_RATE_LIMIT_DELAY_MINUTES", "45")
    monkeypatch.setenv("ORCHESTRATOR_AUTO_RESUME_COPILOT_MAX_NUDGES", "1")
    monkeypatch.setenv("ORCHESTRATOR_AUTO_RESUME_COPILOT_NUDGE_WINDOW_MINUTES", "1440")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router
    from github_agent_orchestrator.server.dashboard import loop_status

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return []
        if dir_path == "planning/issue_queue/processed":
            return ["planning/issue_queue/processed/dev-1.md"]
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)
    monkeypatch.setattr(loop_status, "_list_repo_markdown_files_under", fake_list_repo_md)
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        loop_status,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(
        loop_status,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(loop_status, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(
        dashboard_router,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 5, "pull_request": {}}},
            }
        ],
    )
    monkeypatch.setattr(
        loop_status,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 5, "pull_request": {}}},
            }
        ],
    )
    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "title": "Dev: One",
            "requested_reviewers": [],
            "requested_teams": [],
            "mergeable_state": "clean",
            "html_url": "https://github.com/acme/repo/pull/5",
        },
    )
    monkeypatch.setattr(
        loop_status,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "title": "Dev: One",
            "requested_reviewers": [],
            "requested_teams": [],
            "mergeable_state": "clean",
            "html_url": "https://github.com/acme/repo/pull/5",
        },
    )

    # Copilot fails twice; there is already one prior nudge in the window.
    monkeypatch.setattr(
        dashboard_router,
        "_list_issue_events_raw",
        lambda *_a, **_k: [
            {
                "event": "copilot_work_started",
                "created_at": "2026-01-03T00:00:00Z",
                "performed_via_github_app": {"slug": "copilot-swe-agent"},
            },
            {
                "event": "copilot_work_finished_failure",
                "created_at": "2026-01-03T00:00:00Z",
                "performed_via_github_app": {"slug": "copilot-swe-agent"},
            },
            {
                "event": "copilot_work_finished_failure",
                "created_at": "2026-01-03T01:00:00Z",
                "performed_via_github_app": {"slug": "copilot-swe-agent"},
            },
        ],
    )

    monkeypatch.setattr(
        dashboard_router,
        "_utc_now",
        lambda: dashboard_router._dt_from_iso("2026-01-03T01:46:00Z"),
    )

    monkeypatch.setattr(
        dashboard_router,
        "_list_issue_comments_raw",
        lambda *_a, **_k: [
            {
                "id": 1,
                "created_at": "2026-01-03T00:46:00Z",
                "user": {"login": "alice"},
                "body": "@copilot please can you attempt to resume this work now?",
            }
        ],
    )

    posted: dict[str, object] = {}

    def fake_post_json(_settings, *, url: str, payload: dict[str, object]):
        posted["url"] = url
        posted["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)

    client = TestClient(create_app())
    _loop = client.get("/api/loop").json()

    # Budget is exhausted, so no post occurs.
    assert posted == {}
