"""Dashboard-focused REST API.

This router implements the endpoints used by the React dashboard in `ui/`.

All routes are mounted under `/api`.
"""

from __future__ import annotations

import re
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query, Request

from github_agent_orchestrator import __version__
from github_agent_orchestrator.github_labels import (
    LABEL_DEVELOPMENT,
    LABEL_REVIEW_CONSUMPTION,
    LABEL_UPDATE_CAPABILITY,
    LABEL_UPDATE_REVIEW,
)
from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard.automation_auto_link import (
    maybe_auto_link_focused_issue_to_pr as _maybe_auto_link_focused_issue_to_pr,
)
from github_agent_orchestrator.server.dashboard.automation_auto_resume import (
    maybe_auto_resume_copilot_after_rate_limit as _maybe_auto_resume_copilot_after_rate_limit,
)
from github_agent_orchestrator.server.dashboard.github_api import (
    _github_delete_json,
    _github_get_json,
    _github_get_list,
    _github_get_list_with_headers,
    _github_graphql_post,
    _github_headers,
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
    pull_request_is_approved_from_reviews as _pull_request_is_approved_from_reviews,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    pull_request_is_merge_candidate as _pull_request_is_merge_candidate,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    pull_request_is_ready_for_review as _pull_request_is_ready_for_review,
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
    get_branch_head_commit_sha as _get_branch_head_commit_sha,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    get_commit_tree_sha as _get_commit_tree_sha,
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
    get_repo_tree_recursive as _get_repo_tree_recursive,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_issue_comments_raw as _list_issue_comments_raw,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_issue_events_raw as _list_issue_events_raw,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_issue_timeline_raw as _list_issue_timeline_raw,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_open_issues_raw as _list_open_issues_raw,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_open_pull_requests_raw as _list_open_pull_requests_raw,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    list_repo_markdown_files_under as _list_repo_markdown_files_under,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    search_issue_number_by_body_marker as _search_issue_number_by_body_marker,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    _ensure_gap_analysis_issue_exists as _ensure_gap_analysis_issue_exists,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    _load_gap_analysis_template_or_raise as _load_gap_analysis_template_or_raise,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    _merge_next_ready_pull_request as _merge_next_ready_pull_request,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    _promote_next_unpromoted_capability_queue_item as _promote_next_unpromoted_capability_queue_item,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    _promote_next_unpromoted_development_queue_item as _promote_next_unpromoted_development_queue_item,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    ensure_gap_analysis_issue as ensure_gap_analysis_issue,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    merge_next_ready_development_pull_request as merge_next_ready_development_pull_request,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    promote_next_pending_issue_queue_item as promote_next_pending_issue_queue_item,
)
from github_agent_orchestrator.server.dashboard.queue_helpers import (
    _GAP_ANALYSIS_TITLES,
    _QUEUE_EXCLUDED_PREFIXES,
    _is_gap_analysis_issue_title,
    _parse_queue_file_for_issue,
    _queue_category_for_filename,
    _queue_filename,
    _search_issue_number_by_queue_marker,
)
from github_agent_orchestrator.server.dashboard.text_utilities import (
    _AUTO_LINK_NOTICE_MARKER,
    _COPILOT_RATE_LIMIT_RESUME_COMMENT,
    _comment_body_is_auto_link_notice,
    _comment_body_is_copilot_resume_nudge,
    _dt_from_iso,
    _first_markdown_line_as_title,
    _normalize_issue_title,
    _normalize_repo_path_candidate,
    _strip_fenced_code_blocks,
    _utc_now,
    _utc_now_iso,
)

router = APIRouter()


# Apply router decorators to imported loop action endpoints
promote_next_pending_issue_queue_item = router.post("/loop/promote")(
    promote_next_pending_issue_queue_item
)
ensure_gap_analysis_issue = router.post("/loop/gap-analysis/ensure")(ensure_gap_analysis_issue)
merge_next_ready_development_pull_request = router.post("/loop/merge")(
    merge_next_ready_development_pull_request
)


# Marker used to make capability-update issues (created after merges) idempotent.
_CAPABILITY_UPDATE_FROM_PR_MARKER_PREFIX = "orchestrator:capability-update-from-pr"

# Marker used to make review-actions update issues idempotent.
_REVIEW_UPDATE_FROM_PR_MARKER_PREFIX = "orchestrator:review-update-from-pr"

# Marker used to make review-consumption issues idempotent.
_REVIEW_CONSUMPTION_MARKER_PREFIX = "orchestrator:review-consumption"


_CAPABILITY_ISSUE_TITLE_SOURCE_PR_RE = re.compile(r"merged\s+pr\s+#(\d+)", re.IGNORECASE)
_CAPABILITY_ISSUE_BODY_SOURCE_PR_RE = re.compile(
    rf"{re.escape(_CAPABILITY_UPDATE_FROM_PR_MARKER_PREFIX)}\s+([^#\s]+)#(\d+)",
    re.IGNORECASE,
)


def _settings(request: Request) -> ServerSettings:
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, ServerSettings):
        # This should never happen for the real app, but keeps the API fail-fast.
        raise HTTPException(status_code=500, detail="Server settings not configured")
    return settings


def _make_github_issue_url(repo: str, issue_number: int) -> str | None:
    if not repo.strip():
        return None
    return f"https://github.com/{repo.strip()}/issues/{issue_number}"


def _active_repo(request: Request, settings: ServerSettings) -> str:
    repo_param = request.query_params.get("repo", "").strip()
    active = repo_param or settings.default_repo.strip()
    if not active:
        raise HTTPException(
            status_code=409,
            detail="repo is required (pass ?repo=owner/name or set ORCHESTRATOR_DEFAULT_REPO)",
        )
    return active


def _active_ref(request: Request) -> str:
    return request.query_params.get("ref", "").strip()


_GAP_ANALYSIS_TEMPLATE_PATHS: tuple[str, ...] = (
    "planning/issue_templates/gap-analysis.md",
    "planning/issue_templates/gap_analysis.md",
)


_REVIEW_CONSUMPTION_TEMPLATE_PATHS: tuple[str, ...] = (
    "planning/issue_templates/review-consumption.md",
    "planning/issue_templates/review_consumption.md",
)


_REVIEW_ACTIONS_AFTER_MERGE_TEMPLATE_PATHS: tuple[str, ...] = (
    "planning/issue_templates/review-actions-after-pr-merge.md",
    "planning/issue_templates/review_actions_after_pr_merge.md",
)


def _load_review_consumption_template_or_raise(
    *, settings: ServerSettings, repo: str, branch: str
) -> str:
    """Load the review-consumption issue template from the target repository."""

    for template_path in _REVIEW_CONSUMPTION_TEMPLATE_PATHS:
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
            "Unable to load review consumption template from the target repository. "
            "Expected planning/issue_templates/review-consumption.md"
        ),
    )


def _review_actions_path_for_review_path(review_path: str) -> str:
    p = Path(review_path)
    if p.suffix.lower() == ".md":
        return str(p.with_suffix(".actions.md")).replace("\\", "/")
    return f"{review_path}.actions.md"


def _pick_next_review_file(*, settings: ServerSettings, repo: str, branch: str) -> str | None:
    """Pick a review document to consume (stable ordering).

    We intentionally keep this deterministic and low-intelligence: choose the lexicographically
    first `review-*.md` file in `/planning/reviews/`, excluding `*.actions.md`.
    """

    paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=repo,
        dir_path="planning/reviews",
        ref=branch,
    )
    candidates: list[str] = []
    for p in paths:
        name = Path(p).name.lower()
        if not name.startswith("review-"):
            continue
        if name.endswith(".actions.md"):
            continue
        candidates.append(p)
    return sorted(candidates)[0] if candidates else None


def _ensure_review_consumption_issue_exists(
    *, settings: ServerSettings, repo: str
) -> dict[str, object]:
    """Ensure there is exactly one open review-consumption issue (best-effort).

    In review mode, Step 1a is "review consumption": read a review artefact and produce the
    next concrete work item in `/planning/issue_queue/pending/`.
    """

    branch = _get_default_branch(settings, repository=repo)

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    for it in raw_issues:
        if not isinstance(it, dict):
            continue
        if "pull_request" in it:
            continue
        if not _issue_has_label(it, label_name=LABEL_REVIEW_CONSUMPTION):
            continue
        num = it.get("number")
        if not isinstance(num, int):
            continue

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
            detail="ORCHESTRATOR_GITHUB_TOKEN is required to create review consumption issues",
        )

    review_path = _pick_next_review_file(settings=settings, repo=repo, branch=branch)
    if review_path is None:
        raise HTTPException(
            status_code=409,
            detail="No review files found under planning/reviews (expected review-*.md)",
        )
    actions_path = _review_actions_path_for_review_path(review_path)

    template_body = _load_review_consumption_template_or_raise(
        settings=settings, repo=repo, branch=branch
    )
    marker = f"{_REVIEW_CONSUMPTION_MARKER_PREFIX} {review_path}"
    body = (
        template_body.replace("{{REVIEW_PATH}}", review_path)
        .replace("{{REVIEW_ACTIONS_PATH}}", actions_path)
        .rstrip()
        + f"\n\n---\n\n<!-- {marker} -->\n"
    )

    issue_title = f"Identify next actionable work from review: {Path(review_path).name}"
    _ensure_repo_label_exists(settings, repository=repo, label_name=LABEL_REVIEW_CONSUMPTION)
    issue = _github_post_json(
        settings,
        url=_repo_api_url(settings, repository=repo, path="issues"),
        payload={
            "title": issue_title,
            "body": body,
            "labels": [LABEL_REVIEW_CONSUMPTION],
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


def _queue_file_is_excluded_for_loop_mode(*, filename: str, loop_mode: str) -> bool:
    """Return True if the queue file should be ignored by the active loop mode.

    In build mode, `review-*` artefacts are excluded from the development loop.
    In review mode, `review-*` artefacts are treated as primary work items.
    """

    lowered = (filename or "").lower()
    mode = (loop_mode or "").strip().lower()
    if mode == "review" and lowered.startswith("review-"):
        return False
    return lowered.startswith(_QUEUE_EXCLUDED_PREFIXES)


def _assign_issue_to_copilot(
    settings: ServerSettings,
    *,
    repository: str,
    issue_number: int,
    target_repo: str,
    base_branch: str,
    instructions: str,
) -> list[str]:
    # Safety: before assigning, repair known-unsafe gap-analysis issue bodies.
    # This guard lives here (the single assignment choke-point) so ALL call sites benefit.
    try:
        issue = _github_get_json(
            settings,
            url=_repo_api_url(settings, repository=repository, path=f"issues/{issue_number}"),
        )
        title = issue.get("title")
        body = issue.get("body")
        if isinstance(title, str) and _is_gap_analysis_issue_title(title) and isinstance(body, str):
            _repair_gap_analysis_issue_body_if_unsafe(
                settings=settings,
                repo=repository,
                issue_number=issue_number,
                branch=base_branch,
                existing_body=body,
            )
        elif isinstance(body, str) and _gap_analysis_issue_body_looks_unsafe(body):
            # These phrases should only appear in a gap analysis issue; refuse to assign
            # anything else until it is corrected.
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Refusing to assign issue #{issue_number}: body contains known-unsafe gap-analysis "
                    "instructions"
                ),
            )
    except HTTPException as e:
        # Only block assignment when we are explicitly refusing due to known-unsafe instructions.
        # Any other HTTPException here is likely from the best-effort issue fetch and should not
        # prevent assignment.
        if e.status_code == 409:
            raise
    except Exception:
        # Best-effort: if we can't read the issue body for any reason, don't block assignment.
        # (The GitHub assignment API can still succeed, and other safety gates exist elsewhere.)
        pass

    payload: dict[str, Any] = {"assignees": [settings.copilot_assignee]}
    agent_assignment: dict[str, str] = {}
    if target_repo.strip():
        agent_assignment["target_repository"] = target_repo.strip()
    if base_branch.strip():
        agent_assignment["base_branch"] = base_branch.strip()
    if instructions.strip():
        agent_assignment["additional_instructions"] = instructions.strip()
    if agent_assignment:
        payload["agent_assignment"] = agent_assignment

    data = _github_post_json(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"issues/{issue_number}/assignees"),
        payload=payload,
    )
    assignees = data.get("assignees")
    if not isinstance(assignees, list):
        return []
    returned: list[str] = []
    for a in assignees:
        if isinstance(a, dict):
            login = a.get("login")
            if isinstance(login, str) and login.strip():
                returned.append(login)
    return returned


@router.post("/loop/promote")
@router.post("/loop/gap-analysis/ensure")
@router.post("/loop/review/ensure")
def ensure_review_consumption_issue(request: Request) -> dict[str, object]:
    """Step 1a (review mode) action: ensure a review-consumption issue exists and is assigned."""

    settings = _settings(request)
    repo = _active_repo(request, settings)
    out = _ensure_review_consumption_issue_exists(settings=settings, repo=repo)

    created = bool(out.get("created"))
    num = out.get("issueNumber")
    summary = "Review consumption issue ensured"
    if isinstance(num, int):
        summary = f"{'Created' if created else 'Ensured'} review consumption issue #{num}"
    return {
        **out,
        "repo": repo,
        "branch": _get_default_branch(settings, repository=repo),
        "summary": summary,
    }


_REVIEW_QUEUE_SOURCE_RE = re.compile(r"^\s*source\s+review\s*:\s*(.+?)\s*$", re.IGNORECASE)
_REVIEW_QUEUE_ACTIONS_RE = re.compile(r"^\s*review\s+actions\s*:\s*(.+?)\s*$", re.IGNORECASE)
_REVIEW_QUEUE_ID_DATE_RE = re.compile(r"\breview-(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)


def _extract_review_paths_from_queue_content(
    *, queue_id: str, queue_content: str
) -> tuple[str | None, str | None]:
    """Best-effort extraction of the source review + actions paths from a queue artefact."""

    review_path: str | None = None
    actions_path: str | None = None

    for raw in (queue_content or "").splitlines():
        line = raw.strip("\n")
        m = _REVIEW_QUEUE_SOURCE_RE.match(line)
        if m and review_path is None:
            candidate = _normalize_repo_path_candidate(m.group(1) or "")
            if candidate:
                review_path = candidate
            continue
        m2 = _REVIEW_QUEUE_ACTIONS_RE.match(line)
        if m2 and actions_path is None:
            candidate = _normalize_repo_path_candidate(m2.group(1) or "")
            if candidate:
                actions_path = candidate

    # Fallback: infer from filename when it contains a canonical date.
    if review_path is None:
        m = _REVIEW_QUEUE_ID_DATE_RE.search(queue_id or "")
        if m:
            date = (m.group(1) or "").strip()
            review_path = f"planning/reviews/review-{date}.md"
    if actions_path is None and review_path is not None:
        actions_path = _review_actions_path_for_review_path(review_path)

    return review_path, actions_path


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
    """Render (title, body) for a post-merge review actions update issue."""

    review_path, actions_path = _extract_review_paths_from_queue_content(
        queue_id=Path(queue_path).name,
        queue_content=queue_content,
    )

    # Robust fallback: do not depend on LLM-authored queue artefact structure.
    # If we cannot infer the review context, default to the next review file under planning/reviews.
    if review_path is None:
        fallback_review = _pick_next_review_file(settings=settings, repo=repo, branch=branch)
        if isinstance(fallback_review, str) and fallback_review.strip():
            review_path = fallback_review.strip()
            actions_path = actions_path or _review_actions_path_for_review_path(review_path)

    review_path = review_path or "(unknown review source)"
    actions_path = actions_path or "(unknown actions path)"

    marker = f"{_REVIEW_UPDATE_FROM_PR_MARKER_PREFIX} {repo}#{pr_number} {actions_path}"
    template = _load_review_actions_after_merge_template_or_raise(
        settings=settings,
        repo=repo,
        branch=branch,
    )

    pr_description = pr_body.strip() or "(no PR description)"
    discussion = discussion_markdown.strip() or "(no PR comments)"
    body = (
        template.replace("{{PR_NUMBER}}", str(pr_number))
        .replace("{{PR_TITLE}}", pr_title or "")
        .replace("{{PR_DESCRIPTION}}", pr_description)
        .replace("{{PR_COMMENTS}}", discussion)
        .replace("{{REVIEW_PATH}}", review_path)
        .replace("{{REVIEW_ACTIONS_PATH}}", actions_path)
        .replace("{{QUEUE_PATH}}", queue_path)
        .replace("{{MARKER}}", marker)
        .rstrip()
        + "\n"
    )

    title = f"Update review actions based on merged PR #{pr_number}"
    return title, body


def _template_category_from_filename(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith("review-"):
        return "review"
    if lowered.startswith("gap-"):
        return "gap"
    if lowered.startswith("system-"):
        return "system"
    if lowered.startswith("maintenance-"):
        return "maintenance"
    return "unknown"


def _load_repo_cognitive_task_templates(
    *,
    settings: ServerSettings,
    repository: str,
    ref: str,
) -> list[dict[str, object]]:
    paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=repository,
        dir_path="planning/issue_templates",
        ref=ref,
    )
    tasks: list[dict[str, object]] = []
    for p in paths:
        content, _sha = _get_repo_text_file(settings, repository=repository, path=p, ref=ref)
        name = Path(p).stem
        tasks.append(
            {
                "id": Path(p).name,
                "name": name.replace("_", " "),
                "category": _template_category_from_filename(name),
                "enabled": True,
                "promptText": content,
                "targetFolder": "planning/issue_queue/pending",
                "trigger": {"kind": "MANUAL_ONLY"},
                "editable": False,
            }
        )
    tasks.sort(key=lambda t: str(t.get("name") or "").lower())
    return tasks


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    """Simple connectivity check for the UI."""

    settings = _settings(request)
    repo_param = request.query_params.get("repo", "").strip()
    repo = repo_param or settings.default_repo.strip()
    return {
        "ok": True,
        "status": "ok",
        "version": __version__,
        "repoName": repo,
    }


@router.get("/docs/goal")
def doc_goal(request: Request) -> dict[str, object]:
    settings = _settings(request)
    repo = _active_repo(request, settings)
    ref = _active_ref(request)
    content, sha = _get_repo_text_file(
        settings,
        repository=repo,
        path="planning/vision/goal.md",
        ref=ref,
    )
    return {
        "key": "goal",
        "title": "Goal",
        "path": "planning/vision/goal.md",
        "lastUpdatedIso": _utc_now_iso(),
        "sha": sha,
        "repo": repo,
        "ref": (ref or None),
        "content": content,
    }


@router.get("/docs/capabilities")
def doc_capabilities(request: Request) -> dict[str, object]:
    settings = _settings(request)
    repo = _active_repo(request, settings)
    ref = _active_ref(request)
    content, sha = _get_repo_text_file(
        settings,
        repository=repo,
        path="planning/state/system_capabilities.md",
        ref=ref,
    )
    return {
        "key": "capabilities",
        "title": "System Capabilities",
        "path": "planning/state/system_capabilities.md",
        "lastUpdatedIso": _utc_now_iso(),
        "sha": sha,
        "repo": repo,
        "ref": (ref or None),
        "content": content,
    }


@router.get("/cognitive-tasks")
def list_cognitive_tasks(request: Request) -> list[dict[str, object]]:
    settings = _settings(request)
    repo = _active_repo(request, settings)
    ref = _active_ref(request)
    return _load_repo_cognitive_task_templates(settings=settings, repository=repo, ref=ref)


@router.get("/timeline")
def list_timeline(
    request: Request, limit: int = Query(default=200, ge=1, le=1000)
) -> list[dict[str, object]]:
    settings = _settings(request)
    repo = _active_repo(request, settings)
    ref = _active_ref(request)

    # A lightweight, repo-derived timeline: show recent commits that touched planning/.
    # This avoids any local persistence.
    params: dict[str, str] = {
        "per_page": str(min(limit, 100)),
        "path": "planning",
    }
    if ref:
        params["sha"] = ref
    data = requests.get(
        _repo_api_url(settings, repository=repo, path="commits"),
        headers=_github_headers(settings),
        params=params,
        timeout=30,
    )
    data.raise_for_status()
    raw = data.json()
    if not isinstance(raw, list):
        raise HTTPException(status_code=502, detail="Unexpected GitHub commits response")

    out: list[dict[str, object]] = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        sha = c.get("sha")
        commit = c.get("commit")
        if not isinstance(commit, dict):
            continue
        message = commit.get("message")
        author = commit.get("author")
        if not isinstance(author, dict):
            continue
        ts = author.get("date")
        if not isinstance(ts, str):
            continue
        summary = message.splitlines()[0] if isinstance(message, str) and message else "Commit"
        out.append(
            {
                "id": str(sha or ""),
                "tsIso": ts,
                "kind": "GIT_COMMIT",
                "summary": summary,
                "typePath": "planning",
                "links": (
                    [{"label": "Commit", "url": c.get("html_url")}] if c.get("html_url") else None
                ),
            }
        )

    out.sort(key=lambda e: str(e.get("tsIso") or ""), reverse=True)
    return out[:limit]


@router.get("/issues")
def list_issues(request: Request, status: str = Query(default="open")) -> list[dict[str, object]]:
    settings = _settings(request)
    repo = _active_repo(request, settings)
    ref = _active_ref(request)

    # GitHub issues API (not local state). Note: this includes PRs; we filter those out.
    desired_state = "open" if status == "open" else "all"
    params: dict[str, str] = {"state": desired_state, "per_page": "100"}
    if ref:
        # Not a supported parameter for issues API; ignore.
        pass

    resp = requests.get(
        _repo_api_url(settings, repository=repo, path="issues"),
        headers=_github_headers(settings),
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()
    if not isinstance(raw, list):
        raise HTTPException(status_code=502, detail="Unexpected GitHub issues response")

    now = datetime.now(tz=UTC)
    mapped: list[dict[str, object]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        if "pull_request" in it:
            continue
        num = it.get("number")
        title = it.get("title")
        state = it.get("state")
        created_at = it.get("created_at")
        updated_at = it.get("updated_at")
        html_url = it.get("html_url")
        if not isinstance(num, int) or not isinstance(title, str):
            continue
        st = "OPEN" if state == "open" else "CLOSED"
        created_dt = _dt_from_iso(created_at) if isinstance(created_at, str) else now
        age_seconds = max(0, int((now - created_dt).total_seconds()))
        mapped.append(
            {
                "id": str(num),
                "title": title,
                "typePath": "github/issues",
                "status": st,
                "ageSeconds": age_seconds,
                "githubIssueUrl": (
                    str(html_url)
                    if isinstance(html_url, str)
                    else _make_github_issue_url(repo, num)
                ),
                "prUrl": None,
                "lastUpdatedIso": (
                    str(updated_at) if isinstance(updated_at, str) else _utc_now_iso()
                ),
                "isActive": False,
            }
        )

    open_issues = [i for i in mapped if i.get("status") == "OPEN"]
    if open_issues:
        newest = max(open_issues, key=lambda i: str(i.get("lastUpdatedIso") or ""))
        for i in mapped:
            i["isActive"] = i["id"] == newest.get("id")

    mapped.sort(key=lambda i: str(i.get("lastUpdatedIso") or ""), reverse=True)
    return mapped


@router.get("/active")
def get_active(request: Request) -> dict[str, object]:
    issues = list_issues(request, status="open")
    active = next((i for i in issues if i.get("isActive") is True), None)
    timeline = list_timeline(request, limit=1)
    last = timeline[0] if timeline else None
    return {
        "activeIssue": active,
        "lastAction": (
            None
            if last is None
            else {
                "tsIso": last.get("tsIso"),
                "summary": last.get("summary"),
            }
        ),
    }


@router.get("/overview")
def overview(request: Request) -> dict[str, object]:
    issues = list_issues(request, status="open")
    open_count = len([i for i in issues if i.get("status") == "OPEN"])
    active = next((i for i in issues if i.get("isActive") is True), None)
    timeline = list_timeline(request, limit=1)
    last = timeline[0] if timeline else None
    return {
        "activeIssueId": None if active is None else active.get("id"),
        "openIssueCount": open_count,
        "lastEventIso": (last.get("tsIso") if last is not None else _utc_now_iso()),
    }


@router.get("/loop")
def loop_status(request: Request) -> dict[str, object]:
    """Return a UI-friendly summary of the orchestrator's 1a–3c loop.

    The intent is to help visualize where the system currently is *without* adding
    new "intelligence". This is a best-effort stage derived from persisted state.
    """

    settings = _settings(request)

    repo_param = request.query_params.get("repo", "").strip()
    active_repo = repo_param or settings.default_repo.strip()
    if not active_repo:
        raise HTTPException(
            status_code=409,
            detail="repo is required (pass ?repo=owner/name or set ORCHESTRATOR_DEFAULT_REPO)",
        )

    ref = request.query_params.get("ref", "").strip()
    return _loop_status_for_repo(settings=settings, active_repo=active_repo, ref=ref)


def _loop_status_for_repo(
    *, settings: ServerSettings, active_repo: str, ref: str
) -> dict[str, object]:
    mode = getattr(settings, "loop_mode", "build")
    pending_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=active_repo,
        dir_path="planning/issue_queue/pending",
        ref=ref,
    )
    processed_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=active_repo,
        dir_path="planning/issue_queue/processed",
        ref=ref,
    )
    complete_paths = _list_repo_markdown_files_under(
        settings=settings,
        repository=active_repo,
        dir_path="planning/issue_queue/complete",
        ref=ref,
    )

    pending_count = len(pending_paths)
    processed_count = len(processed_paths)
    complete_count = len(complete_paths)

    # --- GitHub repo-derived signals (no local checkout/state) ---
    raw_issues = _list_open_issues_raw(settings, repository=active_repo)
    open_issue_titles: list[str] = []
    open_capability_issue_numbers: list[int] = []
    open_review_update_issue_numbers: list[int] = []
    open_review_consumption_issue_numbers: list[int] = []
    open_issue_titles_by_number: dict[int, str] = {}
    for it in raw_issues:
        if "pull_request" in it:
            continue
        num = it.get("number")
        title = it.get("title")
        if isinstance(title, str):
            open_issue_titles.append(title)
            if isinstance(num, int):
                open_issue_titles_by_number[num] = title
        if isinstance(num, int) and _issue_has_label(it, label_name=LABEL_UPDATE_CAPABILITY):
            open_capability_issue_numbers.append(num)
        if isinstance(num, int) and _issue_has_label(it, label_name=LABEL_UPDATE_REVIEW):
            open_review_update_issue_numbers.append(num)
        if isinstance(num, int) and _issue_has_label(it, label_name=LABEL_REVIEW_CONSUMPTION):
            open_review_consumption_issue_numbers.append(num)

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

    has_open_gap_analysis_issue = bool(gap_issue_nums)

    raw_open_prs = _list_open_pull_requests_raw(settings, repository=active_repo, limit=100)
    open_pr_count = len(raw_open_prs)

    pending_files = [_queue_filename(p) for p in pending_paths]
    pending_by_category: dict[str, list[str]] = {}
    for filename in pending_files:
        pending_by_category.setdefault(_queue_category_for_filename(filename), []).append(filename)

    dev_pending = pending_by_category.get("development", [])
    review_pending = pending_by_category.get("review", [])
    cap_pending = pending_by_category.get("capability", [])
    excluded_pending = [
        f
        for f in pending_files
        if _queue_file_is_excluded_for_loop_mode(filename=f, loop_mode=mode)
    ]

    processed_files = [_queue_filename(p) for p in processed_paths]
    processed_by_category: dict[str, list[str]] = {}
    for filename in processed_files:
        processed_by_category.setdefault(_queue_category_for_filename(filename), []).append(
            filename
        )

    dev_processed = processed_by_category.get("development", [])
    review_processed = processed_by_category.get("review", [])
    cap_processed = processed_by_category.get("capability", [])

    # Associate queue files (pending + processed) -> GitHub issues by matching the file title
    # (first line) to open issue titles. Then associate issues -> PRs via issue timeline events.
    queue_issue_numbers: dict[str, int | None] = {}
    queue_display_titles: dict[str, str] = {}
    issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    pr_lookups = 0
    timeline_lookups = 0

    open_issues_for_matching = [it for it in raw_issues if isinstance(it, dict)]
    pr_cache: dict[int, dict[str, Any]] = {}
    pr_review_request_cache: dict[int, bool] = {}

    queue_paths_for_linkage = list(pending_paths) + list(processed_paths)
    for queue_path in queue_paths_for_linkage:
        content, _sha = _get_repo_text_file(
            settings,
            repository=active_repo,
            path=queue_path,
            ref=ref,
        )

        # Display title keeps original casing for UI; matching uses normalized title.
        display_title = ""
        for raw in content.splitlines():
            line = raw.strip("\n")
            if not line.strip():
                continue
            if line.lstrip().startswith("#"):
                line = line.lstrip().lstrip("#").strip()
            display_title = line.strip()
            break
        if display_title:
            queue_display_titles[queue_path] = display_title

        title_norm = _first_markdown_line_as_title(content)
        issue_num = _best_match_issue_number(title_norm, open_issues_for_matching)
        queue_issue_numbers[queue_path] = issue_num

        if issue_num is None:
            continue

        if issue_num not in issue_to_open_prs:
            timeline = _list_issue_timeline_raw(
                settings, repository=active_repo, issue_number=issue_num
            )
            timeline_lookups += 1
            pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)

            open_prs: list[dict[str, Any]] = []
            ready_prs: list[dict[str, Any]] = []
            for pr_num in sorted(pr_nums):
                pr_data = pr_cache.get(pr_num)
                if pr_data is None:
                    pr_data = _get_pull_request(settings, repository=active_repo, pr_number=pr_num)
                    pr_cache[pr_num] = pr_data
                    pr_lookups += 1

                if pr_data.get("state") != "open":
                    continue
                open_prs.append(pr_data)

                review_requested = _pull_request_has_review_request(pr_data)
                if not review_requested:
                    cached_rr = pr_review_request_cache.get(pr_num)
                    if cached_rr is None:
                        cached_rr = _pull_request_has_review_request_history(
                            settings,
                            repository=active_repo,
                            pr_number=pr_num,
                        )
                        pr_review_request_cache[pr_num] = cached_rr
                        timeline_lookups += 1
                    review_requested = cached_rr

                if _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                    ready_prs.append(pr_data)

            issue_to_open_prs[issue_num] = open_prs
            issue_to_open_ready_prs[issue_num] = ready_prs

    # Capability update issues (Step E/F/G) are derived from labels, not queue files.
    cap_issue_nums = sorted(set(open_capability_issue_numbers))
    cap_issue_with_pr = False
    cap_issue_ready_for_review = False
    cap_issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    cap_issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    for issue_num in cap_issue_nums:
        if issue_num in issue_to_open_prs:
            cap_open_prs_existing = list(issue_to_open_prs.get(issue_num) or [])
            cap_ready_prs_existing = list(issue_to_open_ready_prs.get(issue_num) or [])
            cap_issue_to_open_prs[issue_num] = cap_open_prs_existing
            cap_issue_to_open_ready_prs[issue_num] = cap_ready_prs_existing
            cap_issue_with_pr = cap_issue_with_pr or bool(cap_open_prs_existing)
            cap_issue_ready_for_review = cap_issue_ready_for_review or bool(cap_ready_prs_existing)
            continue

        timeline = _list_issue_timeline_raw(
            settings, repository=active_repo, issue_number=issue_num
        )
        timeline_lookups += 1
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)

        cap_open_prs_list: list[dict[str, Any]] = []
        cap_ready_prs_list: list[dict[str, Any]] = []
        for linked_pr_num in sorted(pr_nums):
            pr_data = pr_cache.get(linked_pr_num)
            if pr_data is None:
                pr_data = _get_pull_request(
                    settings, repository=active_repo, pr_number=linked_pr_num
                )
                pr_cache[linked_pr_num] = pr_data
                pr_lookups += 1
            if pr_data.get("state") != "open":
                continue
            cap_issue_with_pr = True
            cap_open_prs_list.append(pr_data)

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(linked_pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=active_repo,
                        pr_number=linked_pr_num,
                    )
                    pr_review_request_cache[linked_pr_num] = cached_rr
                    timeline_lookups += 1
                review_requested = cached_rr

            if _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                cap_issue_ready_for_review = True
                cap_ready_prs_list.append(pr_data)

        cap_issue_to_open_prs[issue_num] = cap_open_prs_list
        cap_issue_to_open_ready_prs[issue_num] = cap_ready_prs_list

    # Gap-analysis issues (Step A) are derived from titles, not queue artefacts.
    gap_issue_nums = sorted(set(gap_issue_nums))
    gap_issue_with_pr = False
    gap_issue_ready_for_review = False
    gap_issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    gap_issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    for issue_num in gap_issue_nums:
        if issue_num in issue_to_open_prs:
            gap_open_prs_existing = list(issue_to_open_prs.get(issue_num) or [])
            gap_ready_prs_existing = list(issue_to_open_ready_prs.get(issue_num) or [])
            gap_issue_to_open_prs[issue_num] = gap_open_prs_existing
            gap_issue_to_open_ready_prs[issue_num] = gap_ready_prs_existing
            gap_issue_with_pr = gap_issue_with_pr or bool(gap_open_prs_existing)
            gap_issue_ready_for_review = gap_issue_ready_for_review or bool(gap_ready_prs_existing)
            continue

        timeline = _list_issue_timeline_raw(
            settings, repository=active_repo, issue_number=issue_num
        )
        timeline_lookups += 1
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)

        gap_open_prs_list: list[dict[str, Any]] = []
        gap_ready_prs_list: list[dict[str, Any]] = []
        for linked_pr_num in sorted(pr_nums):
            pr_data = pr_cache.get(linked_pr_num)
            if pr_data is None:
                pr_data = _get_pull_request(
                    settings, repository=active_repo, pr_number=linked_pr_num
                )
                pr_cache[linked_pr_num] = pr_data
                pr_lookups += 1
            if pr_data.get("state") != "open":
                continue
            gap_issue_with_pr = True
            gap_open_prs_list.append(pr_data)

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(linked_pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=active_repo,
                        pr_number=linked_pr_num,
                    )
                    pr_review_request_cache[linked_pr_num] = cached_rr
                    timeline_lookups += 1
                review_requested = cached_rr

            if _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                gap_issue_ready_for_review = True
                gap_ready_prs_list.append(pr_data)

        gap_issue_to_open_prs[issue_num] = gap_open_prs_list
        gap_issue_to_open_ready_prs[issue_num] = gap_ready_prs_list

    # Review-mode issues are derived from labels.
    review_intake_issue_nums = sorted(set(open_review_consumption_issue_numbers))
    review_update_issue_nums = sorted(set(open_review_update_issue_numbers))

    review_intake_with_pr = False
    review_intake_ready_for_review = False
    review_intake_issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    review_intake_issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    for issue_num in review_intake_issue_nums:
        timeline = _list_issue_timeline_raw(
            settings, repository=active_repo, issue_number=issue_num
        )
        timeline_lookups += 1
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)

        intake_open_prs: list[dict[str, Any]] = []
        intake_ready_prs: list[dict[str, Any]] = []
        for linked_pr_num in sorted(pr_nums):
            pr_data = pr_cache.get(linked_pr_num)
            if pr_data is None:
                pr_data = _get_pull_request(
                    settings, repository=active_repo, pr_number=linked_pr_num
                )
                pr_cache[linked_pr_num] = pr_data
                pr_lookups += 1
            if pr_data.get("state") != "open":
                continue
            review_intake_with_pr = True
            intake_open_prs.append(pr_data)

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(linked_pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=active_repo,
                        pr_number=linked_pr_num,
                    )
                    pr_review_request_cache[linked_pr_num] = cached_rr
                    timeline_lookups += 1
                review_requested = cached_rr

            if _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                review_intake_ready_for_review = True
                intake_ready_prs.append(pr_data)

        review_intake_issue_to_open_prs[issue_num] = intake_open_prs
        review_intake_issue_to_open_ready_prs[issue_num] = intake_ready_prs

    review_update_with_pr = False
    review_update_ready_for_review = False
    review_update_issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    review_update_issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    for issue_num in review_update_issue_nums:
        timeline = _list_issue_timeline_raw(
            settings, repository=active_repo, issue_number=issue_num
        )
        timeline_lookups += 1
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)

        upd_open_prs: list[dict[str, Any]] = []
        upd_ready_prs: list[dict[str, Any]] = []
        for linked_pr_num in sorted(pr_nums):
            pr_data = pr_cache.get(linked_pr_num)
            if pr_data is None:
                pr_data = _get_pull_request(
                    settings, repository=active_repo, pr_number=linked_pr_num
                )
                pr_cache[linked_pr_num] = pr_data
                pr_lookups += 1
            if pr_data.get("state") != "open":
                continue
            review_update_with_pr = True
            upd_open_prs.append(pr_data)

            review_requested = _pull_request_has_review_request(pr_data)
            if not review_requested:
                cached_rr = pr_review_request_cache.get(linked_pr_num)
                if cached_rr is None:
                    cached_rr = _pull_request_has_review_request_history(
                        settings,
                        repository=active_repo,
                        pr_number=linked_pr_num,
                    )
                    pr_review_request_cache[linked_pr_num] = cached_rr
                    timeline_lookups += 1
                review_requested = cached_rr

            if _pull_request_is_merge_candidate(pr_data, review_requested=review_requested):
                review_update_ready_for_review = True
                upd_ready_prs.append(pr_data)

        review_update_issue_to_open_prs[issue_num] = upd_open_prs
        review_update_issue_to_open_ready_prs[issue_num] = upd_ready_prs

    dev_pending_paths = [p for p in pending_paths if _queue_filename(p) in set(dev_pending)]
    review_pending_paths = [p for p in pending_paths if _queue_filename(p) in set(review_pending)]
    cap_pending_paths = [p for p in pending_paths if _queue_filename(p) in set(cap_pending)]
    dev_processed_paths = [p for p in processed_paths if _queue_filename(p) in set(dev_processed)]
    review_processed_paths = [
        p for p in processed_paths if _queue_filename(p) in set(review_processed)
    ]
    cap_processed_paths = [p for p in processed_paths if _queue_filename(p) in set(cap_processed)]

    dev_inflight_paths = dev_pending_paths + dev_processed_paths
    review_inflight_paths = review_pending_paths + review_processed_paths
    cap_inflight_paths = cap_pending_paths + cap_processed_paths

    def _has_associated_open_pr(queue_path: str) -> bool:
        issue_num = queue_issue_numbers.get(queue_path)
        if issue_num is None:
            return False
        return bool(issue_to_open_prs.get(issue_num))

    def _has_associated_ready_pr(queue_path: str) -> bool:
        issue_num = queue_issue_numbers.get(queue_path)
        if issue_num is None:
            return False
        return bool(issue_to_open_ready_prs.get(issue_num))

    dev_with_pr = [p for p in dev_inflight_paths if _has_associated_open_pr(p)]
    dev_ready_for_review = [p for p in dev_inflight_paths if _has_associated_ready_pr(p)]
    review_with_pr = [p for p in review_inflight_paths if _has_associated_open_pr(p)]
    review_ready_for_review = [p for p in review_inflight_paths if _has_associated_ready_pr(p)]

    cap_with_pr = [p for p in cap_inflight_paths if _has_associated_open_pr(p)]
    cap_ready_for_review = [p for p in cap_inflight_paths if _has_associated_ready_pr(p)]

    dev_unpromoted = [p for p in dev_pending_paths if queue_issue_numbers.get(p) is None]
    review_unpromoted = [p for p in review_pending_paths if queue_issue_numbers.get(p) is None]
    dev_promoted_no_pr = [
        p
        for p in dev_pending_paths
        if queue_issue_numbers.get(p) is not None and not _has_associated_open_pr(p)
    ]
    review_promoted_no_pr = [
        p
        for p in review_pending_paths
        if queue_issue_numbers.get(p) is not None and not _has_associated_open_pr(p)
    ]
    cap_unpromoted = [p for p in cap_pending_paths if queue_issue_numbers.get(p) is None]
    cap_promoted_no_pr = [
        p
        for p in cap_pending_paths
        if queue_issue_numbers.get(p) is not None and not _has_associated_open_pr(p)
    ]

    # --- Stage selection (priority is loop order) ---
    # Stages are stable 1a–3c; labels vary by loop mode.
    if mode == "review":
        # Review intake (Step 1)
        if review_intake_issue_nums:
            if review_intake_ready_for_review:
                stage = "1c"
                stage_label = "1c — Review intake PR ready for merge"
                active_step = 2
                stage_reason = "open review intake issue has an associated open PR ready for review"
            elif review_intake_with_pr:
                stage = "1b"
                stage_label = "1b — Review intake execution"
                active_step = 1
                stage_reason = "open review intake issue has an associated open PR"
            else:
                stage = "1a"
                stage_label = "1a — Review intake issue"
                active_step = 0
                stage_reason = "open review intake issue detected (no PR yet)"
        # Review actions update (Step 3)
        elif review_update_issue_nums:
            # We intentionally reuse the E/F/G step numbers for the update phase.
            if review_update_ready_for_review:
                stage = "3c"
                stage_label = "3c — Review actions PR ready for merge"
                active_step = 8
                stage_reason = "open review update issue has an associated open PR ready for review"
            elif review_update_with_pr:
                stage = "3b"
                stage_label = "3b — Review actions update execution"
                active_step = 7
                stage_reason = "open review update issue has an associated open PR"
            else:
                stage = "3a"
                stage_label = "3a — Review actions update issue"
                active_step = 6
                stage_reason = "open review update issue exists (no PR yet)"
        # Development (Step 2) from review queue artefacts
        elif review_pending or review_processed or dev_pending or dev_processed:
            work_inflight_paths = review_inflight_paths + dev_inflight_paths
            work_unpromoted = review_unpromoted + dev_unpromoted
            work_ready = review_ready_for_review + dev_ready_for_review
            work_with_pr = review_with_pr + dev_with_pr
            work_promoted_no_pr = review_promoted_no_pr + dev_promoted_no_pr

            if work_unpromoted:
                stage = "2a"
                stage_label = "2a — Development issue creation"
                active_step = 3
                stage_reason = "pending work queue file(s) exist without an associated open issue"
            elif work_ready:
                stage = "2c"
                stage_label = "2c — Development PR ready for merge"
                active_step = 5
                stage_reason = "work has an open PR with review requested and no conflicts"
            else:
                stage = "2b"
                stage_label = "2b — Development execution"
                active_step = 4
                if work_with_pr:
                    stage_reason = "pending work queue file(s) have an associated open PR"
                else:
                    stage_reason = (
                        "pending work queue file(s) have an associated open issue but no PR yet"
                    )
        elif processed_count > 0:
            stage = "2b"
            stage_label = "2b — Development execution"
            active_step = 4
            stage_reason = "processed queue artefacts exist"
        else:
            stage = "1a"
            stage_label = "1a — Review intake issue"
            active_step = 0
            stage_reason = "no pending/processed artefacts"

    # Build mode (existing semantics)
    elif has_open_gap_analysis_issue:
        if gap_issue_ready_for_review:
            stage = "1c"
            stage_label = "1c — Gap analysis PR ready for merge"
            active_step = 2
            stage_reason = "open gap analysis issue has an associated open PR ready for review"
        elif gap_issue_with_pr:
            stage = "1b"
            stage_label = "1b — Gap analysis execution"
            active_step = 1
            stage_reason = "open gap analysis issue has an associated open PR"
        else:
            stage = "1a"
            stage_label = "1a — Gap analysis issue"
            active_step = 0
            stage_reason = "open gap analysis issue detected (no PR yet)"
    elif cap_issue_nums:
        if cap_issue_ready_for_review:
            stage = "3c"
            stage_label = "3c — Capability PR ready for merge"
            active_step = 8
            stage_reason = (
                "open capability update issue exists and has an associated open PR ready for review"
            )
        elif cap_issue_with_pr:
            stage = "3b"
            stage_label = "3b — Capability update execution"
            active_step = 7
            stage_reason = "open capability update issue exists and has an associated open PR"
        else:
            stage = "3a"
            stage_label = "3a — Capability update issue"
            active_step = 6
            stage_reason = "open capability update issue exists (no PR yet)"
    elif dev_pending or dev_processed:
        if dev_unpromoted:
            stage = "2a"
            stage_label = "2a — Development issue creation"
            active_step = 3
            stage_reason = (
                "pending development queue file(s) exist without an associated open issue"
            )
        elif dev_ready_for_review:
            stage = "2c"
            stage_label = "2c — Development PR ready for merge"
            active_step = 5
            stage_reason = "development work has an open PR with review requested and no conflicts"
        else:
            stage = "2b"
            stage_label = "2b — Development execution"
            active_step = 4
            if dev_with_pr:
                stage_reason = "pending development queue file(s) have an associated open PR"
            else:
                stage_reason = (
                    "pending development queue file(s) have an associated open issue but no PR yet"
                )
    elif cap_pending or cap_processed:
        # Legacy path: capability update represented by queue artefacts.
        if cap_unpromoted:
            stage = "3a"
            stage_label = "3a — Capability update queued"
            active_step = 6
            stage_reason = (
                "pending capability update queue file(s) exist without an associated open issue"
            )
        elif cap_ready_for_review:
            stage = "3c"
            stage_label = "3c — Capability PR ready for merge"
            active_step = 8
            stage_reason = "pending capability update queue file(s) have an associated ready PR"
        else:
            stage = "3b"
            stage_label = "3b — Capability update in progress"
            active_step = 7
            stage_reason = "pending capability update queue file(s) have an associated open PR"
    elif processed_count > 0:
        stage = "2b"
        stage_label = "2b — Development execution"
        active_step = 4
        stage_reason = "processed queue artefacts exist"
    else:
        stage = "1a"
        stage_label = "1a — Gap analysis issue"
        active_step = 0
        stage_reason = "no pending/processed artefacts"

    warnings: list[str] = []
    warnings.append(
        "Loop status is derived exclusively from git-tracked files in the target repository; "
        "no local JSON stores are consulted."
    )
    warnings.append(
        "Pending queue files are associated to GitHub issues by matching the file title (first line) "
        "against open issue titles; PR association is derived from issue cross-references in GitHub."
    )
    warnings.append(
        f"Capability update issues are detected by the '{LABEL_UPDATE_CAPABILITY}' label (open issues)."
    )
    if mode == "review":
        warnings.append(
            f"Review intake issues are detected by the '{LABEL_REVIEW_CONSUMPTION}' label (open issues)."
        )
        warnings.append(
            f"Review update issues are detected by the '{LABEL_UPDATE_REVIEW}' label (open issues)."
        )

    def _first_path(paths: list[str]) -> str | None:
        if not paths:
            return None
        return sorted(paths)[0]

    focus: dict[str, object] | None = None
    if mode == "review" and stage in {"1a", "1b", "1c"} and review_intake_issue_nums:
        issue_num = sorted(review_intake_issue_nums)[0]
        title = open_issue_titles_by_number.get(issue_num) or ""

        prs = review_intake_issue_to_open_prs.get(issue_num) or []
        ready_prs = review_intake_issue_to_open_ready_prs.get(issue_num) or []
        selected_pr = ready_prs[0] if ready_prs else (prs[0] if prs else None)

        focus_pr_num: int | None = None
        focus_pr_url: str | None = None
        if isinstance(selected_pr, dict):
            raw_pr_num = selected_pr.get("number")
            if isinstance(raw_pr_num, int):
                focus_pr_num = raw_pr_num
            raw_pr_url = selected_pr.get("html_url")
            if isinstance(raw_pr_url, str) and raw_pr_url.strip():
                focus_pr_url = raw_pr_url

        focus = {
            "kind": "review",
            "title": title,
            "issueNumber": issue_num,
            "issueUrl": _make_github_issue_url(active_repo, issue_num),
            "pullNumber": focus_pr_num,
            "pullUrl": focus_pr_url,
        }
    elif mode == "review" and stage in {"3a", "3b", "3c"} and review_update_issue_nums:
        issue_num = sorted(review_update_issue_nums)[0]
        title = open_issue_titles_by_number.get(issue_num) or ""

        prs = review_update_issue_to_open_prs.get(issue_num) or []
        ready_prs = review_update_issue_to_open_ready_prs.get(issue_num) or []
        selected_pr = ready_prs[0] if ready_prs else (prs[0] if prs else None)

        upd_focus_pr_num: int | None = None
        upd_focus_pr_url: str | None = None
        if isinstance(selected_pr, dict):
            raw_pr_num = selected_pr.get("number")
            if isinstance(raw_pr_num, int):
                upd_focus_pr_num = raw_pr_num
            raw_pr_url = selected_pr.get("html_url")
            if isinstance(raw_pr_url, str) and raw_pr_url.strip():
                upd_focus_pr_url = raw_pr_url

        focus = {
            "kind": "reviewUpdate",
            "title": title,
            "issueNumber": issue_num,
            "issueUrl": _make_github_issue_url(active_repo, issue_num),
            "pullNumber": upd_focus_pr_num,
            "pullUrl": upd_focus_pr_url,
        }
    elif stage in {"1a", "1b", "1c"} and gap_issue_nums:
        issue_num = gap_issue_nums[0]
        title = open_issue_titles_by_number.get(issue_num) or ""

        prs = gap_issue_to_open_prs.get(issue_num) or []
        ready_prs = gap_issue_to_open_ready_prs.get(issue_num) or []
        selected_pr = ready_prs[0] if ready_prs else (prs[0] if prs else None)

        gap_focus_pr_num: int | None = None
        gap_focus_pr_url: str | None = None
        if isinstance(selected_pr, dict):
            raw_pr_num = selected_pr.get("number")
            if isinstance(raw_pr_num, int):
                gap_focus_pr_num = raw_pr_num
            raw_pr_url = selected_pr.get("html_url")
            if isinstance(raw_pr_url, str) and raw_pr_url.strip():
                gap_focus_pr_url = raw_pr_url

        focus = {
            "kind": "gap",
            "title": title,
            "issueNumber": issue_num,
            "issueUrl": _make_github_issue_url(active_repo, issue_num),
            "pullNumber": gap_focus_pr_num,
            "pullUrl": gap_focus_pr_url,
        }
    elif stage in {"2a", "2b", "2c"}:
        # In review mode, Step 2 spans both review queue artefacts and development queue artefacts.
        if mode == "review":
            inflight_paths = review_inflight_paths + dev_inflight_paths
            unpromoted_paths = review_unpromoted + dev_unpromoted
            ready_paths = review_ready_for_review + dev_ready_for_review
            with_pr_paths = review_with_pr + dev_with_pr
        else:
            inflight_paths = dev_inflight_paths
            unpromoted_paths = dev_unpromoted
            ready_paths = dev_ready_for_review
            with_pr_paths = dev_with_pr

        if stage == "2a":
            focus_path = _first_path(unpromoted_paths)
        elif stage == "2c":
            focus_path = _first_path(ready_paths)
        else:
            # Prefer items that already have PRs, then fall back to any inflight item.
            focus_path = _first_path(with_pr_paths) or _first_path(inflight_paths)

        if focus_path:
            issue_num = queue_issue_numbers.get(focus_path)
            focus_pr_num: int | None = None
            focus_pr_url: str | None = None
            if isinstance(issue_num, int):
                prs = issue_to_open_prs.get(issue_num) or []
                ready_prs = issue_to_open_ready_prs.get(issue_num) or []
                selected_pr = ready_prs[0] if ready_prs else (prs[0] if prs else None)
                if isinstance(selected_pr, dict):
                    raw_pr_num = selected_pr.get("number")
                    if isinstance(raw_pr_num, int):
                        focus_pr_num = raw_pr_num
                    raw_pr_url = selected_pr.get("html_url")
                    if isinstance(raw_pr_url, str) and raw_pr_url.strip():
                        focus_pr_url = raw_pr_url

            title = queue_display_titles.get(focus_path) or ""
            if isinstance(issue_num, int) and issue_num in open_issue_titles_by_number:
                # If we have a clean match, prefer the canonical issue title.
                title = open_issue_titles_by_number.get(issue_num) or title

            focus = {
                "kind": "development",
                "queuePath": focus_path,
                "queueId": _queue_filename(focus_path),
                "title": title,
                "issueNumber": issue_num,
                "issueUrl": (
                    _make_github_issue_url(active_repo, int(issue_num))
                    if isinstance(issue_num, int)
                    else None
                ),
                "pullNumber": focus_pr_num,
                "pullUrl": focus_pr_url,
            }
    elif stage in {"3a", "3b", "3c"} and cap_issue_nums:
        issue_num = sorted(cap_issue_nums)[0]
        title = open_issue_titles_by_number.get(issue_num) or ""

        # Attempt to recover the original (merged) PR that triggered this capability-update issue.
        # This is more useful for operator context than the templated capability issue title.
        issue_body = ""
        issue_title_for_parse = title
        try:
            issue_data = _github_get_json(
                settings,
                url=_repo_api_url(settings, repository=active_repo, path=f"issues/{issue_num}"),
            )
            raw_body = issue_data.get("body")
            raw_title = issue_data.get("title")
            if isinstance(raw_body, str):
                issue_body = raw_body
            if isinstance(raw_title, str) and raw_title.strip():
                issue_title_for_parse = raw_title
        except HTTPException:
            # Best-effort only: lack of issue body shouldn't break loop display.
            issue_body = ""

        source_pr_number = _extract_source_pr_number_from_capability_issue(
            repository=active_repo,
            issue_title=issue_title_for_parse,
            issue_body=issue_body,
        )
        source_pr_title: str | None = None
        source_pr_url: str | None = None
        if isinstance(source_pr_number, int):
            try:
                source_pr = _get_pull_request(
                    settings,
                    repository=active_repo,
                    pr_number=source_pr_number,
                )
                raw_title = source_pr.get("title")
                if isinstance(raw_title, str) and raw_title.strip():
                    source_pr_title = raw_title
                raw_url = source_pr.get("html_url")
                if isinstance(raw_url, str) and raw_url.strip():
                    source_pr_url = raw_url
            except HTTPException:
                source_pr_title = None
                source_pr_url = None
        prs = cap_issue_to_open_prs.get(issue_num) or []
        ready_prs = cap_issue_to_open_ready_prs.get(issue_num) or []
        selected_pr = ready_prs[0] if ready_prs else (prs[0] if prs else None)

        cap_focus_pr_num: int | None = None
        cap_focus_pr_url: str | None = None
        if isinstance(selected_pr, dict):
            raw_pr_num = selected_pr.get("number")
            if isinstance(raw_pr_num, int):
                cap_focus_pr_num = raw_pr_num
            raw_pr_url = selected_pr.get("html_url")
            if isinstance(raw_pr_url, str) and raw_pr_url.strip():
                cap_focus_pr_url = raw_pr_url

        focus = {
            "kind": "capability",
            "title": title,
            "issueNumber": issue_num,
            "issueUrl": _make_github_issue_url(active_repo, issue_num),
            "pullNumber": cap_focus_pr_num,
            "pullUrl": cap_focus_pr_url,
            "sourceTitle": source_pr_title,
            "sourcePullNumber": source_pr_number,
            "sourcePullUrl": source_pr_url,
        }

    # Best-effort automation: if configured, auto-link the focused issue to a likely PR.
    # This addresses cases where Copilot opened a PR without adding `Fixes #<issue>`.
    if isinstance(focus, dict):
        link_msg = _maybe_auto_link_focused_issue_to_pr(
            settings=settings,
            repository=active_repo,
            focus=focus,
            raw_open_prs=raw_open_prs,
        )
        if isinstance(link_msg, str) and link_msg.strip():
            warnings.append(link_msg)

    # Best-effort automation: if configured, auto-nudge Copilot to resume after a rate limit stop.
    # This is intentionally scoped to the focused PR only to avoid scanning the entire repo.
    if settings.auto_resume_copilot_on_rate_limit and isinstance(focus, dict):
        focus_pull_number = focus.get("pullNumber")
        if isinstance(focus_pull_number, int) and focus_pull_number > 0:
            msg = _maybe_auto_resume_copilot_after_rate_limit(
                settings=settings,
                repository=active_repo,
                pr_number=focus_pull_number,
            )
            if isinstance(msg, str) and msg.strip():
                warnings.append(msg)

    return {
        "nowIso": _utc_now_iso(),
        "repo": active_repo,
        "ref": (ref or None),
        "loopMode": mode,
        "stage": stage,
        "stageLabel": stage_label,
        "activeStep": active_step,
        "stageReason": stage_reason,
        "sources": {
            "queueCounts": "github_git_tree",
        },
        "counts": {
            "pending": pending_count,
            "processed": processed_count,
            "complete": complete_count,
            "openIssues": len(open_issue_titles),
            "openPullRequests": open_pr_count,
            "openGapAnalysisIssues": len(gap_issue_nums),
            "openGapAnalysisIssuesWithPr": (1 if gap_issue_with_pr else 0),
            "openGapAnalysisIssuesReadyForReview": (1 if gap_issue_ready_for_review else 0),
            "openReviewConsumptionIssues": len(set(open_review_consumption_issue_numbers)),
            "openReviewUpdateIssues": len(set(open_review_update_issue_numbers)),
            "unpromotedPending": len(
                [p for p in pending_paths if queue_issue_numbers.get(p) is None]
            ),
            "pendingDevelopment": len(dev_pending),
            "pendingReview": len(review_pending),
            "pendingCapabilityUpdates": len(cap_pending),
            "pendingExcluded": len(excluded_pending),
            "pendingDevelopmentWithoutPr": len(dev_promoted_no_pr),
            "pendingDevelopmentWithPr": len(dev_with_pr),
            "pendingDevelopmentReadyForReview": len(dev_ready_for_review),
            "pendingReviewWithoutPr": len(review_promoted_no_pr),
            "pendingReviewWithPr": len(review_with_pr),
            "pendingReviewReadyForReview": len(review_ready_for_review),
            "pendingCapabilityUpdatesWithoutPr": len(cap_promoted_no_pr),
            "pendingCapabilityUpdatesWithPr": len(cap_with_pr),
            "pendingCapabilityUpdatesReadyForReview": len(cap_ready_for_review),
            # Issue-driven capability update signals.
            "openCapabilityUpdateIssues": len(cap_issue_nums),
            "openCapabilityUpdateIssuesWithPr": (1 if cap_issue_with_pr else 0),
            "openCapabilityUpdateIssuesReadyForReview": (1 if cap_issue_ready_for_review else 0),
        },
        "debug": {
            "pendingQueueFilesSample": pending_paths[:20],
            "processedQueueFilesSample": processed_paths[:20],
            "completeQueueFilesSample": complete_paths[:20],
            "pendingExcludedPrefixes": list(_QUEUE_EXCLUDED_PREFIXES),
            "gapAnalysisIssueTitles": list(_GAP_ANALYSIS_TITLES),
            "issueTimelineLookups": timeline_lookups,
            "pullRequestLookups": pr_lookups,
        },
        "warnings": warnings,
        "focus": focus,
        "runningJob": None,
        "lastAction": None,
    }
