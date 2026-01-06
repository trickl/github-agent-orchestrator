# Extract loop_status.py module from dashboard_router.py (Final Refactor)

## Context

This is the **final extraction** in the dashboard_router.py refactoring series. Four of five planned extractions have been completed:

1. ✅ `github_issue_pr_helpers.py` - PR evaluation and issue matching (PR #36)
2. ✅ `automation_auto_link.py` - Auto-link automation (PR #42)
3. ✅ `automation_auto_resume.py` - Auto-resume automation (PR #42)
4. ✅ `loop_actions.py` - Promote and merge operations (PR #48)
5. **→ `loop_status.py`** - Loop-stage computation and status reporting (THIS TASK)

**Current state**: `dashboard_router.py` is at 1834 lines (down from 4746 lines originally, 61.4% reduction achieved).

**Target state**: Reduce `dashboard_router.py` to ~600 lines (87% total reduction), achieving the goal of keeping route declarations and thin orchestration only.

## Review Item Being Addressed

From `review-2026-01-05-refactor-large-files.md`, Review Item A.5:

> **A.5) `server/dashboard/loop_status.py`**
> - Move loop-stage computation helpers verbatim.
>
> Acceptance criteria:
> - `dashboard_router.py` keeps route registrations + thin orchestration only.
> - No behavior changes; tests pass.

## Task Description

Extract the loop status computation logic from `dashboard_router.py` into a new focused module `server/dashboard/loop_status.py`, following the established move-first, patch-second pattern.

### Functions to Extract

The following functions should be moved verbatim to the new `loop_status.py` module:

#### 1. Core Loop Status Functions

- `loop_status(request: Request) -> dict[str, object]` (line ~900)
  - Public FastAPI endpoint for UI-friendly loop status summary
  - Will remain importable from dashboard_router.py via import alias

- `_loop_status_for_repo(*, settings: ServerSettings, active_repo: str, ref: str) -> dict[str, object]` (line ~921)
  - Main logic for computing loop stage from persisted GitHub state
  - ~900+ lines of stage computation, queue analysis, PR/issue linkage
  - This is the core function that must be extracted

#### 2. Helper Functions

- `_queue_file_is_excluded_for_loop_mode(*, filename: str, loop_mode: str) -> bool` (line ~413)
  - Determines if a queue file should be excluded based on loop mode
  - Used by loop status computation to filter pending files

### Supporting Dependencies

The extracted module will need to import helper functions from existing dashboard modules:

**From `github_operations.py`:**
- `get_repo_text_file()`, `list_repo_markdown_files_under()`
- `list_open_issues_raw()`, `list_open_pull_requests_raw()`
- `get_pull_request()`, `list_issue_timeline_raw()`

**From `github_issue_pr_helpers.py`:**
- `best_match_issue_number()`, `issue_has_label()`
- `linked_pr_numbers_from_issue_timeline()`
- `pull_request_has_review_request()`, `pull_request_has_review_request_history()`
- `pull_request_is_merge_candidate()`

**From `queue_helpers.py`:**
- `_GAP_ANALYSIS_TITLES`, `_QUEUE_EXCLUDED_PREFIXES`
- `_is_gap_analysis_issue_title()`, `_queue_category_for_filename()`, `_queue_filename()`

**From `text_utilities.py`:**
- `_utc_now_iso()`, `_first_markdown_line_as_title()`

**From `loop_actions.py`:**
- `_extract_source_pr_number_from_capability_issue()` (already extracted in PR #48)

**From `github_api.py`:**
- `_github_get_json()`, `_repo_api_url()`

**From `github_labels.py`:**
- `LABEL_UPDATE_CAPABILITY`, `LABEL_UPDATE_REVIEW`, `LABEL_REVIEW_CONSUMPTION`

**Lazy imports from `dashboard_router`:**
For functions still residing in `dashboard_router.py`, use the lazy import pattern established in PR #42 and PR #48:
- `_settings()` - request context helper
- `_make_github_issue_url()` - GitHub issue URL builder

These will be imported lazily inside the extracted functions to avoid circular dependencies:

```python
def loop_status(request: Request) -> dict[str, object]:
    from github_agent_orchestrator.server import dashboard_router
    settings = dashboard_router._settings(request)
    # ... rest of function
```

### Implementation Steps

Follow the established "move-first, patch-second" pattern from previous PRs:

#### Step 1: Create the new module
1. Create `src/github_agent_orchestrator/server/dashboard/loop_status.py`
2. Add module docstring explaining purpose: "Loop status computation and stage reporting for the orchestrator dashboard"
3. Move all identified functions **verbatim** from `dashboard_router.py`
4. Add necessary imports at the top of the new module
5. Use lazy imports for `dashboard_router._settings()` and `dashboard_router._make_github_issue_url()` to avoid circular dependencies

#### Step 2: Update dashboard_router.py
1. Import the extracted public endpoint with alias:
   ```python
   from github_agent_orchestrator.server.dashboard.loop_status import (
       loop_status as loop_status,
   )
   ```
2. Import private helper if needed:
   ```python
   from github_agent_orchestrator.server.dashboard.loop_status import (
       _queue_file_is_excluded_for_loop_mode as _queue_file_is_excluded_for_loop_mode,
   )
   ```
3. Apply router decorator to the imported endpoint:
   ```python
   loop_status = router.get("/loop/status")(loop_status)
   ```
4. Remove the original function definitions from `dashboard_router.py`

#### Step 3: Update test files
The loop status tests are in `tests/unit/test_dashboard_api_loop_status.py` (created in PR #18).

1. Review existing test patches for functions being extracted
2. Add dual-patching for extracted functions (following PR #48 pattern):
   ```python
   # If tests currently patch dashboard_router._loop_status_for_repo:
   monkeypatch.setattr(dashboard_router, "_loop_status_for_repo", mock_func)
   monkeypatch.setattr(loop_status, "_loop_status_for_repo", mock_func)
   ```
3. Ensure all tests pass with both patches in place

### Verification Steps

1. Run linters and formatters:
   ```bash
   ruff check src/github_agent_orchestrator/server/dashboard/loop_status.py
   black src/github_agent_orchestrator/server/dashboard/loop_status.py
   isort src/github_agent_orchestrator/server/dashboard/loop_status.py
   ```

2. Run loop status tests specifically:
   ```bash
   pytest tests/unit/test_dashboard_api_loop_status.py -v
   ```

3. Run all dashboard API tests:
   ```bash
   pytest tests/unit/test_dashboard_api*.py -v
   ```

4. Verify line count reduction:
   ```bash
   wc -l src/github_agent_orchestrator/server/dashboard_router.py
   wc -l src/github_agent_orchestrator/server/dashboard/loop_status.py
   ```

Expected: dashboard_router.py should be reduced from 1834 lines to ~600 lines (1234 line reduction), with loop_status.py containing ~1234+ lines.

### Success Criteria

- ✅ New `server/dashboard/loop_status.py` module created with all loop status functions
- ✅ `dashboard_router.py` reduced to ~600 lines (route registrations + thin orchestration only)
- ✅ All imports updated correctly with no circular dependencies
- ✅ Import aliases maintain backward compatibility for test patching
- ✅ All tests pass (especially `test_dashboard_api_loop_status.py`)
- ✅ No behavior changes - endpoints return identical responses
- ✅ Linting passes for both files

### Refactor Safety Rules (CRITICAL)

These constraints from the review consumption template MUST be followed:

1. **Move code verbatim first** into the new module location
2. **Update imports/call sites** to make it run, address visibility, scope and parameterization as a fix on the migrated code
3. **Only then do targeted improvements** if absolutely necessary

**Additional constraints:**
1. Do **not** change the logic of code unless it has been identified as a clear bug
2. Do **not** maintain legacy endpoints for backwards compatibility
3. **Always delete** any leftover, unused code
4. Do **not** leave comments on changes made within the code
5. Do **not** rewrite functions from scratch during refactors
6. **Ensure all tests and linting pass** after each change

### Notes

- This is the final extraction in the dashboard_router.py refactoring series
- The loop_status logic is ~900+ lines and is the largest remaining block in dashboard_router.py
- After this extraction, dashboard_router.py should contain only:
  - Route registration (@router decorators)
  - Thin request parameter extraction and validation
  - Review consumption helpers (these remain as they are specific to review workflow orchestration)
  - Cognitive task template loading (small helper functions)
  - Basic utility functions that don't fit elsewhere
- The lazy import pattern (importing dashboard_router inside functions) is the established solution for circular dependencies
- Follow the dual-patching pattern from PR #48 for test compatibility
