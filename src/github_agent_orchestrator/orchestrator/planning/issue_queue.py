"""Materialise planning issue-queue artefacts.

The orchestrator's core contract is that it promotes queued artefacts (files) into
GitHub issues, assigns those issues to Copilot, and then moves the files to
`processed/`.

This module is intentionally *dumb*:
- it does not interpret the content beyond extracting the first-line title
- it does not generate new tasks

It only performs the file -> issue wiring.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

QUEUE_MARKER_PREFIX = "orchestrator-issue-queue-id:"


@dataclass(frozen=True, slots=True)
class IssueQueueItem:
    """A single pending queue file."""

    path: Path
    queue_id: str
    title: str
    body: str


def discover_pending_items(pending_dir: Path) -> list[Path]:
    """Return pending queue files in a stable order."""

    if not pending_dir.exists():
        return []

    candidates = [p for p in pending_dir.iterdir() if p.is_file()]
    # Stable ordering: filename sort.
    return sorted(candidates, key=lambda p: p.name)


def parse_issue_queue_item(path: Path) -> IssueQueueItem:
    """Parse a queue file into title/body.

    Rules:
    - Issue title is derived from the first line of the file.
    - Body is the full file content, plus a hidden marker to support idempotent
      promotion.
    """

    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines:
        raise ValueError(f"Queue file is empty: {path}")

    first = lines[0].rstrip("\n")
    if not first.strip():
        raise ValueError(f"Queue file has an empty first line (title): {path}")

    # Treat common markdown title formatting as cosmetic.
    title = first
    if title.lstrip().startswith("#"):
        title = title.lstrip().lstrip("#").strip()

    if not title:
        raise ValueError(f"Queue file title resolves to empty after normalization: {path}")

    queue_id = path.name

    # Keep body close to the original file while still tagging it.
    marker = f"<!-- {QUEUE_MARKER_PREFIX} {queue_id} -->"
    body = raw if marker in raw else raw.rstrip() + "\n\n---\n\n" + marker + "\n"

    return IssueQueueItem(path=path, queue_id=queue_id, title=title, body=body)


def compute_content_hash(text: str) -> str:
    """Compute a short stable hash for a queue item body.

    This is not currently used for idempotency (we key by filename), but it is
    useful for diagnostics and future enhancements.
    """

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:12]


def move_to_processed(*, item_path: Path, processed_dir: Path) -> Path:
    """Move a processed queue file to the processed directory.

    Returns:
        The destination path.
    """

    processed_dir.mkdir(parents=True, exist_ok=True)
    dest = processed_dir / item_path.name
    if dest.exists():
        raise FileExistsError(f"Processed destination already exists: {dest}")
    return item_path.replace(dest)
