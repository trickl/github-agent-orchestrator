from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TaskInputs:
    """Fully materialised inputs for a cognitive step.

    Keep this explicit. Avoid implicit global context.
    """

    data: dict[str, object]


@dataclass(frozen=True, slots=True)
class TaskResult:
    ok: bool
    output: dict[str, object] | None = None
    message: str = ""


class CognitiveTask(Protocol):
    """A synthesis step (often LLM-backed).

    Cognitive tasks are passive: they do not trigger themselves and they do not
    decide workflow transitions.
    """

    def run(self, inputs: TaskInputs) -> TaskResult: ...
