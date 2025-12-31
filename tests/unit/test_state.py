"""Unit tests for Phase 1A local persistence."""

from __future__ import annotations

from pathlib import Path

from github_agent_orchestrator.orchestrator.github.issue_service import IssueRecord, IssueStore


def test_issue_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "agent_state" / "issues.json"
    store = IssueStore(path)

    assert store.load() == []

    store.save(
        [
            IssueRecord(
                issue_number=10,
                title="T",
                created_at="2025-01-01T00:00:00+00:00",
                status="open",
                assignees=[],
            )
        ]
    )

    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].issue_number == 10
    assert loaded[0].title == "T"
