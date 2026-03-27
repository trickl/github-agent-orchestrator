"""Auto-dedup automation for closing duplicate issues and orphaned PRs.

When the orchestrator is dispatched concurrently (e.g. schedule + workflow_run at the
same moment), it can create duplicate follow-up issues (e.g. two "Update system
capabilities based on merged PR #N" issues).  Copilot then creates a PR for each,
wasting action minutes and creating merge conflicts.

This module detects and closes duplicates:
  - Duplicate issues: keep the lowest-numbered open issue, close the rest.
  - Orphaned PRs: close open PRs whose target branch references a closed issue.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import suppress
from typing import Any

from fastapi import HTTPException

from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard.github_api import (
    _github_patch_json,
    _repo_api_url,
)


def _issue_label_names(issue: dict[str, Any]) -> list[str]:
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return []
    return [
        label.get("name")
        for label in labels
        if isinstance(label, dict) and isinstance(label.get("name"), str)
    ]


def _issue_number(issue: dict[str, Any]) -> int | None:
    num = issue.get("number")
    return num if isinstance(num, int) else None


def _issue_title(issue: dict[str, Any]) -> str:
    title = issue.get("title")
    return title.strip() if isinstance(title, str) else ""


def _pr_number(pr: dict[str, Any]) -> int | None:
    num = pr.get("number")
    return num if isinstance(num, int) else None


def _pr_base_ref(pr: dict[str, Any]) -> str:
    base = pr.get("base")
    if isinstance(base, dict):
        ref = base.get("ref")
        if isinstance(ref, str):
            return ref.strip()
    return ""


def _close_issue(settings: ServerSettings, repository: str, issue_number: int) -> bool:
    """Close an issue as not_planned. Returns True on success."""
    with suppress(HTTPException):
        _github_patch_json(
            settings,
            url=_repo_api_url(settings, repository=repository, path=f"issues/{issue_number}"),
            payload={"state": "closed", "state_reason": "not_planned"},
        )
        return True
    return False


def _close_pull_request(settings: ServerSettings, repository: str, pr_number: int) -> bool:
    """Close a pull request. Returns True on success."""
    with suppress(HTTPException):
        _github_patch_json(
            settings,
            url=_repo_api_url(settings, repository=repository, path=f"pulls/{pr_number}"),
            payload={"state": "closed"},
        )
        return True
    return False


_DEDUP_LABELS = {"Update Capability", "Update Review"}


def maybe_auto_close_duplicate_issues(
    *,
    settings: ServerSettings,
    repository: str,
    open_issues: list[dict[str, Any]],
) -> list[str]:
    """Detect and close duplicate follow-up issues, keeping the lowest-numbered one.

    Duplicates are identified by having the same title AND the same label from the
    set of labels that the orchestrator creates follow-up issues with.

    Returns a list of warning/info strings describing actions taken.
    """

    if not getattr(settings, "auto_close_duplicate_issues", True):
        return []
    if not settings.github_token.strip():
        return []

    # Group issues by (label, normalised title) to find duplicates.
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for issue in open_issues:
        if "pull_request" in issue:
            continue
        num = _issue_number(issue)
        if num is None:
            continue
        title = _issue_title(issue)
        if not title:
            continue
        for label_name in _issue_label_names(issue):
            if label_name in _DEDUP_LABELS:
                groups[(label_name, title.lower())].append(num)

    messages: list[str] = []
    for (label, _title), issue_nums in groups.items():
        if len(issue_nums) < 2:
            continue
        sorted_nums = sorted(issue_nums)
        keep = sorted_nums[0]
        duplicates = sorted_nums[1:]
        for dup_num in duplicates:
            closed = _close_issue(settings, repository, dup_num)
            if closed:
                messages.append(
                    f"Auto-closed duplicate {label} issue #{dup_num} "
                    f"(keeping #{keep})."
                )

    return messages


def maybe_auto_close_orphaned_prs(
    *,
    settings: ServerSettings,
    repository: str,
    raw_open_prs: list[dict[str, Any]],
    open_issues: list[dict[str, Any]],
    work_branch_prefix: str = "orchestrator/work",
) -> list[str]:
    """Close open PRs whose work branch references an issue that is no longer open.

    When an issue is closed (e.g. as a duplicate), any PR targeting
    ``orchestrator/work/issue-<N>`` for that issue is orphaned and should be closed.

    Returns a list of warning/info strings describing actions taken.
    """

    if not getattr(settings, "auto_close_duplicate_issues", True):
        return []
    if not settings.github_token.strip():
        return []

    # Build set of open issue numbers.
    open_issue_nums: set[int] = set()
    for issue in open_issues:
        if "pull_request" in issue:
            continue
        num = _issue_number(issue)
        if num is not None:
            open_issue_nums.add(num)

    prefix = f"{work_branch_prefix}/issue-"
    messages: list[str] = []

    for pr in raw_open_prs:
        if not isinstance(pr, dict):
            continue
        pr_num = _pr_number(pr)
        if pr_num is None:
            continue

        base_ref = _pr_base_ref(pr)
        if not base_ref.startswith(prefix):
            continue

        # Extract issue number from branch name like "orchestrator/work/issue-208"
        suffix = base_ref[len(prefix) :]
        try:
            branch_issue_num = int(suffix)
        except (ValueError, TypeError):
            continue

        if branch_issue_num in open_issue_nums:
            continue

        closed = _close_pull_request(settings, repository, pr_num)
        if closed:
            messages.append(
                f"Auto-closed orphaned PR #{pr_num} "
                f"(targets {base_ref}, issue #{branch_issue_num} is not open)."
            )

    return messages
