"""Unit tests for deterministic workflow actions."""

from __future__ import annotations

from pathlib import Path

from github_agent_orchestrator.orchestrator.workflow.actions import MovePendingIssueFile
from github_agent_orchestrator.orchestrator.workflow.events import TriggerEvent


def test_move_pending_issue_file_is_idempotent(tmp_path: Path) -> None:
    pending_dir = tmp_path / "planning" / "issue_queue" / "pending"
    processed_dir = tmp_path / "planning" / "issue_queue" / "processed"
    pending_dir.mkdir(parents=True)

    item = pending_dir / "dev-20250101.md"
    item.write_text("# Title\n\nBody\n", encoding="utf-8")

    action = MovePendingIssueFile(item_path=item, processed_dir=processed_dir)
    r1 = action.execute(TriggerEvent(type="PENDING_ISSUE_DETECTED", payload={}))
    assert r1.ok
    assert (processed_dir / item.name).exists()

    # Second run should succeed even though source file is already moved.
    r2 = action.execute(TriggerEvent(type="PENDING_ISSUE_DETECTED", payload={}))
    assert r2.ok
    assert r2.message in {"Already moved", "Moved"}
