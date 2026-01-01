from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class WorkflowState(str, Enum):
    PLANNING_READY = "planning_ready"
    GAP_ANALYSIS_RUNNING = "gap_analysis_running"
    PENDING_ISSUE_CREATED = "pending_issue_created"
    ISSUE_CREATED = "issue_created"
    PR_IN_PROGRESS = "pr_in_progress"
    PR_COMPLETED_UNREVIEWED = "pr_completed_unreviewed"
    PR_MERGED = "pr_merged"
    POST_PR_SYNTHESIS_RUNNING = "post_pr_synthesis_running"
    SYSTEM_CAPABILITIES_UPDATED = "system_capabilities_updated"


ALLOWED_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.PLANNING_READY: {WorkflowState.GAP_ANALYSIS_RUNNING},
    WorkflowState.GAP_ANALYSIS_RUNNING: {WorkflowState.PENDING_ISSUE_CREATED},
    WorkflowState.PENDING_ISSUE_CREATED: {WorkflowState.ISSUE_CREATED},
    WorkflowState.ISSUE_CREATED: {WorkflowState.PR_IN_PROGRESS},
    WorkflowState.PR_IN_PROGRESS: {WorkflowState.PR_COMPLETED_UNREVIEWED},
    WorkflowState.PR_COMPLETED_UNREVIEWED: {WorkflowState.PR_MERGED},
    WorkflowState.PR_MERGED: {WorkflowState.POST_PR_SYNTHESIS_RUNNING},
    WorkflowState.POST_PR_SYNTHESIS_RUNNING: {WorkflowState.SYSTEM_CAPABILITIES_UPDATED},
    WorkflowState.SYSTEM_CAPABILITIES_UPDATED: {WorkflowState.PLANNING_READY},
}


class IllegalTransitionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WorkflowEntity:
    """The entity the workflow is currently acting on.

    This intentionally stays small and explicit. Add fields as real needs appear.
    """

    issue_id: int | None = None
    pr_number: int | None = None
    queue_id: str | None = None
    repository: str | None = None

    def to_json(self) -> dict[str, object]:
        out: dict[str, object] = {}
        if self.issue_id is not None:
            out["issue_id"] = self.issue_id
        if self.pr_number is not None:
            out["pr_number"] = self.pr_number
        if self.queue_id is not None:
            out["queue_id"] = self.queue_id
        if self.repository is not None:
            out["repository"] = self.repository
        return out

    @staticmethod
    def from_json(obj: dict[str, object]) -> WorkflowEntity:
        def _int(v: object) -> int | None:
            if isinstance(v, int):
                return v
            if isinstance(v, str):
                try:
                    return int(v)
                except ValueError:
                    return None
            return None

        issue_id = _int(obj.get("issue_id"))
        pr_number = _int(obj.get("pr_number"))
        queue_raw = obj.get("queue_id")
        queue_id = queue_raw if isinstance(queue_raw, str) else None
        repo_raw = obj.get("repository")
        repository = repo_raw if isinstance(repo_raw, str) else None
        return WorkflowEntity(
            issue_id=issue_id, pr_number=pr_number, queue_id=queue_id, repository=repository
        )


@dataclass(frozen=True, slots=True)
class WorkflowSnapshot:
    state: WorkflowState
    entity: WorkflowEntity

    def to_json(self) -> dict[str, object]:
        return {"state": self.state.value, "entity": self.entity.to_json()}


def transition(*, current: WorkflowSnapshot, to: WorkflowState) -> WorkflowSnapshot:
    allowed = ALLOWED_TRANSITIONS.get(current.state, set())
    if to not in allowed:
        raise IllegalTransitionError(f"Illegal transition: {current.state.value} -> {to.value}")
    return WorkflowSnapshot(state=to, entity=current.entity)


class WorkflowStateStore:
    """Persist the workflow state machine explicitly.

    This makes long-running execution restartable and inspectable.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> WorkflowSnapshot:
        if not self._path.exists():
            return WorkflowSnapshot(state=WorkflowState.PLANNING_READY, entity=WorkflowEntity())

        raw = json.loads(self._path.read_text(encoding="utf-8"))
        state_raw = raw.get("state")
        entity_raw = raw.get("entity")

        state = (
            WorkflowState(state_raw) if isinstance(state_raw, str) else WorkflowState.PLANNING_READY
        )
        entity = (
            WorkflowEntity.from_json(entity_raw)
            if isinstance(entity_raw, dict)
            else WorkflowEntity()
        )
        return WorkflowSnapshot(state=state, entity=entity)

    def save(self, snapshot: WorkflowSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(snapshot.to_json(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def update(
        self, *, to: WorkflowState, entity: WorkflowEntity | None = None
    ) -> WorkflowSnapshot:
        current = self.load()
        next_snapshot = transition(current=current, to=to)
        if entity is not None:
            next_snapshot = WorkflowSnapshot(state=next_snapshot.state, entity=entity)
        self.save(next_snapshot)
        return next_snapshot
