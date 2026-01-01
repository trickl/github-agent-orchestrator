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

    # No open issues => pending files cannot match any issue => no associated PR => Step B
    monkeypatch.setattr(dashboard_router, "_list_open_issues_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_list_open_pull_requests_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_list_issue_timeline_raw", lambda *_a, **_k: [])
    monkeypatch.setattr(dashboard_router, "_get_pull_request", lambda *_a, **_k: {})

    client = TestClient(create_app())

    loop = client.get("/api/loop").json()
    # Pending development queue files exist and no PR is associated => Step B
    assert loop["stage"] == "B"
    assert loop["activeStep"] == 1
    assert loop["counts"]["pending"] == 2
    assert loop["counts"]["openIssues"] == 0
    assert loop["counts"]["openPullRequests"] == 0
