Extract loop action helpers from dashboard_router.py (promote, merge, gap-analysis)

## Context

This task addresses **Review Item A.4** from `planning/reviews/review-2026-01-05-refactor-large-files.md`.

The review identified that `dashboard_router.py` (currently 3667 lines after prior extractions) is still acting as a god-module mixing HTTP route declarations with lots of supporting logic. The review recommends continuing the incremental extraction process that has already successfully reduced the file from 4746 lines through multiple PRs.

This task focuses on extracting the loop action operations (promote and merge) as the next incremental step, following the successful pattern established by prior extractions of:
- Pure utilities → `text_utilities.py` (PR #30)
- GitHub operations → `github_operations.py` and `github_issue_pr_helpers.py` (PR #36)
- Automation features → `automation_auto_link.py` and `automation_auto_resume.py` (PR #42)

## Review Items Being Addressed

From the review's "Recommended next steps (incremental, move-first)" section:

**A.4) `server/dashboard/loop_actions.py`**
- Move promote/merge helpers verbatim.

This is the fourth of five planned module extractions to bring `dashboard_router.py` down to ~600 lines (target: 87% total reduction from original 4746 lines).

## Scope

### Functions to Extract

**Core promote/merge operations (public endpoints and their implementations):**
1. `promote_next_pending_issue_queue_item()` (line 637) - FastAPI endpoint for queue promotion
2. `_promote_next_unpromoted_development_queue_item()` (line 1648) - Promotes dev queue items
3. `_promote_next_unpromoted_capability_queue_item()` (line 1782) - Promotes capability queue items

4. `merge_next_ready_development_pull_request()` (line 701) - FastAPI endpoint for PR merging
5. `_merge_next_ready_pull_request()` (line 723) - Main merge orchestrator
6. `_merge_next_ready_development_pull_request()` (line 2087) - Merges development PRs

**Merge strategy functions (try_merge family):**
7. `_try_merge_next_ready_labeled_issue_pull_request()` (line 757) - Merges labeled issue PRs
8. `_try_merge_next_ready_review_update_pull_request()` (line 971) - Merges review update PRs
9. `_try_merge_next_ready_gap_analysis_pull_request()` (line 982) - Merges gap analysis PRs
10. `_try_merge_next_ready_review_consumption_pull_request()` (line 1211) - Merges review consumption PRs
11. `_try_merge_next_ready_capability_pull_request()` (line 1430) - Merges capability tracking PRs

**Gap-analysis helpers (ensuring and maintaining gap analysis issues):**
12. `ensure_gap_analysis_issue()` (line 655) - FastAPI endpoint for gap analysis
13. `_ensure_gap_analysis_issue_exists()` (line 307) - Creates/updates gap analysis issue
14. `_gap_analysis_issue_body_looks_unsafe()` (line 249) - Safety check for issue body
15. `_repair_gap_analysis_issue_body_if_unsafe()` (line 265) - Repairs unsafe issue body

**Template loading helpers:**
16. `_load_gap_analysis_template_or_raise()` (line 168) - Loads gap analysis template
17. `_load_review_actions_after_merge_template_or_raise()` (line 224) - Loads review actions template

**Supporting helpers (used by merge/promote operations):**
18. `_extract_source_pr_number_from_capability_issue()` (line 1921) - Extracts PR number from capability issue
19. `_render_capability_update_issue_body()` (line 1960) - Renders capability update issue body

### Functions That Should NOT Be Extracted

The following functions should remain in `dashboard_router.py` as they belong to other concerns:

- `_load_review_consumption_template_or_raise()` - Used by review consumption (separate concern)
- `ensure_review_consumption_issue()` - Review consumption endpoint (separate concern)
- `_ensure_review_consumption_issue_exists()` - Review consumption logic (separate concern)
- `_review_actions_path_for_review_path()` - Review file path helper (separate concern)
- `_pick_next_review_file()` - Review selection logic (separate concern)
- `_queue_file_is_excluded_for_loop_mode()` - Loop status concern (will be extracted with loop_status.py)
- `_assign_issue_to_copilot()` - Generic GitHub helper (could be moved to github_operations later)
- `_extract_review_paths_from_queue_content()` - Review consumption helper (separate concern)
- `_render_review_actions_update_issue_body()` - Review actions helper (separate concern)

### Dependencies

The new `loop_actions.py` module will import from existing leaf modules:
- `github_operations.py` for GitHub API calls (get_pull_request, list_open_issues_raw, etc.)
- `github_issue_pr_helpers.py` for PR evaluation (pull_request_is_merge_candidate, etc.)
- `text_utilities.py` for text processing
- `github_api.py` for low-level API helpers (_github_post_json, _github_patch_json, etc.)
- `queue_helpers.py` for queue file operations

The module will also need:
- `ServerSettings` from `server.config`
- `Request` from `fastapi` (for the three public endpoint functions)
- Standard library imports (Path, datetime, json, logging, etc.)

### Expected Line Count Impact

Based on the function line numbers identified:
- **Approximate lines to extract**: ~1300-1500 lines (19 functions spanning lines 168-2450)
- **Before**: `dashboard_router.py` at 3667 lines
- **After**: `dashboard_router.py` at ~2200-2400 lines (35-40% reduction)
- **New file**: `loop_actions.py` (~1400-1600 lines with docstrings and imports)

After this extraction, one more module remains (`loop_status.py` with ~900 lines) to reach the target of ~600 lines for `dashboard_router.py`.

## Implementation Instructions

### Refactor Safety Rules (Mandatory)

Following the review's explicit constraints:

1. **Move code verbatim first** into the new module
2. **Update imports/call sites** to make it run
3. **Address visibility, scope, and parameterization** as fixes on the migrated code
4. **Only then do targeted improvements** (if any)

Additional constraints:
- Do not change the logic of code unless it's a clear bug
- Do not maintain legacy endpoints for backwards compatibility  
- Always delete any leftover, unused code
- Do not leave comments on changes made within the code
- Do not rewrite functions from scratch during refactors
- Ensure all tests and linting pass after each change

### Step 1: Create `loop_actions.py` skeleton

1. Create new file: `src/github_agent_orchestrator/server/dashboard/loop_actions.py`
2. Add comprehensive module docstring explaining the purpose:
   ```python
   """Loop action operations: promote and merge.
   
   This module contains the core orchestration logic for the two primary loop actions:
   - **Promote**: Converting pending queue files into assigned GitHub issues
   - **Merge**: Merging ready pull requests and triggering follow-up actions
   
   These operations are the "write side" of the orchestration loop, complementing
   the "read side" status computation in loop_status.py.
   """
   ```

3. Add all necessary imports (will be determined from the functions being moved)

### Step 2: Extract functions in logical groups

**Group 1: Template loading (lines 168-247)**
- Move `_load_gap_analysis_template_or_raise()` verbatim
- Move `_load_review_actions_after_merge_template_or_raise()` verbatim

**Group 2: Gap-analysis helpers (lines 249-409)**
- Move `_gap_analysis_issue_body_looks_unsafe()` verbatim
- Move `_repair_gap_analysis_issue_body_if_unsafe()` verbatim
- Move `_ensure_gap_analysis_issue_exists()` verbatim

**Group 3: Public endpoints (lines 637-679, 701-722)**
- Move `promote_next_pending_issue_queue_item()` verbatim (FastAPI endpoint)
- Move `ensure_gap_analysis_issue()` verbatim (FastAPI endpoint)
- Move `merge_next_ready_development_pull_request()` verbatim (FastAPI endpoint)

**Group 4: Merge orchestration (lines 723-970)**
- Move `_merge_next_ready_pull_request()` verbatim (main merge orchestrator)
- Move `_try_merge_next_ready_labeled_issue_pull_request()` verbatim

**Group 5: Merge strategies - reviews (lines 971-1210)**
- Move `_try_merge_next_ready_review_update_pull_request()` verbatim
- Move `_try_merge_next_ready_gap_analysis_pull_request()` verbatim

**Group 6: Merge strategies - consumption (lines 1211-1429)**
- Move `_try_merge_next_ready_review_consumption_pull_request()` verbatim

**Group 7: Merge strategies - capabilities (lines 1430-1647)**
- Move `_try_merge_next_ready_capability_pull_request()` verbatim

**Group 8: Promote operations (lines 1648-1920)**
- Move `_promote_next_unpromoted_development_queue_item()` verbatim
- Move `_promote_next_unpromoted_capability_queue_item()` verbatim

**Group 9: Supporting helpers (lines 1921-2030)**
- Move `_extract_source_pr_number_from_capability_issue()` verbatim
- Move `_render_capability_update_issue_body()` verbatim

**Group 10: Development merge (lines 2087-2452)**
- Move `_merge_next_ready_development_pull_request()` verbatim

### Step 3: Handle import strategy

Based on the successful patterns from previous extractions, choose the appropriate strategy:

**Option A: Import aliasing pattern** (used in PR #36 for `github_operations.py`)
- Import functions from `loop_actions.py` using underscore aliases in `dashboard_router.py`
- Example: `from ...loop_actions import promote_next_pending_issue_queue_item as promote_next_pending_issue_queue_item`
- This maintains test compatibility where tests mock `dashboard_router.promote_next_pending_issue_queue_item`

**Option B: Lazy imports pattern** (used in PR #42 for automation modules)
- Import `dashboard_router` inside function bodies in `loop_actions.py` to avoid circular dependencies
- Use this if functions in `loop_actions.py` need to call other `dashboard_router` functions that aren't being extracted
- Example: Inside a function: `from github_agent_orchestrator.server import dashboard_router`

**Recommendation**: Start with Option A (import aliasing) as it's cleaner. Only fall back to Option B if circular dependency issues arise during implementation.

### Step 4: Update `dashboard_router.py`

1. Add import statement at the top of `dashboard_router.py`:
   ```python
   from github_agent_orchestrator.server.dashboard.loop_actions import (
       promote_next_pending_issue_queue_item,
       ensure_gap_analysis_issue,
       merge_next_ready_development_pull_request,
   )
   ```
   
2. Delete the original function definitions (all 19 functions listed in scope)

3. For the three public FastAPI endpoint functions, if they need to remain registered in `dashboard_router.py`'s router:
   - Keep the router registration in `dashboard_router.py`
   - Import and use the function from `loop_actions.py`
   - OR move the router registration to `loop_actions.py` if that's the pattern

4. Update any internal calls within `dashboard_router.py` that referenced these functions

### Step 5: Verify test compatibility

1. Run the test file covering loop actions:
   ```bash
   pytest tests/unit/test_dashboard_api_loop_actions.py -v
   ```

2. The tests should pass without modification because they test the public endpoints which remain accessible

3. If tests fail due to mocking issues:
   - Tests currently mock `dashboard_router._function_name`
   - Update test mocks to patch `loop_actions._function_name` instead
   - OR if using import aliasing, tests can continue mocking `dashboard_router._function_name`

### Step 6: Run full test suite

1. Run all dashboard tests:
   ```bash
   pytest tests/unit/test_dashboard_api_*.py -v
   ```

2. Ensure no regressions in other test files

3. Run linting:
   ```bash
   ruff check src/github_agent_orchestrator/server/
   black --check src/github_agent_orchestrator/server/
   mypy src/github_agent_orchestrator/server/
   ```

### Step 7: Verify line count reduction

1. Check the new line count:
   ```bash
   wc -l src/github_agent_orchestrator/server/dashboard_router.py
   wc -l src/github_agent_orchestrator/server/dashboard/loop_actions.py
   ```

2. Expected results:
   - `dashboard_router.py`: ~2200-2400 lines (down from 3667)
   - `loop_actions.py`: ~1400-1600 lines (new)

## Acceptance Criteria

✅ **Completeness**:
- All 19 identified functions extracted to `loop_actions.py`
- No duplicate function definitions remain in `dashboard_router.py`
- All extracted functions are accessible from `dashboard_router.py` (via imports)

✅ **Correctness**:
- All tests in `test_dashboard_api_loop_actions.py` pass (10 tests)
- All other dashboard tests continue to pass
- No behavior changes in the promote or merge operations
- Linting passes (ruff, black, mypy)

✅ **Architecture**:
- No circular imports introduced
- `loop_actions.py` is a proper leaf module or imports only from other leaf modules
- Clear separation between loop actions (this module) and loop status (future module)
- Module docstring clearly explains the purpose and scope

✅ **Code Quality**:
- Functions moved verbatim (no logic changes)
- Imports are clean and organized
- No leftover unused code in `dashboard_router.py`
- No comments added explaining the refactoring (code should be self-evident)

## Notes

### Why This Extraction Is Safe

1. **Established pattern**: Following the same move-first approach used successfully in PRs #30, #36, and #42
2. **Test coverage**: The 10 tests in `test_dashboard_api_loop_actions.py` provide comprehensive coverage of these operations
3. **Clear boundaries**: Loop actions are distinct from loop status, making this a clean separation
4. **Incremental progress**: This is the fourth of five planned extractions, each reducing complexity step-by-step

### Relationship to Loop Status

The functions being extracted here are **action operations** (promote/merge). They are distinct from:
- **Status operations** (computing loop stage, checking readiness) - will be extracted to `loop_status.py` next
- **Automation operations** (auto-link, auto-resume) - already extracted in PR #42

Keep this distinction clear during implementation to avoid scope creep.

### Testing Strategy

The existing test file `tests/unit/test_dashboard_api_loop_actions.py` was specifically created in PR #12 and PR #18 to test these operations in isolation. The tests mock GitHub API calls and verify the promote/merge logic. No test modifications should be needed if the import strategy preserves the same call paths.

## References

- Source review: `planning/reviews/review-2026-01-05-refactor-large-files.md`
- Review actions: `planning/reviews/review-2026-01-05-refactor-large-files.actions.md`
- Related PRs: #30 (text utilities), #36 (github operations), #42 (automation modules)
- Test coverage: `tests/unit/test_dashboard_api_loop_actions.py` (10 tests, 707 lines)
