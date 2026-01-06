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
)

ERR_UNEXPECTED_GITHUB_CREATE_ISSUE_RESPONSE = "Unexpected GitHub create issue response"
ERR_UNEXPECTED_PULL_REQUEST_RESPONSE_NUMBER = "Unexpected pull request response (number)"
ERR_MISSING_GITHUB_TOKEN_FOR_MERGE = "ORCHESTRATOR_GITHUB_TOKEN is required to merge pull requests"
ERR_DRAFT_PR_MISSING_NODE_ID = "Pull request is draft but is missing node_id; cannot mark ready"
ERR_MERGE_DID_NOT_COMPLETE = "Merge did not complete (merged=false)"
APPROVAL_REVIEW_BODY = "Approved by orchestrator automation."
DEVELOPMENT_QUEUE_PENDING_DIR = "planning/issue_queue/pending"

MARK_READY_FOR_REVIEW_MUTATION = (
    "mutation($pullRequestId: ID!) {"
    "  markPullRequestReadyForReview(input: { pullRequestId: $pullRequestId }) {"
    "    pullRequest { id isDraft }"
    "  }"
    "}"
)

# --- Compatibility shims (tests + monkeypatching) ---
#
# Unit tests patch these names on `loop_actions` to prevent real GitHub API calls.
# Implement them as wrapper functions so they remain available even when not used directly.


def _github_get_json(
    settings: ServerSettings, *, url: str, params: dict[str, str] | None = None
) -> dict[str, Any]:
    from github_agent_orchestrator.server.dashboard.github_api import _github_get_json as _impl

    return _impl(settings, url=url, params=params)


def _github_get_list(
    settings: ServerSettings, *, url: str, params: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    from github_agent_orchestrator.server.dashboard.github_api import _github_get_list as _impl

    return _impl(settings, url=url, params=params)



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
        f"open a pr that adds exactly one new file under /{DEVELOPMENT_QUEUE_PENDING_DIR}/",
        f"create one development task in {DEVELOPMENT_QUEUE_PENDING_DIR}/",
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


def _find_open_gap_analysis_issue(raw_issues: list[object]) -> dict[str, Any] | None:
    for it in raw_issues:
        if not isinstance(it, dict):
            continue
        if "pull_request" in it:
            continue
        title = it.get("title")
        if isinstance(title, str) and _is_gap_analysis_issue_title(title):
            return it
    return None


def _issue_is_assigned_to_login(issue: dict[str, Any], *, login: str) -> bool:
    assignees = issue.get("assignees")
    if not isinstance(assignees, list):
        return False
    for a in assignees:
        if isinstance(a, dict) and a.get("login") == login:
            return True
    return False


def _gap_analysis_issue_result_from_existing(
    *, settings: ServerSettings, repo: str, branch: str, issue: dict[str, Any]
) -> dict[str, object] | None:
    num = issue.get("number")
    if not isinstance(num, int):
        return None

    # If an unsafe gap-analysis issue already exists, repair it before assigning.
    # This avoids costly self-referential instructions.
    body = issue.get("body")
    if isinstance(body, str):
        _repair_gap_analysis_issue_body_if_unsafe(
            settings=settings,
            repo=repo,
            issue_number=num,
            branch=branch,
            existing_body=body,
        )

    assigned: list[dict[str, Any]] | list[str] = []
    if not _issue_is_assigned_to_login(issue, login=settings.copilot_assignee):
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


def _ensure_gap_analysis_issue_exists(*, settings: ServerSettings, repo: str) -> dict[str, object]:
    """Ensure there is exactly one open gap analysis issue (best-effort).

    This is used by the server-side auto progression loop when
    ORCHESTRATOR_AUTO_PROMOTE_ENABLED=true.

    The gap analysis task remains "cognitive" (it produces a queue artefact), but this helper
    can automatically open + assign the issue so the overall cycle can keep moving.
    """

    branch = _get_default_branch(settings, repository=repo)

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    existing = _find_open_gap_analysis_issue(raw_issues)
    if existing is not None:
        result = _gap_analysis_issue_result_from_existing(
            settings=settings,
            repo=repo,
            branch=branch,
            issue=existing,
        )
        if result is not None:
            return result

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
        raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_CREATE_ISSUE_RESPONSE)

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


def heal_orphaned_processed_queue_items(request: Request) -> dict[str, object]:
    """Heal orphaned processed queue artefacts.

    This addresses a common "broken loop" scenario:
    - A queue artefact exists under planning/issue_queue/processed/
    - There are no open issues/PRs that match it (so the loop sits in Stage 2b forever)

    Healing is conservative:
    - Only move processed -> complete when we can prove a linked PR was merged.
    - In build mode, ensure the corresponding 'Update Capability' follow-up issue exists.

    This endpoint intentionally performs ONE healing pass per call.
    """

    settings = _settings(request)
    repo = _active_repo(request, settings)
    return _heal_orphaned_processed_queue_items(settings=settings, repo=repo)


def _pull_request_is_merged(pr_data: dict[str, Any]) -> bool:
    merged = pr_data.get("merged")
    if merged is True:
        return True
    merged_at = pr_data.get("merged_at")
    return isinstance(merged_at, str) and bool(merged_at.strip())


def _heal_orphaned_processed_queue_items(
    *, settings: ServerSettings, repo: str
) -> dict[str, object]:
    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail="ORCHESTRATOR_GITHUB_TOKEN is required to heal orphaned processed queue items",
        )

    branch = _get_default_branch(settings, repository=repo)
    mode = getattr(settings, "loop_mode", "build")

    processed_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=repo,
        dir_path="planning/issue_queue/processed",
        ref=branch,
    )
    if not processed_paths:
        raise HTTPException(status_code=409, detail="No processed queue artefacts to heal")

    # Open issues are used for title matching; if none match a processed item, it's a candidate orphan.
    raw_issues = _list_open_issues_raw(settings, repository=repo)
    open_issues_for_matching = [it for it in raw_issues if isinstance(it, dict)]

    healed: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for processed_path in sorted(processed_paths):
        queue_id = _queue_filename(processed_path)
        content, sha = _get_repo_text_file(
            settings,
            repository=repo,
            path=processed_path,
            ref=branch,
        )

        title_norm = _first_markdown_line_as_title(content)
        matched_open_issue = None
        if title_norm:
            matched_open_issue = _best_match_issue_number(title_norm, open_issues_for_matching)

        if isinstance(matched_open_issue, int):
            skipped.append(
                {
                    "queueId": queue_id,
                    "queuePath": processed_path,
                    "reason": "queue artefact still matches an open issue (not orphaned)",
                    "issueNumber": matched_open_issue,
                }
            )
            continue

        # Try to locate the historical issue by the queue marker.
        issue_num = _search_issue_number_by_queue_marker(settings, repository=repo, queue_id=queue_id)
        if not isinstance(issue_num, int):
            skipped.append(
                {
                    "queueId": queue_id,
                    "queuePath": processed_path,
                    "reason": "no issue found containing the queue marker; refusing to auto-heal",
                }
            )
            continue

        try:
            issue_data = _github_get_json(
                settings,
                url=_repo_api_url(settings, repository=repo, path=f"issues/{issue_num}"),
            )
        except HTTPException as e:
            skipped.append(
                {
                    "queueId": queue_id,
                    "queuePath": processed_path,
                    "issueNumber": issue_num,
                    "reason": f"unable to fetch issue #{issue_num} (HTTP {e.status_code}); refusing to auto-heal",
                }
            )
            continue

        issue_state = issue_data.get("state") if isinstance(issue_data, dict) else None
        if issue_state != "closed":
            skipped.append(
                {
                    "queueId": queue_id,
                    "queuePath": processed_path,
                    "issueNumber": issue_num,
                    "reason": "issue containing queue marker is not closed; refusing to mark complete",
                }
            )
            continue

        timeline = _list_issue_timeline_raw(settings, repository=repo, issue_number=issue_num)
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)
        merged_pr_data: dict[str, Any] | None = None
        merged_pr_number: int | None = None
        for pr_num in sorted(pr_nums):
            with suppress(Exception):
                pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_num)
                if _pull_request_is_merged(pr_data):
                    merged_pr_data = pr_data
                    merged_pr_number = int(pr_num)
                    break

        if merged_pr_data is None or merged_pr_number is None:
            skipped.append(
                {
                    "queueId": queue_id,
                    "queuePath": processed_path,
                    "issueNumber": issue_num,
                    "reason": "no merged PR linked from the historical issue; refusing to auto-heal",
                }
            )
            continue

        # Case A: we have proof a linked PR was merged -> mark artefact complete.
        complete_path = f"planning/issue_queue/complete/{queue_id}"
        _ensure_repo_file_present_in_complete(
            settings,
            repository=repo,
            complete_path=complete_path,
            content_text=content,
            branch=branch,
            message=f"Heal orphaned processed artefact: move {queue_id} to issue_queue/complete",
        )
        _delete_repo_file_if_present(
            settings,
            repository=repo,
            path=processed_path,
            sha=sha,
            branch=branch,
            message=f"Heal orphaned processed artefact: remove {queue_id} from issue_queue/processed",
        )

        raw_pr_title = merged_pr_data.get("title")
        raw_pr_body = merged_pr_data.get("body")
        pr_title = raw_pr_title if isinstance(raw_pr_title, str) else ""
        pr_body = raw_pr_body if isinstance(raw_pr_body, str) else ""

        follow_issue_number: int | None = None
        follow_issue_created: bool | None = None
        follow_issue_label: str | None = None
        follow_issue_assigned: list[str] | None = None

        # Ensure the follow-up issue (capability update in build mode, review update in review mode).
        with suppress(Exception):
            follow_issue_number, follow_issue_created, follow_issue_label = (
                _ensure_followup_issue_after_development_merge(
                    settings=settings,
                    repo=repo,
                    branch=branch,
                    loop_mode=mode,
                    pr_number=merged_pr_number,
                    pr_title=pr_title,
                    pr_body=pr_body,
                    queue_path=processed_path,
                    queue_content=content,
                )
            )
            follow_issue_assigned = _assign_issue_to_copilot(
                settings,
                repository=repo,
                issue_number=follow_issue_number,
                target_repo=repo,
                base_branch=branch,
                instructions="",
            )

        healed.append(
            {
                "queueId": queue_id,
                "queuePath": processed_path,
                "completePath": complete_path,
                "historicalIssueNumber": issue_num,
                "mergedPullNumber": merged_pr_number,
                "followupIssueNumber": follow_issue_number,
                "followupIssueCreated": follow_issue_created,
                "followupIssueLabel": follow_issue_label,
                "followupIssueAssigned": follow_issue_assigned,
            }
        )

    if not healed:
        raise HTTPException(
            status_code=409,
            detail=(
                "No orphaned processed queue artefacts could be healed (either still in-flight or "
                "insufficient evidence of merge)"
            ),
        )

    return {
        "repo": repo,
        "branch": branch,
        "mode": mode,
        "healed": healed,
        "skipped": skipped,
        "summary": f"Healed {len(healed)} orphaned processed artefact(s)",
    }


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


def _require_github_token_for_merge(settings: ServerSettings) -> None:
    if not settings.github_token.strip():
        raise HTTPException(status_code=409, detail=ERR_MISSING_GITHUB_TOKEN_FOR_MERGE)


def _issue_numbers_with_label(raw_issues: list[object], *, label_name: str) -> list[int]:
    issue_nums: list[int] = []
    for it in raw_issues:
        if not isinstance(it, dict):
            continue
        if "pull_request" in it:
            continue
        num = it.get("number")
        if isinstance(num, int) and _issue_has_label(it, label_name=label_name):
            issue_nums.append(num)
    return issue_nums


def _gap_analysis_issue_numbers(raw_issues: list[object]) -> list[int]:
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
    return gap_issue_nums


def _open_pull_request_or_none(
    *, settings: ServerSettings, repo: str, pr_number: int
) -> dict[str, Any] | None:
    pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_number)
    return pr_data if pr_data.get("state") == "open" else None


def _review_requested_for_pr_cached(
    *,
    settings: ServerSettings,
    repo: str,
    pr_number: int,
    pr_data: dict[str, Any],
    cache: dict[int, bool],
) -> bool:
    review_requested = _pull_request_has_review_request(pr_data)
    if review_requested:
        return True
    cached_rr = cache.get(pr_number)
    if cached_rr is None:
        cached_rr = _pull_request_has_review_request_history(
            settings,
            repository=repo,
            pr_number=pr_number,
        )
        cache[pr_number] = cached_rr
    return bool(cached_rr)


def _select_first_ready_pr_linked_to_issues(
    *,
    settings: ServerSettings,
    repo: str,
    issue_nums: list[int],
    require_review_requested: bool,
) -> tuple[int, dict[str, Any], bool] | None:
    pr_review_request_cache: dict[int, bool] = {}
    for issue_num in sorted(set(issue_nums)):
        timeline = _list_issue_timeline_raw(settings, repository=repo, issue_number=issue_num)
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)
        for pr_num in sorted(pr_nums):
            pr_data = _open_pull_request_or_none(settings=settings, repo=repo, pr_number=pr_num)
            if pr_data is None:
                continue
            review_requested = _review_requested_for_pr_cached(
                settings=settings,
                repo=repo,
                pr_number=pr_num,
                pr_data=pr_data,
                cache=pr_review_request_cache,
            )
            if require_review_requested and not review_requested:
                continue
            if not _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                continue
            return issue_num, pr_data, bool(review_requested)
    return None


def _pr_number_or_502(pr_data: dict[str, Any]) -> int:
    pr_number = pr_data.get("number")
    if not isinstance(pr_number, int):
        raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_PULL_REQUEST_RESPONSE_NUMBER)
    return pr_number


def _raise_if_pr_wip(*, pr_number: int, pr_data: dict[str, Any]) -> None:
    pr_title = pr_data.get("title")
    if isinstance(pr_title, str) and _pull_request_title_is_wip(pr_title):
        raise HTTPException(
            status_code=409,
            detail=f"Pull request #{pr_number} is still WIP; refusing to mark ready or merge.",
        )


def _require_review_requested_or_409(*, pr_number: int, review_requested: bool) -> None:
    if not review_requested:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Pull request #{pr_number} has no review-request signal; refusing to mark ready "
                "or merge."
            ),
        )


def _try_mark_pull_request_ready_for_review(
    *, settings: ServerSettings, pr_node_id: str
) -> str | None:
    graphql_url = _graphql_api_url(settings)
    mutation = MARK_READY_FOR_REVIEW_MUTATION
    try:
        payload = _github_graphql_post(
            settings,
            query=mutation,
            variables={"pullRequestId": pr_node_id},
        )
    except HTTPException as e:
        return str(e.detail)

    gql_errors = _graphql_errors_as_message(payload)
    if gql_errors:
        return f"markPullRequestReadyForReview refused for {graphql_url}: {gql_errors}"
    return None


def _ensure_pr_not_draft_or_409(
    *, settings: ServerSettings, repo: str, pr_number: int, pr_data: dict[str, Any]
) -> dict[str, Any]:
    if pr_data.get("draft") is not True:
        return pr_data

    ready_for_review_error: str | None = None
    pr_node_id = pr_data.get("node_id")
    if not isinstance(pr_node_id, str) or not pr_node_id.strip():
        ready_for_review_error = ERR_DRAFT_PR_MISSING_NODE_ID
    else:
        ready_for_review_error = _try_mark_pull_request_ready_for_review(
            settings=settings,
            pr_node_id=pr_node_id,
        )

    pr_data = _get_pull_request(settings, repository=repo, pr_number=pr_number)
    if pr_data.get("draft") is True:
        detail = f"Pull request #{pr_number} is still a draft; cannot merge."
        if ready_for_review_error:
            detail = f"{detail} {ready_for_review_error}"
        raise HTTPException(status_code=409, detail=detail)

    return pr_data


def _try_approve_pull_request(
    *,
    settings: ServerSettings,
    repo: str,
    pr_number: int,
) -> tuple[bool, str | None]:
    try:
        _github_post_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/reviews"),
            payload={"event": "APPROVE", "body": APPROVAL_REVIEW_BODY},
        )
        return True, None
    except HTTPException as e:
        return False, str(e.detail)


def _merge_pull_request_squash_or_409(
    *,
    settings: ServerSettings,
    repo: str,
    pr_number: int,
) -> str | None:
    merge_url = _repo_api_url(settings, repository=repo, path=f"pulls/{pr_number}/merge")
    status, body = _github_put_json(settings, url=merge_url, payload={"merge_method": "squash"})
    if status not in {200, 201}:
        raise HTTPException(status_code=409, detail=f"Merge refused (HTTP {status}): {body}")

    if not isinstance(body, dict) or not bool(body.get("merged")):
        raise HTTPException(status_code=409, detail=ERR_MERGE_DID_NOT_COMPLETE)
    raw_sha = body.get("sha")
    return raw_sha if isinstance(raw_sha, str) else None


def _delete_head_branch_best_effort(
    *,
    settings: ServerSettings,
    repo: str,
    pr_data: dict[str, Any],
) -> bool:
    try:
        head = pr_data.get("head")
        if not isinstance(head, dict):
            return False
        head_ref = head.get("ref")
        repo_obj = head.get("repo")
        head_repo = repo_obj.get("full_name") if isinstance(repo_obj, dict) else None

        if not (isinstance(head_ref, str) and head_ref.strip()):
            return False
        if head_ref in {"main", "master"}:
            return False
        if head_repo != repo:
            return False

        del_url = _repo_api_url(settings, repository=repo, path=f"git/refs/heads/{head_ref}")
        status_del, _body_del = _github_delete_json(settings, url=del_url)
        return status_del in {200, 204, 404}
    except Exception:
        return False


def _close_issue_best_effort(
    *,
    settings: ServerSettings,
    repo: str,
    issue_number: int,
) -> tuple[bool, str | None]:
    try:
        _github_patch_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path=f"issues/{issue_number}"),
            payload={"state": "closed"},
        )
        return True, None
    except HTTPException as e:
        return False, str(e.detail)


def _try_merge_next_ready_labeled_issue_pull_request(
    *,
    settings: ServerSettings,
    repo: str,
    label_name: str,
    issue_kind_for_summary: str,
) -> dict[str, object] | None:
    """Merge a ready PR linked to an open issue with a specific label, then close the issue."""

    _require_github_token_for_merge(settings)
    branch = _get_default_branch(settings, repository=repo)

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    issue_nums = _issue_numbers_with_label(raw_issues, label_name=label_name)
    if not issue_nums:
        return None

    selected = _select_first_ready_pr_linked_to_issues(
        settings=settings,
        repo=repo,
        issue_nums=issue_nums,
        require_review_requested=False,
    )
    if selected is None:
        return None

    selected_issue_num, selected_pr_data, _review_requested = selected

    pr_number = _pr_number_or_502(selected_pr_data)
    _raise_if_pr_wip(pr_number=pr_number, pr_data=selected_pr_data)
    selected_pr_data = _ensure_pr_not_draft_or_409(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
        pr_data=selected_pr_data,
    )

    approved, approval_error = _try_approve_pull_request(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
    )
    merge_sha = _merge_pull_request_squash_or_409(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
    )
    branch_deleted = _delete_head_branch_best_effort(settings=settings, repo=repo, pr_data=selected_pr_data)

    issue_closed, issue_close_error = _close_issue_best_effort(
        settings=settings,
        repo=repo,
        issue_number=int(selected_issue_num),
    )

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

    _require_github_token_for_merge(settings)
    branch = _get_default_branch(settings, repository=repo)

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    gap_issue_nums = _gap_analysis_issue_numbers(raw_issues)
    if not gap_issue_nums:
        return None

    selected = _select_first_ready_pr_linked_to_issues(
        settings=settings,
        repo=repo,
        issue_nums=gap_issue_nums,
        require_review_requested=True,
    )
    if selected is None:
        return None

    selected_issue_num, selected_pr_data, review_requested = selected

    pr_number = _pr_number_or_502(selected_pr_data)
    _raise_if_pr_wip(pr_number=pr_number, pr_data=selected_pr_data)
    _require_review_requested_or_409(pr_number=pr_number, review_requested=review_requested)

    selected_pr_data = _ensure_pr_not_draft_or_409(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
        pr_data=selected_pr_data,
    )

    approved, approval_error = _try_approve_pull_request(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
    )

    merge_sha = _merge_pull_request_squash_or_409(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
    )

    branch_deleted = _delete_head_branch_best_effort(
        settings=settings,
        repo=repo,
        pr_data=selected_pr_data,
    )

    issue_closed, issue_close_error = _close_issue_best_effort(
        settings=settings,
        repo=repo,
        issue_number=int(selected_issue_num),
    )

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

    _require_github_token_for_merge(settings)
    branch = _get_default_branch(settings, repository=repo)

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    issue_nums = _issue_numbers_with_label(raw_issues, label_name=LABEL_REVIEW_CONSUMPTION)
    if not issue_nums:
        return None

    selected = _select_first_ready_pr_linked_to_issues(
        settings=settings,
        repo=repo,
        issue_nums=issue_nums,
        require_review_requested=True,
    )
    if selected is None:
        return None

    selected_issue_num, selected_pr_data, review_requested = selected

    pr_number = _pr_number_or_502(selected_pr_data)
    _raise_if_pr_wip(pr_number=pr_number, pr_data=selected_pr_data)
    _require_review_requested_or_409(pr_number=pr_number, review_requested=review_requested)

    selected_pr_data = _ensure_pr_not_draft_or_409(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
        pr_data=selected_pr_data,
    )

    approved, approval_error = _try_approve_pull_request(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
    )

    merge_sha = _merge_pull_request_squash_or_409(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
    )

    branch_deleted = _delete_head_branch_best_effort(
        settings=settings,
        repo=repo,
        pr_data=selected_pr_data,
    )

    issue_closed, issue_close_error = _close_issue_best_effort(
        settings=settings,
        repo=repo,
        issue_number=int(selected_issue_num),
    )

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
    return _try_merge_next_ready_labeled_issue_pull_request(
        settings=settings,
        repo=repo,
        label_name=LABEL_UPDATE_CAPABILITY,
        issue_kind_for_summary="capability",
    )


def _promotable_development_queue_candidates(
    pending_paths: list[str], *, loop_mode: str
) -> list[str]:
    promotable_categories = {"development"} if loop_mode != "review" else {"development", "review"}
    candidates: list[str] = []
    for p in sorted(pending_paths):
        filename = _queue_filename(p)
        if _queue_file_is_excluded_for_loop_mode(filename=filename, loop_mode=loop_mode):
            continue
        if _queue_category_for_filename(filename) not in promotable_categories:
            continue
        candidates.append(p)
    return candidates


def _select_first_unpromoted_queue_item(
    *,
    settings: ServerSettings,
    repo: str,
    branch: str,
    candidates: list[str],
    open_issues_for_matching: list[dict[str, Any]],
) -> tuple[str, str, str, str | None]:
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
            return pending_path, raw, sha, title_norm

    raise HTTPException(
        status_code=409,
        detail="No unpromoted development queue files found (all match open issues)",
    )


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
        dir_path=DEVELOPMENT_QUEUE_PENDING_DIR,
        ref=branch,
    )
    if not pending_paths:
        raise HTTPException(status_code=409, detail="No pending issue-queue files to promote")

    # Preload open issues once; title matching is used to decide promotion status.
    raw_issues = _list_open_issues_raw(settings, repository=repo)
    open_issues_for_matching = [it for it in raw_issues if isinstance(it, dict)]

    # Select next unpromoted work item in stable order.
    mode = getattr(settings, "loop_mode", "build")
    candidates = _promotable_development_queue_candidates(pending_paths, loop_mode=mode)

    if not candidates:
        detail = "No promotable development queue files found"
        if mode == "review":
            detail = "No promotable review/development queue files found"
        raise HTTPException(status_code=409, detail=detail)

    selected_path, selected_raw, selected_sha, selected_title_norm = _select_first_unpromoted_queue_item(
        settings=settings,
        repo=repo,
        branch=branch,
        candidates=candidates,
        open_issues_for_matching=open_issues_for_matching,
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
            raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_CREATE_ISSUE_RESPONSE)
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
        dir_path=DEVELOPMENT_QUEUE_PENDING_DIR,
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
            raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_CREATE_ISSUE_RESPONSE)
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

    return (
        _capability_source_pr_from_marker(repository=repository, issue_body=issue_body)
        or _capability_source_pr_from_title(issue_title=issue_title)
        or _capability_source_pr_from_body_summary(issue_body=issue_body)
        or None
    )


def _parse_int_if_digits(raw: str) -> int | None:
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    return None


def _capability_source_pr_from_marker(*, repository: str, issue_body: str) -> int | None:
    repo_norm = repository.strip().strip("/").lower()
    match = _CAPABILITY_ISSUE_BODY_SOURCE_PR_RE.search(issue_body or "")
    if not match:
        return None

    marker_repo = (match.group(1) or "").strip().strip("/").lower()
    if marker_repo != repo_norm:
        return None

    raw_num = match.group(2) or ""
    return _parse_int_if_digits(raw_num)


def _capability_source_pr_from_title(*, issue_title: str) -> int | None:
    match = _CAPABILITY_ISSUE_TITLE_SOURCE_PR_RE.search(issue_title or "")
    if not match:
        return None
    raw_num = match.group(1) or ""
    return _parse_int_if_digits(raw_num)


def _capability_source_pr_from_body_summary(*, issue_body: str) -> int | None:
    match = re.search(r"\bPR\s+number:\s*(\d+)\b", issue_body or "", flags=re.IGNORECASE)
    if not match:
        return None
    raw_num = match.group(1) or ""
    return _parse_int_if_digits(raw_num)


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


def _development_merge_candidate_paths(
    inflight_paths: list[str], *, loop_mode: str
) -> list[str]:
    mergeable_categories = {"development"} if loop_mode != "review" else {"development", "review"}
    candidates: list[str] = []
    for p in sorted(inflight_paths):
        filename = _queue_filename(p)
        if _queue_file_is_excluded_for_loop_mode(filename=filename, loop_mode=loop_mode):
            continue
        if _queue_category_for_filename(filename) not in mergeable_categories:
            continue
        candidates.append(p)
    return candidates


def _select_ready_development_merge_candidate(
    *,
    settings: ServerSettings,
    repo: str,
    branch: str,
    candidates: list[str],
    open_issues_for_matching: list[dict[str, Any]],
) -> tuple[str, str, str, str, int, dict[str, Any], bool] | None:
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
            pr_data = _open_pull_request_or_none(settings=settings, repo=repo, pr_number=pr_num)
            if pr_data is None:
                continue
            review_requested = _review_requested_for_pr_cached(
                settings=settings,
                repo=repo,
                pr_number=pr_num,
                pr_data=pr_data,
                cache=pr_review_request_cache,
            )
            if not _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                continue

            queue_id = _queue_filename(queue_path)
            return queue_id, queue_path, queue_sha, content, issue_num, pr_data, bool(review_requested)
    return None


def _ensure_followup_issue_after_development_merge(
    *,
    settings: ServerSettings,
    repo: str,
    branch: str,
    loop_mode: str,
    pr_number: int,
    pr_title: str,
    pr_body: str,
    queue_path: str,
    queue_content: str,
) -> tuple[int, bool, str]:
    if loop_mode == "review":
        follow_issue_label = LABEL_UPDATE_REVIEW
        marker = f"{_REVIEW_UPDATE_FROM_PR_MARKER_PREFIX} {repo}#{pr_number}"
        existing = _search_issue_number_by_body_marker(settings, repository=repo, marker=marker)
        if existing is not None:
            return existing, False, follow_issue_label

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
            queue_path=queue_path,
            queue_content=queue_content,
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
            raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_CREATE_ISSUE_RESPONSE)
        return num, True, follow_issue_label

    follow_issue_label = LABEL_UPDATE_CAPABILITY
    marker = f"{_CAPABILITY_UPDATE_FROM_PR_MARKER_PREFIX} {repo}#{pr_number}"
    existing = _search_issue_number_by_body_marker(settings, repository=repo, marker=marker)
    if existing is not None:
        return existing, False, follow_issue_label

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
        raise HTTPException(status_code=502, detail=ERR_UNEXPECTED_GITHUB_CREATE_ISSUE_RESPONSE)
    return num, True, follow_issue_label


def _merge_next_ready_development_pull_request(
    *, settings: ServerSettings, repo: str
) -> dict[str, object]:
    _require_github_token_for_merge(settings)

    branch = _get_default_branch(settings, repository=repo)
    mode = getattr(settings, "loop_mode", "build")

    # Discover the next ready PR deterministically from inflight development queue items.
    raw_issues = _list_open_issues_raw(settings, repository=repo)
    open_issues_for_matching = [it for it in raw_issues if isinstance(it, dict)]

    pending_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=repo,
        dir_path=DEVELOPMENT_QUEUE_PENDING_DIR,
        ref=branch,
    )
    processed_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=repo,
        dir_path="planning/issue_queue/processed",
        ref=branch,
    )
    inflight_paths = list(pending_paths) + list(processed_paths)

    candidates = _development_merge_candidate_paths(inflight_paths, loop_mode=mode)
    selected = _select_ready_development_merge_candidate(
        settings=settings,
        repo=repo,
        branch=branch,
        candidates=candidates,
        open_issues_for_matching=open_issues_for_matching,
    )
    if selected is None:
        raise HTTPException(status_code=409, detail="No ready development pull requests found")

    queue_id, source_path, source_sha, source_content, issue_number, pr_data, review_requested = (
        selected
    )

    pr_number = _pr_number_or_502(pr_data)
    _raise_if_pr_wip(pr_number=pr_number, pr_data=pr_data)
    _require_review_requested_or_409(pr_number=pr_number, review_requested=review_requested)

    pr_data = _ensure_pr_not_draft_or_409(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
        pr_data=pr_data,
    )

    approved, approval_error = _try_approve_pull_request(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
    )

    merge_sha = _merge_pull_request_squash_or_409(
        settings=settings,
        repo=repo,
        pr_number=pr_number,
    )

    # Move the queue file to complete/ to avoid lingering processed artefacts keeping the loop in C.
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

    branch_deleted = _delete_head_branch_best_effort(settings=settings, repo=repo, pr_data=pr_data)

    # Create a follow-up issue and assign it to Copilot.
    raw_title = pr_data.get("title")
    raw_body = pr_data.get("body")
    pr_title = raw_title if isinstance(raw_title, str) else ""
    pr_body = raw_body if isinstance(raw_body, str) else ""

    follow_issue_number, follow_issue_created, follow_issue_label = (
        _ensure_followup_issue_after_development_merge(
            settings=settings,
            repo=repo,
            branch=branch,
            loop_mode=mode,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_body=pr_body,
            queue_path=source_path,
            queue_content=source_content,
        )
    )

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
        "developmentIssueNumber": int(issue_number),
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
