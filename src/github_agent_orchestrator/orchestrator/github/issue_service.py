"""Issue creation service with local persistence.

Phase 1A requirements:
- authenticate with token from config
- create issue with title/body/optional labels
- persist minimal metadata locally
- idempotent-safe (by title, scoped to repository)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from github_agent_orchestrator.orchestrator.github.client import (
    CreatedIssue,
    GitHubClient,
    IssueDetails,
    LinkedPullRequest,
)

logger = logging.getLogger(__name__)


class IssueRecord(BaseModel):
    """Minimal persisted representation of a created GitHub issue."""

    repository: str = Field(default="")
    issue_number: int
    title: str
    created_at: str
    status: str = Field(default="open")
    assignees: list[str] = Field(default_factory=list)

    # Optional linkage to a planning queue artefact (used for orchestrator materialisation).
    # We persist a stable queue ID (typically the filename) to make issue creation idempotent
    # even if local state is lost.
    source_queue_id: str | None = Field(default=None)
    source_queue_path: str | None = Field(default=None)

    linked_pull_requests: list[dict[str, object]] = Field(default_factory=list)
    pr_last_checked_at: str | None = Field(default=None)
    pr_completion: str | None = Field(
        default=None,
        description="One of: no_pr | merged | closed | timeout",
    )

    @classmethod
    def from_created_issue(cls, issue: CreatedIssue) -> IssueRecord:
        created = issue.created_at
        if created.tzinfo is not None:
            created_at = created.astimezone(UTC).isoformat()
        else:
            created_at = created.replace(tzinfo=UTC).isoformat()
        return cls(
            repository=issue.repository,
            issue_number=issue.number,
            title=issue.title,
            created_at=created_at,
            status=issue.status,
        )


@dataclass(frozen=True, slots=True)
class IssueAlreadyExists(Exception):
    """Raised when an issue with the given idempotency key already exists locally."""

    existing: IssueRecord

    def __str__(self) -> str:
        return f"Issue already exists: #{self.existing.issue_number} {self.existing.title!r}"


@dataclass(frozen=True, slots=True)
class LinkedPullRequestMonitorResult:
    """Result of polling linked PRs for an issue."""

    issue_number: int
    completion: str
    pull_requests: list[LinkedPullRequest]
    updated_record: IssueRecord | None


@dataclass(frozen=True, slots=True)
class PullRequestMergeOutcome:
    pull_number: int
    merged: bool
    message: str
    branch_deleted: bool


class IssueStore:
    """JSON-file backed store for created issue records."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[IssueRecord]:
        if not self._path.exists():
            return []

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning(
                "Issue state file is not valid JSON; treating as empty",
                extra={"path": str(self._path)},
            )
            return []

        if raw is None:
            return []

        if not isinstance(raw, list):
            logger.warning(
                "Issue state file has unexpected shape; treating as empty",
                extra={"path": str(self._path)},
            )
            return []

        records: list[IssueRecord] = []
        for item in raw:
            record = IssueRecord.model_validate(item)

            # Backward-compatibility: older state files didn't persist the repo.
            # We can best-effort infer it from linked PR URLs when present.
            if not record.repository.strip():
                inferred = _infer_repository_from_record(record)
                if inferred:
                    record = record.model_copy(update={"repository": inferred})

            records.append(record)
        return records

    def save(self, issues: list[IssueRecord]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [issue.model_dump(mode="json") for issue in issues]
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def find_by_title(self, title: str, *, repository: str | None = None) -> IssueRecord | None:
        normalized = title.strip()
        repo = repository.strip() if repository is not None else None
        for issue in self.load():
            if issue.title.strip() == normalized:
                if repo is None:
                    return issue
                if issue.repository.strip() == repo:
                    return issue
        return None

    def find_by_queue_id(
        self, queue_id: str, *, repository: str | None = None
    ) -> IssueRecord | None:
        normalized = queue_id.strip()
        if not normalized:
            return None
        repo = repository.strip() if repository is not None else None
        for issue in self.load():
            if (issue.source_queue_id or "").strip() != normalized:
                continue
            if repo is None:
                return issue
            if issue.repository.strip() == repo:
                return issue
        return None

    def add(self, record: IssueRecord) -> None:
        issues = self.load()
        issues.append(record)
        self.save(issues)

    def find_by_number(self, issue_number: int) -> IssueRecord | None:
        for issue in self.load():
            if issue.issue_number == issue_number:
                return issue
        return None

    def upsert(self, record: IssueRecord) -> None:
        issues = self.load()
        for idx, existing in enumerate(issues):
            if existing.issue_number == record.issue_number:
                issues[idx] = record
                self.save(issues)
                return
        issues.append(record)
        self.save(issues)


class IssueService:
    """High-level, testable issue creation orchestration."""

    def __init__(self, *, github: GitHubClient, store: IssueStore) -> None:
        self._github = github
        self._store = store

    def create_issue(
        self, *, title: str, body: str | None, labels: list[str] | None
    ) -> IssueRecord:
        existing = self._store.find_by_title(title, repository=self._github.repository)
        if existing is not None:
            raise IssueAlreadyExists(existing)

        created_issue = self._github.create_issue(title=title, body=body, labels=labels)
        record = IssueRecord.from_created_issue(created_issue)
        self._store.add(record)

        logger.info(
            "Issue created",
            extra={
                "issue_number": record.issue_number,
                "title": record.title,
                "status": record.status,
            },
        )
        return record

    def create_issue_from_queue(
        self,
        *,
        queue_id: str,
        queue_path: str,
        title: str,
        body: str | None,
        labels: list[str] | None,
    ) -> IssueRecord:
        """Create a GitHub issue sourced from a planning issue-queue artefact.

        Idempotency is based on (repository, queue_id), not on the issue title.
        """

        existing = self._store.find_by_queue_id(queue_id, repository=self._github.repository)
        if existing is not None:
            raise IssueAlreadyExists(existing)

        created_issue = self._github.create_issue(title=title, body=body, labels=labels)
        record = IssueRecord.from_created_issue(created_issue)
        record = record.model_copy(
            update={
                "source_queue_id": queue_id,
                "source_queue_path": queue_path,
            }
        )
        self._store.add(record)

        logger.info(
            "Issue created from queue",
            extra={
                "issue_number": record.issue_number,
                "title": record.title,
                "source_queue_id": queue_id,
            },
        )
        return record

    def record_existing_issue_from_queue(
        self,
        *,
        issue: IssueDetails,
        queue_id: str,
        queue_path: str,
    ) -> IssueRecord:
        """Persist an already-existing GitHub issue as originating from a queue item."""

        record = IssueRecord.from_created_issue(
            CreatedIssue(
                repository=issue.repository,
                number=issue.number,
                title=issue.title,
                created_at=issue.created_at,
                status=issue.status,
            )
        )
        record = record.model_copy(
            update={
                "assignees": issue.assignees,
                "source_queue_id": queue_id,
                "source_queue_path": queue_path,
            }
        )
        self._store.upsert(record)
        return record

    def assign_issue(self, *, issue_number: int, assignees: list[str]) -> IssueRecord | None:
        """Assign an existing issue and (optionally) reflect it in local state.

        Returns:
            The updated IssueRecord if the issue exists in local state, otherwise None.
        """

        returned_assignees = self._github.assign_issue(
            issue_number=issue_number,
            assignees=assignees,
        )

        existing = self._store.find_by_number(issue_number)
        if existing is None:
            logger.info(
                "Issue assigned (not present in local store)",
                extra={"issue_number": issue_number, "assignees": returned_assignees},
            )
            return None

        updated = existing.model_copy(update={"assignees": returned_assignees})
        self._store.upsert(updated)
        logger.info(
            "Issue assignment persisted",
            extra={"issue_number": issue_number, "assignees": updated.assignees},
        )
        return updated

    def assign_issue_to_copilot(
        self,
        *,
        issue_number: int,
        copilot_assignee: str,
        target_repo: str,
        base_branch: str = "",
        custom_instructions: str = "",
        custom_agent: str = "",
        model: str = "",
    ) -> IssueRecord | None:
        """Assign an existing issue to Copilot coding agent.

        This uses GitHub's public-preview support for Copilot issue assignment by posting an
        `agent_assignment` object alongside the assignee login.
        """

        returned_assignees = self._github.assign_issue_with_agent_assignment(
            issue_number=issue_number,
            assignees=[copilot_assignee],
            agent_assignment={
                "target_repo": target_repo,
                "base_branch": base_branch,
                "custom_instructions": custom_instructions,
                "custom_agent": custom_agent,
                "model": model,
            },
        )

        existing = self._store.find_by_number(issue_number)
        if existing is None:
            logger.info(
                "Issue assigned to Copilot (not present in local store)",
                extra={"issue_number": issue_number, "assignees": returned_assignees},
            )
            return None

        updated = existing.model_copy(update={"assignees": returned_assignees})
        self._store.upsert(updated)
        logger.info(
            "Copilot assignment persisted",
            extra={"issue_number": issue_number, "assignees": updated.assignees},
        )
        return updated

    def reassign_issue_to_copilot(
        self,
        *,
        issue_number: int,
        copilot_assignee: str,
        target_repo: str,
        base_branch: str = "",
        custom_instructions: str = "",
        custom_agent: str = "",
        model: str = "",
    ) -> IssueRecord | None:
        """Unassign Copilot from an issue (if present) then assign again.

        This is useful when Copilot previously failed to start (e.g. due to token permissions)
        and you want to retrigger the agent after fixing the token.
        """

        current = self._github.get_issue_assignees(issue_number=issue_number)

        # GitHub may surface Copilot in the assignees list as "Copilot" even if we assigned via
        # the bot login. Remove any Copilot-related assignee while preserving other assignees.
        copilotish = [a for a in current if "copilot" in a.lower()]
        if copilotish:
            self._github.remove_assignees(issue_number=issue_number, assignees=copilotish)

        return self.assign_issue_to_copilot(
            issue_number=issue_number,
            copilot_assignee=copilot_assignee,
            target_repo=target_repo,
            base_branch=base_branch,
            custom_instructions=custom_instructions,
            custom_agent=custom_agent,
            model=model,
        )

    def refresh_linked_pull_requests(
        self,
        *,
        issue_number: int,
        pull_requests: list[LinkedPullRequest] | None = None,
    ) -> IssueRecord | None:
        """Fetch linked PRs for an issue and persist them in local state (if present).

        Returns:
            Updated IssueRecord if the issue exists in local state, otherwise None.
        """

        prs = pull_requests
        if prs is None:
            prs = self._github.get_linked_pull_requests(issue_number=issue_number)
        existing = self._store.find_by_number(issue_number)
        if existing is None:
            logger.info(
                "Linked pull requests fetched (not present in local store)",
                extra={"issue_number": issue_number, "pull_request_count": len(prs)},
            )
            return None

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        updated = existing.model_copy(
            update={
                "linked_pull_requests": [_linked_pr_to_json(p) for p in prs],
                "pr_last_checked_at": now,
            }
        )
        self._store.upsert(updated)
        logger.info(
            "Linked pull requests persisted",
            extra={
                "issue_number": issue_number,
                "pull_request_numbers": [p.number for p in prs],
            },
        )
        return updated

    def wait_for_linked_pull_requests_complete(
        self,
        *,
        issue_number: int,
        poll_interval_seconds: float = 10.0,
        timeout_seconds: float = 1800.0,
        require_pull_request: bool = True,
    ) -> LinkedPullRequestMonitorResult:
        """Poll linked PRs for an issue until they reach a terminal state.

        Semantics:
            - "complete" means there are no OPEN linked PRs remaining.
            - completion is recorded as:
                - merged: all linked PRs are merged
                - closed: at least one linked PR is closed without merge (and none are open)
                - timeout: polling timed out

        Returns:
            The updated IssueRecord if the issue exists in local state, otherwise None.
        """

        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be > 0")
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be >= 0")

        started = time.monotonic()
        last_pr_numbers: list[int] | None = None

        while True:
            prs = self._github.get_linked_pull_requests(issue_number=issue_number)
            pr_numbers = [p.number for p in prs]
            if last_pr_numbers != pr_numbers:
                logger.info(
                    "Linked pull requests changed",
                    extra={"issue_number": issue_number, "pull_request_numbers": pr_numbers},
                )
                last_pr_numbers = pr_numbers

            terminal_status = _evaluate_pr_completion(
                prs, require_pull_request=require_pull_request
            )
            updated = self.refresh_linked_pull_requests(
                issue_number=issue_number,
                pull_requests=prs,
            )

            if updated is not None and terminal_status is not None:
                now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                updated = updated.model_copy(
                    update={
                        "pr_completion": terminal_status,
                        "pr_last_checked_at": now,
                    }
                )
                self._store.upsert(updated)

            if terminal_status is not None:
                logger.info(
                    "Linked pull requests complete",
                    extra={
                        "issue_number": issue_number,
                        "completion": terminal_status,
                        "pull_request_numbers": pr_numbers,
                    },
                )
                return LinkedPullRequestMonitorResult(
                    issue_number=issue_number,
                    completion=terminal_status,
                    pull_requests=prs,
                    updated_record=updated,
                )

            if timeout_seconds and (time.monotonic() - started) >= timeout_seconds:
                logger.warning(
                    "Timed out waiting for linked pull requests",
                    extra={"issue_number": issue_number, "timeout_seconds": timeout_seconds},
                )
                if updated is not None:
                    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    updated = updated.model_copy(
                        update={"pr_completion": "timeout", "pr_last_checked_at": now}
                    )
                    self._store.upsert(updated)
                return LinkedPullRequestMonitorResult(
                    issue_number=issue_number,
                    completion="timeout",
                    pull_requests=prs,
                    updated_record=updated,
                )

            time.sleep(poll_interval_seconds)

    def wait_for_linked_pull_requests_present(
        self,
        *,
        issue_number: int,
        poll_interval_seconds: float = 10.0,
        timeout_seconds: float = 1800.0,
    ) -> list[LinkedPullRequest]:
        """Poll until at least one linked PR is visible for the issue."""

        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be > 0")
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be >= 0")

        started = time.monotonic()
        while True:
            prs = self._github.get_linked_pull_requests(issue_number=issue_number)
            if prs:
                logger.info(
                    "Linked pull requests discovered",
                    extra={
                        "issue_number": issue_number,
                        "pull_request_numbers": [p.number for p in prs],
                    },
                )
                # Persist what we see.
                self.refresh_linked_pull_requests(issue_number=issue_number, pull_requests=prs)
                return prs

            if timeout_seconds and (time.monotonic() - started) >= timeout_seconds:
                logger.warning(
                    "Timed out waiting for linked pull requests to appear",
                    extra={"issue_number": issue_number, "timeout_seconds": timeout_seconds},
                )
                return []

            time.sleep(poll_interval_seconds)

    def merge_linked_pull_requests(
        self,
        *,
        issue_number: int,
        poll_interval_seconds: float = 10.0,
        timeout_seconds: float = 1800.0,
        merge_method: str = "squash",
        mark_ready_for_review: bool = True,
        delete_branch: bool = True,
    ) -> list[PullRequestMergeOutcome]:
        """Wait for linked PRs, mark them ready for review, then merge + delete branches.

        This is intentionally best-effort:
        - If merge is refused (checks/approvals), we keep polling until timeout.
        - Branch deletion is skipped for forks and protected/default-like branches.
        """

        prs = self.wait_for_linked_pull_requests_present(
            issue_number=issue_number,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )

        open_prs = [p for p in prs if p.state.upper() == "OPEN"]
        if not open_prs:
            logger.info(
                "No open linked PRs to merge",
                extra={
                    "issue_number": issue_number,
                    "pull_request_numbers": [p.number for p in prs],
                },
            )
            return []

        started = time.monotonic()
        outcomes: list[PullRequestMergeOutcome] = []

        for pr in open_prs:
            # Avoid hammering the ready-for-review endpoint. We'll attempt it once per PR
            # if the PR remains a draft.
            ready_attempted = False

            while True:
                pr_details = self._github.get_pull_request(pull_number=pr.number)

                if pr_details.merged:
                    branch_deleted = False
                    if delete_branch:
                        try:
                            branch_deleted = self._github.delete_pull_request_branch(
                                pull_number=pr.number
                            )
                        except Exception:
                            logger.exception(
                                "Branch deletion failed (continuing)",
                                extra={"issue_number": issue_number, "pull_number": pr.number},
                            )
                    outcomes.append(
                        PullRequestMergeOutcome(
                            pull_number=pr.number,
                            merged=True,
                            message="already merged",
                            branch_deleted=branch_deleted,
                        )
                    )
                    break

                if pr_details.state.lower() != "open":
                    outcomes.append(
                        PullRequestMergeOutcome(
                            pull_number=pr.number,
                            merged=False,
                            message=f"pull request is not open (state={pr_details.state})",
                            branch_deleted=False,
                        )
                    )
                    break

                if pr_details.draft:
                    if mark_ready_for_review and not ready_attempted:
                        ready_attempted = True
                        try:
                            self._github.mark_pull_request_ready_for_review(pull_number=pr.number)
                        except Exception:
                            logger.exception(
                                "Failed to mark PR ready for review (continuing)",
                                extra={"issue_number": issue_number, "pull_number": pr.number},
                            )

                    # Draft PRs cannot be merged; wait and retry.
                    if timeout_seconds and (time.monotonic() - started) >= timeout_seconds:
                        outcomes.append(
                            PullRequestMergeOutcome(
                                pull_number=pr.number,
                                merged=False,
                                message="timeout: pull request is still a draft",
                                branch_deleted=False,
                            )
                        )
                        break

                    time.sleep(poll_interval_seconds)
                    continue

                merge = self._github.merge_pull_request(
                    pull_number=pr.number,
                    merge_method=merge_method,
                )
                if merge.merged:
                    branch_deleted = False
                    if delete_branch:
                        try:
                            branch_deleted = self._github.delete_pull_request_branch(
                                pull_number=pr.number
                            )
                        except Exception:
                            logger.exception(
                                "Branch deletion failed (continuing)",
                                extra={"issue_number": issue_number, "pull_number": pr.number},
                            )
                    outcomes.append(
                        PullRequestMergeOutcome(
                            pull_number=pr.number,
                            merged=True,
                            message=merge.message,
                            branch_deleted=branch_deleted,
                        )
                    )
                    break

                # Not merged yet; decide whether to keep waiting.
                if timeout_seconds and (time.monotonic() - started) >= timeout_seconds:
                    outcomes.append(
                        PullRequestMergeOutcome(
                            pull_number=pr.number,
                            merged=False,
                            message=f"timeout: {merge.message}",
                            branch_deleted=False,
                        )
                    )
                    break

                time.sleep(poll_interval_seconds)

        return outcomes


def _infer_repository_from_record(record: IssueRecord) -> str:
    """Best-effort inference for legacy IssueRecords that did not persist repository.

    We only infer from linked pull request URLs, because those embed owner/repo.
    If we can't infer confidently, return an empty string.
    """

    for pr in record.linked_pull_requests:
        url = pr.get("url")
        if not isinstance(url, str) or not url.strip():
            continue

        parsed = urlparse(url)
        path = parsed.path.lstrip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    return ""


def _linked_pr_to_json(pr: LinkedPullRequest) -> dict[str, object]:
    return {
        "number": pr.number,
        "url": pr.url,
        "title": pr.title,
        "state": pr.state,
        "is_draft": pr.is_draft,
        "merged": pr.merged,
        "merged_at": pr.merged_at,
        "closed_at": pr.closed_at,
        "updated_at": pr.updated_at,
    }


def _evaluate_pr_completion(
    prs: list[LinkedPullRequest], *, require_pull_request: bool
) -> str | None:
    if not prs:
        return "no_pr" if not require_pull_request else None

    any_open = any(p.state.upper() == "OPEN" for p in prs)
    if any_open:
        return None

    # No open PRs remain.
    all_merged = all(p.merged or p.state.upper() == "MERGED" for p in prs)
    if all_merged:
        return "merged"

    # Terminal but not fully merged.
    return "closed"
