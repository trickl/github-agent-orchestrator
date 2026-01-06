"""Tests for dashboard loop action endpoints (promote, merge, ensure)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from github_agent_orchestrator.server.app import create_app


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
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")

    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(loop_actions, "_ensure_repo_label_exists", lambda *_a, **_k: None)

    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        lambda *_a, **_k: ["planning/issue_queue/pending/dev-1.md"],
    )
    monkeypatch.setattr(
        loop_actions,
        "_list_repo_markdown_files_under",
        lambda *_a, **_k: ["planning/issue_queue/pending/dev-1.md"],
    )

    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == "planning/issue_queue/pending/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-1"
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)
    monkeypatch.setattr(loop_actions, "_get_repo_text_file", fake_get_repo_text_file)

    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(loop_actions, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(
        dashboard_router, "_search_issue_number_by_queue_marker", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        loop_actions, "_search_issue_number_by_queue_marker", lambda *_a, **_k: None
    )

    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues"):
            return {"number": 123, "html_url": "https://github.com/acme/repo/issues/123"}
        if url.endswith("/issues/123/assignees"):
            return {"assignees": [{"login": "copilot-swe-agent[bot]"}]}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)
    monkeypatch.setattr(loop_actions, "_github_post_json", fake_post_json)
    monkeypatch.setattr(dashboard_router, "_github_put_json", lambda *_a, **_k: (201, {}))
    monkeypatch.setattr(loop_actions, "_github_put_json", lambda *_a, **_k: (201, {}))
    monkeypatch.setattr(dashboard_router, "_github_delete_json", lambda *_a, **_k: (200, {}))
    monkeypatch.setattr(loop_actions, "_github_delete_json", lambda *_a, **_k: (200, {}))

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


def test_ensure_gap_analysis_issue_exists_creates_and_assigns(monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(loop_actions, "_list_open_issues_raw", lambda *_a, **_k: [])
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
    monkeypatch.setattr(loop_actions, "_github_post_json", fake_post_json)
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
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
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
    monkeypatch.setattr(loop_actions, "_assign_issue_to_copilot", fake_assign)

    out = dashboard_router._ensure_gap_analysis_issue_exists(
        settings=dashboard_router.ServerSettings(),
        repo="acme/repo",
    )
    assert out["created"] is False
    assert out["issueNumber"] == 42
    assert out["assigned"]
    assert called.get("issue_number") == 42


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
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(loop_actions, "_list_open_issues_raw", lambda *_a, **_k: [])
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
    monkeypatch.setattr(loop_actions, "_github_get_json", fake_get_json)

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
    monkeypatch.setattr(loop_actions, "_github_post_json", fake_post_json)

    client = TestClient(create_app())
    resp = client.post("/api/loop/gap-analysis/ensure")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo"] == "acme/repo"
    assert data["branch"] == "main"
    assert data["issueNumber"] == 777
    assert data["created"] is True
    assert "summary" in data


def test_ensure_gap_analysis_issue_exists_repairs_unsafe_existing_issue_before_assign(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
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
    monkeypatch.setattr(loop_actions, "_github_patch_json", fake_patch_json)

    assigned_called: dict[str, object] = {}

    def fake_assign(*_a, **kwargs):
        assigned_called.update(kwargs)
        return [{"login": "copilot-swe-agent[bot]"}]

    monkeypatch.setattr(dashboard_router, "_assign_issue_to_copilot", fake_assign)
    monkeypatch.setattr(loop_actions, "_assign_issue_to_copilot", fake_assign)

    out = dashboard_router._ensure_gap_analysis_issue_exists(
        settings=dashboard_router.ServerSettings(),
        repo="acme/repo",
    )
    assert out["created"] is False
    assert out["issueNumber"] == 99
    assert assigned_called.get("issue_number") == 99
    assert isinstance(patched.get("payload"), dict)
    assert str(patched["payload"].get("body") or "").strip() == "# Gap Analysis\n\nUse the template"


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
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(loop_actions, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(
        dashboard_router, "_search_issue_number_by_body_marker", lambda *_a, **_k: None
    )
    monkeypatch.setattr(dashboard_router, "_github_get_list", lambda *_a, **_k: [])
    monkeypatch.setattr(loop_actions, "_github_get_list", lambda *_a, **_k: [])

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
    monkeypatch.setattr(loop_actions, "_list_repo_markdown_files_under", fake_list_repo_md)

    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == "planning/issue_queue/processed/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-queue"
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)
    monkeypatch.setattr(loop_actions, "_get_repo_text_file", fake_get_repo_text_file)

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
    monkeypatch.setattr(loop_actions, "_github_put_json", fake_put_json)

    def fake_delete_json(*_a, **_k):
        return 204, None

    monkeypatch.setattr(dashboard_router, "_github_delete_json", fake_delete_json)
    monkeypatch.setattr(loop_actions, "_github_delete_json", fake_delete_json)

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
    monkeypatch.setattr(loop_actions, "_github_post_json", fake_post_json)

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
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")

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
    monkeypatch.setattr(loop_actions, "_list_issue_timeline_raw", fake_timeline)

    monkeypatch.setattr(dashboard_router, "_github_get_list", lambda *_a, **_k: [])
    monkeypatch.setattr(loop_actions, "_github_get_list", lambda *_a, **_k: [])

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
    monkeypatch.setattr(loop_actions, "_github_post_json", fake_post_json)

    # Merge call.
    def fake_put_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/pulls/5/merge"):
            return 200, {"merged": True, "sha": "deadbeef"}
        return 500, {"message": "unexpected"}

    monkeypatch.setattr(dashboard_router, "_github_put_json", fake_put_json)
    monkeypatch.setattr(loop_actions, "_github_put_json", fake_put_json)
    monkeypatch.setattr(dashboard_router, "_github_delete_json", lambda *_a, **_k: (204, None))
    monkeypatch.setattr(loop_actions, "_github_delete_json", lambda *_a, **_k: (204, None))

    # Close issue.
    def fake_patch_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues/202"):
            return {"number": 202, "state": "closed"}
        raise AssertionError(f"Unexpected PATCH url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_patch_json", fake_patch_json)
    monkeypatch.setattr(loop_actions, "_github_patch_json", fake_patch_json)

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
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(loop_actions, "_ensure_repo_label_exists", lambda *_a, **_k: None)
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
    monkeypatch.setattr(loop_actions, "_list_open_issues_raw", lambda *_a, **_k: [])
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
    monkeypatch.setattr(loop_actions, "_github_post_json", fake_post_json)
    monkeypatch.setattr(dashboard_router, "_github_put_json", lambda *_a, **_k: (201, {}))
    monkeypatch.setattr(loop_actions, "_github_put_json", lambda *_a, **_k: (201, {}))
    monkeypatch.setattr(dashboard_router, "_github_delete_json", lambda *_a, **_k: (204, None))
    monkeypatch.setattr(loop_actions, "_github_delete_json", lambda *_a, **_k: (204, None))

    out = dashboard_router._promote_next_unpromoted_capability_queue_item(
        settings=dashboard_router.ServerSettings(),
        repo="acme/repo",
    )
    assert out["issueNumber"] == 321
    assert str(out["queuePath"]).endswith("planning/issue_queue/pending/system-1.md")
    assert str(out["processedPath"]).endswith("planning/issue_queue/processed/system-1.md")


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
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(loop_actions, "_ensure_repo_label_exists", lambda *_a, **_k: None)

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
    monkeypatch.setattr(loop_actions, "_list_repo_markdown_files_under", fake_list_repo_md)

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
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")

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
    monkeypatch.setattr(loop_actions, "_github_get_list", lambda *_a, **_k: [])

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
    monkeypatch.setattr(loop_actions, "_github_post_json", fake_post_json)

    # Merge call.
    def fake_put_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/pulls/5/merge"):
            return 200, {"merged": True, "sha": "deadbeef"}
        return 500, {"message": "unexpected"}

    monkeypatch.setattr(dashboard_router, "_github_put_json", fake_put_json)
    monkeypatch.setattr(loop_actions, "_github_put_json", fake_put_json)
    monkeypatch.setattr(dashboard_router, "_github_delete_json", lambda *_a, **_k: (204, None))
    monkeypatch.setattr(loop_actions, "_github_delete_json", lambda *_a, **_k: (204, None))

    # Close issue.
    def fake_patch_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues/42"):
            return {"number": 42, "state": "closed"}
        raise AssertionError(f"Unexpected PATCH url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_patch_json", fake_patch_json)
    monkeypatch.setattr(loop_actions, "_github_patch_json", fake_patch_json)

    client = TestClient(create_app())
    resp = client.post("/api/loop/merge")
    assert resp.status_code == 200
    data = resp.json()
    assert data["merged"] is True
    assert data["pullNumber"] == 5
    # Reused merge schema field points at the closed gap-analysis issue.
    assert data["capabilityIssueNumber"] == 42
