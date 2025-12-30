"""Core package initialization."""

from github_agent_orchestrator.core.config import OrchestratorConfig
from github_agent_orchestrator.core.orchestrator import Orchestrator

__all__ = [
    "Orchestrator",
    "OrchestratorConfig",
]
