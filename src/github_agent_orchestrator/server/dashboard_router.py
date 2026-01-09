"""Dashboard-focused REST API.

This router implements the endpoints used by the React dashboard in `ui/`.

All routes are mounted under `/api`.
"""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query, Request

from github_agent_orchestrator import __version__
from github_agent_orchestrator.github_labels import (
    LABEL_REVIEW_CONSUMPTION,
)
from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard import text_utilities as _text_utilities
from github_agent_orchestrator.server.dashboard.github_api import (
    _github_delete_json,
    _github_get_json,
    _github_headers,
    _github_post_json,
    _github_put_json,
    _repo_api_url,
)
from github_agent_orchestrator.server.dashboard.github_issue_pr_helpers import (
    issue_has_label as _issue_has_label,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    ensure_repo_label_exists as _ensure_repo_label_exists,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    get_default_branch as _get_default_branch,
)
from github_agent_orchestrator.server.dashboard.github_operations import (
    get_repo_text_file as _get_repo_text_file,
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
from github_agent_orchestrator.server.dashboard.loop_actions import (
    _ensure_gap_analysis_issue_exists as _ensure_gap_analysis_issue_exists,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    _gap_analysis_issue_body_looks_unsafe as _gap_analysis_issue_body_looks_unsafe,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    _load_gap_analysis_template_or_raise as _load_gap_analysis_template_or_raise,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    _load_review_actions_after_merge_template_or_raise as _load_review_actions_after_merge_template_or_raise,
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
    _repair_gap_analysis_issue_body_if_unsafe as _repair_gap_analysis_issue_body_if_unsafe,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    ensure_gap_analysis_issue as ensure_gap_analysis_issue,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    heal_orphaned_processed_queue_items as heal_orphaned_processed_queue_items,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    merge_next_ready_development_pull_request as merge_next_ready_development_pull_request,
)
from github_agent_orchestrator.server.dashboard.loop_actions import (
    promote_next_pending_issue_queue_item as promote_next_pending_issue_queue_item,
)
from github_agent_orchestrator.server.dashboard.loop_status import (
    _queue_file_is_excluded_for_loop_mode as _queue_file_is_excluded_for_loop_mode,
)
from github_agent_orchestrator.server.dashboard.loop_status import loop_status as loop_status
from github_agent_orchestrator.server.dashboard.queue_helpers import (
    _is_gap_analysis_issue_title,
)
from github_agent_orchestrator.server.dashboard.text_utilities import (
    _dt_from_iso,
    _normalize_repo_path_candidate,
    _utc_now_iso,
)
from github_agent_orchestrator.server.local_templates import load_local_template_or_raise

router = APIRouter()


# --- Compatibility shims (tests + intra-module monkeypatching) ---
#
# Several modules (and unit tests) monkeypatch these names on `dashboard_router` to ensure
# deterministic behavior and prevent accidental real GitHub API calls.
#
# Ruff may remove unused imports; keeping these as small wrapper functions ensures they
# remain available without relying on unused re-exports.

_AUTO_LINK_NOTICE_MARKER = _text_utilities._AUTO_LINK_NOTICE_MARKER
_COPILOT_RATE_LIMIT_RESUME_COMMENT = _text_utilities._COPILOT_RATE_LIMIT_RESUME_COMMENT


def _comment_body_is_auto_link_notice(body: str) -> bool:
    return _text_utilities._comment_body_is_auto_link_notice(body)


def _comment_body_is_copilot_resume_nudge(body: str) -> bool:
    return _text_utilities._comment_body_is_copilot_resume_nudge(body)


def _github_get_list(
    settings: ServerSettings, *, url: str, params: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    from github_agent_orchestrator.server.dashboard.github_api import _github_get_list as _impl

    return _impl(settings, url=url, params=params)


def _github_patch_json(
    settings: ServerSettings,
    *,
    url: str,
    payload: dict[str, Any],
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    from github_agent_orchestrator.server.dashboard.github_api import _github_patch_json as _impl

    return _impl(settings, url=url, payload=payload, params=params)


def _list_issue_timeline_raw(
    settings: ServerSettings, *, repository: str, issue_number: int
) -> list[dict[str, Any]]:
    """Compatibility shim for tests and helper functions.

    The dashboard test suite monkeypatches `dashboard_router._list_issue_timeline_raw` to
    prevent accidental real GitHub API calls.
    """

    from github_agent_orchestrator.server.dashboard.github_operations import (
        list_issue_timeline_raw as _impl,
    )

    return _impl(settings, repository=repository, issue_number=issue_number)


def _list_open_pull_requests_raw(
    settings: ServerSettings, *, repository: str, limit: int = 30
) -> list[dict[str, Any]]:
    from github_agent_orchestrator.server.dashboard.github_operations import (
        list_open_pull_requests_raw as _impl,
    )

    return _impl(settings, repository=repository, limit=limit)


def _get_pull_request(
    settings: ServerSettings, *, repository: str, pr_number: int
) -> dict[str, Any]:
    from github_agent_orchestrator.server.dashboard.github_operations import (
        get_pull_request as _impl,
    )

    return _impl(settings, repository=repository, pr_number=pr_number)


def _search_issue_number_by_queue_marker(
    settings: ServerSettings, *, repository: str, queue_id: str
) -> int | None:
    from github_agent_orchestrator.server.dashboard.queue_helpers import (
        _search_issue_number_by_queue_marker as _impl,
    )

    return _impl(settings, repository=repository, queue_id=queue_id)


def _normalize_issue_title(title: str) -> str:
    from github_agent_orchestrator.server.dashboard.text_utilities import (
        _normalize_issue_title as _impl,
    )

    return _impl(title)


def _strip_fenced_code_blocks(markdown: str) -> str:
    from github_agent_orchestrator.server.dashboard.text_utilities import (
        _strip_fenced_code_blocks as _impl,
    )

    return _impl(markdown)


def _utc_now() -> datetime:
    from github_agent_orchestrator.server.dashboard.text_utilities import _utc_now as _impl

    return _impl()


def _list_issue_comments_raw(
    settings: ServerSettings, *, repository: str, issue_number: int
) -> list[dict[str, Any]]:
    from github_agent_orchestrator.server.dashboard.github_operations import (
        list_issue_comments_raw as _impl,
    )

    return _impl(settings, repository=repository, issue_number=issue_number)


def _list_issue_events_raw(
    settings: ServerSettings, *, repository: str, issue_number: int
) -> list[dict[str, Any]]:
    from github_agent_orchestrator.server.dashboard.github_operations import (
        list_issue_events_raw as _impl,
    )

    return _impl(settings, repository=repository, issue_number=issue_number)


def _github_graphql_post(
    settings: ServerSettings,
    *,
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from github_agent_orchestrator.server.dashboard.github_api import _github_graphql_post as _impl

    return _impl(settings, query=query, variables=variables)


# Apply router decorators to imported loop action endpoints
promote_next_pending_issue_queue_item = router.post("/loop/promote")(
    promote_next_pending_issue_queue_item
)
ensure_gap_analysis_issue = router.post("/loop/gap-analysis/ensure")(ensure_gap_analysis_issue)
merge_next_ready_development_pull_request = router.post("/loop/merge")(
    merge_next_ready_development_pull_request
)
heal_orphaned_processed_queue_items = router.post("/loop/heal")(
    heal_orphaned_processed_queue_items
)

# Apply router decorator to imported loop status endpoint
loop_status = router.get("/loop")(loop_status)


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
    """Load the review-consumption issue template from the local repository."""

    _ = (settings, repo, branch)

    attempts: list[str] = []
    for template_path in _REVIEW_CONSUMPTION_TEMPLATE_PATHS:
        try:
            return load_local_template_or_raise(relative_path=template_path)
        except HTTPException as e:
            attempts.append(f"{template_path}: {getattr(e, 'detail', '')}")

    tried = "; ".join(attempts[:3])
    more = "" if len(attempts) <= 3 else f" (+{len(attempts) - 3} more)"
    raise HTTPException(
        status_code=502,
        detail=(
            "Unable to load local review consumption template. "
            "Expected planning/issue_templates/review-consumption.md. "
            f"Attempts: {tried}{more}"
        ),
    )


def _review_actions_path_for_review_path(review_path: str) -> str:
    p = Path(review_path)
    if p.suffix.lower() == ".md":
        return str(p.with_suffix(".actions.md")).replace("\\", "/")
    return f"{review_path}.actions.md"


def _ensure_repo_text_file_present(
    *,
    settings: ServerSettings,
    repo: str,
    branch: str,
    path: str,
    content_text: str,
    message: str,
) -> None:
    """Best-effort create-or-update for a text file in the target repository."""

    url = _repo_api_url(settings, repository=repo, path=f"contents/{path}")
    encoded = base64.b64encode(content_text.encode("utf-8")).decode("utf-8")
    payload: dict[str, Any] = {
        "message": message,
        "content": encoded,
        "branch": branch,
    }

    status, body = _github_put_json(settings, url=url, payload=payload)
    if status == 201:
        return
    if status == 422:
        existing = _github_get_json(settings, url=url, params={"ref": branch})
        sha = existing.get("sha")
        if isinstance(sha, str) and sha.strip():
            payload["sha"] = sha
            status2, _body2 = _github_put_json(settings, url=url, payload=payload)
            if status2 in {200, 201}:
                return

    raise HTTPException(
        status_code=502,
        detail=f"Failed to write repo file (HTTP {status}) at {path}: {body}",
    )


def _delete_repo_file_if_present(
    *,
    settings: ServerSettings,
    repo: str,
    branch: str,
    path: str,
    sha: str,
    message: str,
) -> None:
    url = _repo_api_url(settings, repository=repo, path=f"contents/{path}")
    payload = {"message": message, "sha": sha, "branch": branch}
    status, body = _github_delete_json(settings, url=url, payload=payload)
    if status in {200, 204, 404}:
        return
    raise HTTPException(
        status_code=502,
        detail=f"Failed to delete repo file (HTTP {status}) at {path}: {body}",
    )


def _review_consumption_issue_has_linked_pull_requests(
    *, timeline: list[dict[str, Any]]
) -> bool:
    """Conservative check: if timeline contains any cross-referenced PR, treat as linked."""

    for ev in timeline:
        if not isinstance(ev, dict):
            continue
        if ev.get("event") != "cross-referenced":
            continue
        src = ev.get("source")
        if not isinstance(src, dict):
            continue
        issue = src.get("issue")
        if not isinstance(issue, dict):
            continue
        if "pull_request" in issue:
            return True
    return False


def _archive_review_and_actions_if_present(
    *, settings: ServerSettings, repo: str, branch: str, review_path: str
) -> None:
    """Move a review artefact and its actions file (if present) into planning/reviews/completed/."""

    completed_dir = "planning/reviews/completed"
    actions_path = _review_actions_path_for_review_path(review_path)

    for src_path in [review_path, actions_path]:
        try:
            content, sha = _get_repo_text_file(
                settings,
                repository=repo,
                path=src_path,
                ref=branch,
            )
        except HTTPException as e:
            # Actions files are allowed to be missing.
            if e.status_code == 404:
                continue
            raise

        dest_path = f"{completed_dir}/{Path(src_path).name}"
        _ensure_repo_text_file_present(
            settings=settings,
            repo=repo,
            branch=branch,
            path=dest_path,
            content_text=content,
            message=f"Archive {Path(src_path).name} (review complete)",
        )
        _delete_repo_file_if_present(
            settings=settings,
            repo=repo,
            branch=branch,
            path=src_path,
            sha=sha,
            message=f"Remove {Path(src_path).name} from active reviews (review complete)",
        )


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
        # Reviews under planning/reviews/completed/ are archived and must be ignored.
        norm = p.replace("\\", "/")
        if "/completed/" in norm:
            continue
        name = Path(p).name.lower()
        if not name.startswith("review-"):
            continue
        if name.endswith(".actions.md"):
            continue
        candidates.append(p)
    return sorted(candidates)[0] if candidates else None


def _issue_is_assigned_to_login(issue: dict[str, Any], *, login: str) -> bool:
    assignees = issue.get("assignees")
    if not isinstance(assignees, list):
        return False
    return any(isinstance(a, dict) and a.get("login") == login for a in assignees)


def _first_open_review_consumption_issue_number(
    raw_issues: list[object],
    *,
    copilot_login: str,
) -> tuple[int | None, bool]:
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
        return num, _issue_is_assigned_to_login(it, login=copilot_login)
    return None, False


def _review_consumption_candidate_should_be_archived(
    *,
    settings: ServerSettings,
    repo: str,
    branch: str,
    review_path: str,
) -> bool:
    """Return True if the review should be archived as fully consumed.

    We only archive a review when the most recent review-consumption issue for that review
    was closed *without producing a queue artefact* (per the review-consumption template's
    completion check).

    A closed review-consumption issue can also mean: "this run produced a queue item and the
    issue was closed after its PR merged". In that case we must NOT archive the review; we
    should allow Step 1a to run again to generate the next work item.
    """

    marker = f"{_REVIEW_CONSUMPTION_MARKER_PREFIX} {review_path}"
    existing = _search_issue_number_by_body_marker(
        settings,
        repository=repo,
        marker=marker,
        state="closed",
    )
    if existing is None:
        return False

    issue = _github_get_json(
        settings,
        url=_repo_api_url(settings, repository=repo, path=f"issues/{existing}"),
    )
    if not isinstance(issue, dict) or issue.get("state") != "closed":
        return False

    created_at = issue.get("created_at")
    closed_at = issue.get("closed_at")
    created_dt = _dt_from_iso(created_at) if isinstance(created_at, str) else None
    closed_dt = _dt_from_iso(closed_at) if isinstance(closed_at, str) else None
    created_epoch = int(created_dt.timestamp()) if created_dt is not None else None
    closed_epoch = int(closed_dt.timestamp()) if closed_dt is not None else None

    # If we can find a review queue artefact created during the lifetime of this issue (and
    # referring to this review), then work exists and the review must remain active.
    if _review_consumption_issue_produced_queue_output(
        settings=settings,
        repo=repo,
        branch=branch,
        review_path=review_path,
        issue_created_epoch=created_epoch,
        issue_closed_epoch=closed_epoch,
    ):
        return False

    return True


def _queue_item_epoch_seconds_from_queue_id(queue_id: str) -> int | None:
    """Best-effort timestamp extraction from a queue id.

    Supports:
    - review-<unix_seconds>-...
    - review-YYYY-MM-DD-...

    Returns unix epoch seconds, or None if unknown.
    """

    m = re.match(r"^review-(\d{9,12})(?:\b|-)" , queue_id)
    if m is not None:
        try:
            return int(m.group(1))
        except Exception:
            return None

    m = re.match(r"^review-(\d{4}-\d{2}-\d{2})(?:\b|-)" , queue_id, flags=re.IGNORECASE)
    if m is None:
        return None
    try:
        dt = datetime.fromisoformat(m.group(1)).replace(tzinfo=UTC)
        return int(dt.timestamp())
    except Exception:
        return None


def _review_consumption_issue_produced_queue_output(
    *,
    settings: ServerSettings,
    repo: str,
    branch: str,
    review_path: str,
    issue_created_epoch: int | None,
    issue_closed_epoch: int | None,
) -> bool:
    """Return True if there is evidence this issue produced review work.

    Why this is intentionally heuristic:
    - The review-consumption template *asks* the agent to produce a queue artefact, but does not
      strictly enforce that the artefact includes a machine-parseable `Source review:` line.
    - Review filenames are not guaranteed to follow `review-YYYY-MM-DD.md`.

    Therefore we treat either of these as evidence of output:
    1) A `review-*.md` queue artefact whose queue-id timestamp falls within the issue lifetime.
       (This is the most reliable signal when queue ids include epoch seconds.)
    2) Fallback: queue content explicitly references `review_path` via parsed `Source review:`.
    """

    queue_dirs = (
        "planning/issue_queue/pending",
        "planning/issue_queue/processed",
        "planning/issue_queue/complete",
    )

    candidates: list[str] = []
    for d in queue_dirs:
        try:
            paths = _list_repo_markdown_files_under(
                settings=settings,
                repository=repo,
                dir_path=d,
                ref=branch,
            )
        except Exception:
            continue
        for p in paths:
            name = Path(p).name
            if name.lower().startswith("review-"):
                candidates.append(p)

    # If we have timestamps, narrow to items plausibly created during the issue run.
    def in_window(queue_id: str) -> tuple[bool, int | None]:
        ts = _queue_item_epoch_seconds_from_queue_id(queue_id)
        if ts is None:
            return True, None
        if issue_created_epoch is not None and ts < issue_created_epoch - 60:
            return False, ts
        if issue_closed_epoch is not None and ts > issue_closed_epoch + 3600:
            return False, ts
        return True, ts

    for p in sorted(set(candidates)):
        queue_id = Path(p).name
        ok, ts = in_window(queue_id)
        if not ok:
            continue

        # Primary signal: if the queue id encodes time and it falls within the issue window,
        # we consider this evidence that the review-consumption issue produced output.
        # This avoids relying on the LLM-authored queue file structure.
        if ts is not None and issue_created_epoch is not None:
            return True

        try:
            content, _sha = _get_repo_text_file(
                settings,
                repository=repo,
                path=p,
                ref=branch,
            )
        except Exception:
            continue

        extracted_review_path, _extracted_actions_path = _extract_review_paths_from_queue_content(
            queue_id=queue_id,
            queue_content=content,
        )
        if extracted_review_path == review_path:
            return True
    return False


def _select_next_review_consumption_target_or_raise(
    *,
    settings: ServerSettings,
    repo: str,
    branch: str,
) -> tuple[str, str]:
    while True:
        review_path = _pick_next_review_file(settings=settings, repo=repo, branch=branch)
        if review_path is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "No uncompleted review files found under planning/reviews "
                    "(expected review-*.md)"
                ),
            )

        if not _review_consumption_candidate_should_be_archived(
            settings=settings,
            repo=repo,
            branch=branch,
            review_path=review_path,
        ):
            return review_path, _review_actions_path_for_review_path(review_path)

        _archive_review_and_actions_if_present(
            settings=settings,
            repo=repo,
            branch=branch,
            review_path=review_path,
        )


def _ensure_review_consumption_issue_exists(
    *, settings: ServerSettings, repo: str
) -> dict[str, object]:
    """Ensure there is exactly one open review-consumption issue (best-effort).

    In review mode, Step 1a is "review consumption": read a review artefact and produce the
    next concrete work item in `/planning/issue_queue/pending/`.
    """

    branch = _get_default_branch(settings, repository=repo)

    raw_issues = _list_open_issues_raw(settings, repository=repo)
    existing_num, already_assigned = _first_open_review_consumption_issue_number(
        raw_issues,
        copilot_login=settings.copilot_assignee,
    )
    if isinstance(existing_num, int):
        assigned: list[dict[str, Any]] | list[str] = []
        if not already_assigned:
            assigned = _assign_issue_to_copilot(
                settings,
                repository=repo,
                issue_number=existing_num,
                target_repo=repo,
                base_branch=branch,
                instructions="",
            )
        return {
            "created": False,
            "issueNumber": existing_num,
            "issueUrl": _make_github_issue_url(repo, existing_num),
            "assigned": assigned,
        }

    if not settings.github_token.strip():
        raise HTTPException(
            status_code=409,
            detail="ORCHESTRATOR_GITHUB_TOKEN is required to create review consumption issues",
        )

    # If the next review was already processed and the last review-consumption run produced no PR
    # (per the template's completion check), archive the review and move on.
    review_path, actions_path = _select_next_review_consumption_target_or_raise(
        settings=settings,
        repo=repo,
        branch=branch,
    )

    template_body = _load_review_consumption_template_or_raise(
        settings=settings, repo=repo, branch=branch
    )
    marker = f"{_REVIEW_CONSUMPTION_MARKER_PREFIX} {review_path}"
    body = (
        template_body.replace("{{REVIEW_PATH}}", review_path)
        .replace("{{REVIEW_ACTIONS_PATH}}", actions_path or "")
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


def _assign_issue_to_copilot(
    settings: ServerSettings,
    *,
    repository: str,
    issue_number: int,
    target_repo: str,
    base_branch: str,
    instructions: str,
) -> list[str]:
    _enforce_safe_assignment_or_raise(
        settings=settings,
        repository=repository,
        issue_number=issue_number,
        base_branch=base_branch,
    )

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


def _enforce_safe_assignment_or_raise(
    *,
    settings: ServerSettings,
    repository: str,
    issue_number: int,
    base_branch: str,
) -> None:
    """Before assigning, repair or block known-unsafe gap-analysis instructions (best-effort)."""

    # This guard lives here (the single assignment choke-point) so ALL call sites benefit.
    try:
        issue = _github_get_json(
            settings,
            url=_repo_api_url(settings, repository=repository, path=f"issues/{issue_number}"),
        )
    except HTTPException as e:
        # Only block assignment when we are explicitly refusing due to known-unsafe instructions.
        # Any other HTTPException here is likely from the best-effort issue fetch.
        if e.status_code == 409:
            raise
        return
    except Exception:
        # Best-effort: if we can't read the issue body for any reason, don't block assignment.
        return

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
        return

    if isinstance(body, str) and _gap_analysis_issue_body_looks_unsafe(body):
        # These phrases should only appear in a gap analysis issue; refuse to assign
        # anything else until it is corrected.
        raise HTTPException(
            status_code=409,
            detail=(
                f"Refusing to assign issue #{issue_number}: body contains known-unsafe gap-analysis "
                "instructions"
            ),
        )


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


def _review_path_from_queue_line(line: str) -> str | None:
    m = _REVIEW_QUEUE_SOURCE_RE.match(line)
    if not m:
        return None
    return _normalize_repo_path_candidate(m.group(1) or "")


def _review_actions_path_from_queue_line(line: str) -> str | None:
    m = _REVIEW_QUEUE_ACTIONS_RE.match(line)
    if not m:
        return None
    return _normalize_repo_path_candidate(m.group(1) or "")


def _scan_review_paths_in_queue_lines(queue_content: str) -> tuple[str | None, str | None]:
    review_path: str | None = None
    actions_path: str | None = None

    for raw in (queue_content or "").splitlines():
        line = raw.strip("\n")

        if review_path is None:
            candidate = _review_path_from_queue_line(line)
            if candidate:
                review_path = candidate

        if actions_path is None:
            candidate = _review_actions_path_from_queue_line(line)
            if candidate:
                actions_path = candidate

    return review_path, actions_path


def _extract_review_paths_from_queue_content(
    *, queue_id: str, queue_content: str
) -> tuple[str | None, str | None]:
    """Best-effort extraction of the source review + actions paths from a queue artefact."""

    review_path, actions_path = _scan_review_paths_in_queue_lines(queue_content)

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
    # Cognitive task templates are defined by this orchestrator repo.
    # Do not load them from the target repository.
    _ = (settings, repository, ref)
    from github_agent_orchestrator.server.local_templates import _find_repo_root

    root = _find_repo_root()
    template_dir = root / "planning" / "issue_templates"
    if not template_dir.exists() or not template_dir.is_dir():
        raise HTTPException(
            status_code=502,
            detail=f"Local template directory not found: {template_dir}",
        )

    paths = [
        str(p.relative_to(root)).replace("\\", "/")
        for p in template_dir.rglob("*.md")
        if p.is_file()
    ]

    tasks: list[dict[str, object]] = []
    for p in paths:
        content = load_local_template_or_raise(relative_path=p)
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


def _timeline_entry_from_commit(c: object) -> dict[str, object] | None:
    if not isinstance(c, dict):
        return None
    sha = c.get("sha")
    commit = c.get("commit")
    if not isinstance(commit, dict):
        return None
    message = commit.get("message")
    author = commit.get("author")
    if not isinstance(author, dict):
        return None
    ts = author.get("date")
    if not isinstance(ts, str):
        return None

    summary = message.splitlines()[0] if isinstance(message, str) and message else "Commit"
    link = c.get("html_url")
    return {
        "id": str(sha or ""),
        "tsIso": ts,
        "kind": "GIT_COMMIT",
        "summary": summary,
        "typePath": "planning",
        "links": ([{"label": "Commit", "url": link}] if link else None),
    }


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

    out = [e for e in (_timeline_entry_from_commit(c) for c in raw) if e is not None]

    out.sort(key=lambda e: str(e.get("tsIso") or ""), reverse=True)
    return out[:limit]


def _issue_row_from_github_item(
    *,
    repo: str,
    it: object,
    now: datetime,
) -> dict[str, object] | None:
    if not isinstance(it, dict):
        return None
    if "pull_request" in it:
        return None

    num = it.get("number")
    title = it.get("title")
    if not isinstance(num, int) or not isinstance(title, str):
        return None

    state = it.get("state")
    created_at = it.get("created_at")
    updated_at = it.get("updated_at")
    html_url = it.get("html_url")

    st = "OPEN" if state == "open" else "CLOSED"
    created_dt = _dt_from_iso(created_at) if isinstance(created_at, str) else now
    age_seconds = max(0, int((now - created_dt).total_seconds()))

    return {
        "id": str(num),
        "title": title,
        "typePath": "github/issues",
        "status": st,
        "ageSeconds": age_seconds,
        "githubIssueUrl": (str(html_url) if isinstance(html_url, str) else _make_github_issue_url(repo, num)),
        "prUrl": None,
        "lastUpdatedIso": (str(updated_at) if isinstance(updated_at, str) else _utc_now_iso()),
        "isActive": False,
    }


@router.get("/issues")
def list_issues(request: Request, status: str = Query(default="open")) -> list[dict[str, object]]:
    settings = _settings(request)
    repo = _active_repo(request, settings)
    _active_ref(request)

    # GitHub issues API (not local state). Note: this includes PRs; we filter those out.
    desired_state = "open" if status == "open" else "all"
    params: dict[str, str] = {"state": desired_state, "per_page": "100"}

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
    mapped = [
        r
        for r in (
            _issue_row_from_github_item(repo=repo, it=it, now=now)
            for it in raw
        )
        if r is not None
    ]

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
