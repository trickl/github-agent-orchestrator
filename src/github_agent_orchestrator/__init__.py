"""GitHub Agent Orchestrator.

Phase 1/1A provides a minimal, local-first CLI with:
- configuration loaded from `.env`
- structured logging
- GitHub issue creation with local JSON persistence
"""

__version__ = "0.1.0"

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings

__all__ = ["__version__", "OrchestratorSettings"]
