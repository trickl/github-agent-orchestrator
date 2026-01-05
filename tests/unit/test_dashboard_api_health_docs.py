"""Tests for dashboard health and documentation endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from github_agent_orchestrator.server.app import create_app


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
