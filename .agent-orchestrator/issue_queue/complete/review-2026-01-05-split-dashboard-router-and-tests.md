Split dashboard_router.py and test_dashboard_api.py into focused modules

## Context
This task addresses items **A** and **B** from review `.agent-orchestrator/reviews/review-2026-01-05-refactor-large-files.md`.

The review identified that `dashboard_router.py` (4746 lines) and `tests/unit/test_dashboard_api.py` (2109 lines) are acting as "god-modules" that mix too many concerns. This makes safe changes harder and increases the chance of accidental coupling.

## Review Items Being Addressed

### A) Continue splitting `dashboard_router.py` by concern
The review recommends creating 5 new leaf-style modules (no FastAPI router objects) to extract supporting logic from `dashboard_router.py`:

1. `server/dashboard/github_issue_pr_helpers.py` - Move timeline/listing helpers and PR evaluation functions
2. `server/dashboard/automation_auto_link.py` - Move auto-link helpers
3. `server/dashboard/automation_auto_resume.py` - Move auto-resume helpers
4. `server/dashboard/loop_actions.py` - Move promote/merge helpers
5. `server/dashboard/loop_status.py` - Move loop-stage computation helpers

Acceptance criteria:
- `dashboard_router.py` keeps route registrations + thin orchestration only
- No behavior changes; tests pass

### B) Split `tests/unit/test_dashboard_api.py`
The review recommends splitting the test file by feature area into 6 new files, keeping tests identical:

1. `tests/unit/test_dashboard_api_health_docs.py`
2. `tests/unit/test_dashboard_api_cognitive_tasks.py`
3. `tests/unit/test_dashboard_api_loop_status.py`
4. `tests/unit/test_dashboard_api_auto_resume.py`
5. `tests/unit/test_dashboard_api_auto_link.py`
6. `tests/unit/test_dashboard_api_loop_actions.py`

Acceptance criteria:
- Same test coverage, just reorganized
- CI still passes

## Detailed Instructions

### Phase 1: Extract production code from dashboard_router.py

For each of the 5 new modules listed in section A:

1. **Identify the functions** in `dashboard_router.py` that belong to each concern area
2. **Move code verbatim** - copy the exact function definitions (including docstrings, type hints, and implementation) into the new module file
3. **Add necessary imports** to the new module file to make the extracted functions work
4. **Update dashboard_router.py** to:
   - Import the moved functions from their new locations
   - Remove the original function definitions
   - Keep all route declarations and orchestration logic intact
5. **Test after each module extraction** to ensure no behavior changes

Key guidelines:
- Create leaf modules (utilities only, no FastAPI dependencies unless absolutely necessary)
- Avoid circular imports by keeping helper modules independent
- Move functions verbatim first; do NOT rewrite or refactor logic
- Keep function signatures stable
- Only adjust imports and call sites to make code run

### Phase 2: Split test_dashboard_api.py

For each of the 6 new test files listed in section B:

1. **Identify test functions** in `test_dashboard_api.py` that belong to each feature area:
   - Health/docs: tests for `/health`, `/`, `/docs` endpoints
   - Cognitive tasks: tests related to cognitive task endpoints
   - Loop status: tests for loop stage computation and status
   - Auto-resume: tests for auto-resume functionality
   - Auto-link: tests for auto-link functionality
   - Loop actions: tests for promote/merge operations

2. **Copy test functions verbatim** into the appropriate new test file
3. **Copy any shared fixtures or setup code** needed by the extracted tests
4. **Verify imports** - ensure all necessary imports are present in new test files
5. **Remove extracted tests** from the original `test_dashboard_api.py`
6. **Run tests after each split** to verify coverage is maintained

Key guidelines:
- Keep test logic identical - this is pure reorganization
- Maintain all fixtures, mocks, and test data
- Do not modify test behavior or assertions
- Ensure each new test file can run independently

### Phase 3: Cleanup and Validation

1. **Delete the original `test_dashboard_api.py`** once all tests are extracted (if empty)
2. **Run full test suite** to ensure all tests pass: `pytest tests/unit/test_dashboard_api*.py`
3. **Verify line counts** - `dashboard_router.py` should be significantly reduced
4. **Check for unused imports** in all modified files
5. **Run linters** (ruff, black, isort, mypy) on all modified files

## Constraints (CRITICAL - Must Follow)

1. **Move-first, patch-second**: Always move code verbatim to new location first, then update imports/call sites as fixes
2. **No logic changes**: Do not change the logic of code unless it has been identified as a clear bug
3. **No backwards compatibility layers**: Do not maintain legacy endpoints
4. **Delete unused code**: Always delete any leftover, unused code after extraction
5. **No inline comments**: Do not leave comments on changes made within the code
6. **No rewrites**: Do not rewrite functions from scratch during refactors

## Risks / Notes

- **Circular imports**: Keep helper modules as "leaf" utilities with no dependencies on dashboard_router
- **Import order**: Use isort to maintain consistent import ordering
- **Test isolation**: Ensure each new test file has all necessary fixtures and can run independently
- **Incremental approach**: Complete each module extraction before moving to the next
- **Git commits**: Commit after each successful module extraction to create a clear audit trail

## Success Criteria

- `dashboard_router.py` reduced from 4746 lines to roughly 1000-1500 lines (route declarations + thin orchestration)
- Original `test_dashboard_api.py` split into 6 focused test files
- All tests pass with identical coverage
- No behavior changes in the API
- All files pass linting (ruff, black, isort, mypy)
- No circular import issues

