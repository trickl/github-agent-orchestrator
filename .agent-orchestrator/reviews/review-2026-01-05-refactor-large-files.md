# Review: large-file complexity (refactor plan refresh)

Date: 2026-01-05

This review assesses the current "large files" situation and proposes an incremental, low-risk path to reduce complexity.

Key constraint (must hold throughout): **move-first, patch-second**.

## Snapshot (large files ≥ 500 lines)

(From `scripts/find_large_files.py --format md --top 50` on 2026-01-05)

| Lines | Path |
| ---: | --- |
| 4746 | `src/github_agent_orchestrator/server/dashboard_router.py` |
| 2109 | `tests/unit/test_dashboard_api.py` |
| 1192 | `src/github_agent_orchestrator/orchestrator/github/client.py` |
| 1135 | `src/github_agent_orchestrator/orchestrator/main.py` |
| 768 | `src/github_agent_orchestrator/orchestrator/github/issue_service.py` |

## What’s already improved (don’t repeat)

- A `server/dashboard/` package exists.
- `server/dashboard/github_api.py` has been extracted from `dashboard_router.py`.
- `server/dashboard/queue_helpers.py` has been extracted from `dashboard_router.py`.

## Primary critique

### 1) `dashboard_router.py` is still acting as a god-module

Symptoms:
- It mixes HTTP route declarations with lots of supporting logic:
  - GitHub timeline/PR heuristics
  - auto-link / auto-resume automation
  - promote/merge operations
  - loop-stage computation
- The sheer size makes safe changes harder and increases the chance of accidental coupling.

### 2) `tests/unit/test_dashboard_api.py` is doing too much

Symptoms:
- One file covers multiple independent concerns (health, cognitive tasks, loop status, auto-resume, auto-link, promote/merge, gap-analysis ensure/repair).
- Refactoring production code becomes harder because the test file itself is difficult to navigate.

### 3) GitHub client + CLI entrypoint are large and likely to grow

- `orchestrator/github/client.py` is a multi-concern facade (URLs, pagination, parsing, higher-level operations).
- `orchestrator/main.py` contains extensive CLI wiring and a long command dispatch chain.

## Recommended next steps (incremental, move-first)

### A) Continue splitting `dashboard_router.py` by concern

Suggested new modules (leaf-style, no FastAPI router objects):

1) `server/dashboard/github_issue_pr_helpers.py`
- Move timeline/listing helpers and PR evaluation functions verbatim.

2) `server/dashboard/automation_auto_link.py`
- Move auto-link helpers verbatim.

3) `server/dashboard/automation_auto_resume.py`
- Move auto-resume helpers verbatim.

4) `server/dashboard/loop_actions.py`
- Move promote/merge helpers verbatim.

5) `server/dashboard/loop_status.py`
- Move loop-stage computation helpers verbatim.

Acceptance criteria:
- `dashboard_router.py` keeps route registrations + thin orchestration only.
- No behavior changes; tests pass.

### B) Split `tests/unit/test_dashboard_api.py`

Split by feature area (new files), keeping tests identical:
- `tests/unit/test_dashboard_api_health_docs.py`
- `tests/unit/test_dashboard_api_cognitive_tasks.py`
- `tests/unit/test_dashboard_api_loop_status.py`
- `tests/unit/test_dashboard_api_auto_resume.py`
- `tests/unit/test_dashboard_api_auto_link.py`
- `tests/unit/test_dashboard_api_loop_actions.py`

Acceptance criteria:
- Same test coverage, just reorganized.
- CI still passes.

### C) Tackle `orchestrator/main.py` and `orchestrator/github/client.py` next

- Extract CLI subcommand handler functions into `orchestrator/commands/*`.
- For the GitHub client, move helpers into modules (urls/pagination/parsing) while keeping `GitHubClient` as the facade.

Acceptance criteria:
- Public CLI behavior unchanged.
- Public `GitHubClient` behavior unchanged.

## Notes / risks

- Avoid circular imports: keep helper modules as “leaf” utilities.
- Keep signatures stable; move verbatim first.
- Run `pytest` after each slice.

