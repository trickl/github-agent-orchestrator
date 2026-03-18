"""In-memory event log for webhook development visibility."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock
from typing import Any

_MAX_EVENTS = 500
_EVENTS: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
_EVENT_LOCK = Lock()


def append_event(event: dict[str, Any]) -> None:
    """Append an event snapshot to the in-memory ring buffer."""
    snapshot = deepcopy(event)
    snapshot.setdefault("received_at", datetime.now(UTC).isoformat())
    with _EVENT_LOCK:
        _EVENTS.append(snapshot)


def get_recent_events(limit: int = 50) -> list[dict[str, Any]]:
    """Return most recent events first."""
    clamped = max(1, min(limit, _MAX_EVENTS))
    with _EVENT_LOCK:
        items = list(_EVENTS)
    recent = list(reversed(items[-clamped:]))
    return deepcopy(recent)


def clear_events() -> None:
    """Clear all events (primarily for test isolation)."""
    with _EVENT_LOCK:
        _EVENTS.clear()
