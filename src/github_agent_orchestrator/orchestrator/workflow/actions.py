from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import (
    IssueAlreadyExists,
    IssueService,
    IssueStore,
)
from github_agent_orchestrator.orchestrator.planning.issue_queue import (
    QUEUE_MARKER_PREFIX,
    move_to_processed,
    parse_issue_queue_item,
)

from .events import TriggerEvent


@dataclass(frozen=True, slots=True)
class ActionResult:
    ok: bool
    message: str
    details: dict[str, object] | None = None


class Action(Protocol):
    """A deterministic, testable, idempotent step."""

    def execute(self, event: TriggerEvent) -> ActionResult: ...


@dataclass(frozen=True, slots=True)
class MovePendingIssueFile(Action):
    """Move a pending issue file to processed/.

    Idempotency:
      - If the source is already moved (source missing but dest exists), this is a success.
      - If the destination exists and source exists, we fail loudly (conflicting state).
    """

    item_path: Path
    processed_dir: Path

    def execute(self, _event: TriggerEvent) -> ActionResult:
        dest = self.processed_dir / self.item_path.name
        if not self.item_path.exists() and dest.exists():
            return ActionResult(ok=True, message="Already moved", details={"dest": str(dest)})
        try:
            moved = move_to_processed(item_path=self.item_path, processed_dir=self.processed_dir)
            return ActionResult(ok=True, message="Moved", details={"dest": str(moved)})
        except FileExistsError as e:
            return ActionResult(ok=False, message=str(e), details={"dest": str(dest)})


@dataclass(frozen=True, slots=True)
class CreateGitHubIssueFromPendingFile(Action):
    """Create a GitHub issue from a pending queue file.

    This is deterministic and idempotent:
      - primary idempotency is (repository, queue_id) via IssueStore
      - as a fallback, it checks for an existing issue by body marker
    """

    repository: str
    github: GitHubClient
    issue_store: IssueStore
    pending_file: Path
    labels: list[str] | None

    def execute(self, _event: TriggerEvent) -> ActionResult:
        issue_service = IssueService(github=self.github, store=self.issue_store)
        item = parse_issue_queue_item(self.pending_file)
        queue_path = str(item.path.as_posix())

        existing = self.issue_store.find_by_queue_id(item.queue_id, repository=self.repository)
        if existing is not None:
            return ActionResult(
                ok=True,
                message="Issue already exists",
                details={"issue_number": existing.issue_number, "title": existing.title},
            )

        # Body marker fallback in case local state was lost.
        marker = f"{QUEUE_MARKER_PREFIX} {item.queue_id}"
        existing_number = self.github.find_issue_number_by_body_marker(marker=marker)
        if existing_number is not None:
            details = self.github.get_issue(issue_number=existing_number)
            record = issue_service.record_existing_issue_from_queue(
                issue=details,
                queue_id=item.queue_id,
                queue_path=queue_path,
            )
            return ActionResult(
                ok=True,
                message="Recorded existing issue",
                details={"issue_number": record.issue_number, "title": record.title},
            )

        try:
            record = issue_service.create_issue_from_queue(
                queue_id=item.queue_id,
                queue_path=queue_path,
                title=item.title,
                body=item.body,
                labels=self.labels,
            )
            return ActionResult(
                ok=True,
                message="Created issue",
                details={"issue_number": record.issue_number, "title": record.title},
            )
        except IssueAlreadyExists as e:
            return ActionResult(
                ok=True,
                message="Issue already exists",
                details={"issue_number": e.existing.issue_number, "title": e.existing.title},
            )
