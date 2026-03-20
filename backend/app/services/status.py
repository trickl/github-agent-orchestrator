"""Repository status and timeline services for local control-plane state."""

from __future__ import annotations

import base64

from typing import Any

from backend.app.github.client import GitHubClient
from backend.app.services.run_state import get_repo_run_state

TARGET_STATE_PATH = ".agent-orchestrator/state/target_state.md"
LEGACY_TARGET_STATE_PATHS = (
    ".orchestrator-agent/state/target_state.md",
    ".agent-orchestrator/state/targetstate.md",
)
EXCLUDED_DEVELOPMENT_PR_TITLE_SUBSTRINGS = (
    "gap analysis",
    "update capability",
    "update current state",
    "target state",
    "update review",
)


def _extract_non_empty_text(contents_response: Any) -> str:
    if not isinstance(contents_response, dict):
        return ""

    encoded = contents_response.get("content")
    if not isinstance(encoded, str) or not encoded.strip():
        return ""

    try:
        decoded = base64.b64decode(encoded.encode("utf-8"), validate=False).decode("utf-8")
    except Exception:
        return ""

    return decoded.strip()


async def _target_state_has_content(client: GitHubClient, owner: str, repo: str, path: str) -> bool:
    response = await client.request(
        "GET",
        f"/repos/{owner}/{repo}/contents/{path}",
        params={"ref": "main"},
        expected_status={200, 404},
    )
    if isinstance(response, dict) and response.get("message") == "Not Found":
        return False
    return bool(_extract_non_empty_text(response))


async def _has_target_state(client: GitHubClient, owner: str, repo: str) -> bool:
    if await _target_state_has_content(client, owner, repo, TARGET_STATE_PATH):
        return True
    for legacy_path in LEGACY_TARGET_STATE_PATHS:
        if await _target_state_has_content(client, owner, repo, legacy_path):
            return True
    return False


def _is_development_pr(title: str) -> bool:
    lowered = title.lower()
    return not any(marker in lowered for marker in EXCLUDED_DEVELOPMENT_PR_TITLE_SUBSTRINGS)


async def get_status(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    workflow_file: str | None = None,  # noqa: ARG001
) -> dict[str, Any]:
    """Get local control-plane status for a repository."""

    has_target_state = await _has_target_state(client, owner, repo)
    repo_state = get_repo_run_state(f"{owner}/{repo}")

    return {
        "owner": owner,
        "repo": repo,
        "hasTargetState": has_target_state,
        "status": repo_state.status,
        "currentStep": repo_state.current_step,
        "active_issue_ids": [],
        "active_pr_ids": [],
        "latest_run": None,
        "status_artifact": None,
    }


async def list_development_pull_requests(client: GitHubClient, owner: str, repo: str) -> list[dict[str, str]]:
    """Return development pull requests (newest first), excluding orchestration/meta PRs."""

    pulls = await client.request(
        "GET",
        f"/repos/{owner}/{repo}/pulls",
        params={"state": "all", "sort": "created", "direction": "desc", "per_page": 100},
    )
    if not isinstance(pulls, list):
        return []

    timeline: list[dict[str, str]] = []
    for pr in pulls:
        if not isinstance(pr, dict):
            continue
        title = pr.get("title")
        url = pr.get("html_url")
        created_at = pr.get("created_at")
        if not isinstance(title, str) or not isinstance(url, str) or not isinstance(created_at, str):
            continue
        if not _is_development_pr(title):
            continue
        timeline.append(
            {
                "title": title,
                "url": url,
                "createdAt": created_at,
            }
        )

    return timeline


async def list_accessible_repositories(client: GitHubClient) -> list[str]:
    """List repositories available to the current GitHub App installation token."""

    payload = await client.request(
        "GET",
        "/installation/repositories",
        params={"per_page": 100},
    )
    if not isinstance(payload, dict):
        return []

    repos = payload.get("repositories")
    if not isinstance(repos, list):
        return []

    full_names = [
        item.get("full_name")
        for item in repos
        if isinstance(item, dict) and isinstance(item.get("full_name"), str)
    ]
    return sorted(set(full_names))
