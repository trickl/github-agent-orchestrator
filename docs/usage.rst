Usage Guide
===========

This guide documents the Phase 1/1A functionality: configuration, logging, and GitHub issue
creation with local persistence.

Installation
------------

Basic Installation
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   pip install github-agent-orchestrator

Development Installation
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   git clone https://github.com/trickl/github-agent-orchestrator.git
   cd github-agent-orchestrator
   pip install -e ".[dev]"

Configuration
-------------

Environment Variables
~~~~~~~~~~~~~~~~~~~~~

Create a ``.env`` file in your project root:

.. code-block:: bash

   # Required
   ORCHESTRATOR_GITHUB_TOKEN=ghp_...

   # Optional (defaults shown)
   GITHUB_BASE_URL=https://api.github.com
   LOG_LEVEL=INFO
   AGENT_STATE_PATH=agent_state

Repository selection is passed per command via ``--repo``.

Usage
-----

Create an Issue (CLI)
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   orchestrator create-issue \
     --repo "owner/repo" \
     --title "New feature request" \
     --body "Description of the feature" \
     --labels "enhancement"

Programmatic Issue Creation
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
   from github_agent_orchestrator.orchestrator.github.client import GitHubClient
   from github_agent_orchestrator.orchestrator.github.issue_service import IssueService, IssueStore

   settings = OrchestratorSettings()

   github = GitHubClient(
       token=settings.github_token,
       repository="owner/repo",
       base_url=settings.github_base_url,
   )

   service = IssueService(github=github, store=IssueStore(settings.issues_state_file))
   record = service.create_issue(
       title="New feature request",
       body="Description of the feature",
       labels=["enhancement"],
   )

   print(record.issue_number)

Monitor Linked Pull Requests (Polling)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If a pull request is linked to an issue (for example, using closing keywords like
``Fixes #123``), you can poll until the linked PRs are in a terminal state.

This is useful for Copilot coding agent flows where the PR is created asynchronously.

.. code-block:: bash

   # Poll until the linked PR is merged, or time out after 2 hours
   orchestrator monitor-prs \
     --repo "owner/repo" \
     --issue-number 123 \
     --poll-seconds 15 \
     --timeout-seconds 7200

Local State and Idempotency
---------------------------

Created issue metadata is persisted to ``agent_state/issues.json`` (or the directory configured
via ``AGENT_STATE_PATH``). The issue service is idempotent-safe locally: if an issue with the
same title is already recorded, it will not create a duplicate.

Testing
-------

.. code-block:: bash

   pytest

Linting and Formatting
----------------------

.. code-block:: bash

   ruff check src/ tests/
   black --check src/ tests/
   mypy src/
