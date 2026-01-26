"""Tests for cost command output."""

from __future__ import annotations

import argparse
import json

import pytest

from github_agent_orchestrator.orchestrator.commands.cost import handle_cost
from github_agent_orchestrator.orchestrator.config import OrchestratorSettings


def test_cost_command_outputs_estimates(capsys: pytest.CaptureFixture[str]) -> None:
    settings = OrchestratorSettings(require_github_token=False)
    args = argparse.Namespace(pretty=False)

    rc = handle_cost(args, settings)
    assert rc == 0

    out = capsys.readouterr().out.strip()
    payload = json.loads(out)

    assert payload["premium_request_cost_usd"] == 0.04
    assert payload["estimated_premium_requests_per_pr"] == 1
    assert payload["estimated_prs_per_iteration"] == 3
    assert payload["estimated_premium_requests_per_iteration"] == 3
    assert payload["estimated_cost_per_iteration_usd"] == 0.12
