"""Handler for reset command."""

from __future__ import annotations

import argparse

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings


def handle_reset(args: argparse.Namespace, settings: OrchestratorSettings) -> int:  # noqa: ARG001
    """Handle the reset command."""

    if not args.yes:
        print("Refusing to reset without --yes")
        return 2

    print("Reset local state")
    print("- no local runtime state files are used")
    return 0
