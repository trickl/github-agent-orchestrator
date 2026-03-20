"""In-memory run state tracking for orchestrator workflow dispatches."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class RepoRunState:
    """Current control-plane execution state for a repository."""

    status: str = "idle"
    current_step: str | None = None


_RUN_STATES: dict[str, RepoRunState] = {}
_RUN_STATE_LOCK = Lock()


def get_repo_run_state(repo_full_name: str) -> RepoRunState:
    """Get run state for a repository, defaulting to idle."""

    with _RUN_STATE_LOCK:
        return _RUN_STATES.get(repo_full_name, RepoRunState())


def set_repo_run_state(repo_full_name: str, *, status: str, current_step: str | None = None) -> None:
    """Set run state for a repository."""

    with _RUN_STATE_LOCK:
        _RUN_STATES[repo_full_name] = RepoRunState(status=status, current_step=current_step)
