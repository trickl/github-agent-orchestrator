"""Support moving issue-queue artefacts to a completed folder via a PR.

In the canonical loop, the issue queue is a handoff boundary:
- pending/: candidate work items not yet promoted
- processed/: promoted to a GitHub issue (no longer pending)
- complete/: work item is done (typically after the linked PR is merged)

This module implements deterministic plumbing to move a single file from pending/ to complete/
inside a target repository by opening and (optionally) merging a PR.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class QueueMovePlan:
    source_path: str
    dest_path: str
    filename: str


def plan_move_to_complete(*, source_path: str, complete_dir: str) -> QueueMovePlan:
    """Plan a move from a source path to a destination inside complete_dir."""

    src = source_path.lstrip("/")
    if not src:
        raise ValueError("source_path is required")

    # A trailing slash indicates a directory, not a file path.
    if src.endswith("/"):
        raise ValueError("source_path must include a filename")

    filename = Path(src).name
    if not filename:
        raise ValueError("source_path must include a filename")

    dest_dir = complete_dir.strip().lstrip("/")
    if not dest_dir:
        raise ValueError("complete_dir is required")

    dest = str(Path(dest_dir) / filename)
    return QueueMovePlan(source_path=src, dest_path=dest, filename=filename)
