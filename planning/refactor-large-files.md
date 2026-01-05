# Refactor plan: reduce large-file complexity

Date: 2026-01-05

This document proposes an incremental, low-risk plan to reduce complexity caused by very large
Python files (especially those exceeding 500 lines).

Key constraint (must hold throughout): **move-first, patch-second**.

- We will **move functions/methods verbatim first** into new modules.
- Then we will **patch call sites** to fix imports/visibility/scoping.
- We will **not rewrite logic** (behavior must remain equivalent).

## How we identify large files

A helper script is included at `scripts/find_large_files.py`.

Defaults:
- scans the repo root
- includes only `.py`
- excludes generated/vendor dirs (including `node_modules/` and `htmlcov/`)
- reports files **≥ 500 lines**

Suggested usage:
- `python scripts/find_large_files.py`
- `python scripts/find_large_files.py --format md --top 50`

## Current large files (≥ 500 lines)

From the scan on 2026-01-05:

| Lines | Path |
| ---: | --- |
| 4746 | `src/github_agent_orchestrator/server/dashboard_router.py` |
| 2109 | `tests/unit/test_dashboard_api.py` |
| 1192 | `src/github_agent_orchestrator/orchestrator/github/client.py` |
| 1135 | `src/github_agent_orchestrator/orchestrator/main.py` |
| 768 | `src/github_agent_orchestrator/orchestrator/github/issue_service.py` |

## Cross-cutting refactor approach

### Golden rules

1. **Move first, patch second**
   - Step 1: copy/move functions into new module(s) unchanged.
   - Step 2: update the original file to import and call those moved functions.
   - Step 3: run tests.

2. **One coherent slice per PR**
   - Each PR moves one cluster of related functions and keeps behavior unchanged.

3. **Keep public API stable**
   - Anything imported from outside the file should keep its name/signature unless we
     explicitly coordinate a change.

4. **Avoid circular imports**
   - Prefer “leaf” helper modules (pure helpers, no FastAPI router objects) and have
     `dashboard_router.py` import from them.

5. **Prove equivalence with tests**
   - Run `./scripts/verify-ci.sh` (or at least `pytest`) after each move.

### Mechanical steps (repeatable recipe)

For each group of functions to move:

1. Create a new module (e.g. `src/.../server/dashboard/github_api.py`).
2. Move selected functions verbatim.
3. Fix any missing imports in the new module (minimal edits).
4. In the old module, replace the moved function bodies with imports + calls, or remove them
   if not needed.
5. Update internal references (`_private_fn` calls) to reference the new module import.
6. Run tests; only then proceed to the next slice.

---

## File-by-file plan

### 1) `src/github_agent_orchestrator/server/dashboard_router.py` (4746 lines)

#### What it currently does (high-level)

This module contains:
- FastAPI route registrations (12 endpoints) under `router = APIRouter()`
- A large amount of supporting logic, including:
  - REST API helpers (GET/POST/PATCH/PUT/DELETE wrappers, headers, URL builders)
  - GraphQL helpers and error shaping
  - Issue/PR timeline interpretation and heuristics
  - Queue operations (promote pending, move to processed/complete)
  - Merge automation (approve + merge, mark draft ready-for-review)
  - Post-merge “capability update” issue creation and discussion rendering
  - Loop status computation (the “stage” logic) and focused-issue heuristics
  - Best-effort automation: auto-link focused issue ↔ PR, auto-resume Copilot after failures

The only true “router” content is relatively small; most bulk is helper/automation code.

#### Target structure (suggested)

Already in place:
- `src/github_agent_orchestrator/server/dashboard/`

Status (as of 2026-01-05)

Already extracted (done):

1) `server/dashboard/github_api.py`
- `_github_headers`, `_repo_api_url`, `_graphql_api_url`
- `_github_get_json`, `_github_get_list`, `_github_post_json`, `_github_patch_json`, `_github_put_json`, `_github_delete_json`
- `_github_graphql_post`, `_graphql_errors_as_message`

2) `server/dashboard/queue_helpers.py`
- `_queue_filename`, `_queue_category_for_filename`, `_parse_queue_file_for_issue`, etc.

Remaining suggested modules (grouped by concern):

1) `server/dashboard/github_issue_pr_helpers.py`
- `_list_issue_comments_raw`, `_list_issue_events_raw`, `_list_issue_timeline_raw`
- `_linked_pr_numbers_from_issue_timeline`
- `_pull_request_has_review_request`, `_pull_request_has_review_request_history`
- `_pull_request_title_is_wip`, `_pull_request_is_ready_for_review`, `_pull_request_is_merge_candidate`

2) `server/dashboard/automation_auto_link.py`
- `_strip_fenced_code_blocks`, `_issue_is_mentioned_as_closing*`
- `_copilot_login_candidates`, `_maybe_auto_link_focused_issue_to_pr`

3) `server/dashboard/automation_auto_resume.py`
- `_maybe_auto_resume_copilot_after_rate_limit` plus its small helpers

4) `server/dashboard/loop_actions.py`
- `_promote_next_unpromoted_development_queue_item`
- `_promote_next_unpromoted_capability_queue_item`
- `_merge_next_ready_pull_request`, `_try_merge_next_ready_*`, `_merge_next_ready_development_pull_request`
- `_render_capability_update_issue_body`, `_get_pull_request_discussion_markdown`

5) `server/dashboard/loop_status.py`
- `_loop_status_for_repo` and any helpers that are only used for loop stage derivation

Then keep `server/dashboard_router.py` mostly as:
- imports
- `router = APIRouter()`
- endpoint handlers that call into the new modules

#### Suggested slicing order

To minimize risk and avoid circular imports:

1. Move timeline/PR evaluation helpers (`github_issue_pr_helpers.py`).
2. Move auto-link and auto-resume helpers (very self-contained).
3. Move loop actions (promote/merge) next.
4. Move loop status last (it references most helper utilities).

---

### 2) `src/github_agent_orchestrator/orchestrator/github/client.py` (1192 lines)

#### What it currently does

`GitHubClient` is a wrapper around requests + PyGithub and includes:
- URL builders (`_issues_url`, `_pulls_url`, `_repo_url`, `_search_url`)
- REST/GraphQL utilities (`_graphql_url`, `_graphql_post`, session setup)
- Pagination (`_get_paginated_json_list`)
- Parsing helpers (`_parse_datetime`, `_safe_login`, `_parse_pull_request_json`, timeline parsing)
- Higher-level operations (create issue, assign issue, PR operations, branch deletion)

#### Target structure (suggested)

Keep `GitHubClient` as the facade, but move internal helper methods into modules as functions.
This preserves behavior while shrinking the file.

Suggested modules:

- `orchestrator/github/rest_urls.py`
  - move URL-builder methods to module functions (pass `rest_base_url`, `repository_name`).

- `orchestrator/github/rest_pagination.py`
  - move `_get_paginated_json_list` (pass `session`, `url`).

- `orchestrator/github/parsing.py`
  - move `_parse_datetime`, `_safe_login`, `_parse_pull_request_json`, `_linked_pr_numbers_from_issue_timeline`, `_parse_linked_pull_request_rest`.

- `orchestrator/github/pull_requests.py`
  - move methods that operate on PRs (get PR, mark ready for review, merge, delete branch) as module functions.

- `orchestrator/github/issues.py`
  - move methods that operate on issues (get issue, create issue, assign/unassign, search marker).

Implementation pattern (minimal change):
- Module-level functions take the necessary `session`, base URL, repo string, etc.
- `GitHubClient` methods call the moved functions.

---

### 3) `src/github_agent_orchestrator/orchestrator/main.py` (1135 lines)

#### What it currently does

- Defines the CLI parser (`build_parser`) with many subcommands.
- Implements command execution in a large `main()` with a long `if args.command == ...` chain.

#### Target structure (suggested)

- Keep `main.py` as the entrypoint.
- Move subcommand wiring functions and command handlers out.

Suggested modules:

- `orchestrator/cli_parser.py`
  - functions like `add_create_issue_subcommand(subparsers)`, etc.
  - keep `build_parser()` thin by delegating.

- `orchestrator/commands/` package
  - one module per command, e.g.:
    - `commands/create_issue.py` (handler function)
    - `commands/assign_copilot.py`
    - `commands/monitor_prs.py`
    - `commands/merge_linked_prs.py`
    - `commands/gap_analysis_cycle.py`
    - `commands/promote_issue_queue.py`
    - `commands/system_capabilities_after_merge.py`
    - `commands/complete_issue_queue_item.py`
    - `commands/auto_resume_copilot.py`
    - `commands/auto_link_issue_pr.py`

Move plan (mechanical):
- Extract each command block into a function, move that function into its command module,
  and call it from `main.py`.

---

### 4) `src/github_agent_orchestrator/orchestrator/github/issue_service.py` (768 lines)

#### What it currently does

- Defines persisted state model `IssueRecord` and related helper dataclasses.
- Implements local JSON persistence (`IssueStore`).
- Implements orchestration logic (`IssueService`) for:
  - idempotent issue creation (title-based and queue-id-based)
  - assignment to Copilot (agent assignment payload)
  - linked PR polling and completion evaluation
  - best-effort merge + branch deletion loop

#### Target structure (suggested)

This file can be reduced by moving cohesive helper functions and “monitor/merge” logic into
separate modules.

Suggested modules:

- `orchestrator/github/issue_store.py`
  - move `IssueStore` methods if/when we allow moving classes; if sticking strictly to functions only,
    start by moving helper functions used by the store (e.g. repository inference).

- `orchestrator/github/pr_completion.py`
  - move `_evaluate_pr_completion`, `_linked_pr_to_json`

- `orchestrator/github/issue_models.py`
  - (optional) if later allowed, move `IssueRecord` and small dataclasses.

- `orchestrator/github/issue_service.py`
  - keep `IssueService` here, but shrink by importing moved helpers.

Given the “functions only” constraint, the first wins are:
- `_infer_repository_from_record`
- `_linked_pr_to_json`
- `_evaluate_pr_completion`

Then later we can consider moving larger method groups if we loosen the constraint.

---

### 5) `tests/unit/test_dashboard_api.py` (2109 lines)

#### What it currently tests

This file covers multiple independent concerns:
- health + docs endpoints
- cognitive task template exposure
- loop status stage computation (multiple stages)
- auto-resume behavior
- auto-link behavior (including code-fence safety)
- promote/merge endpoints
- gap-analysis ensure behavior and unsafe-body repair behavior

#### Target structure (suggested)

Split into multiple test modules grouped by endpoint/feature:

- `tests/unit/test_dashboard_api_health_docs.py`
  - `test_dashboard_health_and_docs`

- `tests/unit/test_dashboard_api_cognitive_tasks.py`
  - `test_cognitive_tasks_*`

- `tests/unit/test_dashboard_api_loop_status.py`
  - `test_loop_status_*` stage tests

- `tests/unit/test_dashboard_api_auto_resume.py`
  - `test_loop_status_auto_resumes_*`

- `tests/unit/test_dashboard_api_auto_link.py`
  - `test_loop_status_auto_links_*`
  - `test_auto_link_ignores_*`

- `tests/unit/test_dashboard_api_loop_actions.py`
  - promote/merge endpoint tests
  - gap analysis ensure tests

This is a very safe refactor because tests generally don’t have external importers; we just
need to keep any shared fixtures/helpers accessible (either duplicated, or moved into
`tests/unit/dashboard_api_fixtures.py`).

---

## Suggested execution order (highest ROI first)

1. `dashboard_router.py` (largest and most central)
2. `test_dashboard_api.py` (keeps test maintenance sane while router moves)
3. `orchestrator/main.py` (CLI maintainability)
4. `orchestrator/github/client.py` and `issue_service.py` (shared GitHub logic)

## Definition of done

- No file in `src/` exceeds ~500 lines (tests can be slightly larger, but prefer the same cap).
- All tests pass (`./scripts/verify-ci.sh`).
- Imports remain clear (no circular dependencies).
- No behavioral changes: the refactor should be mechanically equivalent.
