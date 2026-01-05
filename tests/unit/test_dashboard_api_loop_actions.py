"""Tests for dashboard loop action endpoints (promote, merge, ensure)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from github_agent_orchestrator.server.app import create_app


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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
