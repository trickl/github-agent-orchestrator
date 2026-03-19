"""Target-state upsert service for repository initialization without source scanning."""

from __future__ import annotations

import base64
from typing import Any

from backend.app.github.client import GitHubClient

TARGET_STATE_PATH = ".agent-orchestrator/state/target_state.md"
ORCHESTRATOR_CONFIG_PATH = ".agent-orchestrator/config.yml"
DEFAULT_ORCHESTRATOR_CONFIG = "mode: semi\n"


def _encode_content(content: str) -> str:
    return base64.b64encode(content.encode("utf-8")).decode("utf-8")


def _extract_sha(get_content_response: Any) -> str | None:
    if not isinstance(get_content_response, dict):
        return None
    sha = get_content_response.get("sha")
    if isinstance(sha, str) and sha.strip():
        return sha
    return None


async def _get_file_sha_if_exists(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    path: str,
    branch: str,
) -> str | None:
    response = await client.request(
        "GET",
        f"/repos/{owner}/{repo}/contents/{path}",
        params={"ref": branch},
        expected_status={200, 404},
    )
    return _extract_sha(response)


async def upsert_target_state(
    client: GitHubClient,
    owner: str,
    repo: str,
    content: str,
    branch: str = "main",
) -> dict[str, Any]:
    """Create or update target state and ensure default orchestrator config exists."""

    target_sha = await _get_file_sha_if_exists(
        client,
        owner,
        repo,
        path=TARGET_STATE_PATH,
        branch=branch,
    )

    target_payload: dict[str, Any] = {
        "message": "Update target state",
        "content": _encode_content(content),
        "branch": branch,
    }
    if target_sha:
        target_payload["sha"] = target_sha

    await client.request(
        "PUT",
        f"/repos/{owner}/{repo}/contents/{TARGET_STATE_PATH}",
        json=target_payload,
    )

    config_sha = await _get_file_sha_if_exists(
        client,
        owner,
        repo,
        path=ORCHESTRATOR_CONFIG_PATH,
        branch=branch,
    )

    config_created = False
    if config_sha is None:
        config_payload = {
            "message": "Ensure orchestrator config",
            "content": _encode_content(DEFAULT_ORCHESTRATOR_CONFIG),
            "branch": branch,
        }
        await client.request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{ORCHESTRATOR_CONFIG_PATH}",
            json=config_payload,
        )
        config_created = True

    return {
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "target_state_path": TARGET_STATE_PATH,
        "target_state_updated": True,
        "target_state_created": target_sha is None,
        "config_path": ORCHESTRATOR_CONFIG_PATH,
        "config_created": config_created,
    }
