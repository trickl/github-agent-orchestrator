"""Handler for status command."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings


def handle_status(args: argparse.Namespace, settings: OrchestratorSettings) -> int:  # noqa: ARG001
    """Handle the status command."""

    from github_agent_orchestrator.server.config import ServerSettings
    from github_agent_orchestrator.server.dashboard.loop_status import _loop_status_for_repo

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

    indent = 2 if args.pretty else None
    print(json.dumps(status, indent=indent, sort_keys=True))
    return 0
