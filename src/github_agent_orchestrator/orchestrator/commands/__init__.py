"""Command handlers for the orchestrator CLI.

This package contains the implementation of all CLI subcommand handlers.
Each handler accepts parsed arguments and settings, and returns an exit code.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable

from github_agent_orchestrator.orchestrator.commands.assign_copilot import (
    handle_assign_copilot,
)
from github_agent_orchestrator.orchestrator.commands.auth import handle_auth
from github_agent_orchestrator.orchestrator.commands.cost import handle_cost
from github_agent_orchestrator.orchestrator.commands.init import handle_init
from github_agent_orchestrator.orchestrator.commands.reset import handle_reset
from github_agent_orchestrator.orchestrator.commands.run_loop import handle_run
from github_agent_orchestrator.orchestrator.commands.auto_link_issue_pr import (
    handle_auto_link_issue_pr,
)
from github_agent_orchestrator.orchestrator.commands.auto_resume_copilot import (
    handle_auto_resume_copilot,
)
from github_agent_orchestrator.orchestrator.commands.complete_issue_queue_item import (
    handle_complete_issue_queue_item,
)
from github_agent_orchestrator.orchestrator.commands.create_issue import handle_create_issue
from github_agent_orchestrator.orchestrator.commands.gap_analysis_cycle import (
    handle_gap_analysis_cycle,
)
from github_agent_orchestrator.orchestrator.commands.merge_linked_prs import (
    handle_merge_linked_prs,
)
from github_agent_orchestrator.orchestrator.commands.monitor_prs import handle_monitor_prs
from github_agent_orchestrator.orchestrator.commands.promote_issue_queue import (
    handle_promote_issue_queue,
)
from github_agent_orchestrator.orchestrator.commands.status import handle_status
from github_agent_orchestrator.orchestrator.commands.system_capabilities_after_merge import (
    handle_system_capabilities_after_merge,
)
from github_agent_orchestrator.orchestrator.config import OrchestratorSettings

CommandHandler = Callable[[argparse.Namespace, OrchestratorSettings], int]

COMMAND_REGISTRY: dict[str, CommandHandler] = {
    "init": handle_init,
    "auth": handle_auth,
    "cost": handle_cost,
    "create-issue": handle_create_issue,
    "assign-copilot": handle_assign_copilot,
    "monitor-prs": handle_monitor_prs,
    "merge-linked-prs": handle_merge_linked_prs,
    "gap-analysis-cycle": handle_gap_analysis_cycle,
    "promote-issue-queue": handle_promote_issue_queue,
    "system-capabilities-after-merge": handle_system_capabilities_after_merge,
    "complete-issue-queue-item": handle_complete_issue_queue_item,
    "auto-resume-copilot": handle_auto_resume_copilot,
    "auto-link-issue-pr": handle_auto_link_issue_pr,
    "status": handle_status,
    "run": handle_run,
    "reset": handle_reset,
}

__all__ = [
    "COMMAND_REGISTRY",
    "CommandHandler",
    "handle_init",
    "handle_auth",
    "handle_cost",
    "handle_create_issue",
    "handle_assign_copilot",
    "handle_monitor_prs",
    "handle_merge_linked_prs",
    "handle_gap_analysis_cycle",
    "handle_promote_issue_queue",
    "handle_system_capabilities_after_merge",
    "handle_complete_issue_queue_item",
    "handle_auto_resume_copilot",
    "handle_auto_link_issue_pr",
    "handle_status",
    "handle_run",
    "handle_reset",
]
