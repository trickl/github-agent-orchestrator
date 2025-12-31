#!/usr/bin/env python3
"""Programmatic issue creation example (Phase 1/1A).

This demonstrates using the orchestrator components directly:

* load settings from `.env`
* create a GitHub issue
* persist minimal metadata to `agent_state/issues.json`

Repository selection is passed as an argument (not read from `.env`).
"""

from __future__ import annotations

import argparse
from typing import Sequence

from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import (
    IssueAlreadyExists,
    IssueService,
    IssueStore,
)
from github_agent_orchestrator.orchestrator.logging import configure_logging


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a GitHub issue (programmatic example).")
    parser.add_argument("--repo", required=True, help='Target repository in the form "owner/repo"')
    parser.add_argument("--title", required=True, help="Issue title")
    parser.add_argument("--body", default="", help="Issue body")
    parser.add_argument(
        "--labels",
        default="",
        help='Comma-separated labels, e.g. "agent,phase-1" (optional)',
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    labels = [label.strip() for label in args.labels.split(",") if label.strip()]

    settings = OrchestratorSettings()
    configure_logging(settings.log_level)

    github = GitHubClient(
        token=settings.github_token,
        repository=args.repo,
        base_url=settings.github_base_url,
    )

    service = IssueService(github=github, store=IssueStore(settings.issues_state_file))

    try:
        record = service.create_issue(title=args.title, body=args.body, labels=labels)
    except IssueAlreadyExists as exc:
        print(str(exc))
        return 0

    print(f"Created issue #{record.number}: {record.title}")
    print(f"URL: {record.url}")
    print(f"Persisted to: {settings.issues_state_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
