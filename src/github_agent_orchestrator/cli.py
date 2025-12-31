"""Legacy module retained only to avoid stale imports.

Phase 1/1A CLI entrypoint is implemented in `github_agent_orchestrator.orchestrator.main`.
"""

from __future__ import annotations

from github_agent_orchestrator.orchestrator.main import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
