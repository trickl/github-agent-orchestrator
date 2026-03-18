"""GitHub Actions workflow control service."""

from __future__ import annotations

from typing import Any

from backend.app.github.client import GitHubClient


async def dispatch_workflow(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    workflow_file: str,
    ref: str,
) -> dict[str, Any]:
    """Dispatch a workflow via workflow_dispatch."""
    await client.request(
        "POST",
        f"/repos/{owner}/{repo}/actions/workflows/{workflow_file}/dispatches",
        json={"ref": ref},
        expected_status={204},
    )
    return {
        "owner": owner,
        "repo": repo,
        "workflow": workflow_file,
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
