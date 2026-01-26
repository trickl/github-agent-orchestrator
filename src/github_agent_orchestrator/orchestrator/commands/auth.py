"""Dispatcher for auth command."""

from __future__ import annotations

import argparse

from github_agent_orchestrator.orchestrator.commands.auth_github import handle_auth_github
from github_agent_orchestrator.orchestrator.config import OrchestratorSettings


def handle_auth(args: argparse.Namespace, settings: OrchestratorSettings) -> int:
    """Handle the auth command."""

    provider = getattr(args, "auth_provider", "")
    if provider == "github":
        return handle_auth_github(args, settings)
    raise ValueError(f"Unknown auth provider: {provider}")
