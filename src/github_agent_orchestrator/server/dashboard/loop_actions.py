"""Loop action operations: promote and merge.

This module contains the core orchestration logic for the two primary loop actions:
- **Promote**: Converting pending queue files into assigned GitHub issues
- **Merge**: Merging ready pull requests and triggering follow-up actions

These operations are the "write side" of the orchestration loop, complementing
the "read side" status computation in loop_status.py.
"""

from __future__ import annotations

import re
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from github_agent_orchestrator.github_labels import (
    LABEL_DEVELOPMENT,
    LABEL_REVIEW_CONSUMPTION,
    LABEL_UPDATE_CAPABILITY,
    LABEL_UPDATE_REVIEW,
)
from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard.github_api import (
    _github_delete_json,
    _github_get_json,
    _github_graphql_post,
    _github_patch_json,
    _github_post_json,
    _github_put_json,
    _graphql_api_url,
    _graphql_errors_as_message,
    _repo_api_url,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    best_match_issue_number as _best_match_issue_number,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    get_pull_request_discussion_markdown as _get_pull_request_discussion_markdown,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    issue_has_label as _issue_has_label,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    linked_pr_numbers_from_issue_timeline as _linked_pr_numbers_from_issue_timeline,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    pull_request_has_review_request as _pull_request_has_review_request,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    pull_request_has_review_request_history as _pull_request_has_review_request_history,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    pull_request_is_merge_candidate as _pull_request_is_merge_candidate,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    pull_request_title_is_wip as _pull_request_title_is_wip,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    delete_repo_file_if_present as _delete_repo_file_if_present,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    ensure_repo_file_present_in_complete as _ensure_repo_file_present_in_complete,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    ensure_repo_file_present_in_processed as _ensure_repo_file_present_in_processed,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    ensure_repo_label_exists as _ensure_repo_label_exists,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    get_default_branch as _get_default_branch,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    get_pull_request as _get_pull_request,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    get_repo_text_file as _get_repo_text_file,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_issue_timeline_raw as _list_issue_timeline_raw,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_open_issues_raw as _list_open_issues_raw,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_repo_markdown_files_under as _list_repo_markdown_files_under,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    search_issue_number_by_body_marker as _search_issue_number_by_body_marker,
)
from github_agent_orchestrator.server.dashboard.queue_helpers import (
    _is_gap_analysis_issue_title,
    _parse_queue_file_for_issue,
    _queue_category_for_filename,
    _queue_filename,
    _search_issue_number_by_queue_marker,
)
from github_agent_orchestrator.server.dashboard.text_utilities import (
    _first_markdown_line_as_title,
    _normalize_repo_path_candidate,
)

# Marker used to make capability-update issues (created after merges) idempotent.
_CAPABILITY_UPDATE_FROM_PR_MARKER_PREFIX = "orchestrator:capability-update-from-pr"

# Marker used to make review-actions update issues idempotent.
_REVIEW_UPDATE_FROM_PR_MARKER_PREFIX = "orchestrator:review-update-from-pr"

_CAPABILITY_ISSUE_TITLE_SOURCE_PR_RE = re.compile(r"merged\s+pr\s+#(\d+)", re.IGNORECASE)
_CAPABILITY_ISSUE_BODY_SOURCE_PR_RE = re.compile(
    rf"{re.escape(_CAPABILITY_UPDATE_FROM_PR_MARKER_PREFIX)}\s+([^#\s]+)#(\d+)",
    re.IGNORECASE,
)

_GAP_ANALYSIS_TEMPLATE_PATHS: tuple[str, ...] = (
    "planning/issue_templates/gap-analysis.md",
    "planning/issue_templates/gap_analysis.md",
)

_REVIEW_ACTIONS_AFTER_MERGE_TEMPLATE_PATHS: tuple[str, ...] = (
    "planning/issue_templates/review-actions-after-pr-merge.md",
    "planning/issue_templates/review_actions_after_pr_merge.md",
)

_REVIEW_QUEUE_SOURCE_RE = re.compile(r"^\s*source\s+review\s*:\s*(.+?)\s*$", re.IGNORECASE)
_REVIEW_QUEUE_ACTIONS_RE = re.compile(r"^\s*review\s+actions\s*:\s*(.+?)\s*$", re.IGNORECASE)
_REVIEW_QUEUE_ID_DATE_RE = re.compile(r"\breview-(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)


def _settings(request: Request) -> ServerSettings:
    """Import from dashboard_router to avoid circular dependency."""
    from github_agent_orchestrator.server import dashboard_router

    return dashboard_router._settings(request)


def _active_repo(request: Request, settings: ServerSettings) -> str:
    """Import from dashboard_router to avoid circular dependency."""
    from github_agent_orchestrator.server import dashboard_router

    return dashboard_router._active_repo(request, settings)


def _make_github_issue_url(repo: str, issue_number: int) -> str | None:
    """Import from dashboard_router to avoid circular dependency."""
    from github_agent_orchestrator.server import dashboard_router

    return dashboard_router._make_github_issue_url(repo, issue_number)


def _assign_issue_to_copilot(
    settings: ServerSettings,
    *,
    repository: str,
    issue_number: int,
    target_repo: str,
    base_branch: str,
    instructions: str,
) -> list[str]:
    """Import from dashboard_router to avoid circular dependency."""
    from github_agent_orchestrator.server import dashboard_router

    return dashboard_router._assign_issue_to_copilot(
        settings,
        repository=repository,
        issue_number=issue_number,
        target_repo=target_repo,
        base_branch=base_branch,
        instructions=instructions,
    )


def _queue_file_is_excluded_for_loop_mode(*, filename: str, loop_mode: str) -> bool:
    """Import from dashboard_router to avoid circular dependency."""
    from github_agent_orchestrator.server import dashboard_router

    return dashboard_router._queue_file_is_excluded_for_loop_mode(
        filename=filename, loop_mode=loop_mode
    )


def _review_actions_path_for_review_path(review_path: str) -> str:
    """Import from dashboard_router to avoid circular dependency."""
    from github_agent_orchestrator.server import dashboard_router

    return dashboard_router._review_actions_path_for_review_path(review_path)


def _pick_next_review_file(*, settings: ServerSettings, repo: str, branch: str) -> str | None:
    """Import from dashboard_router to avoid circular dependency."""
    from github_agent_orchestrator.server import dashboard_router

    return dashboard_router._pick_next_review_file(settings=settings, repo=repo, branch=branch)


def _extract_review_paths_from_queue_content(
    *, queue_id: str, queue_content: str
) -> tuple[str | None, str | None]:
    """Import from dashboard_router to avoid circular dependency."""
    from github_agent_orchestrator.server import dashboard_router

    return dashboard_router._extract_review_paths_from_queue_content(
        queue_id=queue_id, queue_content=queue_content
    )


def _render_review_actions_update_issue_body(
    *,
    settings: ServerSettings,
    repo: str,
    branch: str,
    pr_number: int,
    pr_title: str,
    pr_body: str,
    discussion_markdown: str,
    queue_path: str,
    queue_content: str,
) -> tuple[str, str]:
    """Import from dashboard_router to avoid circular dependency."""
    from github_agent_orchestrator.server import dashboard_router

    return dashboard_router._render_review_actions_update_issue_body(
        settings=settings,
        repo=repo,
        branch=branch,
        pr_number=pr_number,
        pr_title=pr_title,
        pr_body=pr_body,
        discussion_markdown=discussion_markdown,
        queue_path=queue_path,
        queue_content=queue_content,
    )


def _load_gap_analysis_template_or_raise(
    *, settings: ServerSettings, repo: str, branch: str
) -> str:
    """Load the gap analysis issue template.

    Single source of truth: the target repository (GitHub) under planning/issue_templates.
    This keeps behavior predictable for operators: editing the repo template changes what
    the server will create.
    """

    for template_path in _GAP_ANALYSIS_TEMPLATE_PATHS:
        with suppress(Exception):
            content, _sha = _get_repo_text_file(
                settings,
                repository=repo,
                path=template_path,
                ref=branch,
            )
            if content.strip():
                return content

    raise HTTPException(
        status_code=502,
        detail=(
            "Unable to load gap analysis template from the target repository. "
            "Expected one of: planning/issue_templates/gap-analysis.md or "
            "planning/issue_templates/gap_analysis.md"
        ),
    )


def _load_review_actions_after_merge_template_or_raise(
    *, settings: ServerSettings, repo: str, branch: str
) -> str:
    """Load the review-actions-after-merge issue template from the target repository."""

    for template_path in _REVIEW_ACTIONS_AFTER_MERGE_TEMPLATE_PATHS:
        with suppress(Exception):
            content, _sha = _get_repo_text_file(
                settings,
                repository=repo,
                path=template_path,
                ref=branch,
            )
            if content.strip():
                return content

    raise HTTPException(
        status_code=502,
        detail=(
            "Unable to load review actions-after-merge template from the target repository. "
            "Expected planning/issue_templates/review-actions-after-pr-merge.md"
        ),
    )


def _gap_analysis_issue_body_looks_unsafe(body: str) -> bool:
    """Detect unsafe gap-analysis issue bodies.

    We intentionally look for very specific known-bad phrases (from the previous incident)
    to avoid blocking legitimate issue bodies elsewhere.
    """

    lowered = body.lower()
    forbidden = (
        "open a pr that adds exactly one new file",
        "open a pr that adds exactly one new file under /planning/issue_queue/pending/",
        "create one development task in planning/issue_queue/pending/",
    )
    return any(tok in lowered for tok in forbidden)


def _repair_gap_analysis_issue_body_if_unsafe(
    *,
    settings: ServerSettings,
    repo: str,
    issue_number: int,
    branch: str,
    existing_body: str,
) -> bool:
    """Replace an unsafe gap-analysis issue body with the repo template.

    Returns True if a repair was performed.
    """

    if not existing_body.strip():
        return False
    if not _gap_analysis_issue_body_looks_unsafe(existing_body):
        return False

    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail=(
                "ORCHESTRATOR_GITHUB_TOKEN is required to repair unsafe gap analysis issue bodies"
            ),
        )

    repaired_body = (
        _load_gap_analysis_template_or_raise(
            settings=settings,
            repo=repo,
            branch=branch,
        ).rstrip()
        + "\n"
    )
    _github_patch_json(
        settings,
        url=_repo_api_url(settings, repository=repo, path=f"issues/{issue_number}"),
        payload={"body": repaired_body},
    )
    return True


def _ensure_gap_analysis_issue_exists(*, settings: ServerSettings, repo: str) -> dict[str, object]:
    """Ensure there is exactly one open gap analysis issue (best-effort).

    This is used by the server-side auto progression loop when
    ORCHESTRATOR_AUTO_PROMOTE_ENABLED=true.

    The gap analysis task remains "cognitive" (it produces a queue artefact), but this helper
    can automatically open + assign the issue so the overall cycle can keep moving.
    """

    branch = _get_default_branch(settings, repository=repo)

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    for it in raw_issues:
        if not isinstance(it, dict):
            continue
        if "pull_request" in it:
            continue
        title = it.get("title")
        if isinstance(title, str) and _is_gap_analysis_issue_title(title):
            num = it.get("number")
            if isinstance(num, int):
                # If an unsafe gap-analysis issue already exists, repair it before assigning.
                # This avoids costly self-referential instructions.
                body = it.get("body")
                if isinstance(body, str):
                    _repair_gap_analysis_issue_body_if_unsafe(
                        settings=settings,
                        repo=repo,
                        issue_number=num,
                        branch=branch,
                        existing_body=body,
                    )

                # Best-effort: ensure assignment to Copilot so Step A can actually start.
                assignees = it.get("assignees")
                already_assigned = False
                if isinstance(assignees, list):
                    for a in assignees:
                        if isinstance(a, dict) and a.get("login") == settings.copilot_assignee:
                            already_assigned = True
                            break

                assigned: list[dict[str, Any]] | list[str] = []
                if not already_assigned:
                    assigned = _assign_issue_to_copilot(
                        settings,
                        repository=repo,
                        issue_number=num,
                        target_repo=repo,
                        base_branch=branch,
                        instructions="",
                    )

                return {
                    "created": False,
                    "issueNumber": num,
                    "issueUrl": _make_github_issue_url(repo, num),
                    "assigned": assigned,
                }

    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail="ORCHESTRATOR_GITHUB_TOKEN is required to create gap analysis issues",
        )

    template_body = _load_gap_analysis_template_or_raise(
        settings=settings, repo=repo, branch=branch
    )

    issue_title = "Identify the next most important development gap"
    # IMPORTANT: Use the template verbatim. Do not append additional 'Completion' instructions.
    issue_body = template_body.rstrip() + "\n"

    issue = _github_post_json(
        settings,
        url=_repo_api_url(settings, repository=repo, path="issues"),
        payload={
            "title": issue_title,
            "body": issue_body,
        },
    )
    issue_num = issue.get("number")
    if not isinstance(issue_num, int):
        raise HTTPException(status_code=502, detail="Unexpected GitHub create issue response")

    assigned = _assign_issue_to_copilot(
        settings,
        repository=repo,
        issue_number=issue_num,
        target_repo=repo,
        base_branch=branch,
        instructions="",
    )

    return {
        "created": True,
        "issueNumber": issue_num,
        "issueUrl": _make_github_issue_url(repo, issue_num),
        "assigned": assigned,
    }


def promote_next_pending_issue_queue_item(request: Request) -> dict[str, object]:
    """Step 2a action: promote one pending development queue file.

    Deterministic plumbing:
    - find the next unpromoted development queue file (stable filename order)
    - create (or find) the corresponding issue
    - assign it to Copilot
    - move the queue file from pending/ to processed/ in the repo

    This endpoint intentionally performs ONE promotion per call.
    """

    settings = _settings(request)
    repo = _active_repo(request, settings)
    return _promote_next_unpromoted_development_queue_item(settings=settings, repo=repo)


def ensure_gap_analysis_issue(request: Request) -> dict[str, object]:
    """Step 1a action: ensure a gap-analysis issue exists and is assigned.

    This is primarily useful when auto-promotion is disabled.
    """

    settings = _settings(request)
    repo = _active_repo(request, settings)
    out = _ensure_gap_analysis_issue_exists(settings=settings, repo=repo)

    # Keep shape similar to other action endpoints.
    created = bool(out.get("created"))
    num = out.get("issueNumber")
    summary = "Gap analysis issue ensured"
    if isinstance(num, int):
        summary = f"{'Created' if created else 'Ensured'} gap analysis issue #{num}"
    return {
        **out,
        "repo": repo,
        "branch": _get_default_branch(settings, repository=repo),
        "summary": summary,
    }


def merge_next_ready_development_pull_request(request: Request) -> dict[str, object]:
    """Step 1c/2c/3c action: approve + merge the next ready PR.

    Deterministic plumbing:
    - if a capability-update issue has a "ready for review" PR, merge that first (Step 3c)
    - else if a gap-analysis issue has a "ready for review" PR, merge that next (Step 1c)
    - else find the next development queue item with an associated open PR that is "ready for review" (Step 2c)
    - best-effort: mark ready for review (if draft)
    - best-effort: submit an approval review
    - attempt to merge (squash)
    - on success (dev): move the queue file to issue_queue/complete and create + assign an "Update Capability" issue
    - on success (capability): close the capability issue
    - on success (gap): close the gap-analysis issue

    This endpoint intentionally performs ONE merge per call.
    """

    settings = _settings(request)
    repo = _active_repo(request, settings)
    return _merge_next_ready_pull_request(settings=settings, repo=repo)


def _merge_next_ready_pull_request(*, settings: ServerSettings, repo: str) -> dict[str, object]:
    """Merge the next ready PR, preferring capability-update work when present."""

    mode = getattr(settings, "loop_mode", "build")
    if mode == "review":
        # Review mode priority:
        # - review-actions update issues block new merges
        # - then review-consumption (Step 1)
        # - then development/review queue items
        review_merged = _try_merge_next_ready_review_update_pull_request(
            settings=settings,
            repo=repo,
        )
        if review_merged is not None:
            return review_merged
        intake_merged = _try_merge_next_ready_review_consumption_pull_request(
            settings=settings,
            repo=repo,
        )
        if intake_merged is not None:
            return intake_merged
        return _merge_next_ready_development_pull_request(settings=settings, repo=repo)

    # Build mode priority aligns with loop stage determination: capability update issues
    # block new dev merges.
    cap_merged = _try_merge_next_ready_capability_pull_request(settings=settings, repo=repo)
    if cap_merged is not None:
        return cap_merged
    gap_merged = _try_merge_next_ready_gap_analysis_pull_request(settings=settings, repo=repo)
    if gap_merged is not None:
        return gap_merged
    return _merge_next_ready_development_pull_request(settings=settings, repo=repo)


def _try_merge_next_ready_labeled_issue_pull_request(
    *,
    settings: ServerSettings,
    repo: str,
    label_name: str,
    issue_kind_for_summary: str,
) -> dict[str, object] | None:
    """Merge a ready PR linked to an open issue with a specific label, then close the issue."""

    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail="ORCHESTRATOR_GITHUB_TOKEN is required to merge pull requests",
        )

    branch = _get_default_branch(settings, repository=repo)

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    issue_nums: list[int] = []
    for it in raw_issues:
        if not isinstance(it, dict):
            continue
        if "pull_request" in it:
            continue
        num = it.get("number")
        if isinstance(num, int) and _issue_has_label(it, label_name=label_name):
            issue_nums.append(num)

    if not issue_nums:
        return None

    pr_review_request_cache: dict[int, bool] = {}
    selected_issue_num: int | None = None
    selected_pr_data: dict[str, Any] | None = None

    for issue_num in sorted(set(issue_nums)):
        timeline = _list_issue_timeline_raw(settings, repository=repo, issue_number=issue_num)
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)
        for pr_num in sorted(pr_nums):
            pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_num)
            if pr_data.get("state") != "open":
                continue

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=repo,
                        pr_number=pr_num,
                    )
                    pr_review_request_cache[pr_num] = cached_rr
                review_requested = cached_rr

            if not _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                continue

            selected_issue_num = issue_num
            selected_pr_data = pr_data
            break
        if selected_pr_data is not None:
            break

    if selected_issue_num is None or selected_pr_data is None:
        return None

    pr_number = selected_pr_data.get("number")
    if not isinstance(pr_number, int):
        raise HTTPException(status_code=502, detail="Unexpected pull request response (number)")

    # Safety gate: never flip draft->ready or merge while a PR is WIP.
    pr_title = selected_pr_data.get("title")
    if isinstance(pr_title, str) and _pull_request_title_is_wip(pr_title):
        raise HTTPException(
            status_code=409,
            detail=f"Pull request #{pr_number} is still WIP; refusing to mark ready or merge.",
        )

    # Draft PRs cannot be merged; best-effort flip to ready-for-review.
    ready_for_review_error: str | None = None
    if selected_pr_data.get("draft") is True:
        pr_node_id = selected_pr_data.get("node_id")
        graphql_url = _graphql_api_url(settings)
        if not isinstance(pr_node_id, str) or not pr_node_id.strip():
            ready_for_review_error = (
                "Pull request is draft but is missing node_id; cannot mark ready"
            )
        else:
            mutation = (
                "mutation($pullRequestId: ID!) {"
                "  markPullRequestReadyForReview(input: { pullRequestId: $pullRequestId }) {"
                "    pullRequest { id isDraft }"
                "  }"
                "}"
            )
            try:
                payload = _github_graphql_post(
                    settings,
                    query=mutation,
                    variables={"pullRequestId": pr_node_id},
                )
                gql_errors = _graphql_errors_as_message(payload)
                if gql_errors:
                    ready_for_review_error = (
                        f"markPullRequestReadyForReview refused for {graphql_url}: {gql_errors}"
                    )
            except HTTPException as e:
                ready_for_review_error = str(e.detail)

        selected_pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_number)
        if selected_pr_data.get("draft") is True:
            detail = f"Pull request #{pr_number} is still a draft; cannot merge."
            if ready_for_review_error:
                detail = f"{detail} {ready_for_review_error}"
            raise HTTPException(status_code=409, detail=detail)

    # Best-effort approve.
    approved = False
    approval_error: str | None = None
    try:
        _github_post_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/reviews"),
            payload={
                "event": "APPROVE",
                "body": "Approved by orchestrator automation.",
            },
        )
        approved = True
    except HTTPException as e:
        approval_error = str(e.detail)

    merge_url = _repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/merge")
    status, body = _github_put_json(
        settings,
        url=merge_url,
        payload={"merge_method": "squash"},
    )
    if status not in {200, 201}:
        raise HTTPException(status_code=409, detail=f"Merge refused (HTTP {status}): {body}")

    merged = False
    merge_sha: str | None = None
    if isinstance(body, dict):
        merged = bool(body.get("merged"))
        raw_sha = body.get("sha")
        merge_sha = raw_sha if isinstance(raw_sha, str) else None
    if not merged:
        raise HTTPException(status_code=409, detail="Merge did not complete (merged=false)")

    # Best-effort: delete head branch when safe (same-repo only).
    branch_deleted = False
    try:
        head = selected_pr_data.get("head")
        head_ref: str | None = None
        head_repo: str | None = None
        if isinstance(head, dict):
            head_ref = head.get("ref")
            repo_obj = head.get("repo")
            if isinstance(repo_obj, dict):
                head_repo = repo_obj.get("full_name")
        if (
            isinstance(head_ref, str)
            and head_ref.strip()
            and head_ref not in {"main", "master"}
            and head_repo == repo
        ):
            del_url = _repo_api_url(settings, repository=repo, path=f"git/refs/heads/{head_ref}")
            status_del, _body_del = _github_delete_json(settings, url=del_url)
            branch_deleted = status_del in {200, 204, 404}
    except Exception:
        branch_deleted = False

    # Close issue (best-effort).
    issue_closed = False
    issue_close_error: str | None = None
    try:
        _github_patch_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"issues/{selected_issue_num}"),
            payload={"state": "closed"},
        )
        issue_closed = True
    except HTTPException as e:
        issue_close_error = str(e.detail)

    summary = f"Merged PR #{pr_number}; closed {issue_kind_for_summary} issue #{selected_issue_num}"
    if issue_close_error:
        summary = f"{summary} (warning: failed to close issue: {issue_close_error})"

    # Return a superset of the dev merge schema; UI treats many fields as optional.
    return {
        "repo": repo,
        "branch": branch,
        "merged": True,
        "mergeCommitSha": merge_sha,
        "queuePath": None,
        "completePath": None,
        "developmentIssueNumber": None,
        "pullNumber": pr_number,
        "approved": approved,
        "approvalError": approval_error,
        "headBranchDeleted": branch_deleted,
        # Reuse existing schema fields for UI linkage.
        "capabilityIssueNumber": int(selected_issue_num),
        "capabilityIssueCreated": False,
        "capabilityIssueUrl": _make_github_issue_url(repo, int(selected_issue_num)),
        "capabilityIssueAssigned": [],
        "capabilityIssueClosed": issue_closed,
        "summary": summary,
    }


def _try_merge_next_ready_review_update_pull_request(
    *, settings: ServerSettings, repo: str
) -> dict[str, object] | None:
    return _try_merge_next_ready_labeled_issue_pull_request(
        settings=settings,
        repo=repo,
        label_name=LABEL_UPDATE_REVIEW,
        issue_kind_for_summary="review update",
    )


def _try_merge_next_ready_gap_analysis_pull_request(
    *, settings: ServerSettings, repo: str
) -> dict[str, object] | None:
    """Attempt to merge a ready PR linked to an open gap-analysis issue.

    Step A is modeled as a single stage, but gap analysis is often executed via a PR.
    When that PR is ready (non-WIP + review requested, no conflicts), we can merge it
    deterministically.

    Returns:
        A merge result dict if a gap-analysis PR was found and merged, else None.
    """

    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail="ORCHESTRATOR_GITHUB_TOKEN is required to merge pull requests",
        )

    branch = _get_default_branch(settings, repository=repo)

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    gap_issue_nums: list[int] = []
    for it in raw_issues:
        if not isinstance(it, dict):
            continue
        if "pull_request" in it:
            continue
        num = it.get("number")
        title = it.get("title")
        if isinstance(num, int) and isinstance(title, str) and _is_gap_analysis_issue_title(title):
            gap_issue_nums.append(num)

    if not gap_issue_nums:
        return None

    pr_review_request_cache: dict[int, bool] = {}
    selected_issue_num: int | None = None
    selected_pr_data: dict[str, Any] | None = None
    selected_review_requested = False

    for issue_num in sorted(set(gap_issue_nums)):
        timeline = _list_issue_timeline_raw(settings, repository=repo, issue_number=issue_num)
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)
        for pr_num in sorted(pr_nums):
            pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_num)
            if pr_data.get("state") != "open":
                continue

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=repo,
                        pr_number=pr_num,
                    )
                    pr_review_request_cache[pr_num] = cached_rr
                review_requested = cached_rr

            if not _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                continue

            selected_issue_num = issue_num
            selected_pr_data = pr_data
            selected_review_requested = bool(review_requested)
            break
        if selected_pr_data is not None:
            break

    if selected_issue_num is None or selected_pr_data is None:
        return None

    pr_number = selected_pr_data.get("number")
    if not isinstance(pr_number, int):
        raise HTTPException(status_code=502, detail="Unexpected pull request response (number)")

    # Safety gate: never flip draft->ready or merge while a PR is WIP or before review is requested.
    pr_title = selected_pr_data.get("title")
    if isinstance(pr_title, str) and _pull_request_title_is_wip(pr_title):
        raise HTTPException(
            status_code=409,
            detail=f"Pull request #{pr_number} is still WIP; refusing to mark ready or merge.",
        )
    if not selected_review_requested:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Pull request #{pr_number} has no review-request signal; refusing to mark ready "
                "or merge."
            ),
        )

    # Draft PRs cannot be merged; best-effort flip to ready-for-review.
    ready_for_review_error: str | None = None
    if selected_pr_data.get("draft") is True:
        pr_node_id = selected_pr_data.get("node_id")
        graphql_url = _graphql_api_url(settings)
        if not isinstance(pr_node_id, str) or not pr_node_id.strip():
            ready_for_review_error = (
                "Pull request is draft but is missing node_id; cannot mark ready"
            )
        else:
            mutation = (
                "mutation($pullRequestId: ID!) {"
                "  markPullRequestReadyForReview(input: { pullRequestId: $pullRequestId }) {"
                "    pullRequest { id isDraft }"
                "  }"
                "}"
            )
            try:
                payload = _github_graphql_post(
                    settings,
                    query=mutation,
                    variables={"pullRequestId": pr_node_id},
                )
                gql_errors = _graphql_errors_as_message(payload)
                if gql_errors:
                    ready_for_review_error = (
                        f"markPullRequestReadyForReview refused for {graphql_url}: {gql_errors}"
                    )
            except HTTPException as e:
                ready_for_review_error = str(e.detail)

        selected_pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_number)
        if selected_pr_data.get("draft") is True:
            detail = f"Pull request #{pr_number} is still a draft; cannot merge."
            if ready_for_review_error:
                detail = f"{detail} {ready_for_review_error}"
            raise HTTPException(status_code=409, detail=detail)

    # Best-effort approve.
    approved = False
    approval_error: str | None = None
    try:
        _github_post_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/reviews"),
            payload={
                "event": "APPROVE",
                "body": "Approved by orchestrator automation.",
            },
        )
        approved = True
    except HTTPException as e:
        approval_error = str(e.detail)

    merge_url = _repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/merge")
    status, body = _github_put_json(
        settings,
        url=merge_url,
        payload={"merge_method": "squash"},
    )
    if status not in {200, 201}:
        raise HTTPException(status_code=409, detail=f"Merge refused (HTTP {status}): {body}")

    merged = False
    merge_sha: str | None = None
    if isinstance(body, dict):
        merged = bool(body.get("merged"))
        raw_sha = body.get("sha")
        merge_sha = raw_sha if isinstance(raw_sha, str) else None
    if not merged:
        raise HTTPException(status_code=409, detail="Merge did not complete (merged=false)")

    # Best-effort: delete head branch when safe (same-repo only).
    branch_deleted = False
    try:
        head = selected_pr_data.get("head")
        head_ref: str | None = None
        head_repo: str | None = None
        if isinstance(head, dict):
            head_ref = head.get("ref")
            repo_obj = head.get("repo")
            if isinstance(repo_obj, dict):
                head_repo = repo_obj.get("full_name")
        if (
            isinstance(head_ref, str)
            and head_ref.strip()
            and head_ref not in {"main", "master"}
            and head_repo == repo
        ):
            del_url = _repo_api_url(settings, repository=repo, path=f"git/refs/heads/{head_ref}")
            status_del, _body_del = _github_delete_json(settings, url=del_url)
            branch_deleted = status_del in {200, 204, 404}
    except Exception:
        branch_deleted = False

    # Close the gap-analysis issue (best-effort).
    issue_closed = False
    issue_close_error: str | None = None
    try:
        _github_patch_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"issues/{selected_issue_num}"),
            payload={"state": "closed"},
        )
        issue_closed = True
    except HTTPException as e:
        issue_close_error = str(e.detail)

    summary = f"Merged PR #{pr_number}; closed gap analysis issue #{selected_issue_num}"
    if issue_close_error:
        summary = f"{summary} (warning: failed to close issue: {issue_close_error})"

    # Return a superset of the dev merge schema; UI treats many fields as optional.
    return {
        "repo": repo,
        "branch": branch,
        "merged": True,
        "mergeCommitSha": merge_sha,
        "queuePath": None,
        "completePath": None,
        "developmentIssueNumber": None,
        "pullNumber": pr_number,
        "approved": approved,
        "approvalError": approval_error,
        "headBranchDeleted": branch_deleted,
        # Reuse existing schema fields for UI linkage.
        "capabilityIssueNumber": int(selected_issue_num),
        "capabilityIssueCreated": False,
        "capabilityIssueUrl": _make_github_issue_url(repo, int(selected_issue_num)),
        "capabilityIssueAssigned": [],
        "capabilityIssueClosed": issue_closed,
        "summary": summary,
    }


def _try_merge_next_ready_review_consumption_pull_request(
    *, settings: ServerSettings, repo: str
) -> dict[str, object] | None:
    """Attempt to merge a ready PR linked to an open review-consumption issue.

    Review consumption is modeled like gap analysis: it is an issue-driven cognitive step that
    typically lands as a PR adding queue artefacts.
    """

    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail="ORCHESTRATOR_GITHUB_TOKEN is required to merge pull requests",
        )

    branch = _get_default_branch(settings, repository=repo)

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    issue_nums: list[int] = []
    for it in raw_issues:
        if not isinstance(it, dict):
            continue
        if "pull_request" in it:
            continue
        num = it.get("number")
        if isinstance(num, int) and _issue_has_label(it, label_name=LABEL_REVIEW_CONSUMPTION):
            issue_nums.append(num)

    if not issue_nums:
        return None

    pr_review_request_cache: dict[int, bool] = {}
    selected_issue_num: int | None = None
    selected_pr_data: dict[str, Any] | None = None
    selected_review_requested = False

    for issue_num in sorted(set(issue_nums)):
        timeline = _list_issue_timeline_raw(settings, repository=repo, issue_number=issue_num)
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)
        for pr_num in sorted(pr_nums):
            pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_num)
            if pr_data.get("state") != "open":
                continue

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=repo,
                        pr_number=pr_num,
                    )
                    pr_review_request_cache[pr_num] = cached_rr
                review_requested = cached_rr

            if not _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                continue

            selected_issue_num = issue_num
            selected_pr_data = pr_data
            selected_review_requested = bool(review_requested)
            break
        if selected_pr_data is not None:
            break

    if selected_issue_num is None or selected_pr_data is None:
        return None

    pr_number = selected_pr_data.get("number")
    if not isinstance(pr_number, int):
        raise HTTPException(status_code=502, detail="Unexpected pull request response (number)")

    pr_title = selected_pr_data.get("title")
    if isinstance(pr_title, str) and _pull_request_title_is_wip(pr_title):
        raise HTTPException(
            status_code=409,
            detail=f"Pull request #{pr_number} is still WIP; refusing to mark ready or merge.",
        )
    if not selected_review_requested:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Pull request #{pr_number} has no review-request signal; refusing to mark ready "
                "or merge."
            ),
        )

    # Draft PRs cannot be merged; best-effort flip to ready-for-review.
    ready_for_review_error: str | None = None
    if selected_pr_data.get("draft") is True:
        pr_node_id = selected_pr_data.get("node_id")
        graphql_url = _graphql_api_url(settings)
        if not isinstance(pr_node_id, str) or not pr_node_id.strip():
            ready_for_review_error = (
                "Pull request is draft but is missing node_id; cannot mark ready"
            )
        else:
            mutation = (
                "mutation($pullRequestId: ID!) {"
                "  markPullRequestReadyForReview(input: { pullRequestId: $pullRequestId }) {"
                "    pullRequest { id isDraft }"
                "  }"
                "}"
            )
            try:
                payload = _github_graphql_post(
                    settings,
                    query=mutation,
                    variables={"pullRequestId": pr_node_id},
                )
                gql_errors = _graphql_errors_as_message(payload)
                if gql_errors:
                    ready_for_review_error = (
                        f"markPullRequestReadyForReview refused for {graphql_url}: {gql_errors}"
                    )
            except HTTPException as e:
                ready_for_review_error = str(e.detail)

        selected_pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_number)
        if selected_pr_data.get("draft") is True:
            detail = f"Pull request #{pr_number} is still a draft; cannot merge."
            if ready_for_review_error:
                detail = f"{detail} {ready_for_review_error}"
            raise HTTPException(status_code=409, detail=detail)

    approved = False
    approval_error: str | None = None
    try:
        _github_post_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/reviews"),
            payload={
                "event": "APPROVE",
                "body": "Approved by orchestrator automation.",
            },
        )
        approved = True
    except HTTPException as e:
        approval_error = str(e.detail)

    merge_url = _repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/merge")
    status, body = _github_put_json(
        settings,
        url=merge_url,
        payload={"merge_method": "squash"},
    )
    if status not in {200, 201}:
        raise HTTPException(status_code=409, detail=f"Merge refused (HTTP {status}): {body}")

    merged = False
    merge_sha: str | None = None
    if isinstance(body, dict):
        merged = bool(body.get("merged"))
        raw_sha = body.get("sha")
        merge_sha = raw_sha if isinstance(raw_sha, str) else None
    if not merged:
        raise HTTPException(status_code=409, detail="Merge did not complete (merged=false)")

    branch_deleted = False
    try:
        head = selected_pr_data.get("head")
        head_ref: str | None = None
        head_repo: str | None = None
        if isinstance(head, dict):
            head_ref = head.get("ref")
            repo_obj = head.get("repo")
            if isinstance(repo_obj, dict):
                head_repo = repo_obj.get("full_name")
        if (
            isinstance(head_ref, str)
            and head_ref.strip()
            and head_ref not in {"main", "master"}
            and head_repo == repo
        ):
            del_url = _repo_api_url(settings, repository=repo, path=f"git/refs/heads/{head_ref}")
            status_del, _body_del = _github_delete_json(settings, url=del_url)
            branch_deleted = status_del in {200, 204, 404}
    except Exception:
        branch_deleted = False

    issue_closed = False
    issue_close_error: str | None = None
    try:
        _github_patch_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"issues/{selected_issue_num}"),
            payload={"state": "closed"},
        )
        issue_closed = True
    except HTTPException as e:
        issue_close_error = str(e.detail)

    summary = f"Merged PR #{pr_number}; closed review consumption issue #{selected_issue_num}"
    if issue_close_error:
        summary = f"{summary} (warning: failed to close issue: {issue_close_error})"

    return {
        "repo": repo,
        "branch": branch,
        "merged": True,
        "mergeCommitSha": merge_sha,
        "queuePath": None,
        "completePath": None,
        "developmentIssueNumber": None,
        "pullNumber": pr_number,
        "approved": approved,
        "approvalError": approval_error,
        "headBranchDeleted": branch_deleted,
        # Reuse existing schema fields for UI linkage.
        "capabilityIssueNumber": int(selected_issue_num),
        "capabilityIssueCreated": False,
        "capabilityIssueUrl": _make_github_issue_url(repo, int(selected_issue_num)),
        "capabilityIssueAssigned": [],
        "capabilityIssueClosed": issue_closed,
        "summary": summary,
    }


def _try_merge_next_ready_capability_pull_request(
    *, settings: ServerSettings, repo: str
) -> dict[str, object] | None:
    """Attempt to merge a ready PR linked to an open 'Update Capability' issue.

    Returns:
        A merge result dict if a capability PR was found and merged, else None.
    """

    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail="ORCHESTRATOR_GITHUB_TOKEN is required to merge pull requests",
        )

    branch = _get_default_branch(settings, repository=repo)

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    cap_issue_nums: list[int] = []
    for it in raw_issues:
        if not isinstance(it, dict):
            continue
        if "pull_request" in it:
            continue
        num = it.get("number")
        if isinstance(num, int) and _issue_has_label(it, label_name=LABEL_UPDATE_CAPABILITY):
            cap_issue_nums.append(num)

    if not cap_issue_nums:
        return None

    pr_review_request_cache: dict[int, bool] = {}
    selected_issue_num: int | None = None
    selected_pr_data: dict[str, Any] | None = None

    for issue_num in sorted(set(cap_issue_nums)):
        timeline = _list_issue_timeline_raw(settings, repository=repo, issue_number=issue_num)
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)
        for pr_num in sorted(pr_nums):
            pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_num)
            if pr_data.get("state") != "open":
                continue

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=repo,
                        pr_number=pr_num,
                    )
                    pr_review_request_cache[pr_num] = cached_rr
                review_requested = cached_rr

            if not _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                continue

            selected_issue_num = issue_num
            selected_pr_data = pr_data
            break
        if selected_pr_data is not None:
            break

    if selected_issue_num is None or selected_pr_data is None:
        # Capability issues exist, but none are merge-ready.
        return None

    pr_number = selected_pr_data.get("number")
    if not isinstance(pr_number, int):
        raise HTTPException(status_code=502, detail="Unexpected pull request response (number)")

    # Safety gate: never flip draft->ready or merge while a PR is WIP or before review is requested.
    pr_title = selected_pr_data.get("title")
    if isinstance(pr_title, str) and _pull_request_title_is_wip(pr_title):
        raise HTTPException(
            status_code=409,
            detail=f"Pull request #{pr_number} is still WIP; refusing to mark ready or merge.",
        )
    if not review_requested:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Pull request #{pr_number} has no review-request signal; refusing to mark ready "
                "or merge."
            ),
        )

    # Draft PRs cannot be merged; best-effort flip to ready-for-review.
    ready_for_review_error: str | None = None
    if selected_pr_data.get("draft") is True:
        pr_node_id = selected_pr_data.get("node_id")
        graphql_url = _graphql_api_url(settings)
        if not isinstance(pr_node_id, str) or not pr_node_id.strip():
            ready_for_review_error = (
                "Pull request is draft but is missing node_id; cannot mark ready"
            )
        else:
            mutation = (
                "mutation($pullRequestId: ID!) {"
                "  markPullRequestReadyForReview(input: { pullRequestId: $pullRequestId }) {"
                "    pullRequest { id isDraft }"
                "  }"
                "}"
            )
            try:
                payload = _github_graphql_post(
                    settings,
                    query=mutation,
                    variables={"pullRequestId": pr_node_id},
                )
                gql_errors = _graphql_errors_as_message(payload)
                if gql_errors:
                    ready_for_review_error = (
                        f"markPullRequestReadyForReview refused for {graphql_url}: {gql_errors}"
                    )
            except HTTPException as e:
                ready_for_review_error = str(e.detail)

        selected_pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_number)
        if selected_pr_data.get("draft") is True:
            detail = f"Pull request #{pr_number} is still a draft; cannot merge."
            if ready_for_review_error:
                detail = f"{detail} {ready_for_review_error}"
            raise HTTPException(status_code=409, detail=detail)

    # Best-effort approve.
    approved = False
    approval_error: str | None = None
    try:
        _github_post_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/reviews"),
            payload={
                "event": "APPROVE",
                "body": "Approved by orchestrator automation.",
            },
        )
        approved = True
    except HTTPException as e:
        approval_error = str(e.detail)

    merge_url = _repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/merge")
    status, body = _github_put_json(settings, url=merge_url, payload={"merge_method": "squash"})
    if status not in {200, 201}:
        raise HTTPException(status_code=409, detail=f"Merge refused (HTTP {status}): {body}")

    merged = False
    merge_sha: str | None = None
    if isinstance(body, dict):
        merged = bool(body.get("merged"))
        raw_sha = body.get("sha")
        merge_sha = raw_sha if isinstance(raw_sha, str) else None
    if not merged:
        raise HTTPException(status_code=409, detail="Merge did not complete (merged=false)")

    # Best-effort: delete head branch when safe (same-repo only).
    branch_deleted = False
    try:
        head = selected_pr_data.get("head")
        head_ref: str | None = None
        head_repo: str | None = None
        if isinstance(head, dict):
            head_ref = head.get("ref")
            repo_obj = head.get("repo")
            if isinstance(repo_obj, dict):
                head_repo = repo_obj.get("full_name")
        if (
            isinstance(head_ref, str)
            and head_ref.strip()
            and head_ref not in {"main", "master"}
            and head_repo == repo
        ):
            del_url = _repo_api_url(settings, repository=repo, path=f"git/refs/heads/{head_ref}")
            status_del, _body_del = _github_delete_json(settings, url=del_url)
            branch_deleted = status_del in {200, 204, 404}
    except Exception:
        branch_deleted = False

    # Close the capability issue (best-effort) now that the capabilities update is merged.
    issue_closed = False
    issue_close_error: str | None = None
    try:
        _github_patch_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"issues/{selected_issue_num}"),
            payload={"state": "closed"},
        )
        issue_closed = True
    except HTTPException as e:
        issue_close_error = str(e.detail)

    summary = f"Merged PR #{pr_number}; closed capability issue #{selected_issue_num}"
    if issue_close_error:
        summary = f"{summary} (warning: failed to close issue: {issue_close_error})"

    # Return a superset of the dev merge schema; UI treats many fields as optional.
    return {
        "repo": repo,
        "branch": branch,
        "merged": True,
        "mergeCommitSha": merge_sha,
        "queuePath": None,
        "completePath": None,
        "developmentIssueNumber": None,
        "pullNumber": pr_number,
        "approved": approved,
        "approvalError": approval_error,
        "headBranchDeleted": branch_deleted,
        "capabilityIssueNumber": int(selected_issue_num),
        "capabilityIssueCreated": False,
        "capabilityIssueUrl": _make_github_issue_url(repo, int(selected_issue_num)),
        "capabilityIssueAssigned": [],
        "capabilityIssueClosed": issue_closed,
        "summary": summary,
    }


def _promote_next_unpromoted_development_queue_item(
    *, settings: ServerSettings, repo: str
) -> dict[str, object]:
    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail="ORCHESTRATOR_GITHUB_TOKEN is required to promote queue items",
        )

    # Promotions must target the repo's mainline branch.
    branch = _get_default_branch(settings, repository=repo)

    pending_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=repo,
        dir_path="planning/issue_queue/pending",
        ref=branch,
    )
    if not pending_paths:
        raise HTTPException(status_code=409, detail="No pending issue-queue files to promote")

    # Preload open issues once; title matching is used to decide promotion status.
    raw_issues = _list_open_issues_raw(settings, repository=repo)
    open_issues_for_matching = [it for it in raw_issues if isinstance(it, dict)]

    # Select next unpromoted work item in stable order.
    mode = getattr(settings, "loop_mode", "build")
    promotable_categories = {"development"} if mode != "review" else {"development", "review"}
    candidates: list[str] = []
    for p in sorted(pending_paths):
        filename = _queue_filename(p)
        if _queue_file_is_excluded_for_loop_mode(filename=filename, loop_mode=mode):
            continue
        if _queue_category_for_filename(filename) not in promotable_categories:
            continue
        candidates.append(p)

    if not candidates:
        detail = "No promotable development queue files found"
        if mode == "review":
            detail = "No promotable review/development queue files found"
        raise HTTPException(status_code=409, detail=detail)

    selected_path: str | None = None
    selected_raw: str | None = None
    selected_sha: str | None = None
    selected_title_norm: str | None = None

    for pending_path in candidates:
        raw, sha = _get_repo_text_file(
            settings,
            repository=repo,
            path=pending_path,
            ref=branch,
        )
        title_norm = _first_markdown_line_as_title(raw)
        issue_num = _best_match_issue_number(title_norm, open_issues_for_matching)
        if issue_num is None:
            selected_path = pending_path
            selected_raw = raw
            selected_sha = sha
            selected_title_norm = title_norm
            break

    if selected_path is None or selected_raw is None or selected_sha is None:
        raise HTTPException(
            status_code=409,
            detail="No unpromoted development queue files found (all match open issues)",
        )

    queue_id = _queue_filename(selected_path)
    issue_title, issue_body = _parse_queue_file_for_issue(queue_id=queue_id, raw=selected_raw)

    existing_issue_num = _search_issue_number_by_queue_marker(
        settings,
        repository=repo,
        queue_id=queue_id,
    )
    created = False
    if existing_issue_num is None:
        _ensure_repo_label_exists(settings, repository=repo, label_name=LABEL_DEVELOPMENT)
        issue = _github_post_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path="issues"),
            payload={"title": issue_title, "body": issue_body, "labels": [LABEL_DEVELOPMENT]},
        )
        issue_num = issue.get("number")
        if not isinstance(issue_num, int):
            raise HTTPException(status_code=502, detail="Unexpected GitHub create issue response")
        existing_issue_num = issue_num
        created = True

    assigned = _assign_issue_to_copilot(
        settings,
        repository=repo,
        issue_number=existing_issue_num,
        target_repo=repo,
        base_branch=branch,
        instructions="",
    )

    processed_path = f"planning/issue_queue/processed/{queue_id}"
    _ensure_repo_file_present_in_processed(
        settings,
        repository=repo,
        processed_path=processed_path,
        content_text=selected_raw,
        branch=branch,
        message=f"Move {queue_id} to issue_queue/processed",
    )
    _delete_repo_file_if_present(
        settings,
        repository=repo,
        path=selected_path,
        sha=selected_sha,
        branch=branch,
        message=f"Remove {queue_id} from issue_queue/pending (promoted)",
    )

    issue_url = _make_github_issue_url(repo, existing_issue_num)
    return {
        "repo": repo,
        "branch": branch,
        "queuePath": selected_path,
        "processedPath": processed_path,
        "issueNumber": existing_issue_num,
        "issueUrl": issue_url,
        "created": created,
        "assigned": assigned,
        "normalizedTitle": selected_title_norm,
        "summary": f"Promoted {queue_id} to issue #{existing_issue_num}",
    }


def _promote_next_unpromoted_capability_queue_item(
    *, settings: ServerSettings, repo: str
) -> dict[str, object]:
    """Step E (legacy) action: promote one pending *capability* queue file.

    This mirrors `_promote_next_unpromoted_development_queue_item`, but selects queue files
    categorized as `capability` (e.g., `system-*`, `capability-*`, `capabilities-*`).

    Note: the primary capability-update loop (E/F/G) is issue-driven via the
    `Update Capability` label; this function exists for backwards compatibility
    with queue-artefact-based capability updates.
    """

    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail="ORCHESTRATOR_GITHUB_TOKEN is required to promote queue items",
        )

    branch = _get_default_branch(settings, repository=repo)

    pending_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=repo,
        dir_path="planning/issue_queue/pending",
        ref=branch,
    )
    if not pending_paths:
        raise HTTPException(status_code=409, detail="No pending issue-queue files to promote")

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    open_issues_for_matching = [it for it in raw_issues if isinstance(it, dict)]

    # Select next unpromoted *capability* item in stable order.
    selected_path: str | None = None
    selected_sha: str | None = None
    selected_raw: str | None = None
    selected_title_norm: str | None = None
    selected_title: str | None = None
    for p in sorted(pending_paths):
        filename = _queue_filename(p)
        if _queue_category_for_filename(filename) != "capability":
            continue

        content, sha = _get_repo_text_file(settings, repository=repo, path=p, ref=branch)
        title_norm = _first_markdown_line_as_title(content)
        if not title_norm:
            continue

        issue_num = _best_match_issue_number(title_norm, open_issues_for_matching)
        if issue_num is not None:
            # Already promoted (has an open issue match).
            continue

        title, _body = _parse_queue_file_for_issue(queue_id=filename, raw=content)
        selected_path = p
        selected_sha = sha
        selected_raw = content
        selected_title_norm = title_norm
        selected_title = title
        break

    if (
        selected_path is None
        or selected_sha is None
        or selected_raw is None
        or selected_title is None
    ):
        raise HTTPException(status_code=409, detail="No unpromoted capability queue items found")

    queue_id = _queue_filename(selected_path)
    issue_title, issue_body = _parse_queue_file_for_issue(queue_id=queue_id, raw=selected_raw)

    # Idempotency: if we have a queue marker match, reuse the existing issue.
    existing_issue_num = _search_issue_number_by_queue_marker(
        settings,
        repository=repo,
        queue_id=queue_id,
    )
    created = False
    if existing_issue_num is None:
        _ensure_repo_label_exists(settings, repository=repo, label_name=LABEL_UPDATE_CAPABILITY)
        issue = _github_post_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path="issues"),
            payload={
                "title": issue_title,
                "body": issue_body,
                "labels": [LABEL_UPDATE_CAPABILITY],
            },
        )
        issue_num = issue.get("number")
        if not isinstance(issue_num, int):
            raise HTTPException(status_code=502, detail="Unexpected GitHub create issue response")
        existing_issue_num = issue_num
        created = True

    assigned = _assign_issue_to_copilot(
        settings,
        repository=repo,
        issue_number=existing_issue_num,
        target_repo=repo,
        base_branch=branch,
        instructions="",
    )

    processed_path = f"planning/issue_queue/processed/{queue_id}"
    _ensure_repo_file_present_in_processed(
        settings,
        repository=repo,
        processed_path=processed_path,
        content_text=selected_raw,
        branch=branch,
        message=f"Move {queue_id} to issue_queue/processed",
    )
    _delete_repo_file_if_present(
        settings,
        repository=repo,
        path=selected_path,
        sha=selected_sha,
        branch=branch,
        message=f"Remove {queue_id} from issue_queue/pending (promoted)",
    )

    issue_url = _make_github_issue_url(repo, existing_issue_num)
    return {
        "repo": repo,
        "branch": branch,
        "queuePath": selected_path,
        "processedPath": processed_path,
        "issueNumber": existing_issue_num,
        "issueUrl": issue_url,
        "created": created,
        "assigned": assigned,
        "normalizedTitle": selected_title_norm,
        "summary": f"Promoted {queue_id} to issue #{existing_issue_num}",
    }


def _extract_source_pr_number_from_capability_issue(
    *, repository: str, issue_title: str, issue_body: str
) -> int | None:
    """Extract the original (development) PR number that triggered a capability update issue.

    We prefer the embedded marker inserted by the orchestrator for idempotency:

        <!-- orchestrator:capability-update-from-pr owner/repo#123 -->

    and fall back to the human-readable title/body for backwards compatibility.
    """

    repo_norm = repository.strip().strip("/").lower()

    # Primary: marker in the body.
    match = _CAPABILITY_ISSUE_BODY_SOURCE_PR_RE.search(issue_body or "")
    if match:
        marker_repo = (match.group(1) or "").strip().strip("/").lower()
        raw_num = (match.group(2) or "").strip()
        if marker_repo == repo_norm and raw_num.isdigit():
            return int(raw_num)

    # Secondary: title convention.
    match = _CAPABILITY_ISSUE_TITLE_SOURCE_PR_RE.search(issue_title or "")
    if match:
        raw_num = (match.group(1) or "").strip()
        if raw_num.isdigit():
            return int(raw_num)

    # Tertiary: body summary block.
    match = re.search(r"\bPR\s+number:\s*(\d+)\b", issue_body or "", flags=re.IGNORECASE)
    if match:
        raw_num = (match.group(1) or "").strip()
        if raw_num.isdigit():
            return int(raw_num)

    return None


def _render_capability_update_issue_body(
    *,
    repo: str,
    pr_number: int,
    pr_title: str,
    pr_body: str,
    discussion_markdown: str,
) -> str:
    marker = f"<!-- {_CAPABILITY_UPDATE_FROM_PR_MARKER_PREFIX} {repo}#{pr_number} -->"
    pr_description = pr_body.strip() or "(no PR description)"
    discussion = discussion_markdown.strip() or "(no PR comments)"
    return (
        f"Update system capabilities based on merged PR #{pr_number}\n\n"
        "This issue is automatically created after a pull request has been merged.\n\n"
        "The goal is to update the system capabilities document so that it accurately reflects "
        "what the system can do after this change.\n\n"
        "Target file:\n- /planning/state/system_capabilities.md\n\n"
        "Instructions:\n"
        "- Review the merged pull request and its discussion.\n"
        "- Identify any new, changed, or removed capabilities introduced by this PR.\n"
        "- Update the system capabilities document accordingly.\n"
        "- Do not speculate or describe future work.\n"
        "- If a capability is partial or constrained, describe it as such.\n"
        "- If no update is required, explicitly state why and leave the document unchanged.\n\n"
        f"Merged PR summary:\n- PR number: {pr_number}\n- PR title: {pr_title}\n\n"
        "PR description:\n\n"
        f"\n\n{pr_description}\n\n"
        "PR comments and discussion (chronological):\n\n"
        f"\n\n{discussion}\n\n---\n\n{marker}\n"
    )


def _merge_next_ready_development_pull_request(
    *, settings: ServerSettings, repo: str
) -> dict[str, object]:
    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail="ORCHESTRATOR_GITHUB_TOKEN is required to merge pull requests",
        )

    branch = _get_default_branch(settings, repository=repo)

    # Discover the next ready PR deterministically from inflight development queue items.
    raw_issues = _list_open_issues_raw(settings, repository=repo)
    open_issues_for_matching = [it for it in raw_issues if isinstance(it, dict)]

    pending_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=repo,
        dir_path="planning/issue_queue/pending",
        ref=branch,
    )
    processed_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=repo,
        dir_path="planning/issue_queue/processed",
        ref=branch,
    )
    inflight_paths = list(pending_paths) + list(processed_paths)

    mode = getattr(settings, "loop_mode", "build")
    mergeable_categories = {"development"} if mode != "review" else {"development", "review"}
    candidates: list[str] = []
    for p in sorted(inflight_paths):
        filename = _queue_filename(p)
        if _queue_file_is_excluded_for_loop_mode(filename=filename, loop_mode=mode):
            continue
        if _queue_category_for_filename(filename) not in mergeable_categories:
            continue
        candidates.append(p)

    selected: dict[str, Any] | None = None
    pr_review_request_cache: dict[int, bool] = {}
    for queue_path in candidates:
        content, queue_sha = _get_repo_text_file(
            settings,
            repository=repo,
            path=queue_path,
            ref=branch,
        )
        title_norm = _first_markdown_line_as_title(content)
        issue_num = _best_match_issue_number(title_norm, open_issues_for_matching)
        if issue_num is None:
            continue

        timeline = _list_issue_timeline_raw(settings, repository=repo, issue_number=issue_num)
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)
        for pr_num in sorted(pr_nums):
            pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_num)
            if pr_data.get("state") != "open":
                continue

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=repo,
                        pr_number=pr_num,
                    )
                    pr_review_request_cache[pr_num] = cached_rr
                review_requested = cached_rr

            if not _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                continue
            selected = {
                "queue_path": queue_path,
                "queue_sha": queue_sha,
                "queue_content": content,
                "queue_id": _queue_filename(queue_path),
                "issue_number": issue_num,
                "pr": pr_data,
                "review_requested": review_requested,
            }
            break
        if selected is not None:
            break

    if selected is None:
        raise HTTPException(status_code=409, detail="No ready development pull requests found")

    pr_data = selected["pr"]
    review_requested = bool(selected.get("review_requested"))
    pr_number = pr_data.get("number")
    if not isinstance(pr_number, int):
        raise HTTPException(status_code=502, detail="Unexpected pull request response (number)")

    # Safety gate: never flip draft->ready or merge while a PR is WIP or before review is requested.
    pr_title = pr_data.get("title")
    if isinstance(pr_title, str) and _pull_request_title_is_wip(pr_title):
        raise HTTPException(
            status_code=409,
            detail=f"Pull request #{pr_number} is still WIP; refusing to mark ready or merge.",
        )
    if not review_requested:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Pull request #{pr_number} has no review-request signal; refusing to mark ready "
                "or merge."
            ),
        )

    # If PR is a draft, try to mark it ready for review.
    # Draft PRs cannot be merged, so we fail early with a clearer 409 if we can't flip it.
    ready_for_review_error: str | None = None
    if pr_data.get("draft") is True:
        # There is no REST API endpoint to convert a draft PR to "ready for review".
        # See: https://github.com/orgs/community/discussions/70061
        # Use GraphQL: markPullRequestReadyForReview
        pr_node_id = pr_data.get("node_id")
        graphql_url = _graphql_api_url(settings)
        if not isinstance(pr_node_id, str) or not pr_node_id.strip():
            ready_for_review_error = (
                "Pull request is draft but is missing node_id; cannot mark ready"
            )
        else:
            mutation = (
                "mutation($pullRequestId: ID!) {"
                "  markPullRequestReadyForReview(input: { pullRequestId: $pullRequestId }) {"
                "    pullRequest { id isDraft }"
                "  }"
                "}"
            )
            try:
                payload = _github_graphql_post(
                    settings,
                    query=mutation,
                    variables={"pullRequestId": pr_node_id},
                )
                gql_errors = _graphql_errors_as_message(payload)
                if gql_errors:
                    ready_for_review_error = (
                        f"markPullRequestReadyForReview refused for {graphql_url}: {gql_errors}"
                    )
            except HTTPException as e:
                ready_for_review_error = str(e.detail)

        pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_number)

        if pr_data.get("draft") is True:
            detail = f"Pull request #{pr_number} is still a draft; cannot merge."
            if ready_for_review_error:
                detail = f"{detail} {ready_for_review_error}"
            raise HTTPException(status_code=409, detail=detail)

    # Best-effort: submit an approval review (may be refused by policy).
    approved = False
    approval_error: str | None = None
    try:
        _github_post_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/reviews"),
            payload={
                "event": "APPROVE",
                "body": "Approved by orchestrator automation.",
            },
        )
        approved = True
    except HTTPException as e:
        approval_error = str(e.detail)

    # Attempt merge (squash by default). GitHub may refuse if checks/approvals aren't met.
    merge_url = _repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/merge")
    status, body = _github_put_json(
        settings,
        url=merge_url,
        payload={"merge_method": "squash"},
    )
    if status not in {200, 201}:
        raise HTTPException(
            status_code=409,
            detail=f"Merge refused (HTTP {status}): {body}",
        )

    merged = False
    merge_sha: str | None = None
    if isinstance(body, dict):
        merged = bool(body.get("merged"))
        raw_sha = body.get("sha")
        merge_sha = raw_sha if isinstance(raw_sha, str) else None
    if not merged:
        raise HTTPException(status_code=409, detail="Merge did not complete (merged=false)")

    # Move the queue file to complete/ to avoid lingering processed artefacts keeping the loop in C.
    queue_id = str(selected["queue_id"])
    source_path = str(selected["queue_path"])
    source_sha = str(selected["queue_sha"])
    source_content = str(selected["queue_content"])
    complete_path = f"planning/issue_queue/complete/{queue_id}"
    _ensure_repo_file_present_in_complete(
        settings,
        repository=repo,
        complete_path=complete_path,
        content_text=source_content,
        branch=branch,
        message=f"Move {queue_id} to issue_queue/complete",
    )
    _delete_repo_file_if_present(
        settings,
        repository=repo,
        path=source_path,
        sha=source_sha,
        branch=branch,
        message=f"Remove {queue_id} from issue_queue (completed)",
    )

    # Best-effort: delete head branch when safe (same-repo only).
    branch_deleted = False
    try:
        head = pr_data.get("head")
        head_ref: str | None = None
        head_repo: str | None = None
        if isinstance(head, dict):
            head_ref = head.get("ref")
            repo_obj = head.get("repo")
            if isinstance(repo_obj, dict):
                head_repo = repo_obj.get("full_name")
        if (
            isinstance(head_ref, str)
            and head_ref.strip()
            and head_ref not in {"main", "master"}
            and head_repo == repo
        ):
            del_url = _repo_api_url(settings, repository=repo, path=f"git/refs/heads/{head_ref}")
            status_del, _body_del = _github_delete_json(settings, url=del_url)
            branch_deleted = status_del in {200, 204, 404}
    except Exception:
        branch_deleted = False

    # Create a follow-up issue and assign it to Copilot.
    pr_title = pr_data.get("title")
    pr_body = pr_data.get("body")
    if not isinstance(pr_title, str):
        pr_title = ""
    if not isinstance(pr_body, str):
        pr_body = ""

    mode = getattr(settings, "loop_mode", "build")

    follow_issue_number: int
    follow_issue_created = False
    follow_issue_label = LABEL_UPDATE_CAPABILITY
    follow_issue_title: str
    follow_issue_body: str

    if mode == "review":
        follow_issue_label = LABEL_UPDATE_REVIEW
        marker = f"{_REVIEW_UPDATE_FROM_PR_MARKER_PREFIX} {repo}#{pr_number}"
        existing = _search_issue_number_by_body_marker(settings, repository=repo, marker=marker)
        if existing is None:
            _ensure_repo_label_exists(settings, repository=repo, label_name=LABEL_UPDATE_REVIEW)
            discussion_md = _get_pull_request_discussion_markdown(
                settings,
                repository=repo,
                pr_number=pr_number,
            )
            follow_issue_title, follow_issue_body = _render_review_actions_update_issue_body(
                settings=settings,
                repo=repo,
                branch=branch,
                pr_number=pr_number,
                pr_title=pr_title,
                pr_body=pr_body,
                discussion_markdown=discussion_md,
                queue_path=source_path,
                queue_content=source_content,
            )
            created_issue = _github_post_json(
                settings,
                url=_repo_api_url(settings, repository=repo, path="issues"),
                payload={
                    "title": follow_issue_title,
                    "body": follow_issue_body,
                    "labels": [LABEL_UPDATE_REVIEW],
                },
            )
            num = created_issue.get("number")
            if not isinstance(num, int):
                raise HTTPException(
                    status_code=502, detail="Unexpected GitHub create issue response"
                )
            follow_issue_number = num
            follow_issue_created = True
        else:
            follow_issue_number = existing
    else:
        marker = f"{_CAPABILITY_UPDATE_FROM_PR_MARKER_PREFIX} {repo}#{pr_number}"
        existing = _search_issue_number_by_body_marker(settings, repository=repo, marker=marker)
        if existing is None:
            _ensure_repo_label_exists(settings, repository=repo, label_name=LABEL_UPDATE_CAPABILITY)
            discussion_md = _get_pull_request_discussion_markdown(
                settings,
                repository=repo,
                pr_number=pr_number,
            )
            follow_issue_body = _render_capability_update_issue_body(
                repo=repo,
                pr_number=pr_number,
                pr_title=pr_title,
                pr_body=pr_body,
                discussion_markdown=discussion_md,
            )
            follow_issue_title = f"Update system capabilities based on merged PR #{pr_number}"
            created_issue = _github_post_json(
                settings,
                url=_repo_api_url(settings, repository=repo, path="issues"),
                payload={
                    "title": follow_issue_title,
                    "body": follow_issue_body,
                    "labels": [LABEL_UPDATE_CAPABILITY],
                },
            )
            num = created_issue.get("number")
            if not isinstance(num, int):
                raise HTTPException(
                    status_code=502, detail="Unexpected GitHub create issue response"
                )
            follow_issue_number = num
            follow_issue_created = True
        else:
            follow_issue_number = existing

    assigned = _assign_issue_to_copilot(
        settings,
        repository=repo,
        issue_number=follow_issue_number,
        target_repo=repo,
        base_branch=branch,
        instructions="",
    )

    return {
        "repo": repo,
        "branch": branch,
        "merged": True,
        "mergeCommitSha": merge_sha,
        "queuePath": source_path,
        "completePath": complete_path,
        "developmentIssueNumber": int(selected["issue_number"]),
        "pullNumber": pr_number,
        "approved": approved,
        "approvalError": approval_error,
        "headBranchDeleted": branch_deleted,
        "capabilityIssueNumber": follow_issue_number,
        "capabilityIssueCreated": follow_issue_created,
        "capabilityIssueUrl": _make_github_issue_url(repo, follow_issue_number),
        "capabilityIssueAssigned": assigned,
        "summary": (
            f"Merged PR #{pr_number}; created {follow_issue_label.lower()} issue #{follow_issue_number}"
            if follow_issue_created
            else f"Merged PR #{pr_number}; ensured {follow_issue_label.lower()} issue #{follow_issue_number}"
        ),
    }
