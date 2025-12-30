"""GitHub API client wrapper."""

import logging

from github import Auth, Github
from github.Issue import Issue
from github.PullRequest import PullRequest
from github.Repository import Repository

from github_agent_orchestrator.core.config import GitHubConfig

logger = logging.getLogger(__name__)


class GitHubClient:
    """Client for interacting with GitHub API.

    Provides methods for reading and creating PRs and Issues.
    """

    def __init__(self, config: GitHubConfig) -> None:
        """Initialize the GitHub client.

        Args:
            config: GitHub configuration.

        Raises:
            ValueError: If required configuration is missing.
        """
        if not config.token:
            raise ValueError("GitHub token is required")
        if not config.repository:
            raise ValueError("GitHub repository is required")

        self.config = config

        auth = Auth.Token(config.token)
        self.gh = Github(auth=auth, base_url=config.base_url)

        try:
            self.repo: Repository = self.gh.get_repo(config.repository)
            logger.info(f"Connected to repository: {config.repository}")
        except Exception as e:
            logger.error(f"Failed to connect to repository: {e}")
            raise

    def get_pull_request(self, pr_number: int) -> PullRequest:
        """Get a pull request by number.

        Args:
            pr_number: Pull request number.

        Returns:
            PullRequest object.
        """
        logger.debug(f"Fetching pull request #{pr_number}")
        return self.repo.get_pull(pr_number)

    def list_pull_requests(
        self,
        state: str = "open",
        base: str | None = None,
    ) -> list[PullRequest]:
        """List pull requests.

        Args:
            state: State filter ('open', 'closed', 'all').
            base: Base branch filter.

        Returns:
            List of PullRequest objects.
        """
        logger.debug(f"Listing pull requests (state={state}, base={base})")
        if base is not None:
            prs = self.repo.get_pulls(state=state, base=base)
        else:
            prs = self.repo.get_pulls(state=state)
        return list(prs)

    def create_pull_request(
        self,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = False,
    ) -> PullRequest:
        """Create a new pull request.

        Args:
            title: PR title.
            body: PR description.
            head: Head branch name.
            base: Base branch name.
            draft: Whether to create as draft.

        Returns:
            Created PullRequest object.
        """
        logger.info(f"Creating pull request: {title}")

        pr = self.repo.create_pull(
            title=title,
            body=body,
            head=head,
            base=base,
            draft=draft,
        )

        logger.info(f"Pull request created: #{pr.number}")
        return pr

    def get_issue(self, issue_number: int) -> Issue:
        """Get an issue by number.

        Args:
            issue_number: Issue number.

        Returns:
            Issue object.
        """
        logger.debug(f"Fetching issue #{issue_number}")
        return self.repo.get_issue(issue_number)

    def list_issues(
        self,
        state: str = "open",
        labels: list[str] | None = None,
    ) -> list[Issue]:
        """List issues.

        Args:
            state: State filter ('open', 'closed', 'all').
            labels: Label filters.

        Returns:
            List of Issue objects.
        """
        logger.debug(f"Listing issues (state={state}, labels={labels})")
        issues = self.repo.get_issues(state=state, labels=labels or [])
        return list(issues)

    def create_issue(
        self,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> Issue:
        """Create a new issue.

        Args:
            title: Issue title.
            body: Issue description.
            labels: Labels to apply.
            assignees: Assignees.

        Returns:
            Created Issue object.
        """
        logger.info(f"Creating issue: {title}")

        if body is not None:
            issue = self.repo.create_issue(
                title=title,
                body=body,
                labels=labels or [],
                assignees=assignees or [],
            )
        else:
            issue = self.repo.create_issue(
                title=title,
                labels=labels or [],
                assignees=assignees or [],
            )

        logger.info(f"Issue created: #{issue.number}")
        return issue

    def close(self) -> None:
        """Close the GitHub client connection."""
        self.gh.close()
        logger.info("GitHub client closed")
