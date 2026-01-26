"""GitHub API operations for dashboard modules.

This module provides a central collection of GitHub API wrapper functions
that can be imported by dashboard helper modules without creating circular
dependencies.

All functions are thin wrappers around the low-level GitHub API client functions
from github_api.py. They handle repository-specific operations like fetching
issues, PRs, repository files, and managing repository state.
"""

from __future__ import annotations

import base64
from typing import Any

import requests
from fastapi import HTTPException

from github_agent_orchestrator.github_labels import fixed_label_spec_by_name
from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard.github_api import (
    _github_delete_json,
    _github_get_json,
    _github_get_list,
    _github_get_list_with_headers,
    _github_headers,
    _github_put_json,
    _repo_api_url,
)


def list_issue_comments_raw(
    settings: ServerSettings, *, repository: str, issue_number: int
) -> list[dict[str, Any]]:
    """List comments on an issue or PR."""
    return _github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"issues/{issue_number}/comments"),
        params={"per_page": "100"},
    )


def list_issue_events_raw(
    settings: ServerSettings, *, repository: str, issue_number: int
) -> list[dict[str, Any]]:
    """List issue/PR events (REST).

    GitHub surfaces Copilot SWE Agent lifecycle events here (e.g.
    `copilot_work_started`, `copilot_work_finished_failure`).
    """

    return _github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"issues/{issue_number}/events"),
        params={"per_page": "100"},
    )


def list_open_issues_raw(settings: ServerSettings, *, repository: str) -> list[dict[str, Any]]:
    """List open issues in a repository.

    Note: GitHub issues API includes PRs; the caller can filter.
    """
    return _github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path="issues"),
        params={"state": "open", "per_page": "100"},
    )


def list_open_pull_requests_raw(
    settings: ServerSettings, *, repository: str, limit: int = 30
) -> list[dict[str, Any]]:
    """List open pull requests in a repository."""
    per_page = str(max(1, min(limit, 100)))
    return _github_get_list(
        settings,
        url=_repo_api_url(settings, repository=repository, path="pulls"),
        params={"state": "open", "per_page": per_page, "sort": "updated", "direction": "desc"},
    )

def list_workflow_runs_for_head_sha(
    settings: ServerSettings,
    *,
    repository: str,
    head_sha: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    params = {"per_page": str(max(1, min(limit, 100))), "head_sha": head_sha}
    data = _github_get_json(
        settings,
        url=_repo_api_url(settings, repository=repository, path="actions/runs"),
        params=params,
    )
    runs = data.get("workflow_runs")
    if not isinstance(runs, list):
        return []
    return [r for r in runs if isinstance(r, dict)]


def list_workflow_jobs_for_run(
    settings: ServerSettings,
    *,
    repository: str,
    run_id: int,
) -> list[dict[str, Any]]:
    data = _github_get_json(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"actions/runs/{run_id}/jobs"),
        params={"per_page": "100"},
    )
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        return []
    return [j for j in jobs if isinstance(j, dict)]


def download_workflow_job_logs(
    settings: ServerSettings,
    *,
    repository: str,
    job_id: int,
) -> bytes:
    url = _repo_api_url(settings, repository=repository, path=f"actions/jobs/{job_id}/logs")
    resp = requests.get(url, headers=_github_headers(settings), timeout=30, allow_redirects=True)
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"GitHub API request failed with HTTP {resp.status_code} for {url}.",
        )
    return resp.content


def get_pull_request(
    settings: ServerSettings, *, repository: str, pr_number: int
) -> dict[str, Any]:
    """Get a single pull request by number."""
    return _github_get_json(
        settings,
        url=_repo_api_url(settings, repository=repository, path=f"pulls/{pr_number}"),
    )


def list_issue_timeline_raw(
    settings: ServerSettings, *, repository: str, issue_number: int
) -> list[dict[str, Any]]:
    """List issue timeline events.

    Timeline API is the most direct way to find cross-referenced PRs.
    It has historically required a custom media type, so we include a fallback preview.
    """
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


def get_default_branch(settings: ServerSettings, *, repository: str) -> str:
    """Get the default branch for a repository."""
    data = _github_get_json(settings, url=_repo_api_url(settings, repository=repository, path=""))
    branch = data.get("default_branch")
    if isinstance(branch, str) and branch.strip():
        return branch
    return "main"


def get_branch_head_commit_sha(settings: ServerSettings, *, repository: str, branch: str) -> str:
    """Get the commit SHA for the head of a branch."""
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


def get_commit_tree_sha(settings: ServerSettings, *, repository: str, commit_sha: str) -> str:
    """Get the tree SHA for a commit."""
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


def get_repo_tree_recursive(
    settings: ServerSettings, *, repository: str, tree_sha: str
) -> list[dict[str, Any]]:
    """Get a repository tree recursively."""
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


def get_repo_text_file(
    settings: ServerSettings, *, repository: str, path: str, ref: str
) -> tuple[str, str]:
    """Get the content and SHA of a text file from a repository.

    Returns:
        Tuple of (content, sha)
    """
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


def list_repo_markdown_files_under(
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

    resolved_ref = ref.strip() or get_default_branch(settings, repository=repository)
    commit_sha = get_branch_head_commit_sha(
        settings,
        repository=repository,
        branch=resolved_ref,
    )
    tree_sha = get_commit_tree_sha(settings, repository=repository, commit_sha=commit_sha)
    items = get_repo_tree_recursive(settings, repository=repository, tree_sha=tree_sha)

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


def search_issue_number_by_body_marker(
    settings: ServerSettings,
    *,
    repository: str,
    marker: str,
    state: str = "all",
) -> int | None:
    """Search for an issue containing a marker string.

    Args:
        settings: Server settings.
        repository: Target repository (e.g. "owner/name").
        marker: Marker string to search for in issue bodies.
        state: "open", "closed", or "all".

    Notes:
        We use the GitHub Search API. When markers are reused over time (e.g. multiple
        review-consumption iterations for the same review source), we prefer the most
        recently updated match.
    """

    marker_norm = marker.strip()
    if not marker_norm:
        return None

    state_norm = state.strip().lower()
    state_filter = ""
    if state_norm in {"all", "any"}:
        state_filter = ""
    elif state_norm == "open":
        state_filter = " is:open"
    elif state_norm == "closed":
        state_filter = " is:closed"
    else:
        raise ValueError(f"Unexpected issue state filter: {state!r}")

    q = f'repo:{repository} "{marker_norm}" in:body is:issue{state_filter}'
    # Use updated-desc ordering to make this deterministic for markers that may be reused over time
    # (e.g. multiple review-consumption iterations for the same review source file).
    data = _github_get_json(
        settings,
        url=f"{settings.github_base_url.rstrip('/')}/search/issues",
        params={"q": q, "per_page": "5", "sort": "updated", "order": "desc"},
    )
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return None
    num = first.get("number")
    return num if isinstance(num, int) else None


def ensure_repo_file_present_in_processed(
    settings: ServerSettings,
    *,
    repository: str,
    processed_path: str,
    content_text: str,
    branch: str,
    message: str,
) -> None:
    """Ensure a file exists in the processed queue directory."""
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


def ensure_repo_file_present_in_complete(
    settings: ServerSettings,
    *,
    repository: str,
    complete_path: str,
    content_text: str,
    branch: str,
    message: str,
) -> None:
    """Ensure a file exists in the complete queue directory."""
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


def ensure_repo_text_file_present(
    settings: ServerSettings,
    *,
    repository: str,
    path: str,
    content_text: str,
    branch: str,
    message: str,
) -> None:
    """Ensure a text file exists at an arbitrary repository path."""

    norm = path.lstrip("/")
    url = _repo_api_url(settings, repository=repository, path=f"contents/{norm}")
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


def delete_repo_file_if_present(
    settings: ServerSettings,
    *,
    repository: str,
    path: str,
    sha: str,
    branch: str,
    message: str,
) -> None:
    """Delete a file from the repository if it exists."""
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


def ensure_repo_label_exists(
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
