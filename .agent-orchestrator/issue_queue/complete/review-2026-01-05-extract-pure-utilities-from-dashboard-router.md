Extract pure utility functions from dashboard_router.py into a dedicated utilities module

## Context
This task addresses a focused subset of **Review Item A** from review `.agent-orchestrator/reviews/review-2026-01-05-refactor-large-files.md`.

The review identified that `dashboard_router.py` (4746 lines) is acting as a "god-module" that mixes HTTP route declarations with extensive supporting logic. A previous attempt (PR #12) to extract multiple modules from dashboard_router.py was deferred due to circular import issues and tightly-coupled test mocking.

This task takes a safer, incremental approach by extracting **only pure utility functions** that have no dependencies on other dashboard_router functions and pose zero risk of circular imports.

## Review Items Being Addressed

This task addresses a subset of **Review Item A: Continue splitting `dashboard_router.py` by concern**.

Specifically, we are extracting pure utility functions that belong in a leaf-level utilities module, avoiding the circular dependency issues that blocked PR #12.

## Detailed Instructions

### Phase 1: Identify Pure Utility Functions

Review `dashboard_router.py` and identify functions that meet ALL of these criteria:
1. Pure helper functions (no side effects beyond computation)
2. Do NOT call other functions defined in `dashboard_router.py`
3. Do NOT depend on FastAPI, Request objects, or ServerSettings
4. Do NOT make GitHub API calls
5. Are truly "leaf" utilities (string processing, date/time helpers, text parsing, etc.)

Based on initial analysis, candidate functions include:
- `_utc_now()` - Returns current UTC datetime
- `_utc_now_iso()` - Returns current UTC datetime as ISO string
- `_dt_from_iso(value: str)` - Parses ISO datetime string
- `_comment_body_is_copilot_resume_nudge(body: str)` - Checks for resume nudge marker in comment
- `_comment_body_is_auto_link_notice(body: str)` - Checks for auto-link marker in comment
- `_strip_fenced_code_blocks(markdown: str)` - Removes code blocks from markdown
- `_normalize_issue_title(title: str)` - Normalizes issue title for matching
- `_first_markdown_line_as_title(content: str)` - Extracts first line from markdown as title
- `_normalize_repo_path_candidate(value: str)` - Normalizes repository path

**Critical**: Verify each function's implementation to ensure it truly has no dependencies on other dashboard_router functions before including it in the extraction.

### Phase 2: Create New Utilities Module

1. **Create** `src/github_agent_orchestrator/server/dashboard/text_utilities.py`
2. **Move functions verbatim** from `dashboard_router.py` into the new module:
   - Copy each function definition exactly as-is (including docstrings, type hints, implementation)
   - Include any module-level constants that the functions depend on (e.g., `_COPILOT_RATE_LIMIT_RESUME_COMMENT`, `_AUTO_LINK_NOTICE_MARKER`)
3. **Add necessary imports** to the new module (e.g., `from datetime import datetime, timezone`)
4. **Add module docstring** explaining the purpose: pure text/datetime utilities used across dashboard modules

### Phase 3: Update dashboard_router.py

1. **Add import statement** at the top of `dashboard_router.py`:
   ```python
   from .dashboard.text_utilities import (
       _utc_now,
       _utc_now_iso,
       _dt_from_iso,
       _comment_body_is_copilot_resume_nudge,
       _comment_body_is_auto_link_notice,
       _strip_fenced_code_blocks,
       _normalize_issue_title,
       _first_markdown_line_as_title,
       _normalize_repo_path_candidate,
   )
   ```
2. **Delete the original function definitions** from `dashboard_router.py`
3. **Delete any module-level constants** that were moved to the new utilities module
4. **Verify** that all call sites in `dashboard_router.py` still work with the imported functions

### Phase 4: Verify and Test

1. **Run linters** to catch any import errors:
   ```bash
   ruff check src/github_agent_orchestrator/server/dashboard_router.py
   ruff check src/github_agent_orchestrator/server/dashboard/text_utilities.py
   mypy src/github_agent_orchestrator/server/dashboard_router.py
   mypy src/github_agent_orchestrator/server/dashboard/text_utilities.py
   ```

2. **Run targeted tests** to ensure behavior is unchanged:
   ```bash
   pytest tests/unit/test_dashboard_api_health_docs.py -v
   pytest tests/unit/test_dashboard_api_loop_status.py -v
   pytest tests/unit/test_dashboard_api_auto_resume.py -v
   pytest tests/unit/test_dashboard_api_auto_link.py -v
   pytest tests/unit/test_dashboard_api_loop_actions.py -v
   ```

3. **Verify line count reduction**:
   ```bash
   wc -l src/github_agent_orchestrator/server/dashboard_router.py
   wc -l src/github_agent_orchestrator/server/dashboard/text_utilities.py
   ```
   - Expected: `dashboard_router.py` reduced by approximately 80-120 lines
   - Expected: `text_utilities.py` created with approximately 80-120 lines

4. **Run full dashboard test suite** as final validation:
   ```bash
   pytest tests/unit/test_dashboard_api*.py -v
   ```

### Phase 5: Format and Finalize

1. **Run formatters**:
   ```bash
   black src/github_agent_orchestrator/server/dashboard_router.py
   black src/github_agent_orchestrator/server/dashboard/text_utilities.py
   isort src/github_agent_orchestrator/server/dashboard_router.py
   isort src/github_agent_orchestrator/server/dashboard/text_utilities.py
   ```

2. **Final verification**:
   - All tests pass
   - No linting errors
   - No circular import issues
   - Function signatures unchanged
   - Behavior unchanged

## Constraints (CRITICAL - Must Follow)

1. **Move-first, patch-second**: Always move code verbatim to new location first, then update imports/call sites as fixes
2. **No logic changes**: Do not change the logic of code unless it has been identified as a clear bug
3. **No backwards compatibility layers**: Do not maintain legacy endpoints
4. **Delete unused code**: Always delete the original function definitions from dashboard_router.py after extraction
5. **No inline comments**: Do not leave comments on changes made within the code
6. **No rewrites**: Do not rewrite functions from scratch during refactors
7. **Leaf utilities only**: Only extract functions that are true leaf utilities with no dependencies on other dashboard_router functions

## Why This Approach

This task deliberately takes a **minimal, low-risk approach** to begin reducing the size of `dashboard_router.py`:

1. **Avoids circular dependencies**: Pure utilities have no dependencies, so they can't create circular imports
2. **Avoids test mocking issues**: These functions aren't mocked in tests, so moving them won't break test patches
3. **Provides immediate value**: Reduces line count and creates reusable utilities for future extractions
4. **Builds foundation**: Creates a pattern for further extractions and a utilities module that other dashboard modules can use
5. **Low risk**: Since these are pure functions with no side effects, the risk of breaking changes is minimal

## Success Criteria

- `dashboard_router.py` reduced by approximately 80-120 lines (from 4746 to ~4630-4660)
- New `text_utilities.py` module created with ~80-120 lines of pure utility functions
- All tests pass with identical behavior
- No circular import issues
- No linting errors (ruff, black, isort, mypy)
- Function signatures and behavior unchanged
- Clear separation established between route orchestration and pure utilities

## Next Steps (Future Work)

After this task is complete, future tasks can:
1. Extract more complex helper modules (GitHub API helpers, queue file helpers, etc.)
2. Use the utilities module from other dashboard modules
3. Continue incremental extraction following the same move-first, patch-second pattern
4. Address the remaining aspects of Review Item A when architectural changes enable safer extraction

