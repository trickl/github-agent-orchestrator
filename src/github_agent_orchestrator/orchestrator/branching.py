"""Branch resolution helpers for Copilot assignment."""

from __future__ import annotations

from github_agent_orchestrator.orchestrator.github.client import GitHubClient


def resolve_assignment_branch(
    *,
    github: GitHubClient,
    repository: str,
    issue_number: int,
    base_branch_override: str,
    target_base_branch: str,
    create_work_branch: bool,
    work_branch_prefix: str,
) -> str:
    base_branch = target_base_branch.strip() or base_branch_override.strip()
    if not base_branch:
        base_branch = github.get_repository_default_branch(repository=repository)

    if not create_work_branch:
        return base_branch

    work_branch = _work_branch_name(prefix=work_branch_prefix, issue_number=issue_number)
    _ensure_work_branch_exists(
        github=github,
        repository=repository,
        base_branch=base_branch,
        branch=work_branch,
    )
    return work_branch


def _work_branch_name(*, prefix: str, issue_number: int) -> str:
    cleaned = (prefix or "").strip().strip("/")
    if not cleaned:
        cleaned = "orchestrator/work"
    return f"{cleaned}/issue-{issue_number}"


def _ensure_work_branch_exists(
    *,
    github: GitHubClient,
    repository: str,
    base_branch: str,
    branch: str,
) -> None:
    try:
        github.get_branch_head_sha(branch=branch, repository=repository)
        return
    except Exception:
        pass

    base_sha = github.get_branch_head_sha(branch=base_branch, repository=repository)
    github.create_branch(branch=branch, base_sha=base_sha, repository=repository)
