"""Tests for dashboard health and documentation endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from github_agent_orchestrator.server.app import create_app


def test_dashboard_health_and_docs(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / ".agent-orchestrator"
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
        if path == ".agent-orchestrator/vision/goal.md":
            return "# Goal\n\nShip it.\n", "sha-goal"
        if path == ".agent-orchestrator/state/target_state.md":
            return "# Target State\n\n- A\n", "sha-target"
        if path == ".agent-orchestrator/state/current_state.md":
            return "# Current State\n\n- B\n", "sha-current"
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
                "targetFolder": ".agent-orchestrator/issue_queue/pending",
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
    assert goal["path"].endswith(".agent-orchestrator/vision/goal.md")
    assert "Ship it" in goal["content"]

    target_state = client.get("/api/docs/target-state").json()
    assert target_state["key"] == "targetState"
    assert target_state["title"] == "Target"
    assert target_state["path"].endswith(".agent-orchestrator/state/target_state.md")

    current_state = client.get("/api/docs/current-state").json()
    assert current_state["key"] == "currentState"
    assert current_state["title"] == "Current"
    assert current_state["path"].endswith(".agent-orchestrator/state/current_state.md")

    tasks = client.get("/api/cognitive-tasks").json()
    assert any(t.get("id") == "review-complexity.md" for t in tasks)


def test_dashboard_can_write_target_state(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / ".agent-orchestrator"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_REPO", "acme/repo")
    monkeypatch.setenv("ORCHESTRATOR_GITHUB_TOKEN", "ghp_test")

    import github_agent_orchestrator.server.dashboard_router as dashboard_router

    captured: dict[str, object] = {}

    def fake_get_default_branch(*_a, **_k):
        return "main"

    def fake_ensure_repo_text_file_present(*_a, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(dashboard_router, "_get_default_branch", fake_get_default_branch)
    monkeypatch.setattr(
        dashboard_router, "_ensure_repo_text_file_present", fake_ensure_repo_text_file_present
    )

    client = TestClient(create_app())
    payload = {"content": "# Target State\n\nHello\n", "message": "init target"}
    resp = client.post("/api/docs/target-state", json=payload).json()

    assert resp["ok"] is True
    assert resp["path"].endswith(".agent-orchestrator/state/target_state.md")
    assert captured.get("path") == ".agent-orchestrator/state/target_state.md"
    assert captured.get("branch") == "main"
    assert captured.get("content_text") == payload["content"]
    assert captured.get("message") == payload["message"]
