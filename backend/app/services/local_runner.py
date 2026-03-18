"""Local CLI runner for orchestrator execution."""

from __future__ import annotations

import subprocess
from typing import Any


def run_orchestrator(*, cli_command: str, owner: str, repo: str, timeout_seconds: int) -> dict[str, Any]:
    """Execute the orchestrator locally for a specific repository context."""

    target = f"{owner}/{repo}"
    command = [cli_command, "run", "--repo", target]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    return {
        "status": "completed",
        "repo": target,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
    }
