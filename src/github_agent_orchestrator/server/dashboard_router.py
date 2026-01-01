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

from github_agent_orchestrator.server.config import ServerSettings

router = APIRouter()


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
    out: set[int] = set()
    for ev in timeline:
        if not isinstance(ev, dict):
            continue
        if ev.get("event") != "cross-referenced":
            continue
        source = ev.get("source")
        if not isinstance(source, dict):
            continue
        issue = source.get("issue")
        if not isinstance(issue, dict):
            continue
        if "pull_request" not in issue:
            continue
        num = issue.get("number")
        if isinstance(num, int):
            out.add(num)
    return out


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
    # 1) Open issues: used to detect the dedicated Gap Analysis issue.
    raw_issues = _list_open_issues_raw(settings, repository=active_repo)
    open_issue_titles: list[str] = []
    for it in raw_issues:
        if "pull_request" in it:
            continue
        title = it.get("title")
        if isinstance(title, str):
            open_issue_titles.append(title)
    has_open_gap_analysis_issue = any(_is_gap_analysis_issue_title(t) for t in open_issue_titles)

    # 2) Open PRs: used for top-level counts.
    raw_open_prs = _list_open_pull_requests_raw(settings, repository=active_repo, limit=100)
    open_pr_count = len(raw_open_prs)

    pending_files = [_queue_filename(p) for p in pending_paths]
    pending_by_category: dict[str, list[str]] = {}
    for filename in pending_files:
        pending_by_category.setdefault(_queue_category_for_filename(filename), []).append(filename)

    dev_pending = pending_by_category.get("development", [])
    cap_pending = pending_by_category.get("capability", [])
    # Excluded from dev/cap stage heuristics (tracked for visibility).
    excluded_pending = [f for f in pending_files if f.lower().startswith(_QUEUE_EXCLUDED_PREFIXES)]

    # Associate pending queue files -> GitHub issues by matching the file title (first line)
    # to open issue titles. Then associate issues -> PRs via issue timeline cross-references.
    pending_titles: dict[str, str] = {}
    pending_issue_numbers: dict[str, int | None] = {}
    issue_to_open_prs: dict[int, list[dict[str, Any]]] = {}
    issue_to_open_ready_prs: dict[int, list[dict[str, Any]]] = {}
    pr_lookups = 0
    timeline_lookups = 0

    open_issues_for_matching = [it for it in raw_issues if isinstance(it, dict)]
    pr_cache: dict[int, dict[str, Any]] = {}

    for pending_path in pending_paths:
        content, _sha = _get_repo_text_file(
            settings,
            repository=active_repo,
            path=pending_path,
            ref=ref,
        )
        title_norm = _first_markdown_line_as_title(content)
        pending_titles[pending_path] = title_norm
        issue_num = _best_match_issue_number(title_norm, open_issues_for_matching)
        pending_issue_numbers[pending_path] = issue_num

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
                if pr_data.get("draft") is False:
                    ready_prs.append(pr_data)

            issue_to_open_prs[issue_num] = open_prs
            issue_to_open_ready_prs[issue_num] = ready_prs

    dev_pending_paths = [p for p in pending_paths if _queue_filename(p) in set(dev_pending)]
    cap_pending_paths = [p for p in pending_paths if _queue_filename(p) in set(cap_pending)]

    def _has_associated_open_pr(pending_path: str) -> bool:
        issue_num = pending_issue_numbers.get(pending_path)
        if issue_num is None:
            return False
        return bool(issue_to_open_prs.get(issue_num))

    def _has_associated_ready_pr(pending_path: str) -> bool:
        issue_num = pending_issue_numbers.get(pending_path)
        if issue_num is None:
            return False
        return bool(issue_to_open_ready_prs.get(issue_num))

    dev_without_pr = [p for p in dev_pending_paths if not _has_associated_open_pr(p)]
    dev_with_pr = [p for p in dev_pending_paths if _has_associated_open_pr(p)]
    dev_ready_for_review = [p for p in dev_pending_paths if _has_associated_ready_pr(p)]

    cap_without_pr = [p for p in cap_pending_paths if not _has_associated_open_pr(p)]
    cap_with_pr = [p for p in cap_pending_paths if _has_associated_open_pr(p)]
    cap_ready_for_review = [p for p in cap_pending_paths if _has_associated_ready_pr(p)]

    # --- Stage selection (priority is loop order) ---
    if has_open_gap_analysis_issue:
        stage = "A"
        stage_label = "Gap analysis"
        active_step = 0
        stage_reason = "open gap analysis issue detected"
    elif dev_pending:
        if dev_without_pr:
            stage = "B"
            stage_label = "Issue creation"
            active_step = 1
            stage_reason = "pending development queue file(s) exist without an associated open PR"
        elif dev_ready_for_review:
            stage = "D"
            stage_label = "PR ready for review"
            active_step = 3
            stage_reason = "pending development queue file(s) have an open non-draft PR"
        else:
            stage = "C"
            stage_label = "Development (Copilot)"
            active_step = 2
            stage_reason = "pending development queue file(s) have an associated open PR"
    elif cap_pending:
        if cap_without_pr:
            stage = "E"
            stage_label = "Capability update queued"
            active_step = 4
            stage_reason = (
                "pending capability update queue file(s) exist without an associated open PR"
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
            "unpromotedPending": None,
            "pendingDevelopment": len(dev_pending),
            "pendingCapabilityUpdates": len(cap_pending),
            "pendingExcluded": len(excluded_pending),
            "pendingDevelopmentWithoutPr": len(dev_without_pr),
            "pendingDevelopmentWithPr": len(dev_with_pr),
            "pendingDevelopmentReadyForReview": len(dev_ready_for_review),
            "pendingCapabilityUpdatesWithoutPr": len(cap_without_pr),
            "pendingCapabilityUpdatesWithPr": len(cap_with_pr),
            "pendingCapabilityUpdatesReadyForReview": len(cap_ready_for_review),
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
        "runningJob": None,
        "lastAction": None,
    }
