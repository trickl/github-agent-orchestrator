"""Handler for reset command."""

from __future__ import annotations

import argparse
from pathlib import Path

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings


def handle_reset(args: argparse.Namespace, settings: OrchestratorSettings) -> int:  # noqa: ARG001
    """Handle the reset command."""

    if not args.yes:
        print("Refusing to reset without --yes")
        return 2

    removed: list[str] = []
    paths = [
        Path("agent_state") / "issues.json",
        Path("workflow") / "state.json",
    ]
    for path in paths:
        if path.exists():
            path.unlink()
            removed.append(str(path))

    print("Reset local state")
    for item in removed:
        print(f"- removed {item}")
    if not removed:
        print("- nothing to remove")
    return 0
