from __future__ import annotations

import pytest

from github_agent_orchestrator.orchestrator.issue_queue_completion import plan_move_to_complete


def test_plan_move_to_complete_basic() -> None:
    plan = plan_move_to_complete(
        source_path="planning/issue_queue/pending/implement-voltage-heatmap-overlay.md",
        complete_dir="planning/issue_queue/complete",
    )
    assert plan.source_path == "planning/issue_queue/pending/implement-voltage-heatmap-overlay.md"
    assert plan.dest_path == "planning/issue_queue/complete/implement-voltage-heatmap-overlay.md"
    assert plan.filename == "implement-voltage-heatmap-overlay.md"


def test_plan_move_to_complete_rejects_empty() -> None:
    with pytest.raises(ValueError):
        plan_move_to_complete(source_path="", complete_dir="planning/issue_queue/complete")

    with pytest.raises(ValueError):
        plan_move_to_complete(source_path="planning/issue_queue/pending/", complete_dir="x")

    with pytest.raises(ValueError):
        plan_move_to_complete(source_path="a.md", complete_dir="")
