"""Dashboard-focused REST API.

This router implements the endpoints used by the React dashboard in `ui/`.

All routes are mounted under `/api`.
"""

from __future__ import annotations

import base64
import difflib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query, Request

from github_agent_orchestrator.github_labels import (
    LABEL_DEVELOPMENT,
    LABEL_UPDATE_CAPABILITY,
    fixed_label_spec_by_name,
)
from github_agent_orchestrator.orchestrator.planning.issue_queue import QUEUE_MARKER_PREFIX
from github_agent_orchestrator.server.config import ServerSettings

router = APIRouter()


# Marker used to make capability-update issues (created after merges) idempotent.
_CAPABILITY_UPDATE_FROM_PR_MARKER_PREFIX = "orchestrator:capability-update-from-pr"


# Conventions for orchestrator-created artefacts.
#
# These prefixes are used to (a) detect system-managed workstreams and (b) exclude them
# from unrelated stage heuristics.
_QUEUE_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "review-",  # derived from review docs; handled separately
    "system-",  # system capability updates
    "capability-",
    "capabilities-",
    "maintenance-",
)

_QUEUE_CAPABILITY_PREFIXES: tuple[str, ...] = (
    "system-",
    "capability-",
    "capabilities-",
)

# We control the title of the gap analysis issue, so we can safely detect it by title.
_GAP_ANALYSIS_TITLES: tuple[str, ...] = ("identify the next most important development gap",)


def _settings(request: Request) -> ServerSettings:
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, ServerSettings):
        # This should never happen for the real app, but keeps the API fail-fast.
        raise HTTPException(status_code=500, detail="Server settings not configured")
    return settings


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _dt_from_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(tz=UTC)


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


def _github_headers(settings: ServerSettings) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-agent-orchestrator",
    }
    if settings.github_token.strip():
        headers["Authorization"] = f"Bearer {settings.github_token.strip()}"
    return headers


def _repo_api_url(settings: ServerSettings, *, repository: str, path: str) -> str:
    base = settings.github_base_url.rstrip("/")
    repo = repository.strip().strip("/")
    clean_path = path.lstrip("/")
    if clean_path:
        return f"{base}/repos/{repo}/{clean_path}"
    return f"{base}/repos/{repo}"


def _graphql_api_url(settings: ServerSettings) -> str:
    """Return the GitHub GraphQL endpoint for the configured base URL.

    GitHub.com uses https://api.github.com/graphql.
    GitHub Enterprise Server typically uses https://<host>/api/graphql, while REST is /api/v3.
    """

    base = settings.github_base_url.rstrip("/")
    if base.endswith("/api/v3"):
        return base[: -len("/api/v3")] + "/api/graphql"
    return f"{base}/graphql"


def _github_graphql_post(
    settings: ServerSettings,
    *,
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST a GraphQL query/mutation to GitHub.

    GitHub GraphQL errors are returned in the JSON body under "errors" with HTTP 200.
    Callers should inspect the returned payload.
    """

    url = _graphql_api_url(settings)
    payload: dict[str, Any] = {"query": query}
    if variables is not None:
        payload["variables"] = variables

    resp = requests.post(
        url,
        headers=_github_headers(settings),
        json=payload,
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        hint = ""
        if status in {401, 403}:
            hint = (
                "Check ORCHESTRATOR_GITHUB_TOKEN (missing/expired/insufficient scopes) and that it "
                "has access to the repository."
            )
        raise HTTPException(
            status_code=502,
            detail=f"GitHub GraphQL request failed with HTTP {status} for {url}. {hint}".strip(),
        ) from e

    data: Any
    try:
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail="Unexpected GitHub GraphQL response") from e

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Unexpected GitHub GraphQL response")
    return data


def _graphql_errors_as_message(payload: dict[str, Any]) -> str | None:
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return None

    messages: list[str] = []
    for err in errors:
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str) and msg.strip():
                messages.append(msg.strip())

    if messages:
        # Keep the message concise for UI surfacing.
        return "; ".join(messages[:3])
    return str(errors)[:500]


def _github_get_json(
    settings: ServerSettings, *, url: str, params: dict[str, str] | None = None
) -> dict[str, Any]:
    resp = requests.get(
        url,
        headers=_github_headers(settings),
        params=params or None,
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        hint = ""
        if status in {401, 403}:
            hint = (
                "Check ORCHESTRATOR_GITHUB_TOKEN (missing/expired/insufficient scopes) and that it "
                "has access to the repository."
            )
        elif status == 404:
            hint = (
                "Repository or path not found. If the repo is private, GitHub may return 404 when the "
                "token lacks access."
            )

        raise HTTPException(
            status_code=502,
            detail=f"GitHub API request failed with HTTP {status} for {url}. {hint}".strip(),
        ) from e

    data: Any = resp.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Unexpected GitHub API response")
    return data


def _github_post_json(
    settings: ServerSettings,
    *,
    url: str,
    payload: dict[str, Any],
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    resp = requests.post(
        url,
        headers=_github_headers(settings),
        params=params or None,
        json=payload,
        timeout=30,
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        hint = ""
        if status in {401, 403}:
            hint = (
                "Check ORCHESTRATOR_GITHUB_TOKEN (missing/expired/insufficient scopes) and that it "
                "has access to the repository."
            )
        elif status == 404:
            hint = (
                "Repository or endpoint not found. If the repo is private, GitHub may return 404 when the "
                "token lacks access."
            )

        raise HTTPException(
            status_code=502,
            detail=f"GitHub API request failed with HTTP {status} for {url}. {hint}".strip(),
        ) from e

    data: Any = resp.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Unexpected GitHub API response")
    return data


def _github_post_json_with_status(
    settings: ServerSettings,
    *,
    url: str,
    payload: dict[str, Any],
    params: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | str | None]:
    """POST JSON and return (status, body) without raising.

    This mirrors _github_put_json and is used when callers want to interpret
    specific GitHub error statuses for state transitions.
    """

    resp = requests.post(
        url,
        headers=_github_headers(settings),
        params=params or None,
        json=payload,
        timeout=30,
    )
    status = resp.status_code
    if status >= 400:
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return status, body

    try:
        data = resp.json()
    except Exception:
        data = None
    return status, data


def _github_put_json(
    settings: ServerSettings,
    *,
    url: str,
    payload: dict[str, Any],
    params: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | str | None]:
    resp = requests.put(
        url,
        headers=_github_headers(settings),
        params=params or None,
        json=payload,
        timeout=30,
    )
    status = resp.status_code
    if status >= 400:
        # Caller may handle specific statuses (e.g. 422 for missing sha).
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return status, body

    try:
        data = resp.json()
    except Exception:
        data = None
    return status, data


def _github_delete_json(
    settings: ServerSettings,
    *,
    url: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | str | None]:
    resp = requests.delete(
        url,
        headers=_github_headers(settings),
        json=payload or None,
        timeout=30,
    )
    status = resp.status_code
    if status >= 400:
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return status, body
    if status == 204:
        return status, None
    try:
        data = resp.json()
    except Exception:
        data = None
    return status, data


def _ensure_repo_label_exists(
    settings: ServerSettings, *, repository: str, label_name: str
) -> None:
    """Ensure a GitHub label exists in the target repository.

    This is best-effort and idempotent:
    - 201 => created
    - 422 => already exists (or validation failed)
    """

    spec = fixed_label_spec_by_name(label_name)
    if spec is None:
        raise ValueError(f"Not a fixed label: {label_name!r}")

    url = _repo_api_url(settings, repository=repository, path="labels")
    resp = requests.post(
        url,
        headers=_github_headers(settings),
        json={
            "name": spec.name,
            "color": spec.color,
            "description": spec.description,
        },
        timeout=30,
    )

    if resp.status_code in {200, 201}:
        return

    if resp.status_code == 422:
        # Most commonly: label already exists. Treat as success.
        return

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        raise HTTPException(
            status_code=502,
            detail=(
                f"GitHub API request failed with HTTP {status} for {url} while ensuring label."
            ),
        ) from e


def _github_get_list(
    settings: ServerSettings, *, url: str, params: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    resp = requests.get(
        url,
        headers=_github_headers(settings),
        params=params or None,
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        hint = ""
        if status in {401, 403}:
            hint = (
                "Check ORCHESTRATOR_GITHUB_TOKEN (missing/expired/insufficient scopes) and that it "
                "has access to the repository."
            )
        elif status == 404:
            hint = (
                "Repository or path not found. If the repo is private, GitHub may return 404 when the "
                "token lacks access."
            )

        raise HTTPException(
            status_code=502,
            detail=f"GitHub API request failed with HTTP {status} for {url}. {hint}".strip(),
        ) from e

    data: Any = resp.json()
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="Unexpected GitHub API response")
    out: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            out.append(item)
    return out


def _github_get_list_with_headers(
    *,
    url: str,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    resp = requests.get(
        url,
        headers=headers,
        params=params or None,
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = resp.status_code
        hint = ""
        if status in {401, 403}:
            hint = (
                "Check ORCHESTRATOR_GITHUB_TOKEN (missing/expired/insufficient scopes) and that it "
                "has access to the repository."
            )
        elif status == 404:
            hint = (
                "Repository or endpoint not found. If the repo is private, GitHub may return 404 when "
                "the token lacks access."
            )

        raise HTTPException(
            status_code=502,
            detail=f"GitHub API request failed with HTTP {status} for {url}. {hint}".strip(),
        ) from e

    data: Any = resp.json()
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="Unexpected GitHub API response")
    out: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            out.append(item)
    return out


def _queue_filename(path: str) -> str:
    return Path(path).name


def _queue_category_for_filename(filename: str) -> str:
    lowered = filename.lower()
    if lowered.startswith("review-"):
        return "review"
    if lowered.startswith(_QUEUE_CAPABILITY_PREFIXES):
        return "capability"
    if lowered.startswith("gap-"):
        return "gap"
    if lowered.startswith("maintenance-"):
        return "maintenance"
    return "development"


def _is_gap_analysis_issue_title(title: str) -> bool:
    lowered = title.strip().lower()
    if not lowered:
        return False
    return any(lowered == t for t in _GAP_ANALYSIS_TITLES)


def _list_open_issues_raw(settings: ServerSettings, *, repository: str) -> list[dict[str, Any]]:
    # GitHub issues API includes PRs; the caller can filter.
    return _github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path="issues"),
        params={"state": "open", "per_page": "100"},
    )


def _list_open_pull_requests_raw(
    settings: ServerSettings, *, repository: str, limit: int = 30
) -> list[dict[str, Any]]:
    per_page = str(max(1, min(limit, 100)))
    return _github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path="pulls"),
        params={"state": "open", "per_page": per_page, "sort": "updated", "direction": "desc"},
    )


def _get_pull_request(
    settings: ServerSettings, *, repository: str, pr_number: int
) -> dict[str, Any]:
    return _github_get_json(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"pulls/{pr_number}"),
    )


def _normalize_issue_title(title: str) -> str:
    """Normalize a title for matching.

    We intentionally keep this simple and deterministic.
    """

    t = title.strip()
    if t.lstrip().startswith("#"):
        t = t.lstrip().lstrip("#").strip()
    return " ".join(t.lower().split())


def _first_markdown_line_as_title(content: str) -> str:
    for raw in content.splitlines():
        line = raw.strip("\n")
        if not line.strip():
            continue
        return _normalize_issue_title(line)
    return ""


def _parse_queue_file_for_issue(*, queue_id: str, raw: str) -> tuple[str, str]:
    """Parse a queue file's raw content into (issue_title, issue_body).

    This mirrors `parse_issue_queue_item` but operates on raw strings.
    """

    lines = raw.splitlines()
    if not lines:
        raise HTTPException(status_code=422, detail=f"Queue file is empty: {queue_id}")

    first = lines[0].rstrip("\n")
    if not first.strip():
        raise HTTPException(
            status_code=422, detail=f"Queue file has an empty first line: {queue_id}"
        )

    title = first
    if title.lstrip().startswith("#"):
        title = title.lstrip().lstrip("#").strip()
    if not title:
        raise HTTPException(
            status_code=422, detail=f"Queue file title resolves to empty: {queue_id}"
        )

    marker = f"<!-- {QUEUE_MARKER_PREFIX} {queue_id} -->"
    body = raw if marker in raw else raw.rstrip() + "\n\n---\n\n" + marker + "\n"

    return title, body


def _search_issue_number_by_queue_marker(
    settings: ServerSettings, *, repository: str, queue_id: str
) -> int | None:
    # Use the search API to find any issue (open or closed) that contains our marker.
    q = f'repo:{repository} "{QUEUE_MARKER_PREFIX} {queue_id}" in:body is:issue'
    data = _github_get_json(
        settings,
        url=f"{settings.github_base_url.rstrip('/')}/search/issues",
        params={"q": q, "per_page": "5"},
    )
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return None
    num = first.get("number")
    return num if isinstance(num, int) else None


def _search_issue_number_by_body_marker(
    settings: ServerSettings, *, repository: str, marker: str
) -> int | None:
    """Search for any issue (open or closed) containing the given marker string."""

    marker_norm = marker.strip()
    if not marker_norm:
        return None

    q = f'repo:{repository} "{marker_norm}" in:body is:issue'
    data = _github_get_json(
        settings,
        url=f"{settings.github_base_url.rstrip('/')}/search/issues",
        params={"q": q, "per_page": "5"},
    )
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return None
    num = first.get("number")
    return num if isinstance(num, int) else None


def _ensure_repo_file_present_in_processed(
    settings: ServerSettings,
    *,
    repository: str,
    processed_path: str,
    content_text: str,
    branch: str,
    message: str,
) -> None:
    url = _repo_api_url(settings, repository=repository, path=f"contents/{processed_path}")
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
        # Likely "sha is missing" (file exists). Fetch sha and retry as an update.
        existing = _github_get_json(settings, url=url, params={"ref": branch})
        sha = existing.get("sha")
        if isinstance(sha, str) and sha.strip():
            payload["sha"] = sha
            status2, _body2 = _github_put_json(settings, url=url, payload=payload)
            if status2 in {200, 201}:
                return

    raise HTTPException(
        status_code=502,
        detail=f"Failed to write processed queue file (HTTP {status}) at {processed_path}: {body}",
    )


def _ensure_repo_file_present_in_complete(
    settings: ServerSettings,
    *,
    repository: str,
    complete_path: str,
    content_text: str,
    branch: str,
    message: str,
) -> None:
    url = _repo_api_url(settings, repository=repository, path=f"contents/{complete_path}")
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
        # Likely "sha is missing" (file exists). Fetch sha and retry as an update.
        existing = _github_get_json(settings, url=url, params={"ref": branch})
        sha = existing.get("sha")
        if isinstance(sha, str) and sha.strip():
            payload["sha"] = sha
            status2, _body2 = _github_put_json(settings, url=url, payload=payload)
            if status2 in {200, 201}:
                return

    raise HTTPException(
        status_code=502,
        detail=f"Failed to write complete queue file (HTTP {status}) at {complete_path}: {body}",
    )


def _delete_repo_file_if_present(
    settings: ServerSettings,
    *,
    repository: str,
    path: str,
    sha: str,
    branch: str,
    message: str,
) -> None:
    url = _repo_api_url(settings, repository=repository, path=f"contents/{path}")
    payload = {"message": message, "sha": sha, "branch": branch}
    status, body = _github_delete_json(settings, url=url, payload=payload)
    if status in {200, 204}:
        return
    if status == 404:
        return
    raise HTTPException(
        status_code=502,
        detail=f"Failed to delete queue file (HTTP {status}) at {path}: {body}",
    )


def _assign_issue_to_copilot(
    settings: ServerSettings,
    *,
    repository: str,
    issue_number: int,
    target_repo: str,
    base_branch: str,
    instructions: str,
) -> list[str]:
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
def promote_next_pending_issue_queue_item(request: Request) -> dict[str, object]:
    """Step B action: promote one pending development queue file.

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


@router.post("/loop/merge")
def merge_next_ready_development_pull_request(request: Request) -> dict[str, object]:
    """Step D action: approve + merge the next ready development PR.

    Deterministic plumbing:
    - find the next development queue item with an associated open PR that is "ready for review"
    - best-effort: mark ready for review (if draft)
    - best-effort: submit an approval review
    - attempt to merge (squash)
    - on success: move the queue file to issue_queue/complete
    - on success: create + assign a follow-up "Update Capability" issue

    This endpoint intentionally performs ONE merge per call.
    """

    settings = _settings(request)
    repo = _active_repo(request, settings)
    return _merge_next_ready_development_pull_request(settings=settings, repo=repo)


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

    # Select next unpromoted *development* item in stable order.
    candidates: list[str] = []
    for p in sorted(pending_paths):
        filename = _queue_filename(p)
        lower = filename.lower()
        if lower.startswith(_QUEUE_EXCLUDED_PREFIXES):
            continue
        if _queue_category_for_filename(filename) != "development":
            continue
        candidates.append(p)

    if not candidates:
        raise HTTPException(status_code=409, detail="No promotable development queue files found")

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


def _issue_has_label(issue: dict[str, Any], *, label_name: str) -> bool:
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return False
    for lbl in labels:
        if isinstance(lbl, dict) and lbl.get("name") == label_name:
            return True
        if isinstance(lbl, str) and lbl == label_name:
            return True
    return False


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


def _get_pull_request_discussion_markdown(
    settings: ServerSettings, *, repository: str, pr_number: int
) -> str:
    """Best-effort compact discussion rendering for a PR (issue comments + reviews + review comments)."""

    def _as_items(kind: str, raw: list[dict[str, Any]]) -> list[dict[str, str]]:
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

    issue_comments = _github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"issues/{pr_number}/comments"),
        params={"per_page": "100"},
    )
    reviews = _github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"pulls/{pr_number}/reviews"),
        params={"per_page": "100"},
    )
    review_comments = _github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"pulls/{pr_number}/comments"),
        params={"per_page": "100"},
    )

    items = (
        _as_items("issue_comment", issue_comments)
        + _as_items("review", reviews)
        + _as_items("review_comment", review_comments)
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

    candidates: list[str] = []
    for p in sorted(inflight_paths):
        filename = _queue_filename(p)
        lower = filename.lower()
        if lower.startswith(_QUEUE_EXCLUDED_PREFIXES):
            continue
        if _queue_category_for_filename(filename) != "development":
            continue
        candidates.append(p)

    selected: dict[str, Any] | None = None
    pr_approval_cache: dict[int, bool] = {}
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
            is_approved = False
            if not _pull_request_has_review_request(pr_data):
                cached_approved = pr_approval_cache.get(pr_num)
                if cached_approved is None:
                    reviews = _github_get_list(
                        settings,
                        url=_repo_api_url(
                            settings, repository=repo, path=f"pulls/{pr_num}/reviews"
                        ),
                        params={"per_page": "100"},
                    )
                    cached_approved = _pull_request_is_approved_from_reviews(reviews)
                    pr_approval_cache[pr_num] = cached_approved
                is_approved = cached_approved

            if not _pull_request_is_ready_for_review(pr_data, is_approved=is_approved):
                continue
            selected = {
                "queue_path": queue_path,
                "queue_sha": queue_sha,
                "queue_content": content,
                "queue_id": _queue_filename(queue_path),
                "issue_number": issue_num,
                "pr": pr_data,
            }
            break
        if selected is not None:
            break

    if selected is None:
        raise HTTPException(status_code=409, detail="No ready development pull requests found")

    pr_data = selected["pr"]
    pr_number = pr_data.get("number")
    if not isinstance(pr_number, int):
        raise HTTPException(status_code=502, detail="Unexpected pull request response (number)")

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

    # Create a follow-up capability update issue and assign it to Copilot.
    pr_title = pr_data.get("title")
    pr_body = pr_data.get("body")
    if not isinstance(pr_title, str):
        pr_title = ""
    if not isinstance(pr_body, str):
        pr_body = ""

    marker = f"{_CAPABILITY_UPDATE_FROM_PR_MARKER_PREFIX} {repo}#{pr_number}"
    existing_cap_issue = _search_issue_number_by_body_marker(
        settings,
        repository=repo,
        marker=marker,
    )
    cap_issue_number: int
    cap_issue_created = False
    if existing_cap_issue is None:
        _ensure_repo_label_exists(settings, repository=repo, label_name=LABEL_UPDATE_CAPABILITY)
        discussion_md = _get_pull_request_discussion_markdown(
            settings,
            repository=repo,
            pr_number=pr_number,
        )
        cap_body = _render_capability_update_issue_body(
            repo=repo,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_body=pr_body,
            discussion_markdown=discussion_md,
        )
        cap_issue = _github_post_json(
            settings,
            url=_repo_api_url(settings, repository=repo, path="issues"),
            payload={
                "title": f"Update system capabilities based on merged PR #{pr_number}",
                "body": cap_body,
                "labels": [LABEL_UPDATE_CAPABILITY],
            },
        )
        num = cap_issue.get("number")
        if not isinstance(num, int):
            raise HTTPException(status_code=502, detail="Unexpected GitHub create issue response")
        cap_issue_number = num
        cap_issue_created = True
    else:
        cap_issue_number = existing_cap_issue

    assigned = _assign_issue_to_copilot(
        settings,
        repository=repo,
        issue_number=cap_issue_number,
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
        "capabilityIssueNumber": cap_issue_number,
        "capabilityIssueCreated": cap_issue_created,
        "capabilityIssueUrl": _make_github_issue_url(repo, cap_issue_number),
        "capabilityIssueAssigned": assigned,
        "summary": f"Merged PR #{pr_number}; created capability issue #{cap_issue_number}",
    }


def _best_match_issue_number(
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


def _list_issue_timeline_raw(
    settings: ServerSettings, *, repository: str, issue_number: int
) -> list[dict[str, Any]]:
    # Timeline API is the most direct way to find cross-referenced PRs.
    # It has historically required a custom media type, so we include a fallback preview.
    headers = _github_headers(settings)
    headers["Accept"] = ", ".join(
        [
            headers.get("Accept", "application/vnd.github+json"),
            "application/vnd.github.mockingbird-preview+json",
        ]
    )
    return _github_get_list_with_headers(
        url=_repo_api_url(settings, repository=repository, path=f"issues/{issue_number}/timeline"),
        headers=headers,
        params={"per_page": "100"},
    )


def _linked_pr_numbers_from_issue_timeline(timeline: list[dict[str, Any]]) -> set[int]:
    """Extract linked PR numbers from an issue timeline.

    GitHub can represent "issue <-> PR" association in a few ways (cross-reference,
    connected events, etc.). We keep this conservative but support the common shapes
    we see in the REST timeline API.
    """

    def _extract_pr_number(ev: dict[str, Any]) -> int | None:
        # Common: cross-referenced event with nested source.issue.pull_request
        source = ev.get("source")
        if isinstance(source, dict):
            issue = source.get("issue")
            if isinstance(issue, dict) and "pull_request" in issue:
                num = issue.get("number")
                if isinstance(num, int):
                    return num

        # Some events include a "subject" object for the connected PR.
        subject = ev.get("subject")
        if isinstance(subject, dict) and "pull_request" in subject:
            num = subject.get("number")
            if isinstance(num, int):
                return num

        return None

    out: set[int] = set()
    for raw in timeline:
        if not isinstance(raw, dict):
            continue
        event = raw.get("event")
        if event not in {"cross-referenced", "connected"}:
            continue
        pr_num = _extract_pr_number(raw)
        if pr_num is not None:
            out.add(pr_num)
    return out


def _pull_request_has_review_request(pr_data: dict[str, Any]) -> bool:
    requested_reviewers = pr_data.get("requested_reviewers")
    requested_teams = pr_data.get("requested_teams")
    return bool(requested_reviewers) or bool(requested_teams)


def _pull_request_is_approved_from_reviews(reviews: list[dict[str, Any]]) -> bool:
    """Return True if the PR should be treated as "approved".

    GitHub does not expose approval status directly on the PR object. To keep this
    deterministic and REST-only, we interpret the PR reviews list:

    - Use each reviewer's latest review state.
    - Approved means: at least one APPROVED and no CHANGES_REQUESTED outstanding.
    """

    latest_by_user: dict[str, tuple[str, str]] = {}
    for raw in reviews:
        if not isinstance(raw, dict):
            continue

        state = raw.get("state")
        submitted_at = raw.get("submitted_at")
        user = raw.get("user")
        login = user.get("login") if isinstance(user, dict) else None

        if not isinstance(login, str) or not login.strip():
            continue
        if not isinstance(state, str) or not state.strip():
            continue
        if not isinstance(submitted_at, str) or not submitted_at.strip():
            continue

        key = login.strip().lower()
        prev = latest_by_user.get(key)
        if prev is None or submitted_at > prev[0]:
            latest_by_user[key] = (submitted_at, state.strip().upper())

    if not latest_by_user:
        return False

    states = [st for _ts, st in latest_by_user.values()]
    has_changes_requested = any(st == "CHANGES_REQUESTED" for st in states)
    if has_changes_requested:
        return False
    return any(st == "APPROVED" for st in states)


def _pull_request_is_ready_for_review(
    pr_data: dict[str, Any], *, is_approved: bool = False
) -> bool:
    # Must be open.
    if pr_data.get("state") != "open":
        return False

    # Must have either an explicit review request (user or team) OR already be approved.
    # Reason: once reviews are submitted, GitHub may clear requested reviewers even though
    # the PR is now "ready" to merge.
    if not (_pull_request_has_review_request(pr_data) or is_approved):
        return False

    # Should not have merge conflicts ("dirty" == conflicts in GitHub terminology).
    mergeable = pr_data.get("mergeable")
    mergeable_state = pr_data.get("mergeable_state")
    if mergeable is False:
        return False
    if isinstance(mergeable_state, str):
        return mergeable_state.lower() != "dirty"

    return True


def _get_default_branch(settings: ServerSettings, *, repository: str) -> str:
    data = _github_get_json(settings, url=_repo_api_url(settings, repository=repository, path=""))
    branch = data.get("default_branch")
    if isinstance(branch, str) and branch.strip():
        return branch
    return "main"


def _get_branch_head_commit_sha(settings: ServerSettings, *, repository: str, branch: str) -> str:
    data = _github_get_json(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"git/ref/heads/{branch}"),
    )
    obj = data.get("object")
    if not isinstance(obj, dict):
        raise HTTPException(status_code=502, detail="Unexpected GitHub ref response")
    sha = obj.get("sha")
    if not isinstance(sha, str) or not sha.strip():
        raise HTTPException(status_code=502, detail="Unexpected GitHub ref response (sha)")
    return sha


def _get_commit_tree_sha(settings: ServerSettings, *, repository: str, commit_sha: str) -> str:
    data = _github_get_json(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"git/commits/{commit_sha}"),
    )
    tree = data.get("tree")
    if not isinstance(tree, dict):
        raise HTTPException(status_code=502, detail="Unexpected GitHub commit response")
    sha = tree.get("sha")
    if not isinstance(sha, str) or not sha.strip():
        raise HTTPException(status_code=502, detail="Unexpected GitHub commit response (tree sha)")
    return sha


def _get_repo_tree_recursive(
    settings: ServerSettings, *, repository: str, tree_sha: str
) -> list[dict[str, Any]]:
    data = _github_get_json(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"git/trees/{tree_sha}"),
        params={"recursive": "1"},
    )
    items = data.get("tree")
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Unexpected GitHub tree response")
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            out.append(item)
    return out


def _get_repo_text_file(
    settings: ServerSettings, *, repository: str, path: str, ref: str
) -> tuple[str, str]:
    norm = path.lstrip("/")
    params: dict[str, str] | None = {"ref": ref} if ref.strip() else None
    data = _github_get_json(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"contents/{norm}"),
        params=params,
    )
    content = data.get("content")
    encoding = data.get("encoding")
    sha = data.get("sha")
    if not isinstance(sha, str):
        sha = ""
    if not isinstance(content, str) or encoding != "base64":
        raise HTTPException(
            status_code=502, detail=f"Unexpected GitHub contents response for {path}"
        )
    try:
        raw = base64.b64decode(content.encode("utf-8"), validate=False)
        return raw.decode("utf-8"), sha
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to decode repo file: {path}") from e


def _list_repo_markdown_files_under(
    *,
    settings: ServerSettings,
    repository: str,
    dir_path: str,
    ref: str,
) -> list[str]:
    """List markdown file paths under a directory in a GitHub repo (recursive).

    This is intentionally read-only and does not require a local checkout.

    Returns:
        Paths relative to repo root.
    """

    resolved_ref = ref.strip() or _get_default_branch(settings, repository=repository)
    commit_sha = _get_branch_head_commit_sha(
        settings,
        repository=repository,
        branch=resolved_ref,
    )
    tree_sha = _get_commit_tree_sha(settings, repository=repository, commit_sha=commit_sha)
    items = _get_repo_tree_recursive(settings, repository=repository, tree_sha=tree_sha)

    prefix = dir_path.strip().lstrip("/").rstrip("/") + "/"
    out: list[str] = []
    for item in items:
        if item.get("type") != "blob":
            continue
        path = item.get("path")
        if not isinstance(path, str):
            continue
        if not path.startswith(prefix):
            continue
        if not path.lower().endswith(".md"):
            continue
        out.append(path)
    out.sort()
    return out


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
def health() -> dict[str, str]:
    return {"status": "ok"}


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
    """Return a UI-friendly summary of the orchestrator's A–G loop.

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
    for it in raw_issues:
        if "pull_request" in it:
            continue
        num = it.get("number")
        title = it.get("title")
        if isinstance(title, str):
            open_issue_titles.append(title)
        if isinstance(num, int) and _issue_has_label(it, label_name=LABEL_UPDATE_CAPABILITY):
            open_capability_issue_numbers.append(num)

    has_open_gap_analysis_issue = any(_is_gap_analysis_issue_title(t) for t in open_issue_titles)

    raw_open_prs = _list_open_pull_requests_raw(settings, repository=active_repo, limit=100)
    open_pr_count = len(raw_open_prs)

    pending_files = [_queue_filename(p) for p in pending_paths]
    pending_by_category: dict[str, list[str]] = {}
    for filename in pending_files:
        pending_by_category.setdefault(_queue_category_for_filename(filename), []).append(filename)

    dev_pending = pending_by_category.get("development", [])
    cap_pending = pending_by_category.get("capability", [])
    excluded_pending = [f for f in pending_files if f.lower().startswith(_QUEUE_EXCLUDED_PREFIXES)]

    processed_files = [_queue_filename(p) for p in processed_paths]
    processed_by_category: dict[str, list[str]] = {}
    for filename in processed_files:
        processed_by_category.setdefault(_queue_category_for_filename(filename), []).append(
            filename
        )

    dev_processed = processed_by_category.get("development", [])
    cap_processed = processed_by_category.get("capability", [])

    # Associate queue files (pending + processed) -> GitHub issues by matching the file title
    # (first line) to open issue titles. Then associate issues -> PRs via issue timeline events.
    queue_issue_numbers: dict[str, int | None] = {}
    issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    pr_lookups = 0
    pr_review_lookups = 0
    timeline_lookups = 0

    open_issues_for_matching = [it for it in raw_issues if isinstance(it, dict)]
    pr_cache: dict[int, dict[str, Any]] = {}
    pr_approval_cache: dict[int, bool] = {}

    queue_paths_for_linkage = list(pending_paths) + list(processed_paths)
    for queue_path in queue_paths_for_linkage:
        content, _sha = _get_repo_text_file(
            settings,
            repository=active_repo,
            path=queue_path,
            ref=ref,
        )
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

                is_approved = False
                if not _pull_request_has_review_request(pr_data):
                    cached_approved = pr_approval_cache.get(pr_num)
                    if cached_approved is None:
                        reviews = _github_get_list(
                            settings,
                            url=_repo_api_url(
                                settings, repository=active_repo, path=f"pulls/{pr_num}/reviews"
                            ),
                            params={"per_page": "100"},
                        )
                        pr_review_lookups += 1
                        cached_approved = _pull_request_is_approved_from_reviews(reviews)
                        pr_approval_cache[pr_num] = cached_approved
                    is_approved = cached_approved

                if _pull_request_is_ready_for_review(pr_data, is_approved=is_approved):
                    ready_prs.append(pr_data)

            issue_to_open_prs[issue_num] = open_prs
            issue_to_open_ready_prs[issue_num] = ready_prs

    # Capability update issues (Step E/F) are derived from labels, not queue files.
    cap_issue_nums = sorted(set(open_capability_issue_numbers))
    cap_issue_with_pr = False
    cap_issue_ready_for_review = False
    for issue_num in cap_issue_nums:
        if issue_num in issue_to_open_prs:
            cap_issue_with_pr = cap_issue_with_pr or bool(issue_to_open_prs.get(issue_num))
            cap_issue_ready_for_review = cap_issue_ready_for_review or bool(
                issue_to_open_ready_prs.get(issue_num)
            )
            continue

        timeline = _list_issue_timeline_raw(
            settings, repository=active_repo, issue_number=issue_num
        )
        timeline_lookups += 1
        pr_nums = _linked_pr_numbers_from_issue_timeline(timeline)
        for pr_num in sorted(pr_nums):
            pr_data = pr_cache.get(pr_num)
            if pr_data is None:
                pr_data = _get_pull_request(settings, repository=active_repo, pr_number=pr_num)
                pr_cache[pr_num] = pr_data
                pr_lookups += 1
            if pr_data.get("state") != "open":
                continue
            cap_issue_with_pr = True

            is_approved = False
            if not _pull_request_has_review_request(pr_data):
                cached_approved = pr_approval_cache.get(pr_num)
                if cached_approved is None:
                    reviews = _github_get_list(
                        settings,
                        url=_repo_api_url(
                            settings, repository=active_repo, path=f"pulls/{pr_num}/reviews"
                        ),
                        params={"per_page": "100"},
                    )
                    pr_review_lookups += 1
                    cached_approved = _pull_request_is_approved_from_reviews(reviews)
                    pr_approval_cache[pr_num] = cached_approved
                is_approved = cached_approved

            if _pull_request_is_ready_for_review(pr_data, is_approved=is_approved):
                cap_issue_ready_for_review = True

    dev_pending_paths = [p for p in pending_paths if _queue_filename(p) in set(dev_pending)]
    cap_pending_paths = [p for p in pending_paths if _queue_filename(p) in set(cap_pending)]
    dev_processed_paths = [p for p in processed_paths if _queue_filename(p) in set(dev_processed)]
    cap_processed_paths = [p for p in processed_paths if _queue_filename(p) in set(cap_processed)]

    dev_inflight_paths = dev_pending_paths + dev_processed_paths
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

    cap_with_pr = [p for p in cap_inflight_paths if _has_associated_open_pr(p)]
    cap_ready_for_review = [p for p in cap_inflight_paths if _has_associated_ready_pr(p)]

    dev_unpromoted = [p for p in dev_pending_paths if queue_issue_numbers.get(p) is None]
    dev_promoted_no_pr = [
        p
        for p in dev_pending_paths
        if queue_issue_numbers.get(p) is not None and not _has_associated_open_pr(p)
    ]
    cap_unpromoted = [p for p in cap_pending_paths if queue_issue_numbers.get(p) is None]
    cap_promoted_no_pr = [
        p
        for p in cap_pending_paths
        if queue_issue_numbers.get(p) is not None and not _has_associated_open_pr(p)
    ]

    # --- Stage selection (priority is loop order) ---
    if has_open_gap_analysis_issue:
        stage = "A"
        stage_label = "Gap analysis"
        active_step = 0
        stage_reason = "open gap analysis issue detected"
    elif cap_issue_nums:
        if cap_issue_with_pr:
            stage = "F"
            stage_label = "Capability update execution"
            active_step = 5
            stage_reason = "open capability update issue exists and has an associated open PR"
        else:
            stage = "E"
            stage_label = "Capability update issue"
            active_step = 4
            stage_reason = "open capability update issue exists (no PR yet)"
    elif dev_pending or dev_processed:
        if dev_unpromoted:
            stage = "B"
            stage_label = "Issue creation"
            active_step = 1
            stage_reason = (
                "pending development queue file(s) exist without an associated open issue"
            )
        elif dev_ready_for_review:
            stage = "D"
            stage_label = "PR ready for review"
            active_step = 3
            stage_reason = "development work has an open PR with review requested and no conflicts"
        elif dev_with_pr:
            stage = "C"
            stage_label = "Development (Copilot)"
            active_step = 2
            stage_reason = "pending development queue file(s) have an associated open PR"
        else:
            stage = "C"
            stage_label = "Development (Copilot)"
            active_step = 2
            stage_reason = (
                "pending development queue file(s) have an associated open issue but no PR yet"
            )
    elif cap_pending or cap_processed:
        # Legacy path: capability update represented by queue artefacts.
        if cap_unpromoted:
            stage = "E"
            stage_label = "Capability update queued"
            active_step = 4
            stage_reason = (
                "pending capability update queue file(s) exist without an associated open issue"
            )
        else:
            stage = "F"
            stage_label = "Capability update in progress"
            active_step = 5
            stage_reason = "pending capability update queue file(s) have an associated open PR"
    elif processed_count > 0:
        stage = "C"
        stage_label = "Development (Copilot)"
        active_step = 2
        stage_reason = "processed queue artefacts exist"
    else:
        stage = "A"
        stage_label = "Gap analysis"
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

    return {
        "nowIso": _utc_now_iso(),
        "repo": active_repo,
        "ref": (ref or None),
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
            "openGapAnalysisIssues": (1 if has_open_gap_analysis_issue else 0),
            "unpromotedPending": len(
                [p for p in pending_paths if queue_issue_numbers.get(p) is None]
            ),
            "pendingDevelopment": len(dev_pending),
            "pendingCapabilityUpdates": len(cap_pending),
            "pendingExcluded": len(excluded_pending),
            "pendingDevelopmentWithoutPr": len(dev_promoted_no_pr),
            "pendingDevelopmentWithPr": len(dev_with_pr),
            "pendingDevelopmentReadyForReview": len(dev_ready_for_review),
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
            "pullRequestReviewLookups": pr_review_lookups,
        },
        "warnings": warnings,
        "runningJob": None,
        "lastAction": None,
    }
