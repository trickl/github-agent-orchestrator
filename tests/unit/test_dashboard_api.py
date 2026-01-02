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

    assert client.get("/api/health").json() == {"status": "ok"}

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
    assert loop["stage"] == "B"
    assert loop["activeStep"] == 1
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

    assert loop["stage"] == "C"
    assert loop["activeStep"] == 2
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
            "draft": True,
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
        },
    )

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "D"
    assert loop["activeStep"] == 3


def test_loop_status_stage_d_when_processed_has_approved_pr_even_without_review_request(
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

    # PR is open and conflict-free, but requested_reviewers is empty (GitHub clears it after review).
    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "requested_reviewers": [],
            "requested_teams": [],
            "mergeable_state": "clean",
        },
    )

    def fake_github_get_list(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/pulls/5/reviews"):
            return [
                {
                    "state": "APPROVED",
                    "submitted_at": "2026-01-01T00:00:00Z",
                    "user": {"login": "alice"},
                }
            ]
        return []

    monkeypatch.setattr(dashboard_router, "_github_get_list", fake_github_get_list)

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()

    assert loop["stage"] == "D"
    assert loop["activeStep"] == 3


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
    monkeypatch.setattr(dashboard_router, "_get_pull_request", lambda *_a, **_k: {})

    client = TestClient(create_app())
    loop = client.get("/api/loop").json()
    assert loop["stage"] == "E"
    assert loop["activeStep"] == 4


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
