"""GitHub Actions workflow control service."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

import httpx

from backend.app.github.client import GitHubClient


def _normalize_candidate_workflow_paths(workflow_file: str) -> list[str]:
    requested = workflow_file.strip().strip("/")
    if not requested:
        return []

    name = PurePosixPath(requested).name
    candidates = [requested]

    if not requested.startswith(".github/workflows/"):
        candidates.append(f".github/workflows/{name}")

    if name not in candidates:
        candidates.append(name)

    if name.endswith(".yml"):
        alt = name[:-4] + ".yaml"
        candidates.extend([alt, f".github/workflows/{alt}"])
    elif name.endswith(".yaml"):
        alt = name[:-5] + ".yml"
        candidates.extend([alt, f".github/workflows/{alt}"])

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def _extract_workflow_path(entry: Any) -> str | None:
    if not isinstance(entry, dict):
        return None
    path = entry.get("path")
    if isinstance(path, str) and path.strip():
        return path.strip()
    return None


async def _list_repo_workflow_paths(client: GitHubClient, owner: str, repo: str) -> list[str]:
    payload = await client.request(
        "GET",
        f"/repos/{owner}/{repo}/actions/workflows",
        params={"per_page": 100},
        expected_status={200},
    )
    workflows = payload.get("workflows", []) if isinstance(payload, dict) else []
    paths = [_extract_workflow_path(workflow) for workflow in workflows]
    return sorted({path for path in paths if path})


async def _dispatch_by_identifier(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    workflow_identifier: str,
    ref: str,
) -> None:
    await client.request(
        "POST",
        f"/repos/{owner}/{repo}/actions/workflows/{workflow_identifier}/dispatches",
        json={"ref": ref},
        expected_status={204},
    )


async def dispatch_workflow(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    workflow_file: str,
    ref: str,
) -> dict[str, Any]:
    """Dispatch a workflow via workflow_dispatch."""
    requested = workflow_file.strip()
    candidates = _normalize_candidate_workflow_paths(requested)
    if not candidates:
        raise ValueError("Workflow file must be a non-empty string")

    for candidate in candidates:
        try:
            await _dispatch_by_identifier(
                client,
                owner,
                repo,
                workflow_identifier=candidate,
                ref=ref,
            )
            return {
                "owner": owner,
                "repo": repo,
                "workflow": candidate,
                "ref": ref,
                "dispatched": True,
            }
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

    available_paths = await _list_repo_workflow_paths(client, owner, repo)
    if not available_paths:
        raise ValueError(
            f"No GitHub Actions workflows found in target repository '{owner}/{repo}'. "
            "The control plane dispatches workflows from the selected target repository (not the "
            "github-agent-orchestrator control-plane repository). Add a workflow file under "
            "'.github/workflows' in the target repository and enable workflow_dispatch."
        )

    basename_to_path = {PurePosixPath(path).name: path for path in available_paths}
    requested_basename = PurePosixPath(requested).name

    resolved = basename_to_path.get(requested_basename)
    if resolved is None and requested_basename.endswith(".yml"):
        resolved = basename_to_path.get(requested_basename[:-4] + ".yaml")
    elif resolved is None and requested_basename.endswith(".yaml"):
        resolved = basename_to_path.get(requested_basename[:-5] + ".yml")

    if resolved is None:
        for path in available_paths:
            if "orchestrator" in PurePosixPath(path).name.lower():
                resolved = path
                break

    if resolved is None:
        preview = ", ".join(available_paths[:5])
        suffix = "" if len(available_paths) <= 5 else ", ..."
        raise ValueError(
            f"Workflow '{requested}' was not found in target repository '{owner}/{repo}'. "
            f"Available target-repo workflows: {preview}{suffix}. "
            "Set GITHUB_ORCHESTRATOR_WORKFLOW_FILE to one of these paths."
        )

    await _dispatch_by_identifier(
        client,
        owner,
        repo,
        workflow_identifier=resolved,
        ref=ref,
    )
    return {
        "owner": owner,
        "repo": repo,
        "workflow": resolved,
        "ref": ref,
        "dispatched": True,
    }


async def cancel_latest_run(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    workflow_file: str,
) -> dict[str, Any]:
    """Cancel the latest in-progress run for a workflow."""
    runs = await client.request(
        "GET",
        f"/repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs",
        params={"status": "in_progress", "per_page": 1},
    )

    workflow_runs = runs.get("workflow_runs", []) if isinstance(runs, dict) else []
    if not workflow_runs:
        return {
            "owner": owner,
            "repo": repo,
            "workflow": workflow_file,
            "canceled": False,
            "reason": "No in-progress workflow run found",
        }

    latest_run = workflow_runs[0]
    run_id = latest_run.get("id")
    if not isinstance(run_id, int):
        return {
            "owner": owner,
            "repo": repo,
            "workflow": workflow_file,
            "canceled": False,
            "reason": "Latest run did not include a valid run id",
        }

    await client.request(
        "POST",
        f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel",
        expected_status={202, 409},
    )
    return {
        "owner": owner,
        "repo": repo,
        "workflow": workflow_file,
        "canceled": True,
        "run_id": run_id,
        "run_url": latest_run.get("html_url"),
    }
