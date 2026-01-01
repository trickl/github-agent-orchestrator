"""Unit tests for the explicit workflow state machine.

These tests assert that illegal transitions fail loudly and that state is
persisted explicitly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from github_agent_orchestrator.orchestrator.workflow.state_machine import (
    IllegalTransitionError,
    WorkflowEntity,
    WorkflowSnapshot,
    WorkflowState,
    WorkflowStateStore,
    transition,
)


def test_transition_rejects_illegal_transitions() -> None:
    snap = WorkflowSnapshot(state=WorkflowState.PLANNING_READY, entity=WorkflowEntity())
    with pytest.raises(IllegalTransitionError):
        transition(current=snap, to=WorkflowState.ISSUE_CREATED)


def test_store_roundtrip(tmp_path: Path) -> None:
    store = WorkflowStateStore(tmp_path / "workflow" / "state.json")
    assert store.load().state == WorkflowState.PLANNING_READY

    entity = WorkflowEntity(issue_id=123, pr_number=456, queue_id="dev-1.md", repository="o/r")
    store.save(WorkflowSnapshot(state=WorkflowState.PR_IN_PROGRESS, entity=entity))

    loaded = store.load()
    assert loaded.state == WorkflowState.PR_IN_PROGRESS
    assert loaded.entity.issue_id == 123
    assert loaded.entity.pr_number == 456
    assert loaded.entity.queue_id == "dev-1.md"
    assert loaded.entity.repository == "o/r"
