"""Handler for cost command."""

from __future__ import annotations

import argparse
import json

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings


def handle_cost(args: argparse.Namespace, settings: OrchestratorSettings) -> int:
    """Handle the cost command."""

    cost_per_request = settings.premium_request_cost_usd
    requests_per_pr = settings.estimated_premium_requests_per_pr
    prs_per_iteration = settings.estimated_prs_per_iteration

    requests_per_iteration = requests_per_pr * prs_per_iteration
    cost_per_iteration = requests_per_iteration * cost_per_request

    payload = {
        "premium_request_cost_usd": cost_per_request,
        "estimated_premium_requests_per_pr": requests_per_pr,
        "estimated_prs_per_iteration": prs_per_iteration,
        "estimated_premium_requests_per_iteration": requests_per_iteration,
        "estimated_cost_per_iteration_usd": round(cost_per_iteration, 4),
        "note": (
            "Conservative estimate only. Actual costs depend on your Copilot plan, "
            "model multipliers, and billing policies. Check GitHub usage and billing."
        ),
        "reference": {
            "copilot_requests": "https://docs.github.com/en/copilot/concepts/billing/copilot-requests",
            "usage": "https://docs.github.com/en/copilot/how-tos/manage-and-track-spending/monitor-premium-requests",
            "billing": "https://docs.github.com/en/billing/how-tos/products/view-productlicense-use",
            "budgets": "https://docs.github.com/en/billing/managing-your-billing/using-budgets-control-spending",
        },
    }

    if args.pretty:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, sort_keys=True))
    return 0
