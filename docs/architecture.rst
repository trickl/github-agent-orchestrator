Architecture
============

Overview
--------

The Phase 1/1A implementation is intentionally small and local-first.
It focuses on configuration, logging, GitHub issue creation, and local persistence.

Core Components
---------------

Settings
~~~~~~~~

`github_agent_orchestrator.orchestrator.config.OrchestratorSettings` loads configuration from
environment variables and/or a local ``.env`` file.

Logging
~~~~~~~

`github_agent_orchestrator.orchestrator.logging.configure_logging` configures structured JSON
logging using the stdlib ``logging`` package.

GitHub Integration
------------------

The GitHub integration layer is intentionally thin:

* `github_agent_orchestrator.orchestrator.github.client.GitHubClient` wraps PyGithub and
   implements issue creation.
* `github_agent_orchestrator.orchestrator.github.issue_service.IssueService` adds local
   persistence and idempotency checks.

Local State
-----------

Issue metadata is stored locally (default ``agent_state/issues.json``). This local state is the
source of truth for the idempotency check (by title).

Data Flow
---------

1. Load settings from ``.env`` / env vars
2. Configure logging
3. Create an issue via `GitHubClient`
4. Persist metadata locally via `IssueStore`
