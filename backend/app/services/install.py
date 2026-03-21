"""Repository initialization service."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

from backend.app.github.client import GitHubClient
from backend.app.templates.workflows import ORCHESTRATOR_WORKFLOW_PATH, render_orchestrator_workflow


def _decode_content_payload(content_payload: dict[str, Any]) -> str:
    encoded = content_payload.get("content")
    if not isinstance(encoded, str) or not encoded.strip():
        return ""

    normalized = encoded.replace("\n", "")
    try:
        return base64.b64decode(normalized.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


async def initialize_repo(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    target_state: str,
    orchestrator_config: str,
    branch_name: str | None = None,
    open_pr: bool = True,
    apply_directly: bool = False,
) -> dict[str, Any]:
    """Initialize a repository by creating baseline files on a setup branch."""

    repo_data = await client.request("GET", f"/repos/{owner}/{repo}")
    base_branch = repo_data["default_branch"]
    ref = await client.request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{base_branch}")
    base_sha = ref["object"]["sha"]

    if apply_directly:
        branch = base_branch
    else:
        branch = branch_name or f"gao/init-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        await client.request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={
                "ref": f"refs/heads/{branch}",
                "sha": base_sha,
            },
        )

    async def _upsert_file(path: str, content: str) -> str:
        existing = await client.request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": branch},
            expected_status={200, 404},
        )

        existing_sha: str | None = None
        existing_text: str | None = None
        if isinstance(existing, dict) and existing.get("message") != "Not Found":
            sha = existing.get("sha")
            if isinstance(sha, str) and sha.strip():
                existing_sha = sha
            existing_text = _decode_content_payload(existing)

        if existing_text == content:
            return "unchanged"

        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        message = f"Initialize {path}" if existing_sha is None else f"Update {path}"
        request_payload: dict[str, Any] = {
            "message": message,
            "content": encoded,
            "branch": branch,
        }
        if existing_sha:
            request_payload["sha"] = existing_sha

        await client.request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{path}",
            json=request_payload,
        )
        return "created" if existing_sha is None else "updated"

    initialized_files = {
        ".agent-orchestrator/state/target_state.md": await _upsert_file(
            ".agent-orchestrator/state/target_state.md", target_state
        ),
        ".orchestrator.yml": await _upsert_file(".orchestrator.yml", orchestrator_config),
        ORCHESTRATOR_WORKFLOW_PATH: await _upsert_file(
            ORCHESTRATOR_WORKFLOW_PATH,
            render_orchestrator_workflow(),
        ),
    }

    result: dict[str, Any] = {
        "owner": owner,
        "repo": repo,
        "base_branch": base_branch,
        "branch": branch,
        "opened_pull_request": bool(open_pr and not apply_directly),
        "applied_directly": apply_directly,
        "initialized_files": initialized_files,
    }

    if open_pr and not apply_directly:
        pr = await client.request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": "Initialize GitHub Agent Orchestrator",
                "head": branch,
                "base": base_branch,
                "body": (
                    "Initial setup of target-state artifacts and orchestrator workflow.\n\n"
                    "Files:\n"
                    "- .agent-orchestrator/state/target_state.md\n"
                    "- .orchestrator.yml\n"
                    f"- {ORCHESTRATOR_WORKFLOW_PATH}\n"
                ),
            },
        )
        result["pull_request"] = {
            "number": pr.get("number"),
            "url": pr.get("html_url"),
            "state": pr.get("state"),
        }

    return result


async def ensure_orchestrator_workflow(client: GitHubClient, owner: str, repo: str) -> dict[str, Any]:
    """Ensure the orchestrator workflow exists on the repository default branch."""

    repo_data = await client.request("GET", f"/repos/{owner}/{repo}")
    base_branch = repo_data["default_branch"]

    response = await client.request(
        "GET",
        f"/repos/{owner}/{repo}/contents/{ORCHESTRATOR_WORKFLOW_PATH}",
        params={"ref": base_branch},
        expected_status={200, 404},
    )

    existing_sha: str | None = None
    existing_text: str | None = None
    if isinstance(response, dict) and response.get("message") != "Not Found":
        sha = response.get("sha")
        if isinstance(sha, str) and sha.strip():
            existing_sha = sha
        existing_text = _decode_content_payload(response)

    workflow_text = render_orchestrator_workflow()
    if existing_text == workflow_text:
        return {
            "owner": owner,
            "repo": repo,
            "branch": base_branch,
            "workflowPath": ORCHESTRATOR_WORKFLOW_PATH,
            "status": "unchanged",
        }

    encoded = base64.b64encode(workflow_text.encode("utf-8")).decode("utf-8")
    payload: dict[str, Any] = {
        "message": "Bootstrap orchestrator workflow",
        "content": encoded,
        "branch": base_branch,
    }
    if existing_sha:
        payload["sha"] = existing_sha

    await client.request(
        "PUT",
        f"/repos/{owner}/{repo}/contents/{ORCHESTRATOR_WORKFLOW_PATH}",
        json=payload,
    )

    return {
        "owner": owner,
        "repo": repo,
        "branch": base_branch,
        "workflowPath": ORCHESTRATOR_WORKFLOW_PATH,
        "status": "created" if existing_sha is None else "updated",
    }
