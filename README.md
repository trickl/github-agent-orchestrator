# GitHub Agent Orchestrator

[![Tests](https://github.com/trickl/github-agent-orchestrator/workflows/Tests/badge.svg)](https://github.com/trickl/github-agent-orchestrator/actions)
[![Lint](https://github.com/trickl/github-agent-orchestrator/workflows/Lint/badge.svg)](https://github.com/trickl/github-agent-orchestrator/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Minimal GitHub orchestrator with an artefact-driven loop and a dashboard (Phase 1/1A).

This project is intentionally **not** a monolithic “agent”. It is a Git-native **orchestrator / task compiler**
that enables *long-horizon* software execution by keeping the system’s reasoning external, inspectable, and
versioned.

## Core value proposition

Together with Copilot, this system is a **long-horizon software engineering executor** that:

- Operates over **hours, not minutes** (target: ~$12$ hours unattended).
- Runs **multi-PR, multi-issue, multi-review** workstreams.
- **Continuously plans, executes, evaluates, and realigns** against a stated goal.

It uses GitHub as the arena where reasoning is **materialised**:

- **Issues = intent**
- **PRs = execution**
- **Reviews = reflection**
- **Repository files = memory**

Copilot excels at **local optimisation** (the next function, the next test, the next fix). This orchestrator is
about **global optimisation over time**.

## What this repository does (and does not do)

This repository is a Git-native **task compiler**:

- It creates issues from well-defined templates/intent.
- It materialises issues from files (promotes queued artefacts into GitHub issues).

It does **not** decide issue content, reason about solutions, or interpret meaning beyond basic classification and routing.

All “thinking” happens inside Copilot-authored PRs.

## Features

* **🔐 GitHub auth via token** (REST + PyGithub)
* **🧾 Structured JSON logs** (stdlib `logging`)
* **🧩 Minimal CLI** (`orchestrator create-issue`)
* **🌐 REST server + dashboard** (FastAPI + OpenAPI docs + React UI)
* **🧭 Repo-derived loop status** (driven by git-tracked planning artefacts + GitHub state; no DB)
* **📥 Issue queue promotion** (convert `/planning/issue_queue/pending/*` → GitHub issues, one-per-cycle)
* **🔎 Linked PR monitoring** (issue timeline cross-references)
* **✅ PR merge automation (guardrailed)**
    - refuses WIP
    - requires a review-request signal
    - refuses conflicted PRs
    - can flip draft → ready-for-review before merging (best-effort)
* **🧠 Capability update loop** (create + merge a system-capabilities update after a dev merge)
* **🛡️ Gap-analysis safety rails**
    - gap analysis issue body is template-driven (no “open a PR…” self-referential prompts)
    - unsafe legacy bodies are repaired before assignment
* **📦 Orchestrator-owned cognitive templates are local**
    - e.g. the gap-analysis template is shipped with this project and is **not** fetched from the target repo

## Core loop (1a–3c)

This system runs a simple, explicit loop. **The sources of truth are:**

- a goal / plan document in the *target repo*: `/planning/vision/goal.md`
- a system capabilities document in the *target repo*: `/planning/state/system_capabilities.md`
- the queue folders in the *target repo*: `/planning/issue_queue/*`
- the resulting GitHub issues/PRs

Everything else is derived from those artefacts and GitHub history.

### Step 1a — Ensure gap-analysis issue exists (create/assign)

The orchestrator ensures there is a single open **Gap Analysis** issue and assigns it to Copilot.

The issue instructs Copilot to:

- compare the goal vs current capabilities
- identify the next concrete development task
- write **exactly one** handoff artefact into `/planning/issue_queue/pending/`

Nothing else happens at this step.

**How to run it:**

- **UI:** Step 1a → “Ensure gap analysis issue”.
- **API:** `POST /api/loop/gap-analysis/ensure`

Safety note: the gap-analysis issue body is loaded from an orchestrator-owned local template.

Keeping this step explicit is intentional: it’s where prioritisation and judgment live.

### Step 2a — Promote the next queued development task

The orchestrator processes `/planning/issue_queue/pending/` and promotes the next file into a GitHub issue.
This step is deliberately “boring plumbing”:

- reads the next queue file
- creates the GitHub issue
- assigns it to Copilot
- moves the queue file to `processed/`

Rate limiting is intentional: **one issue per call/cycle**.

### Step 2b — Development execution (Copilot)

Copilot works the issue and produces a PR. Review/discussion happens in GitHub.
This is outside the orchestrator’s intelligence.

### Step 2c — Development PR ready for merge

The loop classifies a PR as ready when it is:

- not WIP
- has a review-request signal
- not conflicted

The merge action is deterministic: it merges **one** ready PR per call.

### Step 3a — Capability update issue (created after a merge)

After merging a development PR, the orchestrator creates a *new* “Update Capability” issue whose body:

- includes the PR description
- includes PR comments/discussion (chronological)
- explicitly requests an update to `/planning/state/system_capabilities.md` to reflect the merge

This is the place the system’s *self-knowledge* is updated.

### Step 3b — Capability update execution

That capability-update issue is worked (typically by Copilot). The capabilities document is updated
to match reality.

### Step 3c — Capability PR ready for merge

When the capability PR is ready (same readiness rules), the orchestrator can merge it.

With updated capabilities, Step 1a can be run again and the loop continues.

### Parallel / periodic track — Review tasks

Independently, you can inject review issues every *N* completed development tasks (e.g. complexity
review, architecture drift, refactoring, test coverage). These are just additional issues flowing
through the same pipeline; they don’t disturb the main loop.

Most actions are exposed as explicit endpoints/buttons so you can drive the system manually (dashboard)
or periodically (cron/CI/webhooks), while keeping the behavior deterministic and inspectable.

## Design: artefact-driven orchestration

### Canonical folders (finalised)

The orchestration loop is driven by a small set of canonical artefacts:

```
/planning
    /vision
        goal.md              # User-owned, rarely changes
    /state
        system_capabilities.md
    /reviews
        review-YYYY-MM-DD.md
    /issue_queue
        pending/
        processed/
        complete/
```

Note: **issue templates are orchestrator-owned**. They are shipped with this project and are not
expected to exist in the target repo.

The `/planning/issue_queue` folder is the explicit handoff boundary between reasoning and orchestration.

### The four canonical issue types (never mix)

1) **Gap Analysis (Plan → Build)**

- Purpose: compare `goal.md` vs `system_capabilities.md` and identify the next development step.
- Output: exactly one file in `/planning/issue_queue/pending/dev-<timestamp>.md`.
- Constraints: no code changes, no issue creation; output must be a candidate task (not a fix).

2) **Development Task (Build Something)**

- Input: one file from `/planning/issue_queue/pending/`.
- Output: code + tests and an updated `/planning/state/system_capabilities.md`.
- Promotion: the orchestrator converts the file into a GitHub issue, assigns to Copilot, then moves the file to `processed/`.

3) **Review Task (Critique)**

- Purpose: assess the system from one lens (architecture, correctness, mission alignment, capability completeness).
- Output: exactly one review document in `/planning/reviews/`.
- Constraints: analysis only (no fixes, no new tasks).

4) **Review Consumption (Critique → Action)**

- Purpose: translate critique into candidate work without acting on it.
- Input: one specific review file.
- Output: one or more files in `/planning/issue_queue/pending/review-<timestamp>-<n>.md`.

### Loop constraint (rate limiting)

The orchestrator is intentionally rate-limited:

1. Scan `/planning/issue_queue/pending`.
2. If files exist:
     - Convert the next file → GitHub issue
     - Move file → `issue_queue/processed`
     - Assign to Copilot
     - Exit (one issue per cycle)
3. Else:
     - Optionally create a meta-issue (gap analysis, system state update, review)
4. Sleep / poll

### User role (explicit)

The user owns exactly one artefact:

- `/planning/vision/goal.md`

Everything else is derived.

## Quick Start

### Installation

```bash
pip install github-agent-orchestrator
```

For development:
```bash
git clone https://github.com/trickl/github-agent-orchestrator.git
cd github-agent-orchestrator
pip install -e ".[dev]"
```

With local LLaMA support:
```bash
pip install "github-agent-orchestrator[llama]"
```

### Configuration

Create a `.env` file or set environment variables:

```bash
# GitHub Configuration
# Use a dedicated variable to avoid collisions with other tools/services that
# may also use GITHUB_TOKEN.
ORCHESTRATOR_GITHUB_TOKEN=ghp_...

# Who to assign issues to (default is often the Copilot SWE agent bot).
COPILOT_ASSIGNEE=copilot-swe-agent[bot]

# Optional (defaults shown)
GITHUB_BASE_URL=https://api.github.com
LOG_LEVEL=INFO
AGENT_STATE_PATH=agent_state

# REST server (optional)
# The dashboard reads loop state from this repo unless overridden via `?repo=owner/name`.
ORCHESTRATOR_DEFAULT_REPO=owner/repo
ORCHESTRATOR_HOST=127.0.0.1
ORCHESTRATOR_PORT=8000
```

### Basic Usage (CLI)

```bash
orchestrator create-issue \
  --repo "owner/repo" \
  --title "Phase 1: bootstrap" \
  --body "Create minimal local orchestrator" \
  --labels "agent,phase-1"
```

### Programmatic Usage

```python
from github_agent_orchestrator.orchestrator.config import OrchestratorSettings
from github_agent_orchestrator.orchestrator.github.client import GitHubClient
from github_agent_orchestrator.orchestrator.github.issue_service import IssueService, IssueStore
from github_agent_orchestrator.orchestrator.logging import configure_logging

settings = OrchestratorSettings()
configure_logging(settings.log_level)

github = GitHubClient(
    token=settings.github_token,
    repository="owner/repo",  # provided explicitly (not from .env)
    base_url=settings.github_base_url,
)

service = IssueService(
    github=github,
    store=IssueStore(settings.issues_state_file),
)

record = service.create_issue(
    title="Hello",
    body="Created from Python",
    labels=["agent"],
)

print(record)

```

## REST Server (FastAPI)

Run the REST API (serves OpenAPI docs automatically):

```bash
orchestrator-server
```

If you're running from source without the console script on your PATH:

```bash
python -m github_agent_orchestrator.server
```

Useful endpoints:

- OpenAPI JSON: `http://127.0.0.1:8000/api/openapi.json`
- Swagger UI: `http://127.0.0.1:8000/api/docs`

The server exposes endpoints under:

- `/api` (dashboard API used by the React UI)

## React + Vite UI (minimal scaffold)

A minimal UI scaffold is in `ui/`. It calls the REST API via a dev proxy.

1) Start the backend:

```bash
orchestrator-server
```

2) Start the UI dev server:

```bash
cd ui
npm install
npm run dev
```


## Architecture

The Phase 1/1A implementation spans two layers:

- `src/github_agent_orchestrator/server/`: dashboard API + loop classification/actions (repo-derived)
- `src/github_agent_orchestrator/orchestrator/`: lower-level primitives (CLI, GitHub client/service)

```
src/github_agent_orchestrator/
├── server/
│   ├── dashboard_router.py   # Loop status + action endpoints (/api/loop/*)
│   └── templates/            # Orchestrator-owned templates shipped with the package
└── orchestrator/
    ├── config.py             # .env + env var settings
    ├── logging.py            # JSON logging
    ├── main.py               # CLI entrypoint
    └── github/
        ├── client.py         # PyGithub wrapper
        └── issue_service.py  # Issue creation + (optional) local persistence
```

Key components:

* `dashboard_router.py`: repo-derived loop status and deterministic, one-step actions
* `OrchestratorSettings`: loads config from `.env`
* `GitHubClient`: authenticates and creates issues
* `IssueService`: idempotent-safe issue creation and (optional) local persistence

## Development

### Setup

```bash
# Clone and install
git clone https://github.com/trickl/github-agent-orchestrator.git
cd github-agent-orchestrator
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/github_agent_orchestrator

# Run specific test file
pytest tests/unit/test_config.py
```

### Code Quality

```bash
# Linting
ruff check src/ tests/

# Auto-fix linting issues
ruff check --fix src/ tests/

# Formatting
black src/ tests/

# Import sorting
isort src/ tests/

# Type checking
mypy src/
```

## Documentation

Full documentation is available in the `docs/` directory:

- [Architecture](docs/architecture.rst) - System design and components
- [API Reference](docs/api.rst) - Complete API documentation
- [Usage Guide](docs/usage.rst) - Detailed usage examples
- [Contributing](CONTRIBUTING.md) - Contribution guidelines

Build documentation locally:

```bash
cd docs
make html
open _build/html/index.html
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned features and development timeline.

### Current Status (v0.1.0)
- ✅ Artefact-driven loop classification (9 stages: 1a–3c)
- ✅ Dashboard UI + REST API for status + actions
- ✅ Issue queue promotion (one-per-cycle)
- ✅ Guardrailed merge automation (WIP/review-request/conflict gates)
- ✅ Post-merge capability update issue flow
- ✅ Safety rails for gap-analysis prompt content
- ✅ Comprehensive testing and documentation

### Coming Soon (v0.2.0)
- 🚧 Webhook/event-driven mode (reduce polling)
- 🚧 Better multi-repo ergonomics + onboarding helpers
- 🚧 Richer dashboard diagnostics (why a stage was selected)
- 🚧 Enhanced error handling and recovery

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Contribution Guide

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with tests
4. Run quality checks (`pre-commit run --all-files`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to your fork (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [OpenAI](https://openai.com/) and [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
- GitHub integration via [PyGithub](https://github.com/PyGithub/PyGithub)
- Configuration management with [Pydantic](https://github.com/pydantic/pydantic)

## Support

- 📖 [Documentation](docs/)
- 🐛 [Issue Tracker](https://github.com/trickl/github-agent-orchestrator/issues)
- 💬 [Discussions](https://github.com/trickl/github-agent-orchestrator/discussions)

---

Made with ❤️ by the Trickl team
