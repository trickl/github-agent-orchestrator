from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TriggerEvent:
    """A signal emitted by a trigger.

    Triggers detect external facts (filesystem, GitHub, timers) and emit events.
    Triggers never perform work.
    """

    type: str
    payload: dict[str, object]
