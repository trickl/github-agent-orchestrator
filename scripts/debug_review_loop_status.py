"""Debug helper: print orchestrator loop status for a target repo.

This calls the same internal status computation the dashboard uses.

Usage:
  ORCHESTRATOR_GITHUB_TOKEN=... \
  /path/to/python scripts/debug_review_loop_status.py trickl/breadboard-lab

You can override the mode via ORCHESTRATOR_LOOP_MODE (defaults to 'review' here).
"""

from __future__ import annotations

import json
import os
import sys

from github_agent_orchestrator.server.config import ServerSettings
from github_agent_orchestrator.server.dashboard.loop_status import _loop_status_for_repo


def main(argv: list[str]) -> int:
    repo = argv[1] if len(argv) > 1 else os.getenv("ORCHESTRATOR_DEFAULT_REPO", "").strip()
    if not repo:
        print("ERROR: repo argument required (e.g. trickl/breadboard-lab)", file=sys.stderr)
        return 2

    # Ensure we are querying in review mode unless caller explicitly overrides.
    os.environ.setdefault("ORCHESTRATOR_LOOP_MODE", "review")

    settings = ServerSettings()

    status = _loop_status_for_repo(settings=settings, active_repo=repo, ref="")

    # Print key fields first (human readable), then full JSON for deeper inspection.
    print(f"repo: {status.get('repo')}")
    print(f"loopMode: {status.get('loopMode')}")
    print(f"stage: {status.get('stage')}  ({status.get('stageLabel')})")
    print(f"reason: {status.get('stageReason')}")

    counts = status.get("counts") if isinstance(status, dict) else None
    if isinstance(counts, dict):
        print("counts:")
        for k in [
            "openIssues",
            "openPullRequests",
            "openReviewConsumptionIssues",
            "openReviewUpdateIssues",
            "pending",
            "processed",
            "complete",
            "pendingReview",
            "pendingDevelopment",
            "unpromotedPending",
        ]:
            if k in counts:
                print(f"  {k}: {counts.get(k)}")

    focus = status.get("focus") if isinstance(status, dict) else None
    if isinstance(focus, dict):
        print("focus:")
        for k in ["kind", "title", "issueNumber", "pullNumber", "queuePath", "queueId"]:
            if k in focus:
                print(f"  {k}: {focus.get(k)}")

    print("\n--- full status json ---")
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
