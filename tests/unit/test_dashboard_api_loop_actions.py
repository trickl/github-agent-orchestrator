"""Tests for dashboard loop action endpoints (promote, merge, ensure)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from github_agent_orchestrator.server.app import create_app


def _merge_endpoint_list_repo_md(*_a, **kwargs):
    dir_path = kwargs.get("dir_path")
    if dir_path == ".agent-orchestrator/issue_queue/pending":
        return []
    if dir_path == ".agent-orchestrator/issue_queue/processed":
        return [".agent-orchestrator/issue_queue/processed/dev-1.md"]
    if dir_path == ".agent-orchestrator/issue_queue/complete":
        return []
    return []


def _merge_endpoint_get_repo_text_file(*_a, **kwargs):
    path = kwargs.get("path")
    if path == ".agent-orchestrator/issue_queue/processed/dev-1.md":
        return "Dev: One\n\nBody\n", "sha-queue"
    raise FileNotFoundError(str(path))


def _merge_endpoint_put_json(*_a, **kwargs):
    url = str(kwargs.get("url") or "")
    if url.endswith("/pulls/5/merge"):
        return 200, {"merged": True, "sha": "abc123"}
    if "/contents/.agent-orchestrator/issue_queue/complete/" in url:
        return 201, {}
    return 500, {"message": "unexpected"}


def _merge_endpoint_delete_json(*_a, **_k):
    return 204, None


def _merge_endpoint_post_json(*_a, **kwargs):
    url = str(kwargs.get("url") or "")
    if url.endswith("/pulls/5/reviews"):
        return {"id": 1}
    if url.endswith("/issues"):
        return {"number": 456}
    if url.endswith("/issues/456/assignees"):
        return {"assignees": [{"login": "copilot-swe-agent[bot]"}]}
    raise AssertionError(f"Unexpected POST url: {url}")


def test_loop_promote_endpoint_promotes_one_file(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / ".agent-orchestrator"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")

    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(loop_actions, "_ensure_repo_label_exists", lambda *_a, **_k: None)

    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        lambda *_a, **_k: [".agent-orchestrator/issue_queue/pending/dev-1.md"],
    )
    monkeypatch.setattr(
        loop_actions,
        "_list_repo_markdown_files_under",
        lambda *_a, **_k: [".agent-orchestrator/issue_queue/pending/dev-1.md"],
    )

    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == ".agent-orchestrator/issue_queue/pending/dev-1.md":
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

    # Merge completion moves the processed queue file to complete/ and deletes the processed file.
    # Those helpers live in github_operations (imported into loop_actions), so patch them here.
    monkeypatch.setattr(
        loop_actions, "_ensure_repo_file_present_in_complete", lambda *_a, **_k: None
    )
    monkeypatch.setattr(loop_actions, "_delete_repo_file_if_present", lambda *_a, **_k: None)

    # Merge completion moves the processed queue file to complete/ and deletes it.
    # These helpers are implemented in github_operations and imported into loop_actions.
    monkeypatch.setattr(
        loop_actions, "_ensure_repo_file_present_in_complete", lambda *_a, **_k: None
    )
    monkeypatch.setattr(loop_actions, "_delete_repo_file_if_present", lambda *_a, **_k: None)

    # Merge completion moves the processed queue file to complete/ and deletes the processed file.
    # Those operations are implemented in github_operations and imported into loop_actions.
    monkeypatch.setattr(
        loop_actions, "_ensure_repo_file_present_in_complete", lambda *_a, **_k: None
    )
    monkeypatch.setattr(loop_actions, "_delete_repo_file_if_present", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_router, "_github_put_json", lambda *_a, **_k: (201, {}))
    monkeypatch.setattr(loop_actions, "_github_put_json", lambda *_a, **_k: (201, {}))
    monkeypatch.setattr(dashboard_router, "_github_delete_json", lambda *_a, **_k: (200, {}))
    monkeypatch.setattr(loop_actions, "_github_delete_json", lambda *_a, **_k: (200, {}))

    # The promote path moves the queue file from pending -> processed.
    # Those operations live in github_operations and are imported into loop_actions;
    # patch them here to avoid accidental real GitHub writes.
    monkeypatch.setattr(
        loop_actions, "_ensure_repo_file_present_in_processed", lambda *_a, **_k: None
    )
    monkeypatch.setattr(loop_actions, "_delete_repo_file_if_present", lambda *_a, **_k: None)

    client = TestClient(create_app())
    resp = client.post("/api/loop/promote")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo"] == "acme/repo"
    assert data["branch"] == "main"
    assert data["issueNumber"] == 123
    assert data["created"] is True
    assert data["queuePath"].endswith(".agent-orchestrator/issue_queue/pending/dev-1.md")
    assert data["processedPath"].endswith(".agent-orchestrator/issue_queue/processed/dev-1.md")


def test_load_gap_analysis_template_is_local_not_github(monkeypatch) -> None:
    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(
        loop_actions,
        "_get_repo_text_file",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("Should not call GitHub for templates")
        ),
    )

    content = loop_actions._load_gap_analysis_template_or_raise(
        settings=loop_actions.ServerSettings(),
        repo="acme/repo",
        branch="main",
    )
    assert isinstance(content, str)
    assert "Gap Analysis" in content


def test_ensure_gap_analysis_issue_exists_creates_and_assigns(monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(loop_actions, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **kwargs: (
            "# Target State\n" if kwargs.get("path") == ".agent-orchestrator/state/target_state.md" else "",
            "sha",
        ),
    )
    monkeypatch.setattr(
        loop_actions,
        "_get_repo_text_file",
        lambda *_a, **kwargs: (
            "# Target State\n" if kwargs.get("path") == ".agent-orchestrator/state/target_state.md" else "",
            "sha",
        ),
    )
    monkeypatch.setattr(
        dashboard_router,
        "_load_gap_analysis_template_or_raise",
        lambda **_k: "# Gap Analysis\n\nDo the thing\n",
    )
    monkeypatch.setattr(
        loop_actions,
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

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

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
    monkeypatch.setattr(
        loop_actions,
        "_list_open_issues_raw",
        lambda *_a, **_k: [
            {
                "number": 42,
                "title": "Identify the next most important development gap",
                "assignees": [],
            }
        ],
    )
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **kwargs: (
            "# Target State\n" if kwargs.get("path") == ".agent-orchestrator/state/target_state.md" else "",
            "sha",
        ),
    )
    monkeypatch.setattr(
        loop_actions,
        "_get_repo_text_file",
        lambda *_a, **kwargs: (
            "# Target State\n" if kwargs.get("path") == ".agent-orchestrator/state/target_state.md" else "",
            "sha",
        ),
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


def test_gap_analysis_mode_openai_writes_queue_item(monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("ORCHESTRATOR_GAP_ANALYSIS_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")

    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == ".agent-orchestrator/state/target_state.md":
            return "# Target State\n\n- Target\n", "sha-target"
        if path == ".agent-orchestrator/state/current_state.md":
            return "# Current State\n\n- Current\n", "sha-current"
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(loop_actions, "_get_repo_text_file", fake_get_repo_text_file)
    monkeypatch.setattr(
        loop_actions,
        "_generate_chat_completion",
        lambda **_k: "Dev: Improve gap analysis\n\n- Do the thing\n",
    )

    captured: dict[str, object] = {}

    def fake_ensure_repo_text_file_present(*_a, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(loop_actions, "_ensure_repo_text_file_present", fake_ensure_repo_text_file_present)

    out = loop_actions._ensure_gap_analysis_issue_exists(
        settings=loop_actions.ServerSettings(),
        repo="acme/repo",
    )

    assert out["created"] is True
    assert isinstance(out.get("queuePath"), str)
    assert captured.get("path") is not None
    assert str(captured.get("path")).startswith(".agent-orchestrator/issue_queue/pending/")


def test_gap_analysis_creates_baseline_current_state_when_missing(monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("ORCHESTRATOR_GAP_ANALYSIS_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")

    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == ".agent-orchestrator/state/target_state.md":
            return "# Target State\n\n- Target\n", "sha-target"
        if path == ".agent-orchestrator/state/current_state.md":
            raise HTTPException(status_code=404, detail="missing")
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(loop_actions, "_get_repo_text_file", fake_get_repo_text_file)
    monkeypatch.setattr(
        loop_actions,
        "_generate_chat_completion",
        lambda **_k: "Dev: Improve gap analysis\n\n- Do the thing\n",
    )

    calls: list[dict[str, object]] = []

    def fake_ensure_repo_text_file_present(*_a, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(loop_actions, "_ensure_repo_text_file_present", fake_ensure_repo_text_file_present)

    out = loop_actions._ensure_gap_analysis_issue_exists(
        settings=loop_actions.ServerSettings(),
        repo="acme/repo",
    )

    assert out["created"] is True
    init_calls = [c for c in calls if c.get("path") == ".agent-orchestrator/state/current_state.md"]
    assert init_calls
    expected = (
        "# Current State\n\n"
        "## Overview\n"
        "This repository has no implemented capabilities yet. It is a clean starting point.\n\n"
        "## Specification\n"
        "The target specification is defined in `/.agent-orchestrator/state/target_state.md`.\n\n"
        "## Implemented Capabilities\n"
        "- None.\n\n"
        "## In-Progress\n"
        "- None.\n\n"
        "## Known Gaps (High-Level)\n"
        "- All implementation work remains.\n\n"
        "## Notes\n"
        "This document should be updated after each merged PR that changes capabilities.\n"
    )
    assert init_calls[0].get("content_text") == expected


def test_loop_gap_analysis_ensure_endpoint_creates_and_assigns(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / ".agent-orchestrator"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(loop_actions, "_list_open_issues_raw", lambda *_a, **_k: [])
    # Templates are loaded locally; no GitHub file reads should be attempted for templates.
    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == ".agent-orchestrator/state/target_state.md":
            return "# Target State\n", "sha-target"
        if path == ".agent-orchestrator/state/current_state.md":
            return "", "sha-current"
        raise AssertionError("Unexpected GitHub file read")

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)
    monkeypatch.setattr(loop_actions, "_get_repo_text_file", fake_get_repo_text_file)

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


def test_capability_update_mode_openai_writes_current_state(monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("ORCHESTRATOR_CAPABILITY_UPDATE_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions

    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(
        loop_actions,
        "_get_pull_request_discussion_markdown",
        lambda *_a, **_k: "Discussion",
    )

    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == ".agent-orchestrator/state/current_state.md":
            return "# Current State\n\n- Before\n", "sha-current"
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(loop_actions, "_get_repo_text_file", fake_get_repo_text_file)
    monkeypatch.setattr(
        loop_actions,
        "_generate_chat_completion",
        lambda **_k: "# Current State\n\n- After\n",
    )

    captured: dict[str, object] = {}

    def fake_ensure_repo_text_file_present(*_a, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(loop_actions, "_ensure_repo_text_file_present", fake_ensure_repo_text_file_present)

    num, created, label = loop_actions._ensure_followup_issue_after_development_merge(
        settings=loop_actions.ServerSettings(),
        repo="acme/repo",
        branch="main",
        loop_mode="build",
        pr_number=5,
        pr_title="Add thing",
        pr_body="Body",
        queue_path=".agent-orchestrator/issue_queue/processed/dev-1.md",
        queue_content="Dev: One",
    )

    assert num is None
    assert created is None
    assert label is None
    assert captured.get("path") == ".agent-orchestrator/state/current_state.md"


def test_ensure_gap_analysis_issue_exists_repairs_unsafe_existing_issue_before_assign(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

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
        loop_actions,
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
    monkeypatch.setattr(
        loop_actions,
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
    planning = tmp_path / ".agent-orchestrator"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(loop_actions, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(
        dashboard_router, "_search_issue_number_by_body_marker", lambda *_a, **_k: None
    )
    monkeypatch.setattr(loop_actions, "_search_issue_number_by_body_marker", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_router, "_github_get_list", lambda *_a, **_k: [])
    monkeypatch.setattr(loop_actions, "_github_get_list", lambda *_a, **_k: [])

    monkeypatch.setattr(
        dashboard_router, "_list_repo_markdown_files_under", _merge_endpoint_list_repo_md
    )
    monkeypatch.setattr(
        loop_actions, "_list_repo_markdown_files_under", _merge_endpoint_list_repo_md
    )

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", _merge_endpoint_get_repo_text_file)
    monkeypatch.setattr(loop_actions, "_get_repo_text_file", _merge_endpoint_get_repo_text_file)

    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(
        loop_actions,
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
        loop_actions,
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
    monkeypatch.setattr(
        loop_actions,
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

    monkeypatch.setattr(dashboard_router, "_github_put_json", _merge_endpoint_put_json)
    monkeypatch.setattr(loop_actions, "_github_put_json", _merge_endpoint_put_json)

    monkeypatch.setattr(dashboard_router, "_github_delete_json", _merge_endpoint_delete_json)
    monkeypatch.setattr(loop_actions, "_github_delete_json", _merge_endpoint_delete_json)

    monkeypatch.setattr(dashboard_router, "_github_post_json", _merge_endpoint_post_json)
    monkeypatch.setattr(loop_actions, "_github_post_json", _merge_endpoint_post_json)

    # Merge completion moves the processed queue file to complete/ and deletes the processed file.
    # These helpers are implemented in github_operations and imported into loop_actions.
    monkeypatch.setattr(
        loop_actions, "_ensure_repo_file_present_in_complete", lambda *_a, **_k: None
    )
    monkeypatch.setattr(loop_actions, "_delete_repo_file_if_present", lambda *_a, **_k: None)

    client = TestClient(create_app())
    resp = client.post("/api/loop/merge")
    assert resp.status_code == 200
    data = resp.json()
    assert data["merged"] is True
    assert data["pullNumber"] == 5
    assert data["capabilityIssueNumber"] == 456


def test_loop_heal_endpoint_moves_orphaned_processed_to_complete_and_ensures_followup_issue(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / ".agent-orchestrator"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")

    def fake_list_repo_md(*_a, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == ".agent-orchestrator/issue_queue/processed":
            return [".agent-orchestrator/issue_queue/processed/dev-1.md"]
        return []

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)
    monkeypatch.setattr(loop_actions, "_list_repo_markdown_files_under", fake_list_repo_md)

    # Processed queue file exists.
    def fake_get_repo_text_file(*_a, **kwargs):
        if kwargs.get("path") == ".agent-orchestrator/issue_queue/processed/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-queue"
        raise FileNotFoundError(str(kwargs.get("path")))

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)
    monkeypatch.setattr(loop_actions, "_get_repo_text_file", fake_get_repo_text_file)

    # No open issues -> orphan candidate.
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(loop_actions, "_list_open_issues_raw", lambda *_a, **_k: [])

    # Find the historical issue by queue marker.
    monkeypatch.setattr(
        dashboard_router, "_search_issue_number_by_queue_marker", lambda *_a, **_k: 101
    )
    monkeypatch.setattr(loop_actions, "_search_issue_number_by_queue_marker", lambda *_a, **_k: 101)

    # Issue is closed.
    def fake_get_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/repos/acme/repo/issues/101"):
            return {"number": 101, "state": "closed", "title": "Dev: One", "body": "x"}
        raise AssertionError(f"Unexpected GET url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_get_json", fake_get_json)
    monkeypatch.setattr(loop_actions, "_github_get_json", fake_get_json)

    # Issue timeline links PR #5.
    monkeypatch.setattr(
        dashboard_router,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {"event": "cross-referenced", "source": {"issue": {"number": 5, "pull_request": {}}}}
        ],
    )
    monkeypatch.setattr(
        loop_actions,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {"event": "cross-referenced", "source": {"issue": {"number": 5, "pull_request": {}}}}
        ],
    )

    # PR is merged (Case A).
    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "closed",
            "merged_at": "2026-01-01T00:00:00Z",
            "title": "Add undo/redo",
            "body": "PR body",
        },
    )
    monkeypatch.setattr(
        loop_actions,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "closed",
            "merged_at": "2026-01-01T00:00:00Z",
            "title": "Add undo/redo",
            "body": "PR body",
        },
    )

    # Follow-up issue idempotency search should yield none.
    monkeypatch.setattr(
        dashboard_router, "_search_issue_number_by_body_marker", lambda *_a, **_k: None
    )
    monkeypatch.setattr(loop_actions, "_search_issue_number_by_body_marker", lambda *_a, **_k: None)

    # Avoid label creation side effects.
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(loop_actions, "_ensure_repo_label_exists", lambda *_a, **_k: None)

    # Follow-up issue body needs discussion markdown.
    monkeypatch.setattr(
        loop_actions, "_get_pull_request_discussion_markdown", lambda *_a, **_k: "discussion"
    )

    # Creating follow-up issue and assignment.
    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues"):
            return {"number": 456}
        if url.endswith("/issues/456/assignees"):
            return {"assignees": [{"login": "copilot-swe-agent[bot]"}]}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)
    monkeypatch.setattr(loop_actions, "_github_post_json", fake_post_json)

    # Move processed -> complete and delete processed.
    moved: dict[str, object] = {}
    deleted: dict[str, object] = {}
    monkeypatch.setattr(
        loop_actions,
        "_ensure_repo_file_present_in_complete",
        lambda *_a, **kwargs: moved.update(kwargs),
    )
    monkeypatch.setattr(
        loop_actions,
        "_delete_repo_file_if_present",
        lambda *_a, **kwargs: deleted.update(kwargs),
    )

    client = TestClient(create_app())
    resp = client.post("/api/loop/heal")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo"] == "acme/repo"
    assert data["branch"] == "main"
    assert data["healed"]
    assert moved.get("complete_path") == ".agent-orchestrator/issue_queue/complete/dev-1.md"
    assert deleted.get("path") == ".agent-orchestrator/issue_queue/processed/dev-1.md"


def test_loop_heal_endpoint_closes_open_issue_when_pr_is_merged(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / ".agent-orchestrator"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")

    def fake_list_repo_md(*_a, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == ".agent-orchestrator/issue_queue/processed":
            return [".agent-orchestrator/issue_queue/processed/dev-1.md"]
        return []

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)
    monkeypatch.setattr(loop_actions, "_list_repo_markdown_files_under", fake_list_repo_md)

    def fake_get_repo_text_file(*_a, **kwargs):
        if kwargs.get("path") == ".agent-orchestrator/issue_queue/processed/dev-1.md":
            return "Dev: One\n\nBody\n", "sha-queue"
        raise FileNotFoundError(str(kwargs.get("path")))

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)
    monkeypatch.setattr(loop_actions, "_get_repo_text_file", fake_get_repo_text_file)

    # Open issue matches the queue title.
    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(
        loop_actions,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )

    def fail_queue_marker(*_a, **_k):
        raise AssertionError("queue marker search not expected")

    # Should not search by queue marker when open issue is matched.
    monkeypatch.setattr(
        dashboard_router,
        "_search_issue_number_by_queue_marker",
        fail_queue_marker,
    )
    monkeypatch.setattr(
        loop_actions,
        "_search_issue_number_by_queue_marker",
        fail_queue_marker,
    )

    def fake_get_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/repos/acme/repo/issues/101"):
            return {"number": 101, "state": "open", "title": "Dev: One", "body": "x"}
        raise AssertionError(f"Unexpected GET url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_get_json", fake_get_json)
    monkeypatch.setattr(loop_actions, "_github_get_json", fake_get_json)

    monkeypatch.setattr(
        dashboard_router,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {"event": "cross-referenced", "source": {"issue": {"number": 5, "pull_request": {}}}}
        ],
    )
    monkeypatch.setattr(
        loop_actions,
        "_list_issue_timeline_raw",
        lambda *_a, **_k: [
            {"event": "cross-referenced", "source": {"issue": {"number": 5, "pull_request": {}}}}
        ],
    )

    monkeypatch.setattr(
        dashboard_router,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "closed",
            "merged_at": "2026-01-01T00:00:00Z",
            "title": "Add undo/redo",
            "body": "PR body",
        },
    )
    monkeypatch.setattr(
        loop_actions,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "closed",
            "merged_at": "2026-01-01T00:00:00Z",
            "title": "Add undo/redo",
            "body": "PR body",
        },
    )

    # Close the open issue before healing.
    def fake_patch_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues/101"):
            return {"number": 101, "state": "closed"}
        raise AssertionError(f"Unexpected PATCH url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_patch_json", fake_patch_json)
    monkeypatch.setattr(loop_actions, "_github_patch_json", fake_patch_json)

    monkeypatch.setattr(
        dashboard_router, "_search_issue_number_by_body_marker", lambda *_a, **_k: None
    )
    monkeypatch.setattr(loop_actions, "_search_issue_number_by_body_marker", lambda *_a, **_k: None)
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(loop_actions, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(
        loop_actions, "_get_pull_request_discussion_markdown", lambda *_a, **_k: "discussion"
    )

    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues"):
            return {"number": 456}
        if url.endswith("/issues/456/assignees"):
            return {"assignees": [{"login": "copilot-swe-agent[bot]"}]}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)
    monkeypatch.setattr(loop_actions, "_github_post_json", fake_post_json)

    moved: dict[str, object] = {}
    deleted: dict[str, object] = {}
    monkeypatch.setattr(
        loop_actions,
        "_ensure_repo_file_present_in_complete",
        lambda *_a, **kwargs: moved.update(kwargs),
    )
    monkeypatch.setattr(
        loop_actions,
        "_delete_repo_file_if_present",
        lambda *_a, **kwargs: deleted.update(kwargs),
    )

    client = TestClient(create_app())
    resp = client.post("/api/loop/heal")
    assert resp.status_code == 200
    data = resp.json()
    assert data["healed"]
    assert moved.get("complete_path") == ".agent-orchestrator/issue_queue/complete/dev-1.md"
    assert deleted.get("path") == ".agent-orchestrator/issue_queue/processed/dev-1.md"


def test_loop_merge_endpoint_merges_ready_capability_pr_and_closes_issue(
    monkeypatch, tmp_path: Path
) -> None:
    planning = tmp_path / ".agent-orchestrator"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

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
    monkeypatch.setattr(
        loop_actions,
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
            "body": "Update current_state.md",
            "head": {"ref": "feature/caps", "repo": {"full_name": "acme/repo"}},
        },
    )
    monkeypatch.setattr(
        loop_actions,
        "_get_pull_request",
        lambda *_a, **_k: {
            "number": 5,
            "state": "open",
            "draft": False,
            "requested_reviewers": [{"login": "alice"}],
            "requested_teams": [],
            "mergeable_state": "clean",
            "title": "Update capabilities",
            "body": "Update current_state.md",
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

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(loop_actions, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        lambda *_a, **_k: [".agent-orchestrator/issue_queue/pending/system-1.md"],
    )
    monkeypatch.setattr(
        loop_actions,
        "_list_repo_markdown_files_under",
        lambda *_a, **_k: [".agent-orchestrator/issue_queue/pending/system-1.md"],
    )
    monkeypatch.setattr(
        dashboard_router,
        "_get_repo_text_file",
        lambda *_a, **_k: ("System: Update capability\n\nBody\n", "sha-1"),
    )
    monkeypatch.setattr(
        loop_actions,
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
    monkeypatch.setattr(
        loop_actions,
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

    # Capability promotion also writes processed queue files and deletes the pending file.
    monkeypatch.setattr(
        loop_actions, "_ensure_repo_file_present_in_processed", lambda *_a, **_k: None
    )
    monkeypatch.setattr(loop_actions, "_delete_repo_file_if_present", lambda *_a, **_k: None)

    out = dashboard_router._promote_next_unpromoted_capability_queue_item(
        settings=dashboard_router.ServerSettings(),
        repo="acme/repo",
    )
    assert out["issueNumber"] == 321
    assert str(out["queuePath"]).endswith(".agent-orchestrator/issue_queue/pending/system-1.md")
    assert str(out["processedPath"]).endswith(
        ".agent-orchestrator/issue_queue/processed/system-1.md"
    )


def test_loop_merge_endpoint_fails_cleanly_when_pr_stays_draft(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / ".agent-orchestrator"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(loop_actions, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)
    monkeypatch.setattr(loop_actions, "_ensure_repo_label_exists", lambda *_a, **_k: None)

    def fake_list_repo_md(*_a, **kwargs):
        dir_path = kwargs.get("dir_path")
        if dir_path == ".agent-orchestrator/issue_queue/pending":
            return []
        if dir_path == ".agent-orchestrator/issue_queue/processed":
            return [".agent-orchestrator/issue_queue/processed/dev-1.md"]
        if dir_path == ".agent-orchestrator/issue_queue/complete":
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
        loop_actions,
        "_get_repo_text_file",
        lambda *_a, **_k: ("Dev: One\n\nBody\n", "sha-queue"),
    )

    monkeypatch.setattr(
        dashboard_router,
        "_list_open_issues_raw",
        lambda *_a, **_k: [{"number": 101, "title": "Dev: One", "state": "open"}],
    )
    monkeypatch.setattr(
        loop_actions,
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
    monkeypatch.setattr(
        loop_actions,
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
    monkeypatch.setattr(
        loop_actions,
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
    monkeypatch.setattr(
        loop_actions,
        "_github_graphql_post",
        lambda *_a, **_k: {"errors": [{"message": "Pull Request is still a draft"}]},
    )

    # Merge must not be attempted; if it is, fail the test.
    monkeypatch.setattr(
        dashboard_router,
        "_github_put_json",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("merge should not be attempted")),
    )
    monkeypatch.setattr(
        loop_actions,
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
    planning = tmp_path / ".agent-orchestrator"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("COPILOT_ASSIGNEE", "copilot-swe-agent[bot]")

    import github_agent_orchestrator.server.dashboard.loop_actions as loop_actions
    import github_agent_orchestrator.server.dashboard_router as dashboard_router

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
    monkeypatch.setattr(
        loop_actions,
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
    monkeypatch.setattr(
        loop_actions,
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
    monkeypatch.setattr(
        loop_actions,
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


def test_ensure_review_consumption_archives_completed_review_when_issue_closed(monkeypatch) -> None:
    """If the last review-consumption issue is closed, archive the review.

    This prevents repeatedly re-creating review-consumption issues for the same review file in cases
    where the agent correctly produces no queue artefact.
    """

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    # Repo has one active review + its actions file.
    review_path = ".agent-orchestrator/reviews/review-2026-01-05-refactor-large-files.md"
    actions_path = ".agent-orchestrator/reviews/review-2026-01-05-refactor-large-files.actions.md"

    # The ensure function re-lists .agent-orchestrator/reviews after archiving.
    # Simulate the move by returning completed/ paths after we "write" the archive.
    archived = {"done": False}

    def fake_list_repo_md(*_a, **_k):
        dir_path = str(_k.get("dir_path") or "")
        # The archiving logic scans both .agent-orchestrator/reviews and the issue_queue.
        # For this test, ensure there are no review queue artefacts, so the review is archived.
        if ".agent-orchestrator/issue_queue/" in dir_path:
            return []
        if archived["done"]:
            return [
                ".agent-orchestrator/reviews/completed/review-2026-01-05-refactor-large-files.md",
                ".agent-orchestrator/reviews/completed/review-2026-01-05-refactor-large-files.actions.md",
            ]
        return [review_path, actions_path]

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)
    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)

    # A previous review-consumption issue exists and is closed.
    monkeypatch.setattr(
        dashboard_router, "_search_issue_number_by_body_marker", lambda *_a, **_k: 77
    )

    def fake_get_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues/77"):
            return {"number": 77, "state": "closed", "title": "Review consumption"}
        # For file writes, _ensure_repo_text_file_present fetches existing to get sha on 422.
        # We return a minimal object if requested.
        return {"sha": "sha-existing"}

    monkeypatch.setattr(dashboard_router, "_github_get_json", fake_get_json)
    # Timeline may include a linked PR; we still archive once the issue is closed.
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

    # Source review files exist.
    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == review_path:
            return ("# Review\n\n- Item\n", "sha-review")
        if path == actions_path:
            return ("# Actions\n\n- Done\n", "sha-actions")
        raise AssertionError(f"Unexpected get_repo_text_file path: {path}")

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)

    written: list[str] = []
    deleted: list[str] = []

    def fake_put_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        written.append(url)
        if "contents/.agent-orchestrator/reviews/completed/" in url:
            archived["done"] = True
        return 201, {}

    def fake_delete_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        deleted.append(url)
        return 200, {}

    monkeypatch.setattr(dashboard_router, "_github_put_json", fake_put_json)
    monkeypatch.setattr(dashboard_router, "_github_delete_json", fake_delete_json)

    # If archiving occurred, the ensure endpoint should then report there are no remaining reviews.
    # (We only had one review file.)
    with pytest.raises(HTTPException) as exc:
        dashboard_router._ensure_review_consumption_issue_exists(
            settings=dashboard_router.ServerSettings(),
            repo="acme/repo",
        )

    assert exc.value.status_code == 409
    assert "No uncompleted review files" in str(exc.value.detail)

    # Review and actions were archived to .agent-orchestrator/reviews/completed/ and removed from original paths.
    assert any(
        "contents/.agent-orchestrator/reviews/completed/review-2026-01-05-refactor-large-files.md"
        in u
        for u in written
    )
    assert any(
        "contents/.agent-orchestrator/reviews/completed/review-2026-01-05-refactor-large-files.actions.md"
        in u
        for u in written
    )
    assert any(f"contents/{review_path}" in u for u in deleted)
    assert any(f"contents/{actions_path}" in u for u in deleted)


def test_ensure_review_consumption_does_not_archive_when_closed_issue_produced_queue(
    monkeypatch,
) -> None:
    """A closed review-consumption issue does not imply the review is complete.

    If the closed issue produced a review queue artefact (i.e. it generated work), the review
    must remain active so Step 1a can run again to extract the next item.
    """

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    review_path = ".agent-orchestrator/reviews/review-2026-01-05-refactor-large-files.md"
    actions_path = ".agent-orchestrator/reviews/review-2026-01-05-refactor-large-files.actions.md"
    queue_path = ".agent-orchestrator/issue_queue/pending/review-2026-01-09-sample.md"

    def fake_list_repo_md(*_a, **_k):
        dir_path = str(_k.get("dir_path") or "")
        if dir_path.rstrip("/") == ".agent-orchestrator/reviews":
            return [review_path, actions_path]
        if dir_path.rstrip("/") == ".agent-orchestrator/issue_queue/pending":
            return [queue_path]
        if ".agent-orchestrator/issue_queue/" in dir_path:
            return []
        return []

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)
    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)

    # A previous review-consumption issue exists and is closed.
    def fake_search(*_a, **kwargs):
        if str(kwargs.get("state") or "") == "closed":
            return 77
        return None

    monkeypatch.setattr(dashboard_router, "_search_issue_number_by_body_marker", fake_search)

    def fake_get_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues/77"):
            return {
                "number": 77,
                "state": "closed",
                "title": "Review consumption",
                "created_at": "2026-01-09T00:00:10Z",
                "closed_at": "2026-01-09T00:12:00Z",
            }
        if url.endswith("/issues/123/assignees"):
            return {"assignees": [{"login": "copilot"}]}
        # For file writes, _ensure_repo_text_file_present fetches existing to get sha on 422.
        return {"sha": "sha-existing"}

    monkeypatch.setattr(dashboard_router, "_github_get_json", fake_get_json)

    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == queue_path:
            return (
                "Task title\n\n"
                f"Source review: {review_path}\n"
                f"Review actions: {actions_path}\n\n"
                "Details...\n",
                "sha-queue",
            )
        if path == review_path:
            return ("# Review\n\n- Item\n", "sha-review")
        if path == actions_path:
            return ("# Actions\n\n- Done\n", "sha-actions")
        raise AssertionError(f"Unexpected get_repo_text_file path: {path}")

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)

    created_issues: list[dict[str, object]] = []

    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues"):
            created_issues.append(kwargs.get("payload") or {})
            return {"number": 123}
        if url.endswith("/issues/123/assignees"):
            return {"assignees": [{"login": "copilot"}]}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)

    # No archiving should occur.
    monkeypatch.setattr(dashboard_router, "_github_put_json", lambda *_a, **_k: (201, {}))
    monkeypatch.setattr(dashboard_router, "_github_delete_json", lambda *_a, **_k: (200, {}))

    out = dashboard_router._ensure_review_consumption_issue_exists(
        settings=dashboard_router.ServerSettings(),
        repo="acme/repo",
    )

    assert out.get("created") is True
    assert out.get("issueNumber") == 123
    assert created_issues


def test_ensure_review_consumption_does_not_archive_when_queue_has_source_review_section(
    monkeypatch,
) -> None:
    """Queue artefacts may encode source review as a Markdown section.

    breadboard-lab style queue items often use:

      ## Source Review

    `.agent-orchestrator/reviews/review-...md`

    rather than a single-line "Source review:" field. We must still detect this as output,
    otherwise Step 1a will incorrectly archive an in-progress review.
    """

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")

    review_path = ".agent-orchestrator/reviews/review-2026-01-05-refactor-large-files.md"
    actions_path = ".agent-orchestrator/reviews/review-2026-01-05-refactor-large-files.actions.md"
    # When a review-consumption run has produced output but it has not yet been promoted/merged,
    # the queue artefact will still be in pending/processed. Those items are strong evidence of
    # current work and must prevent the review being archived.
    queue_path = ".agent-orchestrator/issue_queue/pending/review-pixijs-removal-milestone-0-react-setup.md"

    def fake_list_repo_md(*_a, **_k):
        dir_path = str(_k.get("dir_path") or "")
        if dir_path.rstrip("/") == ".agent-orchestrator/reviews":
            return [review_path, actions_path]
        if dir_path.rstrip("/") == ".agent-orchestrator/issue_queue/pending":
            return [queue_path]
        if ".agent-orchestrator/issue_queue/" in dir_path:
            return []
        return []

    monkeypatch.setattr(dashboard_router, "_list_repo_markdown_files_under", fake_list_repo_md)
    monkeypatch.setattr(dashboard_router, "_get_default_branch", lambda *_a, **_k: "main")
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_ensure_repo_label_exists", lambda *_a, **_k: None)

    def fake_search(*_a, **kwargs):
        if str(kwargs.get("state") or "") == "closed":
            return 77
        return None

    monkeypatch.setattr(dashboard_router, "_search_issue_number_by_body_marker", fake_search)

    def fake_get_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues/77"):
            return {
                "number": 77,
                "state": "closed",
                "title": "Review consumption",
                "created_at": "2026-01-09T00:00:10Z",
                "closed_at": "2026-01-09T00:12:00Z",
            }
        if url.endswith("/issues/123/assignees"):
            return {"assignees": [{"login": "copilot"}]}
        return {"sha": "sha-existing"}

    monkeypatch.setattr(dashboard_router, "_github_get_json", fake_get_json)

    def fake_get_repo_text_file(*_a, **kwargs):
        path = kwargs.get("path")
        if path == queue_path:
            return (
                "Task title\n\n" "## Source Review\n\n" f"`{review_path}`\n\n" "Details...\n",
                "sha-queue",
            )
        if path == review_path:
            return ("# Review\n\n- Item\n", "sha-review")
        if path == actions_path:
            return ("# Actions\n\n- Done\n", "sha-actions")
        raise AssertionError(f"Unexpected get_repo_text_file path: {path}")

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)

    created_issues: list[dict[str, object]] = []

    def fake_post_json(*_a, **kwargs):
        url = str(kwargs.get("url") or "")
        if url.endswith("/issues"):
            created_issues.append(kwargs.get("payload") or {})
            return {"number": 123}
        if url.endswith("/issues/123/assignees"):
            return {"assignees": [{"login": "copilot"}]}
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(dashboard_router, "_github_post_json", fake_post_json)

    # No archiving should occur.
    monkeypatch.setattr(dashboard_router, "_github_put_json", lambda *_a, **_k: (201, {}))
    monkeypatch.setattr(dashboard_router, "_github_delete_json", lambda *_a, **_k: (200, {}))

    out = dashboard_router._ensure_review_consumption_issue_exists(
        settings=dashboard_router.ServerSettings(),
        repo="acme/repo",
    )

    assert out.get("created") is True
    assert out.get("issueNumber") == 123
    assert created_issues


def test_review_consumption_ignores_non_timestamped_complete_when_issue_has_timestamps(
    monkeypatch,
) -> None:
    """Non-timestamped complete/ artefacts are too ambiguous to correlate.

    If we have created/closed timestamps for the issue, and a matching review queue artefact lives
    only in complete/ without any parseable timestamp in its filename, treating it as evidence of
    output is prone to false positives (historical outputs referencing the same source review).
    """

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    review_path = ".agent-orchestrator/reviews/review-2026-01-05-refactor-large-files.md"
    queue_path = ".agent-orchestrator/issue_queue/complete/review-pixijs-removal-milestone-0-react-setup.md"

    monkeypatch.setattr(
        dashboard_router,
        "_list_repo_markdown_files_under",
        lambda *_a, **kwargs: (
            [queue_path]
            if str(kwargs.get("dir_path") or "").rstrip("/")
            == ".agent-orchestrator/issue_queue/complete"
            else []
        ),
    )

    def fake_get_repo_text_file(*_a, **kwargs):
        assert kwargs.get("path") == queue_path
        return (
            "Task title\n\n## Source Review\n\n" f"`{review_path}`\n\nDetails...\n",
            "sha-queue",
        )

    monkeypatch.setattr(dashboard_router, "_get_repo_text_file", fake_get_repo_text_file)

    created_epoch = int(dashboard_router._dt_from_iso("2026-01-09T00:00:10Z").timestamp())
    closed_epoch = int(dashboard_router._dt_from_iso("2026-01-09T00:12:00Z").timestamp())

    produced = dashboard_router._review_consumption_issue_produced_queue_output(
        settings=dashboard_router.ServerSettings(),
        repo="acme/repo",
        branch="main",
        review_path=review_path,
        issue_created_epoch=created_epoch,
        issue_closed_epoch=closed_epoch,
    )

    assert produced is False
