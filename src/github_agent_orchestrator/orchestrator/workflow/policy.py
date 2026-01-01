from __future__ import annotations

from dataclasses import dataclass

from .actions import Action
from .events import TriggerEvent
from .state_machine import WorkflowSnapshot


@dataclass(frozen=True, slots=True)
class NextStep:
    """A single next step chosen by policy.

    Exactly one of `action` or `cognitive_task_name` should be set.
    """

    action: Action | None = None
    cognitive_task_name: str | None = None


def decide_next_step(*, state: WorkflowSnapshot, event: TriggerEvent) -> NextStep | None:
    """Policy: (state, event) -> next step.

    This is intentionally small and explicit. It must NOT call LLMs.

    For now, this is a placeholder for upcoming orchestration loop work.
    """

    _ = (state, event)
    return None
