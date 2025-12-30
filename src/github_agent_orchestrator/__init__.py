"""GitHub Agent Orchestrator.

A stateful orchestration engine that manages plans, critiques, issues,
and incremental PRs using GitHub's coding agents. Supports persistent
planning via repo-backed storage and continuous project evolution.
"""

__version__ = "0.1.0"

from github_agent_orchestrator.core.config import OrchestratorConfig
from github_agent_orchestrator.core.orchestrator import Orchestrator

__all__ = [
    "__version__",
    "Orchestrator",
    "OrchestratorConfig",
]
