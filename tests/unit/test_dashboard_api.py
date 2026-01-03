from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from github_agent_orchestrator.server.app import create_app


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_dashboard_health_and_docs(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    # The dashboard server is now repo-derived (no local planning checkout required).
    # Patch internal helpers to avoid network calls.
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_get_repo_text_file(*_args, **kwargs):
        path = kwargs.get("path")
        if path == "planning/vision/goal.md":
            return "# Goal\n\nShip it.\n", "sha-goal"
        if path == "planning/state/system_capabilities.md":
            return "# System Capabilities\n\n- A\n", "sha-caps"
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)
    monkeypatch.setattr(
        dashboard_router,
        "_load_repo_cognitive_task_templates",
        lambda **_k: [
            {
                "id": "review-complexity.md",
                "name": "review complexity",
                "category": "review",
                "enabled": True,
                "promptText": "# Review: Complexity\n",
                "targetFolder": "planning/issue_queue/pending",
                "trigger": {"kind": "MANUAL_ONLY"},
                "editable": False,
            }
        ],
    )

    client = TestClient(create_app())

    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["ok"] is True
    assert "version" in health
    assert health["repoName"] == "acme/repo"

    goal = client.get("/api/docs/goal").json()
    assert goal["key"] == "goal"
    assert goal["title"] == "Goal"
    assert goal["path"].endswith("planning/vision/goal.md")
    assert "Ship it" in goal["content"]

    caps = client.get("/api/docs/capabilities").json()
    assert caps["key"] == "capabilities"
    assert caps["title"] == "System Capabilities"
    assert caps["path"].endswith("planning/state/system_capabilities.md")

    tasks = client.get("/api/cognitive-tasks").json()
    assert any(t.get("id") == "review-complexity.md" for t in tasks)


def test_cognitive_tasks_create_endpoint_is_not_exposed(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    client = TestClient(create_app())

    resp = client.post("/api/cognitive-tasks", json={"name": "Should fail"})
    assert resp.status_code == 405


def test_loop_status_endpoint(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return [
                "planning/issue_queue/pending/dev-1.md",
                "planning/issue_queue/pending/nested/dev-2.md",
            ]
        if dir_path == "planning/issue_queue/processed":
            return []
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)

    # Provide file contents so /api/loop can read the first line title.
    def fake_get_repo_text_file(*_args, **kwargs):
        path = kwargs.get("path")
        if path == "planning/issue_queue/pending/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-1"
        if path == "planning/issue_queue/pending/nested/dev-2.md":
            return "Dev: Two\n\nBody\n", "sha-2"
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)

    # No open issues => pending files cannot match any issue => Step B
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_list_issue_timeline_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_get_pull_request", lambda *_a, **_k: {})

    client = TestClient(create_app())

    loop = client.get("/api/loop").json()
    # Pending development queue files exist and none are promoted to issues => Step B
    assert loop["stage"] == "2a"
    assert loop["activeStep"] == 3
    assert loop["counts"]["pending"] == 2
    assert loop["counts"]["openIssues"] == 0
    assert loop["counts"]["openPullRequests"] == 0
    assert loop["counts"]["unpromotedPending"] == 2
    assert loop["counts"]["pendingDevelopmentWithoutPr"] == 0


def test_loop_status_stage_c_when_issue_exists_but_no_pr(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return ["planning/issue_queue/pending/dev-1.md"]
        if dir_path == "planning/issue_queue/processed":
            return []
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)

    def fake_get_repo_text_file(*_args, **kwargs):
        path = kwargs.get("path")
        if path == "planning/issue_queue/pending/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-1"
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)

    # Open issue matches the pending file title, but no PR cross-references exist.
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_list_issue_timeline_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_get_pull_request", lambda *_a, **_k: {})

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "2b"
    assert loop["activeStep"] == 4
    assert loop["counts"]["pending"] == 1
    assert loop["counts"]["openIssues"] == 1
    assert loop["counts"]["unpromotedPending"] == 0
    assert loop["counts"]["pendingDevelopmentWithoutPr"] == 1


def test_loop_status_stage_d_when_processed_has_ready_pr(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

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

    def fake_get_repo_text_file(*_args, **kwargs):
        path = kwargs.get("path")
        if path == "planning/issue_queue/processed/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-1"
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)

    # Open issue matches the queue file title.
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    # Timeline cross-reference to PR #5.
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

    # PR is open, non-draft, review requested, and conflict-free.
    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "title": "Dev: One",
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
        },
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "2c"
    assert loop["activeStep"] == 5


def test_loop_status_stage_d_when_processed_has_review_requested_event_even_without_requested_reviewers(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

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
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )

    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    def fake_timeline(*_a, **kwargs):
        # Issue -> PR cross reference.
        if kwargs.get("issue_number") == 101:
            return [
                {
                    "event": "cross-referenced",
                    "source": {"issue": {"number": 5, "pull_request": {}}},
                }
            ]
        # PR issue timeline contains the explicit review request signal (requested reviewers can be cleared).
        if kwargs.get("issue_number") == 5:
            return [{"event": "review_requested"}]
        return []

    monkeypatch.setattr(dashboard_router, "_list_issue_timeline_raw", fake_timeline)

    # PR is open and conflict-free, but requested_reviewers is empty (GitHub clears it after review).
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
        },
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "2c"
    assert loop["activeStep"] == 5


def test_loop_status_auto_resumes_copilot_after_rate_limit_delay(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    # Enable auto-resume and ensure GitHub token is present so posting is allowed.
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ORCHESTRATOR_AUTO_RESUME_COPILOT_ON_RATE_LIMIT", "true")
    monkeypatch.setenv("ORCHESTRATOR_AUTO_RESUME_COPILOT_ON_RATE_LIMIT_DELAY_MINUTES", "45")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

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
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    # Issue -> PR cross-reference.
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

    # PR is open but not yet merge-candidate (no review request signal), so stage remains 2b.
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

    # The PR has a Copilot-authored rate limit stop comment at t=00:00Z.
    monkeypatch.setattr(
        dashboard_router,
        "_list_issue_comments_raw",
        lambda *_a, **_k: [
            {
                "id": 1,
                "created_at": "2026-01-03T00:00:00Z",
                "user": {"login": "copilot-swe-agent"},
                "body": (
                    "Sorry, you've hit a rate limit that restricts the number of Copilot model "
                    "requests you can make within a specific time period. Please try again in 46 minutes.\n"
                    "To retry, leave a comment on this pull request asking Copilot to try again."
                ),
            }
        ],
    )

    # Freeze time at 00:46Z so we're past the 45-minute delay.
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
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "2b"
    assert posted["url"].endswith("/repos/acme/repo/issues/5/comments")
    assert posted["payload"] == {"body": "@copilot please can you attempt to resume this work now?"}


def test_loop_status_auto_resumes_copilot_from_graphql_timeline_fallback(
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
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
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

    # REST issue comments are empty, so the implementation should fall back to GraphQL.
    monkeypatch.setattr(dashboard_router, "_list_issue_comments_raw", lambda *_a, **_k: [])

    def fake_graphql_post(*_a, **_k):
        return {
            "data": {
                "repository": {
                    "pullRequest": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "IssueComment",
                                    "createdAt": "2026-01-03T00:00:00Z",
                                    "body": (
                                        "Sorry, you've hit a rate limit that restricts the number of "
                                        "Copilot model requests you can make within a specific time period. "
                                        "Please try again in 46 minutes.\n"
                                        "To retry, leave a comment on this pull request asking Copilot to try again."
                                    ),
                                    "author": {"login": "copilot-swe-agent"},
                                }
                            ]
                        }
                    }
                }
            }
        }

    monkeypatch.setattr(dashboard_router, "_github_graphql_post", fake_graphql_post)

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
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
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

    # No comments, and GraphQL returns no nodes (best-effort fallback).
    monkeypatch.setattr(dashboard_router, "_list_issue_comments_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(
        dashboard_router, "_list_pull_request_timeline_items_via_graphql", lambda *_a, **_k: []
    )

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


def test_loop_status_does_not_advance_when_pr_is_wip(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

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
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
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
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "title": "WIP: Dev: One",
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
        },
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "2b"
    assert loop["activeStep"] == 4


def test_loop_status_stage_a_exposes_gap_pr_ready_for_merge(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    # No queue artefacts; loop is governed by open gap-analysis issue.
    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path in {
            "planning/issue_queue/pending",
            "planning/issue_queue/processed",
            "planning/issue_queue/complete",
        }:
            return []
        return []

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)

    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 42,
                "title": "Identify the next most important development gap",
                "state": "open",
            }
        ],
    )
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    # Gap-analysis issue timeline cross-references PR #5.
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
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "title": "Gap analysis results",
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
            "html_url": "https://github.com/acme/repo/pull/5",
        },
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "1c"
    assert loop["activeStep"] == 2
    assert loop["counts"]["openGapAnalysisIssues"] == 1
    assert loop["counts"]["openGapAnalysisIssuesWithPr"] == 1
    assert loop["counts"]["openGapAnalysisIssuesReadyForReview"] == 1

    focus = loop.get("focus")
    assert isinstance(focus, dict)
    assert focus.get("kind") == "gap"
    assert focus.get("issueNumber") == 42
    assert focus.get("pullNumber") == 5


def test_loop_status_stage_1c_when_gap_pr_is_draft_but_review_requested(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    # No queue artefacts; loop is governed by open gap-analysis issue.
    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        lambda *_a, **_k: [],
    )

    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 42,
                "title": "Identify the next most important development gap",
                "state": "open",
                "assignees": [],
            }
        ],
    )
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    # Gap-analysis issue timeline cross-references PR #5.
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

    # Draft PR with review requested should still count as "ready" for the merge step,
    # because the merge endpoint may mark it ready-for-review before merging.
    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": True,
            "title": "Add development task: Render components",
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
            "html_url": "https://github.com/acme/repo/pull/5",
        },
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "1c"
    assert loop["activeStep"] == 2
    assert loop["counts"]["openGapAnalysisIssues"] == 1
    assert loop["counts"]["openGapAnalysisIssuesWithPr"] == 1
    assert loop["counts"]["openGapAnalysisIssuesReadyForReview"] == 1


def test_loop_promote_endpoint_promotes_one_file(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")

    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)

    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        lambda *_a, **_k: ["planning/issue_queue/pending/dev-1.md"],
    )

    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == "planning/issue_queue/pending/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-1"
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)

    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(
        dashboard_router, "_search_issue_number_by_queue_marker", lambda *_a, **_k: None
    )

    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues"):
            return {"number": 123, "html_url": "https://github.com/acme/repo/issues/123"}
        if url.endswith("/issues/123/assignees"):
            return {"assignees": [{"login": "copilot-swe-agent[bot]"}]}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)
    monkeypatch.setattr(dashboard_router, "_github_put_json", lambda *_a, **_k: (201, {}))
    monkeypatch.setattr(dashboard_router, "_github_delete_json", lambda *_a, **_k: (200, {}))

    client = TestClient(create_app())
    resp = client.post("/api/loop/promote")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo"] == "acme/repo"
    assert data["branch"] == "main"
    assert data["issueNumber"] == 123
    assert data["created"] is True
    assert data["queuePath"].endswith("planning/issue_queue/pending/dev-1.md")
    assert data["processedPath"].endswith("planning/issue_queue/processed/dev-1.md")


def test_loop_gap_analysis_ensure_endpoint_creates_and_assigns(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("# Gap Analysis\n\nDo the thing\n", "sha"),
    )

    def fake_get_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        # Assignment safety gate reads the issue after creation.
        if url.endswith("/repos/acme/repo/issues/777"):
            return {
                "number": 777,
                "title": "Identify the next most important development gap",
                "body": "x",
            }
        raise AssertionError(f"Unexpected GET url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_get_json", fake_get_json)

    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        payload = kwargs.get("payload")
        if url.endswith("/issues"):
            assert isinstance(payload, dict)
            return {"number": 777}
        if url.endswith("/issues/777/assignees"):
            return {"assignees": [{"login": "copilot-swe-agent[bot]"}]}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)

    client = TestClient(create_app())
    resp = client.post("/api/loop/gap-analysis/ensure")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo"] == "acme/repo"
    assert data["branch"] == "main"
    assert data["issueNumber"] == 777
    assert data["created"] is True
    assert "summary" in data


def test_loop_status_stage_e_when_open_update_capability_issue_exists(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return ["planning/issue_queue/pending/dev-1.md"]
        if dir_path == "planning/issue_queue/processed":
            return []
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        fake_list_repo_md,
    )

    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-1"),
    )

    # Both a development issue and an Update Capability issue are open; capability should win.
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {"number": 101, "title": "Dev: One", "state": "open"},
            {
                "number": 202,
                "title": "Update system capabilities based on merged PR #5",
                "state": "open",
                "labels": [{"name": "Update Capability"}],
            },
        ],
    )

    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_list_issue_timeline_raw", lambda *_a, **_k: [])

    # The loop status call now fetches the capability issue body to recover the original PR number.
    def fake_github_get_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/repos/acme/repo/issues/202"):
            return {
                "number": 202,
                "title": "Update system capabilities based on merged PR #5",
                "body": "---\n\n<!-- orchestrator:capability-update-from-pr acme/repo#5 -->\n",
            }
        raise AssertionError(f"Unexpected GET url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_get_json", fake_github_get_json)

    def fake_get_pull_request(*_a, **kwargs):
        pr_number = kwargs.get("pr_number")
        if pr_number == 5:
            return {
                "number": 5,
                "state": "closed",
                "title": "Add thing",
                "html_url": "https://github.com/acme/repo/pull/5",
            }
        return {}

    monkeypatch.setattr(dashboard_router, "_get_pull_request", fake_get_pull_request)

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()
    assert loop["stage"] == "3a"
    assert loop["activeStep"] == 6

    focus = loop.get("focus")
    assert isinstance(focus, dict)
    assert focus.get("kind") == "capability"
    assert focus.get("issueNumber") == 202
    assert focus.get("sourcePullNumber") == 5
    assert focus.get("sourceTitle") == "Add thing"


def test_loop_status_stage_g_when_open_update_capability_issue_has_ready_pr(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    def fake_list_repo_md(*_args, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return []
        if dir_path == "planning/issue_queue/processed":
            return []
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        fake_list_repo_md,
    )

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", lambda *_a, **_k: ("", "sha"))

    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 202,
                "title": "Update system capabilities based on merged PR #5",
                "state": "open",
                "labels": [{"name": "Update Capability"}],
            }
        ],
    )

    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])

    def fake_timeline(*_a, **kwargs):
        if kwargs.get("issue_number") == 202:
            return [
                {
                    "event": "cross-referenced",
                    "source": {"issue": {"number": 7, "pull_request": {}}},
                }
            ]
        return []

    monkeypatch.setattr(dashboard_router, "_list_issue_timeline_raw", fake_timeline)

    def fake_github_get_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/repos/acme/repo/issues/202"):
            return {
                "number": 202,
                "title": "Update system capabilities based on merged PR #5",
                "body": "x\n<!-- orchestrator:capability-update-from-pr acme/repo#5 -->\n",
            }
        raise AssertionError(f"Unexpected GET url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_get_json", fake_github_get_json)

    def fake_get_pull_request(*_a, **kwargs):
        pr_number = kwargs.get("pr_number")
        if pr_number == 7:
            return {
                "number": 7,
                "state": "open",
                "draft": False,
                "requested_reviewers": [{"login": "alice"}],
                "requested_teams": [],
                "mergeable_state": "clean",
                "html_url": "https://github.com/acme/repo/pull/7",
            }
        if pr_number == 5:
            return {
                "number": 5,
                "state": "closed",
                "draft": False,
                "requested_reviewers": [],
                "requested_teams": [],
                "mergeable_state": "clean",
                "title": "Add thing",
                "html_url": "https://github.com/acme/repo/pull/5",
            }
        return {}

    monkeypatch.setattr(dashboard_router, "_get_pull_request", fake_get_pull_request)

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()
    assert loop["stage"] == "3c"
    assert loop["activeStep"] == 8

    focus = loop.get("focus")
    assert isinstance(focus, dict)
    assert focus.get("kind") == "capability"
    assert focus.get("issueNumber") == 202
    assert focus.get("sourcePullNumber") == 5
    assert focus.get("pullNumber") == 7


def test_loop_merge_endpoint_merges_one_ready_pr_and_creates_capability_issue(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(
        dashboard_router, "_search_issue_number_by_body_marker", lambda *_a, **_k: None
    )
    monkeypatch.setattr(dashboard_router, "_github_get_list", lambda *_a, **_k: [])

    def fake_list_repo_md(*_a, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return []
        if dir_path == "planning/issue_queue/processed":
            return ["planning/issue_queue/processed/dev-1.md"]
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)

    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == "planning/issue_queue/processed/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-queue"
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)

    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )

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
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
            "title": "Add thing",
            "body": "PR body",
            "head": {"ref": "feature/one", "repo": {"full_name": "acme/repo"}},
        },
    )

    def fake_put_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/pulls/5/merge"):
            return 200, {"merged": True, "sha": "abc123"}
        if "/contents/planning/issue_queue/complete/" in url:
            return 201, {}
        return 500, {"message": "unexpected"}

    monkeypatch.setattr(dashboard_router, "_github_put_json", fake_put_json)

    def fake_delete_json(*_a, **_k):
        return 204, None

    monkeypatch.setattr(dashboard_router, "_github_delete_json", fake_delete_json)

    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/pulls/5/reviews"):
            return {"id": 1}
        if url.endswith("/issues"):
            return {"number": 456}
        if url.endswith("/issues/456/assignees"):
            return {"assignees": [{"login": "copilot-swe-agent[bot]"}]}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)

    client = TestClient(create_app())
    resp = client.post("/api/loop/merge")
    assert resp.status_code == 200
    data = resp.json()
    assert data["merged"] is True
    assert data["pullNumber"] == 5
    assert data["capabilityIssueNumber"] == 456


def test_loop_merge_endpoint_merges_ready_capability_pr_and_closes_issue(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")

    # An open Update Capability issue exists.
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 202,
                "title": "Update system capabilities based on merged PR #5",
                "state": "open",
                "labels": [{"name": "Update Capability"}],
            }
        ],
    )

    # Issue timeline cross-references PR #5.
    def fake_timeline(*_a, **kwargs):
        if kwargs.get("issue_number") == 202:
            return [
                {
                    "event": "cross-referenced",
                    "source": {"issue": {"number": 5, "pull_request": {}}},
                }
            ]
        return []

    monkeypatch.setattr(dashboard_router, "_list_issue_timeline_raw", fake_timeline)

    monkeypatch.setattr(dashboard_router, "_github_get_list", lambda *_a, **_k: [])

    # PR is open, non-draft, review requested, and conflict-free.
    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
            "title": "Update capabilities",
            "body": "Update system_capabilities.md",
            "head": {"ref": "feature/caps", "repo": {"full_name": "acme/repo"}},
        },
    )

    # Best-effort approval.
    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/pulls/5/reviews"):
            return {"id": 1}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)

    # Merge call.
    def fake_put_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/pulls/5/merge"):
            return 200, {"merged": True, "sha": "deadbeef"}
        return 500, {"message": "unexpected"}

    monkeypatch.setattr(dashboard_router, "_github_put_json", fake_put_json)
    monkeypatch.setattr(dashboard_router, "_github_delete_json", lambda *_a, **_k: (204, None))

    # Close issue.
    def fake_patch_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues/202"):
            return {"number": 202, "state": "closed"}
        raise AssertionError(f"Unexpected PATCH url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_patch_json", fake_patch_json)

    client = TestClient(create_app())
    resp = client.post("/api/loop/merge")
    assert resp.status_code == 200
    data = resp.json()
    assert data["merged"] is True
    assert data["pullNumber"] == 5
    assert data["capabilityIssueNumber"] == 202


def test_promote_next_unpromoted_capability_queue_item_promotes_one_file(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        lambda *_a, **_k: ["planning/issue_queue/pending/system-1.md"],
    )
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("System: Update capability\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(
        dashboard_router,
        "_search_issue_number_by_queue_marker",
        lambda *_a, **_k: None,
    )

    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        payload = kwargs.get("payload")
        if url.endswith("/issues"):
            assert isinstance(payload, dict)
            assert payload.get("labels") == ["Update Capability"]
            return {"number": 321}
        if url.endswith("/issues/321/assignees"):
            return {"assignees": [{"login": "copilot-swe-agent[bot]"}]}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)
    monkeypatch.setattr(dashboard_router, "_github_put_json", lambda *_a, **_k: (201, {}))
    monkeypatch.setattr(dashboard_router, "_github_delete_json", lambda *_a, **_k: (204, None))

    out = dashboard_router._promote_next_unpromoted_capability_queue_item(
        settings=dashboard_router.ServerSettings(),
        repo="acme/repo",
    )
    assert out["issueNumber"] == 321
    assert str(out["queuePath"]).endswith("planning/issue_queue/pending/system-1.md")
    assert str(out["processedPath"]).endswith("planning/issue_queue/processed/system-1.md")


def test_ensure_gap_analysis_issue_exists_creates_and_assigns(monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(
        dashboard_router,
        "_load_gap_analysis_template_or_raise",
        lambda **_k: "# Gap Analysis\n\nDo the thing\n",
    )

    created: dict[str, object] = {}

    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        payload = kwargs.get("payload")
        if url.endswith("/issues"):
            assert isinstance(payload, dict)
            assert "gap" in str(payload.get("title") or "").lower()
            created.update(payload)
            return {"number": 777}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)
    monkeypatch.setattr(
        dashboard_router,
        "_assign_issue_to_copilot",
        lambda *_a, **_k: [{"login": "copilot-swe-agent[bot]"}],
    )

    out = dashboard_router._ensure_gap_analysis_issue_exists(
        settings=dashboard_router.ServerSettings(),
        repo="acme/repo",
    )
    assert out["created"] is True
    assert out["issueNumber"] == 777
    assert out["assigned"]
    created_body = str(created.get("body") or "")
    assert created_body.strip() == "# Gap Analysis\n\nDo the thing"
    assert "Completion:" not in created_body
    assert "Open a PR" not in created_body
    assert "Create one development task" not in created_body


def test_ensure_gap_analysis_issue_exists_assigns_existing_when_unassigned(monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 42,
                "title": "Identify the next most important development gap",
                "assignees": [],
            }
        ],
    )

    called: dict[str, object] = {}

    def fake_assign(*_a, **kwargs):
        called.update(kwargs)
        return [{"login": "copilot-swe-agent[bot]"}]

    monkeypatch.setattr(dashboard_router, "_assign_issue_to_copilot", fake_assign)

    out = dashboard_router._ensure_gap_analysis_issue_exists(
        settings=dashboard_router.ServerSettings(),
        repo="acme/repo",
    )
    assert out["created"] is False
    assert out["issueNumber"] == 42
    assert out["assigned"]
    assert called.get("issue_number") == 42


def test_ensure_gap_analysis_issue_exists_repairs_unsafe_existing_issue_before_assign(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 99,
                "title": "Identify the next most important development gap",
                "assignees": [],
                "body": "# Gap Analysis\n\nCompletion:\n- Open a PR that adds exactly one new file\n",
            }
        ],
    )
    monkeypatch.setattr(
        dashboard_router,
        "_load_gap_analysis_template_or_raise",
        lambda **_k: "# Gap Analysis\n\nUse the template\n",
    )

    patched: dict[str, object] = {}

    def fake_patch_json(*_a, **kwargs):
        patched.update({"url": kwargs.get("url"), "payload": kwargs.get("payload")})
        return {"number": 99}

    monkeypatch.setattr(dashboard_router, "_github_patch_json", fake_patch_json)

    assigned_called: dict[str, object] = {}

    def fake_assign(*_a, **kwargs):
        assigned_called.update(kwargs)
        return [{"login": "copilot-swe-agent[bot]"}]

    monkeypatch.setattr(dashboard_router, "_assign_issue_to_copilot", fake_assign)

    out = dashboard_router._ensure_gap_analysis_issue_exists(
        settings=dashboard_router.ServerSettings(),
        repo="acme/repo",
    )
    assert out["created"] is False
    assert out["issueNumber"] == 99
    assert assigned_called.get("issue_number") == 99
    assert isinstance(patched.get("payload"), dict)
    assert str(patched["payload"].get("body") or "").strip() == "# Gap Analysis\n\nUse the template"


def test_loop_merge_endpoint_fails_cleanly_when_pr_stays_draft(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)

    def fake_list_repo_md(*_a, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == "planning/issue_queue/pending":
            return []
        if dir_path == "planning/issue_queue/processed":
            return ["planning/issue_queue/processed/dev-1.md"]
        if dir_path == "planning/issue_queue/complete":
            return []
        return []

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)

    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-queue"),
    )

    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )

    monkeypatch.setattr(
        dashboard_router,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {"event": "cross-referenced", "source": {"issue": {"number": 5, "pull_request": {}}}}
        ],
    )

    # Draft PR but review requested + clean, so it is considered Stage D "ready" for review.
    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": True,
            "node_id": "PR_node_id",
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
        },
    )

    # GraphQL markPullRequestReadyForReview fails (simulate GitHub refusing or insufficient perms).
    monkeypatch.setattr(
        dashboard_router,
        "_github_graphql_post",
        lambda *_a, **_k: {"errors": [{"message": "Pull Request is still a draft"}]},
    )

    # Merge must not be attempted; if it is, fail the test.
    monkeypatch.setattr(
        dashboard_router,
        "_github_put_json",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("merge should not be attempted")),
    )

    client = TestClient(create_app())
    resp = client.post("/api/loop/merge")
    assert resp.status_code == 409
    detail = resp.json()["detail"].lower()
    assert "still a draft" in detail
    assert "markpullrequestreadyforreview" in detail
    assert "graphql" in detail


def test_loop_merge_endpoint_merges_ready_gap_analysis_pr_and_closes_issue(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")

    # An open gap-analysis issue exists.
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 42,
                "title": "Identify the next most important development gap",
                "state": "open",
            }
        ],
    )

    # Issue timeline cross-references PR #5.
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

    monkeypatch.setattr(dashboard_router, "_github_get_list", lambda *_a, **_k: [])

    # PR is open, non-draft, review requested, and conflict-free.
    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
            "title": "Gap analysis results",
            "body": "Gap analysis body",
            "head": {"ref": "feature/gap", "repo": {"full_name": "acme/repo"}},
        },
    )

    # Best-effort approval.
    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/pulls/5/reviews"):
            return {"id": 1}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)

    # Merge call.
    def fake_put_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/pulls/5/merge"):
            return 200, {"merged": True, "sha": "deadbeef"}
        return 500, {"message": "unexpected"}

    monkeypatch.setattr(dashboard_router, "_github_put_json", fake_put_json)
    monkeypatch.setattr(dashboard_router, "_github_delete_json", lambda *_a, **_k: (204, None))

    # Close issue.
    def fake_patch_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues/42"):
            return {"number": 42, "state": "closed"}
        raise AssertionError(f"Unexpected PATCH url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_patch_json", fake_patch_json)

    client = TestClient(create_app())
    resp = client.post("/api/loop/merge")
    assert resp.status_code == 200
    data = resp.json()
    assert data["merged"] is True
    assert data["pullNumber"] == 5
    # Reused merge schema field points at the closed gap-analysis issue.
    assert data["capabilityIssueNumber"] == 42
