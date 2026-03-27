# GitHub Agent Orchestrator

<img src="docs/github-agent-orchestrator.svg" alt="GitHub Agent Orchestrator diagram" width="600" />

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Git-native **control loop for long-horizon, AI-assisted software development**, built around **bounded context**, **explicit state**, and **Copilot-only cognition**.

This project is intentionally **not** a monolithic chat agent and does **not** rely on a growing conversational context. Instead, planning, execution, and reflection are driven by **Git-tracked artefacts** and executed entirely via **GitHub Copilot**.

---

## Why this exists

Most agent systems follow a familiar pattern:

> Keep appending requests and responses to a growing context window and ask the model what to do next.

That pattern does not scale well for long-horizon software development.

As context grows:

- token cost grows
- summarisation becomes necessary
- details are lost
- state becomes implicit
- drift increases
- errors compound

There is also a deeper problem:

> **LLMs are path-dependent within a single conversational trajectory.**

In practice, once an early conclusion, diagnosis, or design assumption enters the context, later responses often become biased toward **preserving and elaborating that trajectory** rather than reconsidering it cleanly.

That creates a real risk in coding systems:

- early architectural mistakes become sticky
- weak assumptions get rationalised instead of challenged
- incorrect diagnoses propagate into later implementation steps
- coherence is rewarded over correction
- long-running chat loops become harder to steer back onto the best path

This matters for unsupervised development. A system that keeps working inside one expanding conversation can become **entrenched** in a flawed line of reasoning.

**GitHub Agent Orchestrator is designed specifically to resist that failure mode.**

It enforces a different invariant:

> **The LLM context is always bounded.**

All long-term state lives in the repository.

Each iteration operates over a **small, explicit, task-specific context** derived from files, not accumulated conversation. That makes the system easier to inspect, easier to correct, and less vulnerable to reasoning lock-in.

This is a **development control loop**, not a chat loop.

The goal is stable, unsupervised, productive development over periods of up to roughly 12 hours. That makes it useful **overnight** and **while you are away from the keyboard**.

---

## Design principles

GitHub Agent Orchestrator is built around a few strong constraints:

- **Bounded context**: no unbounded prompt growth
- **Explicit state**: long-term memory lives in versioned files
- **Task isolation**: each step is small, concrete, and independently framed
- **Git-native control**: repository artefacts are the source of truth
- **Copilot-only cognition**: reasoning and implementation are performed via GitHub Copilot
- **Stateless orchestration**: the orchestrator script coordinates the loop without becoming a second memory store

These constraints are deliberate. They are what make the system more stable over long horizons than a single persistent conversational thread.

---

## Quick Q&A

### Is this the same as the [Ralph Wiggum loop](https://github.com/vercel/ai/tree/main/examples/ralph-wiggum-loop)?

Short answer: **similar spirit, different mechanism.**

Both are designed for long-horizon, iterative development using AI.

The Ralph Wiggum loop works from a predefined list of requirements and iterates through them.

GitHub Agent Orchestrator instead behaves more like **gradient descent**:

- it computes the difference between **Target State** and **Current State**
- it derives the next issue from that difference
- it updates the Current State after merge
- it recomputes the next step from the new delta

There is no fixed canonical task list.  
Work emerges from the gap between the desired system and the current system.

Just as importantly, GitHub Agent Orchestrator is explicitly designed to avoid the failure mode of a single growing conversational context. Each iteration is re-grounded from repository state rather than inherited from an ever-longer chat transcript.

---

### What do I need to run this?

- a Python environment
- a GitHub account

That is it.

---

## Mental model

- **GitHub Copilot**: does the reasoning and software development
- **GitHub target repository**: contains code plus orchestration state
- **The orchestrator script**: manages the control loop and remains stateless

Concretely:

- Issues = **intent**
- PRs = **execution**
- Reviews = **reflection**
- Repository artefacts = **memory**

![GitHub Agent Orchestrator loop](docs/github-agent-orchestrator-loop.png)

---

## The main control loop

The system continuously iterates over two explicit states:

- **Target State**: `/.agent-orchestrator/state/target_state.md`
- **Current State**: `/.agent-orchestrator/state/current_state.md`

Each loop:

1. Compare target vs current
2. Identify a single concrete next development step
3. Produce one task artefact
4. Execute it via Copilot (issue -> PR)
5. Update the current state after completion
6. Repeat

There is **no growing prompt context**.

Each iteration is intentionally narrow. The model is not asked to carry forward a large conversational narrative. Instead, it is asked to act on explicit repository state.

That is a core part of the design, not an incidental implementation detail.

---

## Canonical artefacts

The entire loop is driven by a small, explicit set of Git-tracked artefacts:

```text
/.agent-orchestrator
    /state
        target_state.md
        current_state.md
    /reviews
        review-YYYY-MM-DD.md
    /issue_queue
        pending/
        processed/
        complete/
```

The `/.agent-orchestrator/issue_queue` directory is the handoff boundary between Copilot's reasoning and the orchestrator's control loop.

---

## Canonical task types

These are kept distinct on purpose.

### 1. Gap analysis

- compares target vs current
- produces exactly one task artefact
- makes no code changes

### 2. Development task

- implements one concrete change
- updates `current_state.md` when a capability refresh is requested

### 3. Review task

- critique only
- focuses on architecture, complexity, correctness, coverage, or maintainability
- produces a review artefact

### 4. Review consumption

- translates critique into candidate tasks
- does not execute them directly

This separation is one of the ways GitHub Agent Orchestrator avoids entrenchment. Generation, critique, and follow-up are not collapsed into one continuously self-reinforcing thread.

---

## Why bounded context is a feature, not a limitation

A common instinct with LLM systems is to preserve as much prior conversation as possible.

GitHub Agent Orchestrator deliberately does the opposite.

Why?

Because for long-running engineering work, preserving every prior turn can make the model more committed to its own earlier conclusions. A fresh, bounded task context is often better for:

- correcting earlier mistakes
- re-evaluating assumptions
- preventing prompt drift
- keeping costs predictable
- making reasoning inspectable
- reducing hidden state

In other words:

> **The system should remember the repository state, not the entire conversational path that happened to produce it.**

That distinction is central to the design.

---

## Features

- Minimal CLI for driving the loop
- Repo-derived loop state with no database
- Copilot-only planning and execution
- Structured JSON logs for the dashboard and API
- Optional REST server and UI dashboard for observability
- Explicit task decomposition
- Bounded-context execution for long-horizon stability

---

## Running checks locally

This repository does **not** run GitHub Actions by default.

After making changes, run the local verification script:

```bash
./scripts/verify-ci.sh
```

It runs linting, formatting checks, type checking, and tests.

---

## User role

The user owns the target specification:

```text
/.agent-orchestrator/state/target_state.md
```

Everything else is derived from that, either directly or indirectly.

---

## Quick start

### CLI-first quick start

```bash
orchestrator init --repo owner/repo
orchestrator auth github --token ghp_...
orchestrator run --repo owner/repo
```

Mode-driven package runner:

```bash
gao run
```

Optional repo override:

```bash
gao run --repo owner/repo
```

For ongoing operation:

```bash
orchestrator status --repo owner/repo --pretty
orchestrator run --repo owner/repo
orchestrator cost --pretty
```

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

### Configuration

```bash
ORCHESTRATOR_GITHUB_TOKEN=ghp_...
COPILOT_ASSIGNEE=copilot-swe-agent[bot]
LOG_LEVEL=INFO
ORCHESTRATOR_LOOP_MODE=build  # or: review
ORCHESTRATOR_TARGET_BASE_BRANCH=  # optional explicit base branch
ORCHESTRATOR_CREATE_WORK_BRANCH=true  # create per-issue work branches (safer default)
ORCHESTRATOR_WORK_BRANCH_PREFIX=orchestrator/work
```

Mode file in repo root (`.orchestrator.yml`):

```yaml
mode: semi
```

Supported values are `manual`, `semi` (default), and `auto`.

---

## REST server and dashboard (optional)

```bash
orchestrator-server
```

To run the same loop in **review mode**:

```bash
orchestrator-server --loop-mode review
```

In review mode:

- Step 1 consumes the next review file under `.agent-orchestrator/reviews/review-*.md` and produces exactly one queue artefact.
- Step 2 executes queued work. Both `review-*.md` and `dev-*.md` artefacts are eligible.
- Step 3 creates an "Update Review" issue that updates `.agent-orchestrator/reviews/review-YYYY-MM-DD.actions.md` with what was resolved.
- Review mode does **not** create "Update Capability" issues, so it does not update `.agent-orchestrator/state/current_state.md`.

API docs:

- OpenAPI: `http://127.0.0.1:8000/api/openapi.json`
- Swagger UI: `http://127.0.0.1:8000/api/docs`

---

## Lightweight local control-plane backend (pre-GitHub-App phase)

For GitHub App-based operation, this repository includes a minimal FastAPI control plane under `backend/app` that talks to **real GitHub repositories** using **GitHub App installation tokens**, while dispatching orchestration runs via **GitHub Actions**.

Run locally:

```bash
uvicorn backend.app.main:app --reload --port 8000
```

Required environment variables:

- `GITHUB_APP_ID` - GitHub App ID
- `GITHUB_APP_PRIVATE_KEY` - GitHub App private key PEM; `\n` escapes supported
- `GITHUB_APP_INSTALLATION_ID` - optional fixed installation id; repo-scoped lookup is used when omitted
- `GITHUB_APP_SLUG` - optional app slug used to build install URL for onboarding
- `GITHUB_APP_INSTALL_URL` - optional explicit install URL override
- `GITHUB_OAUTH_CLIENT_ID` - OAuth app client id for UI sign-in
- `GITHUB_OAUTH_CLIENT_SECRET` - OAuth app client secret
- `GITHUB_OAUTH_REDIRECT_URI` - typically `https://<backend>/auth/github/callback`
- `AUTH_FRONTEND_REDIRECT_URL` - typically your GitHub Pages URL
- `AUTH_SESSION_SECRET` - long random secret used to sign auth session cookies
- `AUTH_ALLOWED_GITHUB_USERS` - optional comma-separated GitHub login allowlist
- `GITHUB_API_URL` - optional, defaults to `https://api.github.com`
- `CORS_ORIGINS` - optional comma-separated list; include your GitHub Pages URL and local dev origin
- `GITHUB_WEBHOOK_SECRET` - required for `POST /webhooks/github` signature verification

Optional auth override flags:

- `BACKEND_REQUIRE_AUTH` - optional, defaults to `true`; set `false` only for local development bypass
- `AUTH_COOKIE_SECURE` - optional, defaults to `true`; set `false` only for non-HTTPS local testing

MVP endpoints:

- `POST /auth/github/start`
- `GET /auth/github-app/install-url`
- `GET /auth/github/callback`
- `GET /auth/me`
- `POST /auth/logout`
- `GET /repos`
- `GET /version`
- `POST /repos/{owner}/{repo}/target-state`
- `POST /repos/{owner}/{repo}/run`
- `GET /repos/{owner}/{repo}/status`
- `GET /repos/{owner}/{repo}/development-prs`
- `POST /webhooks/github`
- `GET /webhooks/events/recent`

`POST /repos/{owner}/{repo}/run` dispatches the configured workflow, `orchestrator.yml` by default, using `workflow_dispatch` for the selected repository.

This control plane requires GitHub App installation for repository access and does **not** require local repository cloning.

`GET /repos/{owner}/{repo}/status` includes `hasTargetState` so the UI can switch between first-time onboarding and the main control panel.

`POST /webhooks/github` currently provides deterministic summaries for:

- `workflow_run`
- `installation_repositories`
- `installation`
- `ping`

All other events are acknowledged and returned as `handled.kind: "unhandled"`.

`GET /webhooks/events/recent` returns an in-memory ring buffer of the latest accepted webhook deliveries, most recent first, which is useful for local debugging.

`GET /version` returns deploy verification metadata:

- `version` - backend semantic version
- `gitSha` - from `RENDER_GIT_COMMIT`, `GIT_COMMIT_SHA`, or `SOURCE_VERSION`
- `buildTimeUtc` - from `BUILD_TIME_UTC` when set; otherwise runtime timestamp

Use this endpoint after deployment to confirm the exact backend revision now serving traffic.

When `BACKEND_REQUIRE_AUTH=true`, control-plane routes under `/repos/*` require a valid signed session from the OAuth login flow. This prevents anonymous web users from invoking repository mutations.

For smoother first-time setup, the onboarding UI calls `GET /auth/github-app/install-url` and surfaces an **Install GitHub App** action when no repositories are visible yet.

---

## Keeping orchestrator runtime fresh in workflow runs

To prevent stale runtime installs in target repositories, ensure each orchestrator workflow installs the package at runtime. A reusable action is available in this repository:

`trickl/github-agent-orchestrator/.github/actions/setup-orchestrator@main`

Recommended usage in target repository workflows:

- use `with: version: latest` to install the newest published package each run
- use `with: version: <x.y.z>` to pin deterministically
- the action verifies the installed version and exposes `installed-version` output

Example step sequence in a workflow job:

1. `actions/setup-python`
2. `trickl/github-agent-orchestrator/.github/actions/setup-orchestrator@main`
3. `gao run --repo <owner/repo>` or `python -m github_agent_orchestrator.cli run --repo <owner/repo>`

The backend `/repos/{owner}/{repo}/update-orchestrator` endpoint also compares workflow pins against the backend package version and can open a PR to bump stale workflow pins.

---

## Automated versioning (main branch)

This repository includes automatic patch versioning on `main` via:

- `.github/workflows/version-bump.yml`
- `scripts/bump_version.py`

On each non-bot push to `main`, the workflow:

1. increments patch version (`x.y.z -> x.y.(z+1)`) in:
   - `pyproject.toml`
   - `src/github_agent_orchestrator/__init__.py`
2. commits the change
3. creates and pushes a `v<version>` git tag

After deployment, call `GET /version` to confirm both semantic version and commit SHA served live.

---

## UI deployment (GitHub Pages) and API connectivity

The UI is configured to support two modes automatically.

### Local development

In `ui/`:

```bash
npm run dev
```

This uses the Vite dev proxy:

```text
/api -> http://127.0.0.1:8000
```

So local UI traffic targets a localhost backend service.

### GitHub Pages deployment

- Workflow: `.github/workflows/ui-pages.yml`
- Build-time API base URL:
  - `https://github-agent-orchestrator.onrender.com`

If you see browser-side `Failed to fetch`, ensure backend CORS allows the UI origin.

Default backend CORS origins are:

- `https://trickl.github.io`
- `http://localhost:5173`
- `http://127.0.0.1:5173`

Override via `CORS_ORIGINS` as a comma-separated list in your deployment environment.

The Pages workflow also configures the correct Vite base path for repository-hosted pages, `/<repo-name>/`, during CI builds.

---

## Current status

- Artefact-driven development control loop
- Bounded-context execution
- Explicit repository-backed state
- Copilot-only planning and implementation
- Repo-derived state with no database
- Optional dashboard and REST API
- Comprehensive tests

---

## To do

- Periodic automated review cycles, for example complexity, test coverage, and visual QA
- Improved error handling and recovery
- Continued refinement of review and critique flows
- Better first-class surfacing of bounded-context benefits in the UI and onboarding flow

---

## License

MIT License - see `LICENSE`.
