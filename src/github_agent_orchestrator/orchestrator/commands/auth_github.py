"""Handler for auth github command."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from github_agent_orchestrator.orchestrator.cli_env import upsert_env_vars
from github_agent_orchestrator.orchestrator.config import OrchestratorSettings


def handle_auth_github(args: argparse.Namespace, settings: OrchestratorSettings) -> int:  # noqa: ARG001
    """Handle the auth github command."""

    token = args.token or os.environ.get("ORCHESTRATOR_GITHUB_TOKEN")
    if not token:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("Missing token. Provide --token or set ORCHESTRATOR_GITHUB_TOKEN.", file=sys.stderr)
        return 2

    env_path = Path(args.env_path).expanduser()
    upsert_env_vars(
        path=env_path,
        updates={"ORCHESTRATOR_GITHUB_TOKEN": token},
        overwrite=True,
        header=("# GitHub Agent Orchestrator",),
    )
    print(f"Saved ORCHESTRATOR_GITHUB_TOKEN to {env_path}")
    return 0
