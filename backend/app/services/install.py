"""Repository initialization service."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

from backend.app.github.client import GitHubClient


async def initialize_repo(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    target_state: str,
    orchestrator_config: str,
    branch_name: str | None = None,
    open_pr: bool = True,
) -> dict[str, Any]:
    """Initialize a repository by creating baseline files on a setup branch."""

    repo_data = await client.request("GET", f"/repos/{owner}/{repo}")
    base_branch = repo_data["default_branch"]
    ref = await client.request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{base_branch}")
    base_sha = ref["object"]["sha"]

    branch = branch_name or f"gao/init-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    await client.request(
        "POST",
        f"/repos/{owner}/{repo}/git/refs",
        json={
            "ref": f"refs/heads/{branch}",
            "sha": base_sha,
        },
    )

    async def _create_file(path: str, content: str) -> None:
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        await client.request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{path}",
            json={
                "message": f"Initialize {path}",
                "content": encoded,
                "branch": branch,
            },
        )

    await _create_file(".orchestrator-agent/state/target_state.md", target_state)
    await _create_file(".orchestrator.yml", orchestrator_config)

    result: dict[str, Any] = {
        "owner": owner,
        "repo": repo,
        "base_branch": base_branch,
        "branch": branch,
        "opened_pull_request": open_pr,
    }

    if open_pr:
        pr = await client.request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": "Initialize GitHub Agent Orchestrator",
                "head": branch,
                "base": base_branch,
                "body": "Initial setup of .orchestrator-agent/state/target_state.md and .orchestrator.yml.",
            },
        )
        result["pull_request"] = {
            "number": pr.get("number"),
            "url": pr.get("html_url"),
            "state": pr.get("state"),
        }

    return result
