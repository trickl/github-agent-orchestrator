from __future__ import annotations

import json
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

    _write(planning / "vision" / "goal.md", "# Goal\n\nShip it.\n")
    _write(planning / "state" / "system_capabilities.md", "# System Capabilities\n\n- A\n")
    _write(planning / "issue_templates" / "review-complexity.md", "# Review: Complexity\n")
    _write(agent_state / "issues.json", json.dumps([]) + "\n")

    client = TestClient(create_app())

    assert client.get("/api/health").json() == {"status": "ok"}

    goal = client.get("/api/docs/goal").json()
    assert goal["key"] == "goal"
    assert goal["title"] == "Goal"
    assert "goal.md" in goal["path"]
    assert "Ship it" in goal["content"]

    caps = client.get("/api/docs/capabilities").json()
    assert caps["key"] == "capabilities"
    assert caps["title"] == "System Capabilities"
    assert "system_capabilities.md" in caps["path"]

    tasks = client.get("/api/cognitive-tasks").json()
    assert any(t.get("id") == "review-complexity.md" for t in tasks)


def test_cognitive_tasks_create_run_creates_queue_item(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))

    _write(planning / "vision" / "goal.md", "# Goal\n")
    _write(planning / "state" / "system_capabilities.md", "# System Capabilities\n")
    _write(agent_state / "issues.json", json.dumps([]) + "\n")

    client = TestClient(create_app())

    task = {
        "name": "Gap analysis: observability",
        "category": "gap",
        "enabled": True,
        "promptText": "Write a gap analysis task.",
        "targetFolder": "planning/issue_queue/pending",
        "trigger": {"kind": "MANUAL_ONLY"},
        "editable": True,
    }

    created = client.post("/api/cognitive-tasks", json=task).json()
    assert created["id"]

    run = client.post(f"/api/cognitive-tasks/{created['id']}/run").json()
    assert run["ok"] is True
    assert run["createdIssueId"].endswith(".md")

    artefact = planning / "issue_queue" / "pending" / run["createdIssueId"]
    assert artefact.exists()

    timeline = client.get("/api/timeline").json()
    assert len(timeline) >= 1
    assert timeline[0]["kind"] == "ISSUE_FILE_CREATED"


def test_loop_status_endpoint(monkeypatch, tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    agent_state = tmp_path / "agent_state"

    monkeypatch.setenv("ORCHESTRATOR_PLANNING_ROOT", str(planning))
    monkeypatch.setenv("AGENT_STATE_PATH", str(agent_state))
    monkeypatch.setenv("ORCHESTRATOR_UI_DIST", str(tmp_path / "ui" / "dist"))

    _write(planning / "vision" / "goal.md", "# Goal\n")
    _write(planning / "state" / "system_capabilities.md", "# System Capabilities\n")
    _write(agent_state / "issues.json", json.dumps([]) + "\n")

    pending_dir = planning / "issue_queue" / "pending"
    _write(pending_dir / "dev-1.md", "# Dev task 1\n\nDo stuff\n")

    client = TestClient(create_app())

    loop = client.get("/api/loop").json()
    assert loop["stage"] in {"A", "B", "C", "D", "F"}
    assert loop["activeStep"] in {0, 1, 2, 3, 5}
    assert loop["counts"]["pending"] == 1
    assert loop["counts"]["unpromotedPending"] == 1
