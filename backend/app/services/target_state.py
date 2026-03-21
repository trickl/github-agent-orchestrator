"""Target-state upsert service for repository initialization without source scanning."""

from __future__ import annotations

import base64
from typing import Any
from typing import Literal

from backend.app.github.client import GitHubClient

TARGET_STATE_PATH = ".agent-orchestrator/state/target_state.md"
ORCHESTRATOR_CONFIG_PATH = ".agent-orchestrator/config.yml"
DEFAULT_ORCHESTRATOR_CONFIG = "mode: manual\n"
ALLOWED_ORCHESTRATOR_MODES = ("manual", "semi", "auto")


def _encode_content(content: str) -> str:
    return base64.b64encode(content.encode("utf-8")).decode("utf-8")


def _decode_content(content: str) -> str:
    try:
        return base64.b64decode(content.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


def _extract_sha(get_content_response: Any) -> str | None:
    if not isinstance(get_content_response, dict):
        return None
    sha = get_content_response.get("sha")
    if isinstance(sha, str) and sha.strip():
        return sha
    return None


def _extract_content(get_content_response: Any) -> str | None:
    if not isinstance(get_content_response, dict):
        return None
    encoded = get_content_response.get("content")
    if not isinstance(encoded, str) or not encoded.strip():
        return None
    return _decode_content(encoded)


def _upsert_mode_in_config(config_text: str, mode: Literal["manual", "semi", "auto"]) -> str:
    lines = config_text.splitlines()
    updated = False
    normalized_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("mode:"):
            normalized_lines.append(f"mode: {mode}")
            updated = True
            continue
        normalized_lines.append(line)

    if not updated:
        normalized_lines.append(f"mode: {mode}")

    return "\n".join(normalized_lines).rstrip() + "\n"


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


async def _resolve_target_branch(
    client: GitHubClient,
    owner: str,
    repo: str,
    requested_branch: str | None,
) -> str:
    if isinstance(requested_branch, str) and requested_branch.strip():
        return requested_branch.strip()

    repo_payload = await client.request("GET", f"/repos/{owner}/{repo}")
    if isinstance(repo_payload, dict):
        default_branch = repo_payload.get("default_branch")
        if isinstance(default_branch, str) and default_branch.strip():
            return default_branch.strip()
    raise RuntimeError(f"Repository '{owner}/{repo}' did not include a valid default_branch")


async def upsert_target_state(
    client: GitHubClient,
    owner: str,
    repo: str,
    content: str,
    branch: str | None = None,
) -> dict[str, Any]:
    """Create or update target state and ensure default orchestrator config exists."""

    resolved_branch = await _resolve_target_branch(client, owner, repo, branch)

    target_sha = await _get_file_sha_if_exists(
        client,
        owner,
        repo,
        path=TARGET_STATE_PATH,
        branch=resolved_branch,
    )

    target_payload: dict[str, Any] = {
        "message": "Update target state",
        "content": _encode_content(content),
        "branch": resolved_branch,
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
        branch=resolved_branch,
    )

    config_created = False
    if config_sha is None:
        config_payload = {
            "message": "Ensure orchestrator config",
            "content": _encode_content(DEFAULT_ORCHESTRATOR_CONFIG),
            "branch": resolved_branch,
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
        "branch": resolved_branch,
        "target_state_path": TARGET_STATE_PATH,
        "target_state_updated": True,
        "target_state_created": target_sha is None,
        "config_path": ORCHESTRATOR_CONFIG_PATH,
        "config_created": config_created,
    }


async def upsert_orchestrator_mode(
    client: GitHubClient,
    owner: str,
    repo: str,
    mode: Literal["manual", "semi", "auto"],
    branch: str | None = None,
) -> dict[str, Any]:
    """Create or update orchestrator mode in repository config."""

    if mode not in ALLOWED_ORCHESTRATOR_MODES:
        raise ValueError(f"Unsupported orchestrator mode: {mode}")

    resolved_branch = await _resolve_target_branch(client, owner, repo, branch)
    config_response = await client.request(
        "GET",
        f"/repos/{owner}/{repo}/contents/{ORCHESTRATOR_CONFIG_PATH}",
        params={"ref": resolved_branch},
        expected_status={200, 404},
    )

    config_sha = _extract_sha(config_response)
    existing_config = _extract_content(config_response)
    if existing_config is None:
        existing_config = DEFAULT_ORCHESTRATOR_CONFIG

    updated_config = _upsert_mode_in_config(existing_config, mode)
    is_noop = config_sha is not None and updated_config == existing_config

    if not is_noop:
        config_payload: dict[str, Any] = {
            "message": f"Update orchestrator mode to {mode}",
            "content": _encode_content(updated_config),
            "branch": resolved_branch,
        }
        if config_sha:
            config_payload["sha"] = config_sha

        await client.request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{ORCHESTRATOR_CONFIG_PATH}",
            json=config_payload,
        )

    return {
        "owner": owner,
        "repo": repo,
        "branch": resolved_branch,
        "mode": mode,
        "config_path": ORCHESTRATOR_CONFIG_PATH,
        "config_created": config_sha is None,
        "updated": not is_noop,
    }
