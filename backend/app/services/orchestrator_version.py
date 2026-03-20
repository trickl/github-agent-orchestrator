"""Orchestrator workflow version inspection and update service."""

from __future__ import annotations

import base64
import re
from typing import Any

from backend.app.github.client import GitHubClient
from github_agent_orchestrator import __version__

LATEST_ORCHESTRATOR_VERSION = __version__
WORKFLOW_PATH = ".github/workflows/orchestrator.yml"
UPDATE_BRANCH = "gao/update-orchestrator-version"
VERSION_REGEX = re.compile(r"github-agent-orchestrator==([0-9]+\.[0-9]+\.[0-9]+)")
UNPINNED_REGEX = re.compile(r"github-agent-orchestrator(?!==[0-9]+\.[0-9]+\.[0-9]+)")


def extract_orchestrator_version(workflow_text: str) -> str | None:
    """Extract pinned orchestrator version from workflow text."""

    match = VERSION_REGEX.search(workflow_text)
    if match is None:
        return None
    return match.group(1)


def is_update_available(current: str | None, latest: str) -> bool:
    """Return whether an update is available based on semantic version comparison."""

    if current is None:
        return True

    current_parts = tuple(int(part) for part in current.split("."))
    latest_parts = tuple(int(part) for part in latest.split("."))
    return current_parts < latest_parts


def _decode_content_payload(content_payload: dict[str, Any]) -> str:
    encoded = content_payload.get("content")
    if not isinstance(encoded, str) or not encoded.strip():
        raise RuntimeError("Workflow content payload did not include base64 content")

    # GitHub may include line breaks in content payload.
    normalized = encoded.replace("\n", "")
    return base64.b64decode(normalized.encode("utf-8")).decode("utf-8")


def _encode_content(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def _pin_to_latest(workflow_text: str, latest: str) -> str:
    if VERSION_REGEX.search(workflow_text):
        return VERSION_REGEX.sub(f"github-agent-orchestrator=={latest}", workflow_text)

    updated, count = UNPINNED_REGEX.subn(
        f"github-agent-orchestrator=={latest}",
        workflow_text,
        count=1,
    )
    if count == 0:
        raise RuntimeError(
            "Workflow does not contain github-agent-orchestrator install command to update"
        )
    return updated


async def _get_workflow_file(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    branch: str,
) -> tuple[str, str]:
    response = await client.request(
        "GET",
        f"/repos/{owner}/{repo}/contents/{WORKFLOW_PATH}",
        params={"ref": branch},
        expected_status={200, 404},
    )

    if not isinstance(response, dict) or response.get("message") == "Not Found":
        raise RuntimeError(f"Workflow file not found: {WORKFLOW_PATH}")

    sha = response.get("sha")
    if not isinstance(sha, str) or not sha.strip():
        raise RuntimeError("Workflow content payload did not include sha")

    return _decode_content_payload(response), sha


async def get_orchestrator_version_info(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    branch: str = "main",
) -> dict[str, Any]:
    """Return current/latest orchestrator version info from workflow file."""

    workflow_text, _sha = await _get_workflow_file(client, owner, repo, branch=branch)
    current = extract_orchestrator_version(workflow_text)
    return {
        "current": current,
        "latest": LATEST_ORCHESTRATOR_VERSION,
        "updateAvailable": is_update_available(current, LATEST_ORCHESTRATOR_VERSION),
    }


async def update_orchestrator_version(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> dict[str, Any]:
    """Update orchestrator workflow pin to latest version on a PR branch."""

    repo_data = await client.request("GET", f"/repos/{owner}/{repo}")
    default_branch = repo_data.get("default_branch") if isinstance(repo_data, dict) else None
    if not isinstance(default_branch, str) or not default_branch.strip():
        raise RuntimeError("Repository metadata did not include a valid default_branch")

    workflow_text, workflow_sha = await _get_workflow_file(
        client,
        owner,
        repo,
        branch=default_branch,
    )
    current = extract_orchestrator_version(workflow_text)

    if not is_update_available(current, LATEST_ORCHESTRATOR_VERSION):
        return {
            "owner": owner,
            "repo": repo,
            "branch": default_branch,
            "workflowPath": WORKFLOW_PATH,
            "current": current,
            "latest": LATEST_ORCHESTRATOR_VERSION,
            "updateAvailable": False,
            "updated": False,
            "message": "Orchestrator workflow is already up to date",
        }

    updated_workflow = _pin_to_latest(workflow_text, LATEST_ORCHESTRATOR_VERSION)

    base_ref = await client.request(
        "GET",
        f"/repos/{owner}/{repo}/git/ref/heads/{default_branch}",
    )
    base_sha = base_ref.get("object", {}).get("sha") if isinstance(base_ref, dict) else None
    if not isinstance(base_sha, str) or not base_sha.strip():
        raise RuntimeError("Default branch ref did not include base sha")

    existing_update_ref = await client.request(
        "GET",
        f"/repos/{owner}/{repo}/git/ref/heads/{UPDATE_BRANCH}",
        expected_status={200, 404},
    )
    if isinstance(existing_update_ref, dict) and existing_update_ref.get("message") == "Not Found":
        await client.request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{UPDATE_BRANCH}", "sha": base_sha},
        )
    else:
        await client.request(
            "PATCH",
            f"/repos/{owner}/{repo}/git/refs/heads/{UPDATE_BRANCH}",
            json={"sha": base_sha, "force": True},
        )

    await client.request(
        "PUT",
        f"/repos/{owner}/{repo}/contents/{WORKFLOW_PATH}",
        json={
            "message": f"Update orchestrator to v{LATEST_ORCHESTRATOR_VERSION}",
            "content": _encode_content(updated_workflow),
            "branch": UPDATE_BRANCH,
            "sha": workflow_sha,
        },
    )

    pr_title = f"Update GitHub Agent Orchestrator to v{LATEST_ORCHESTRATOR_VERSION}"
    previous = current if isinstance(current, str) else "unversioned"
    pr_body = (
        "This updates the orchestrator runtime to the latest version.\n\n"
        f"- Previous: {previous}\n"
        f"- New: {LATEST_ORCHESTRATOR_VERSION}\n"
    )
    pr_response = await client.request(
        "POST",
        f"/repos/{owner}/{repo}/pulls",
        json={
            "title": pr_title,
            "head": UPDATE_BRANCH,
            "base": default_branch,
            "body": pr_body,
        },
    )

    return {
        "owner": owner,
        "repo": repo,
        "branch": UPDATE_BRANCH,
        "baseBranch": default_branch,
        "workflowPath": WORKFLOW_PATH,
        "current": current,
        "latest": LATEST_ORCHESTRATOR_VERSION,
        "updateAvailable": True,
        "updated": True,
        "pullRequest": {
            "number": pr_response.get("number") if isinstance(pr_response, dict) else None,
            "url": pr_response.get("html_url") if isinstance(pr_response, dict) else None,
            "state": pr_response.get("state") if isinstance(pr_response, dict) else None,
        },
    }
