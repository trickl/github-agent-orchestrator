"""Handler for run command."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings


def handle_run(args: argparse.Namespace, settings: OrchestratorSettings) -> int:  # noqa: ARG001
    """Run a single deterministic loop action based on current status."""

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
    repo = args.repo or server_settings.default_repo
    if not repo:
        print("Missing repo. Pass --repo or set ORCHESTRATOR_DEFAULT_REPO.", file=sys.stderr)
        return 2

    ref = args.ref or ""
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
            if args.heal_orphans or getattr(
                server_settings, "auto_heal_orphaned_processed_queue_items", False
            ):
                result = _heal_orphaned_processed_queue_items(
                    settings=server_settings, repo=repo
                )
            else:
                print(
                    "Stage 2b detected. Use --heal-orphans or set "
                    "ORCHESTRATOR_AUTO_HEAL_ORPHANED_PROCESSED_QUEUE_ITEMS=true.",
                    file=sys.stderr,
                )
                return 3
        elif stage == "3a":
            result = _promote_next_unpromoted_capability_queue_item(
                settings=server_settings, repo=repo
            )
        elif stage in {"1c", "2c", "3c"}:
            result = _merge_next_ready_pull_request(settings=server_settings, repo=repo)
        else:
            print("No actionable stage detected.", file=sys.stderr)
            return 3
    except Exception as exc:  # noqa: BLE001
        if getattr(exc, "status_code", None) == 409:
            print(getattr(exc, "detail", "No action taken."), file=sys.stderr)
            return 3
        raise

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
