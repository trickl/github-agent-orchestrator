# GitHub Agent Orchestrator

[![Tests](https://github.com/trickl/github-agent-orchestrator/workflows/Tests/badge.svg)](https://github.com/trickl/github-agent-orchestrator/actions)
[![Lint](https://github.com/trickl/github-agent-orchestrator/workflows/Lint/badge.svg)](https://github.com/trickl/github-agent-orchestrator/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Minimal, local-first GitHub orchestrator (Phase 1/1A).

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

* **🔐 GitHub auth via token** (PyGithub)
* **🧾 Structured JSON logs** (stdlib `logging`)
* **🧩 Minimal CLI** (`orchestrator create-issue`)
* **💾 Local JSON state** (`agent_state/issues.json`)
* **🛡️ Idempotent-safe** issue creation (by title, locally)
* **🌐 REST server adapter** (FastAPI + OpenAPI docs)
* **🔎 Linked PR monitoring** (polling via GitHub REST issue timeline)
* **📥 Issue queue promotion** (convert queued artefacts into GitHub issues)
* **✅ Safe-ish PR merge automation** (mark ready, merge, optionally delete branch)
* **🧠 Post-merge capability update issue** (create a system-capabilities update issue from a merged PR)

## Main processing loop (A–G)

This system runs a simple, explicit loop. **The only sources of truth are:**

- a goal / plan document: `/planning/vision/goal.md`
- a system capabilities document: `/planning/state/system_capabilities.md`

Everything else is derived from those artefacts and the resulting GitHub history.

### Step A — Gap analysis (cognitive, explicit)

You manually (or semi-manually) trigger a *Gap Analysis* cognitive task.

That task:

- compares the goal vs current capabilities
- identifies the next concrete development task
- writes **exactly one** handoff artefact into `/planning/issue_queue/pending/`

Nothing else happens at this step.

**Triggering gap analysis (manual for now):**

- **UI:** run the Gap Analysis cognitive task from the dashboard (Cognitive Tasks).
- **CLI:** create an issue from `planning/issue_templates/gap-analysis.md` and assign it to Copilot.

Keeping this step manual is intentional during early validation: it’s where prioritisation and
judgment live.

### Step B — Issue creation (automatic, hardwired)

The orchestrator processes the pending directory and promotes the next file into a GitHub issue.
This step is deliberately “boring plumbing”:

- reads the next queue file
- creates the GitHub issue
- assigns it to Copilot
- moves the queue file to `processed/`

Rate limiting is intentional: **one issue per cycle**.

### Step C — Development (external / Copilot)

Copilot works the issue and produces a PR. Review/discussion happens in GitHub.
This is outside the orchestrator’s intelligence.

### Step D — PR completion & merge (automatic)

Another orchestrator job detects linked PRs, checks they’re complete/safe, and merges them (or
refuses). Again: deterministic, reliable automation.

### Step E — Capability update issue (cognitive, triggered)

On merge, a cognitive task creates a *new* issue whose body:

- includes the PR description
- includes PR comments/discussion (chronological)
- explicitly requests an update to `/planning/state/system_capabilities.md` to reflect the merge

This is the only place the system’s *self-knowledge* is updated.

### Step F — Capability update execution

That capability-update issue is worked (typically by Copilot). The capabilities document is updated
to match reality, and the issue is closed.

### Step G — Repeat

With updated capabilities, gap analysis can be run again and the loop continues.

### Parallel / periodic track — Review tasks

Independently, you can inject review issues every *N* completed development tasks (e.g. complexity
review, architecture drift, refactoring, test coverage). These are just additional issues flowing
through the same pipeline; they don’t disturb the main loop.

To test the loop in a real scenario, we intentionally keep **Step A (gap analysis) manual for now**.
Everything else (B–F) is designed to be runnable as automated jobs (e.g. cron/CI/webhooks), while still
remaining deterministic and inspectable.

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
```

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

# Optional (defaults shown)
GITHUB_BASE_URL=https://api.github.com
LOG_LEVEL=INFO
AGENT_STATE_PATH=agent_state

# REST server (optional)
# Needed for PR refresh/monitoring because Phase 1 state does not yet persist repo.
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
```

## Architecture

The Phase 1/1A implementation lives under `src/github_agent_orchestrator/orchestrator/`:

```
src/github_agent_orchestrator/
└── orchestrator/
    ├── config.py             # .env + env var settings
    ├── logging.py            # JSON logging
    ├── main.py               # CLI entrypoint
    └── github/
        ├── client.py         # PyGithub wrapper
        └── issue_service.py  # Issue creation + local persistence

agent_state/
└── issues.json               # persisted issue metadata
```

Key components:

* `OrchestratorSettings`: loads config from `.env`
* `GitHubClient`: authenticates and creates issues
* `IssueService`: idempotent-safe issue creation and persistence

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
- ✅ Core architecture and project structure
- ✅ LLM abstraction with OpenAI and LLaMA support
- ✅ GitHub integration for PRs and Issues
- ✅ Persistent state management
- ✅ Comprehensive testing and documentation

### Coming Soon (v0.2.0)
- 🚧 Complete orchestration workflow
- 🚧 Artefact-driven issue queue processing (one issue per cycle)
- 🚧 Automated code review integration
- 🚧 Enhanced error handling

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
