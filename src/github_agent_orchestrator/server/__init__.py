"""FastAPI server adapter for github-agent-orchestrator.

This module exposes a REST API over the existing orchestrator services.

Design intent:
- Keep business logic in `github_agent_orchestrator.orchestrator.*`
- Keep server-specific concerns (routing, CORS, job tracking) here
"""

from __future__ import annotations

__all__ = ["create_app"]

from github_agent_orchestrator.server.app import create_app
