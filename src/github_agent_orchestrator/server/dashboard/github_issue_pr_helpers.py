"""GitHub issue and pull request helper functions for dashboard modules.

This module provides utilities for working with GitHub issues and pull requests,
including PR evaluation, timeline analysis, and matching logic.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard.github_api import (
    _repo_api_url,
)
from github_agent_orchestrator.server.dashboard.text_utilities import (
    _normalize_issue_title,
)

# Copilot often prefixes PR titles with "WIP" while it is still working.
_WIP_TITLE_RE = re.compile(r"^\s*(?:\[\s*)?wip\b", re.IGNORECASE)


def _extract_pr_number_from_timeline_event(ev: dict[str, Any]) -> int | None:
    source = ev.get("source")
    if isinstance(source, dict):
        issue = source.get("issue")
        if isinstance(issue, dict) and "pull_request" in issue:
            num = issue.get("number")
            if isinstance(num, int):
                return num

    subject = ev.get("subject")
    if isinstance(subject, dict) and "pull_request" in subject:
        num = subject.get("number")
        if isinstance(num, int):
            return num

    return None


def _normalized_review_entry(raw: object) -> tuple[str, str, str] | None:
    if not isinstance(raw, dict):
        return None

    state = raw.get("state")
    submitted_at = raw.get("submitted_at")
    user = raw.get("user")
    login = user.get("login") if isinstance(user, dict) else None

    if not isinstance(login, str) or not login.strip():
        return None
    if not isinstance(state, str) or not state.strip():
        return None
    if not isinstance(submitted_at, str) or not submitted_at.strip():
        return None

    key = login.strip().lower()
    return key, submitted_at, state.strip().upper()


def _discussion_items(kind: str, raw: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        created_at = it.get("created_at")
        user = it.get("user")
        author = user.get("login") if isinstance(user, dict) else None
        body = it.get("body")
        url = it.get("html_url") or it.get("url")
        if not isinstance(created_at, str):
            continue
        out.append(
            {
                "created_at": created_at,
                "kind": kind,
                "author": author if isinstance(author, str) else "unknown",
                "body": body if isinstance(body, str) else "",
                "url": url if isinstance(url, str) else "",
            }
        )
    return out


def issue_has_label(issue: dict[str, Any], *, label_name: str) -> bool:
    """Check if an issue has a specific label."""
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return False
    for lbl in labels:
        if isinstance(lbl, dict) and lbl.get("name") == label_name:
            return True
        if isinstance(lbl, str) and lbl == label_name:
            return True
    return False


def linked_pr_numbers_from_issue_timeline(timeline: list[dict[str, Any]]) -> set[int]:
    """Extract linked PR numbers from an issue timeline.

    GitHub can represent "issue <-> PR" association in a few ways (cross-reference,
    connected events, etc.). We keep this conservative but support the common shapes
    we see in the REST timeline API.
    """

    out: set[int] = set()
    for raw in timeline:
        if not isinstance(raw, dict):
            continue
        event = raw.get("event")
        if event not in {"cross-referenced", "connected"}:
            continue
        pr_num = _extract_pr_number_from_timeline_event(raw)
        if pr_num is not None:
            out.add(pr_num)
    return out


def pull_request_title_is_wip(title: str) -> bool:
    """Check if a PR title indicates work-in-progress."""
    if not isinstance(title, str):
        return False
    return bool(_WIP_TITLE_RE.search(title.strip()))


def pull_request_has_review_request(pr_data: dict[str, Any]) -> bool:
    """Check if a PR has active review requests."""
    requested_reviewers = pr_data.get("requested_reviewers")
    requested_teams = pr_data.get("requested_teams")
    return bool(requested_reviewers) or bool(requested_teams)


def pull_request_has_review_request_history(
    settings: ServerSettings, *, repository: str, pr_number: int
) -> bool:
    """Return True if the PR has ever had a review request (best-effort).

    GitHub may clear `requested_reviewers` after reviews are submitted, so we also
    consult the PR issue timeline for `review_requested` / `review_request_removed`
    events.
    """

    # Import here to avoid circular imports and to make this function easy to patch in unit tests.
    #
    # Important: do NOT call github_operations.list_issue_timeline_raw directly here.
    # The dashboard test suite patches dashboard_router._list_issue_timeline_raw (and sometimes
    # loop_status._list_issue_timeline_raw) to prevent accidental real GitHub calls.
    from github_agent_orchestrator.server import dashboard_router

    timeline = dashboard_router._list_issue_timeline_raw(
        settings, repository=repository, issue_number=pr_number
    )
    for ev in timeline:
        if not isinstance(ev, dict):
            continue
        event = ev.get("event")
        if event in {"review_requested", "review_request_removed"}:
            return True
    return False


def pull_request_is_approved_from_reviews(reviews: list[dict[str, Any]]) -> bool:
    """Return True if the PR should be treated as "approved".

    GitHub does not expose approval status directly on the PR object. To keep this
    deterministic and REST-only, we interpret the PR reviews list:

    - Use each reviewer's latest review state.
    - Approved means: at least one APPROVED and no CHANGES_REQUESTED outstanding.
    """

    latest_by_user: dict[str, tuple[str, str]] = {}
    for raw in reviews:
        entry = _normalized_review_entry(raw)
        if entry is None:
            continue
        key, submitted_at, state = entry
        prev = latest_by_user.get(key)
        if prev is None or submitted_at > prev[0]:
            latest_by_user[key] = (submitted_at, state)

    if not latest_by_user:
        return False

    states = [st for _ts, st in latest_by_user.values()]
    has_changes_requested = any(st == "CHANGES_REQUESTED" for st in states)
    if has_changes_requested:
        return False
    return any(st == "APPROVED" for st in states)


def pull_request_is_ready_for_review(pr_data: dict[str, Any], *, review_requested: bool) -> bool:
    """Check if a PR is ready for review (Copilot completion signal)."""
    if pr_data.get("state") != "open":
        return False

    if pr_data.get("draft") is True:
        return False

    title = pr_data.get("title")
    if isinstance(title, str) and pull_request_title_is_wip(title):
        return False

    if not review_requested:
        return False

    mergeable = pr_data.get("mergeable")
    mergeable_state = pr_data.get("mergeable_state")
    if mergeable is False:
        return False
    if isinstance(mergeable_state, str):
        return mergeable_state.lower() != "dirty"

    return True


def pull_request_is_merge_candidate(pr_data: dict[str, Any], *, review_requested: bool) -> bool:
    """Return True if the PR is a candidate for the merge endpoint to act on.

    Unlike `pull_request_is_ready_for_review`, this intentionally allows draft PRs,
    because the merge endpoint may attempt to mark a draft PR as "ready for review"
    (GraphQL mutation) *before* merging.

    Safety gates still apply:
    - PR must be open
    - PR must not be WIP
    - a review must have been requested (signal of Copilot completion)
    - PR must not be conflicted
    """

    if pr_data.get("state") != "open":
        return False

    title = pr_data.get("title")
    if isinstance(title, str) and pull_request_title_is_wip(title):
        return False

    if not review_requested:
        return False

    mergeable = pr_data.get("mergeable")
    mergeable_state = pr_data.get("mergeable_state")
    if mergeable is False:
        return False
    if isinstance(mergeable_state, str):
        return mergeable_state.lower() != "dirty"

    return True


def best_match_issue_number(
    pending_title_norm: str,
    open_issues: list[dict[str, Any]],
    *,
    min_ratio: float = 0.92,
) -> int | None:
    """Match a pending queue title to an open GitHub issue.

    We primarily use normalized title equality, and fall back to a conservative fuzzy match.
    """

    if not pending_title_norm:
        return None

    best_num: int | None = None
    best_ratio = 0.0
    for it in open_issues:
        if "pull_request" in it:
            continue
        num = it.get("number")
        title = it.get("title")
        if not isinstance(num, int) or not isinstance(title, str):
            continue
        issue_title_norm = _normalize_issue_title(title)
        if issue_title_norm == pending_title_norm:
            return num
        ratio = difflib.SequenceMatcher(a=pending_title_norm, b=issue_title_norm).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_num = num

    if best_num is not None and best_ratio >= min_ratio:
        return best_num
    return None


def get_pull_request_discussion_markdown(
    settings: ServerSettings, *, repository: str, pr_number: int
) -> str:
    """Best-effort compact discussion rendering for a PR (issue comments + reviews + review comments)."""

    # Import here to avoid circular imports and to keep this function easy to patch in unit tests.
    # Tests patch dashboard_router._github_get_list to prevent accidental real GitHub calls.
    from github_agent_orchestrator.server import dashboard_router

    issue_comments = dashboard_router._github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"issues/{pr_number}/comments"),
        params={"per_page": "100"},
    )
    reviews = dashboard_router._github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"pulls/{pr_number}/reviews"),
        params={"per_page": "100"},
    )
    review_comments = dashboard_router._github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"pulls/{pr_number}/comments"),
        params={"per_page": "100"},
    )

    items = (
        _discussion_items("issue_comment", issue_comments)
        + _discussion_items("review", reviews)
        + _discussion_items("review_comment", review_comments)
    )

    if not items:
        return "(no PR comments)\n"

    items.sort(key=lambda i: str(i.get("created_at") or ""))

    parts: list[str] = []
    for it in items:
        ts = it.get("created_at") or ""
        kind = it.get("kind") or ""
        author = it.get("author") or "unknown"
        body = (it.get("body") or "").strip() or "(empty)"
        url = (it.get("url") or "").strip()

        header = f"- **{ts}** *( {kind} by {author} )*"
        indented = "\n".join(f"  {line}" for line in body.splitlines())
        parts.append("\n".join([header, indented]))
        if url:
            parts.append(f"  URL: {url}")

    return "\n".join(parts).rstrip() + "\n"
