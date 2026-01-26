Extract automation helper modules from dashboard_router.py (auto-link and auto-resume)

## Context

This task addresses **Review Item A** from `review-2026-01-05-refactor-large-files.md`.

The review identified that `dashboard_router.py` (currently 4038 lines) is still acting as a god-module mixing HTTP route declarations with lots of supporting logic. The review recommends continuing the incremental extraction process that has already successfully reduced the file from 4746 lines to 4038 lines through earlier PRs.

This task focuses on extracting two related automation feature modules as the next incremental step.

## Review Items Being Addressed

From the review's "Recommended next steps (incremental, move-first)" section:

**2) `server/dashboard/automation_auto_link.py`**
- Move auto-link helpers verbatim.

**3) `server/dashboard/automation_auto_resume.py`**
- Move auto-resume helpers verbatim.

These two modules are batched together because:
- They are both automation features (conceptually related)
- They are relatively small (~186 + ~144 = ~330 lines combined)
- They are self-contained with minimal cross-dependencies
- They can be safely extracted together in one PR without conflict

## Scope

### Functions to Extract

**To `automation_auto_link.py` (~186 lines, line 305-490):**
- `_maybe_auto_link_focused_issue_to_pr()` - Main auto-link logic
- `_issue_is_mentioned_as_closing()` - Helper for detecting closing keywords
- `_issue_is_mentioned_as_closing_outside_code_blocks()` - Helper for detecting closing keywords outside code blocks
- Any constants or helper functions used exclusively by auto-link

**To `automation_auto_resume.py` (~144 lines, line 132-275):**
- `_maybe_auto_resume_copilot_after_rate_limit()` - Main auto-resume logic
- `_copilot_login_candidates()` - Helper for identifying Copilot user logins
- Any constants or helper functions used exclusively by auto-resume

### Dependencies

Both modules will import from existing leaf modules:
- `github_operations.py` for GitHub API calls
- `github_issue_pr_helpers.py` for PR/issue evaluation
- `text_utilities.py` for text processing utilities
- `github_api.py` for low-level API helpers

### Expected Line Count Impact

- **Before**: `dashboard_router.py` at 4038 lines
- **After**: `dashboard_router.py` at ~3708 lines (330 line reduction, 8.2%)
- **New files**: 
  - `automation_auto_link.py` (~200 lines with docstrings)
  - `automation_auto_resume.py` (~160 lines with docstrings)

## Implementation Instructions

### Step 1: Create `automation_auto_link.py`

1. Create new file: `src/github_agent_orchestrator/server/dashboard/automation_auto_link.py`
2. Add module docstring explaining the purpose: "Auto-link automation for connecting issues to PRs when GitHub signals are missing"
3. Copy the following functions **verbatim** from `dashboard_router.py`:
   - `_maybe_auto_link_focused_issue_to_pr()` (main function, line ~305-490)
   - `_issue_is_mentioned_as_closing()` (helper, line ~289-299)
   - `_issue_is_mentioned_as_closing_outside_code_blocks()` (helper, line ~301-303)
4. Add necessary imports at the top:
   - Import from `github_operations` (for `get_pull_request`, `list_issue_timeline_raw`, etc.)
   - Import from `github_issue_pr_helpers` (for PR evaluation helpers)
   - Import from `text_utilities` (for `_strip_fenced_code_blocks`, `_AUTO_LINK_NOTICE_MARKER`, `_comment_body_is_auto_link_notice`)
   - Import from `github_api` (for `_github_patch_json`, `_repo_api_url`, etc.)
   - Import `ServerSettings` from `server.config`
5. Keep all function signatures exactly as they are in the original
6. Keep all internal logic exactly as-is (move verbatim first)

### Step 2: Create `automation_auto_resume.py`

1. Create new file: `src/github_agent_orchestrator/server/dashboard/automation_auto_resume.py`
2. Add module docstring explaining the purpose: "Auto-resume automation for nudging Copilot after rate limit failures"
3. Copy the following functions **verbatim** from `dashboard_router.py`:
   - `_maybe_auto_resume_copilot_after_rate_limit()` (main function, line ~132-275)
   - `_copilot_login_candidates()` (helper, line ~276-287)
4. Add necessary imports at the top:
   - Import from `github_operations` (for `list_issue_events_raw`, `list_issue_comments_raw`, etc.)
   - Import from `text_utilities` (for `_COPILOT_RATE_LIMIT_RESUME_COMMENT`, `_comment_body_is_copilot_resume_nudge`, `_dt_from_iso`, `_utc_now`)
   - Import from `github_api` (for `_github_post_json`, `_repo_api_url`, etc.)
   - Import `ServerSettings` from `server.config`
5. Keep all function signatures exactly as they are in the original
6. Keep all internal logic exactly as-is (move verbatim first)

### Step 3: Update `dashboard_router.py`

1. Add imports for the extracted functions using the established aliasing pattern:
   ```python
   from github_agent_orchestrator.server.dashboard.automation_auto_link import (
       maybe_auto_link_focused_issue_to_pr as _maybe_auto_link_focused_issue_to_pr,
   )
   from github_agent_orchestrator.server.dashboard.automation_auto_resume import (
       maybe_auto_resume_copilot_after_rate_limit as _maybe_auto_resume_copilot_after_rate_limit,
   )
   ```
   Note: Remove the leading underscore from the imported function names (public exports from the new modules) but alias them with underscores to maintain backward compatibility in dashboard_router.py.

2. Delete the original function definitions that were moved:
   - Delete `_maybe_auto_resume_copilot_after_rate_limit()` and `_copilot_login_candidates()` (lines ~132-287)
   - Delete `_maybe_auto_link_focused_issue_to_pr()`, `_issue_is_mentioned_as_closing()`, and `_issue_is_mentioned_as_closing_outside_code_blocks()` (lines ~289-490)

3. Verify all call sites in `dashboard_router.py` continue to work with the aliased imports

### Step 4: Export Functions from New Modules

Make the main functions public exports (without leading underscores) in the new modules while helper functions can remain private:

In `automation_auto_link.py`:
- Export: `maybe_auto_link_focused_issue_to_pr` (remove leading underscore for public API)
- Keep private: `_issue_is_mentioned_as_closing`, `_issue_is_mentioned_as_closing_outside_code_blocks`

In `automation_auto_resume.py`:
- Export: `maybe_auto_resume_copilot_after_rate_limit` (remove leading underscore for public API)
- Keep private: `_copilot_login_candidates`

### Step 5: Verify No Circular Dependencies

1. Ensure the new modules only import from:
   - Leaf modules (`github_operations`, `github_issue_pr_helpers`, `text_utilities`, `github_api`)
   - Standard library
   - External packages (requests, etc.)
   - Config (`server.config`)
2. They must NOT import from `dashboard_router` or each other
3. `dashboard_router` imports from the new modules (safe, no cycle)

## Acceptance Criteria

- [ ] `automation_auto_link.py` created with ~200 lines
- [ ] `automation_auto_resume.py` created with ~160 lines
- [ ] `dashboard_router.py` reduced by ~330 lines (4038 → ~3708)
- [ ] All functions moved verbatim (no logic changes)
- [ ] Import aliasing pattern followed for backward compatibility
- [ ] No circular dependencies introduced
- [ ] All existing tests pass without modification
- [ ] Dashboard API endpoints continue to work identically
- [ ] `pytest tests/unit/test_dashboard_api_auto_link.py` passes
- [ ] `pytest tests/unit/test_dashboard_api_auto_resume.py` passes
- [ ] `pytest tests/unit/test_dashboard_api_loop_status.py` passes
- [ ] `pytest tests/unit/test_dashboard_api_loop_actions.py` passes

## Refactor Safety Rules (Mandatory)

1. **Move code verbatim first** into the new modules
2. Update imports in `dashboard_router.py` to make it run
3. Do NOT change any logic during the move
4. Do NOT add improvements or refactoring during the move
5. Do NOT rewrite functions from scratch
6. Keep function signatures identical
7. Tests should pass without any test modifications

## Constraints

1. Do not change the logic of code unless it has been identified as a clear bug
2. Do not maintain legacy endpoints for backwards compatibility (the aliasing IS the compatibility layer)
3. Always delete the leftover original code after moving
4. Do not leave comments on changes made within the code
5. Do not rewrite functions from scratch during refactors

## Testing Strategy

Run existing tests to verify the extraction didn't break anything:
```bash
pytest tests/unit/test_dashboard_api_auto_link.py -v
pytest tests/unit/test_dashboard_api_auto_resume.py -v
pytest tests/unit/test_dashboard_api_loop_status.py -v
pytest tests/unit/test_dashboard_api_loop_actions.py -v
```

These tests already mock the functions at the dashboard_router level, so they should continue to work with the import aliasing pattern.

## Expected Outcome

After this PR:
- `dashboard_router.py` will be ~3708 lines (8.2% reduction from 4038)
- Two new focused modules handle automation concerns
- The file continues toward the target of ~600 lines (87% total reduction goal)
- Foundation is set for the remaining two extractions:
  - `loop_status.py` (~934 lines)
  - `loop_actions.py` (~2293 lines)

