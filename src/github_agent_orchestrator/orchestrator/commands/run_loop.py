"""Handler for run command."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings

MERGE_STAGES = {"1c", "2c", "3c"}


def run_once(
    *,
    repo: str,
    ref: str = "",
    heal_orphans: bool = False,
    auto_approve: bool = True,
) -> tuple[int, dict[str, Any] | None, str | None]:
    """Run a single deterministic loop action.

    Returns a tuple of:
    - exit code
    - result payload (if action executed)
    - informational message (for non-payload outcomes)
    """

    from github_agent_orchestrator.server.config import ServerSettings
    from github_agent_orchestrator.server.dashboard.loop_actions import (
        _ensure_gap_analysis_issue_exists,
        _heal_orphaned_processed_queue_items,
        _merge_next_ready_pull_request,
        _promote_next_unpromoted_capability_queue_item,
        _promote_next_unpromoted_development_queue_item,
    )
    from github_agent_orchestrator.server.dashboard.loop_status import _loop_status_for_repo
    from github_agent_orchestrator.server.dashboard_router import (
        _ensure_review_consumption_issue_exists,
    )

    server_settings = ServerSettings()
    if not repo:
        return 2, None, "Missing repo. Pass --repo or set ORCHESTRATOR_DEFAULT_REPO."

    status: dict[str, Any] = _loop_status_for_repo(
        settings=server_settings,
        active_repo=repo,
        ref=ref,
    )
    stage = status.get("stage") if isinstance(status, dict) else None

    try:
        if stage == "1a":
            if getattr(server_settings, "loop_mode", "build") == "review":
                result = _ensure_review_consumption_issue_exists(
                    settings=server_settings, repo=repo
                )
            else:
                result = _ensure_gap_analysis_issue_exists(settings=server_settings, repo=repo)
        elif stage == "2a":
            result = _promote_next_unpromoted_development_queue_item(
                settings=server_settings, repo=repo
            )
        elif stage == "2b":
            if heal_orphans or getattr(
                server_settings, "auto_heal_orphaned_processed_queue_items", False
            ):
                result = _heal_orphaned_processed_queue_items(
                    settings=server_settings, repo=repo
                )
            else:
                return (
                    3,
                    None,
                    "Stage 2b detected. Use --heal-orphans or set "
                    "ORCHESTRATOR_AUTO_HEAL_ORPHANED_PROCESSED_QUEUE_ITEMS=true.",
                )
        elif stage == "3a":
            result = _promote_next_unpromoted_capability_queue_item(
                settings=server_settings, repo=repo
            )
        elif stage in MERGE_STAGES:
            if not auto_approve:
                return 0, None, "Waiting for manual approval before merge."
            result = _merge_next_ready_pull_request(settings=server_settings, repo=repo)
        else:
            return 3, None, "No actionable stage detected."
    except Exception as exc:  # noqa: BLE001
        if getattr(exc, "status_code", None) == 409:
            return 3, None, str(getattr(exc, "detail", "No action taken."))
        raise

    return 0, result, None


def handle_run(args: argparse.Namespace, settings: OrchestratorSettings) -> int:  # noqa: ARG001
    """Run a single deterministic loop action based on current status."""
    from github_agent_orchestrator.server.config import ServerSettings

    server_settings = ServerSettings()
    repo = args.repo or server_settings.default_repo
    ref = args.ref or ""
    auto_approve = getattr(args, "auto_approve", True)

    exit_code, result, message = run_once(
        repo=repo,
        ref=ref,
        heal_orphans=args.heal_orphans,
        auto_approve=auto_approve,
    )
    if exit_code != 0:
        if message:
            print(message, file=sys.stderr)
        return exit_code

    if result is not None:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif message:
        print(message)
    return 0
