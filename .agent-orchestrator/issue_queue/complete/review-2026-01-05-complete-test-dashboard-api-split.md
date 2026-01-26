Complete test_dashboard_api.py split into focused test files

## Context
This task completes review item **B** from `review-2026-01-05-refactor-large-files.md`.

The review identified that `tests/unit/test_dashboard_api.py` (2109 lines) is doing too much - it covers multiple independent concerns in a single file, making it difficult to navigate when refactoring production code.

PR #12 (merged 2026-01-05) started this work by creating 2 of 6 planned test files. This task completes the remaining 4 test file splits, plus final cleanup.

## Review Item Being Addressed

### B) Split `tests/unit/test_dashboard_api.py` (PARTIALLY COMPLETED)

From the actions file, the following work remains:

1. Complete `test_dashboard_api_loop_actions.py` - add 7 more merge/capability tests
2. Create `test_dashboard_api_loop_status.py` - 16 tests for loop-stage computation
3. Create `test_dashboard_api_auto_resume.py` - 2 tests for auto-resume functionality
4. Create `test_dashboard_api_auto_link.py` - 3 tests for auto-link functionality  
5. Create `test_dashboard_api_cognitive_tasks.py` - move the cognitive tasks test currently in health_docs file, plus any others
6. Remove all extracted tests from original `test_dashboard_api.py`
7. Delete original file once all tests are extracted

## Detailed Instructions

### Phase 1: Complete test_dashboard_api_loop_actions.py

The file exists with 3 tests (156 lines). Add the remaining 7 tests related to merge operations and capability tracking:

1. **Identify** the 7 remaining merge/capability tests in `test_dashboard_api.py`
2. **Copy test functions verbatim** - include the entire test function with all fixtures, mocks, and assertions
3. **Copy any shared fixtures** or helper functions needed by these tests
4. **Verify imports** - ensure all necessary imports are present (pytest, mocks, types, etc.)
5. **Run the tests** to verify they work independently: `pytest tests/unit/test_dashboard_api_loop_actions.py -v`

### Phase 2: Create test_dashboard_api_loop_status.py

This file should contain 16 tests for loop-stage computation and status:

1. **Identify** all tests in `test_dashboard_api.py` related to loop status, loop stage computation, and status endpoints
2. **Create the new file** `tests/unit/test_dashboard_api_loop_status.py`
3. **Copy the test functions verbatim** - include all fixtures, parametrize decorators, and test data
4. **Copy any shared setup code** - fixtures, mock factories, or helper functions used by these tests
5. **Add necessary imports** - copy import blocks from original file and prune to what's needed
6. **Run the tests** to verify: `pytest tests/unit/test_dashboard_api_loop_status.py -v`

### Phase 3: Create test_dashboard_api_auto_resume.py

This file should contain 2 tests for auto-resume functionality:

1. **Identify** the 2 auto-resume tests in `test_dashboard_api.py`
2. **Create the new file** `tests/unit/test_dashboard_api_auto_resume.py`
3. **Copy the test functions verbatim** with all mocking and assertions
4. **Copy shared fixtures** needed for auto-resume tests
5. **Add necessary imports**
6. **Run the tests** to verify: `pytest tests/unit/test_dashboard_api_auto_resume.py -v`

### Phase 4: Create test_dashboard_api_auto_link.py

This file should contain 3 tests for auto-link functionality:

1. **Identify** the 3 auto-link tests in `test_dashboard_api.py`
2. **Create the new file** `tests/unit/test_dashboard_api_auto_link.py`
3. **Copy the test functions verbatim** with all mocking and assertions
4. **Copy shared fixtures** needed for auto-link tests
5. **Add necessary imports**
6. **Run the tests** to verify: `pytest tests/unit/test_dashboard_api_auto_link.py -v`

### Phase 5: Create test_dashboard_api_cognitive_tasks.py

This file should contain tests for cognitive tasks endpoints:

1. **Identify** the cognitive tasks test currently in `test_dashboard_api_health_docs.py` (line noted in actions file)
2. **Identify** any other cognitive tasks tests in the original `test_dashboard_api.py`
3. **Create the new file** `tests/unit/test_dashboard_api_cognitive_tasks.py`
4. **Copy the test functions verbatim** from both source files
5. **Copy shared fixtures** as needed
6. **Add necessary imports**
7. **Remove** the cognitive tasks test from `test_dashboard_api_health_docs.py` (keep only health and docs tests there)
8. **Run the tests** to verify: `pytest tests/unit/test_dashboard_api_cognitive_tasks.py -v`

### Phase 6: Remove extracted tests from original test_dashboard_api.py

1. **Verify** that all test functions have been copied to new files by running all new test files
2. **Delete test functions** from `test_dashboard_api.py` that have been copied to new files
3. **Keep any remaining shared fixtures** that are still needed (if any tests remain)
4. **Run the original file** to verify any remaining tests still pass: `pytest tests/unit/test_dashboard_api.py -v`
5. **If the file is empty** or only contains unused fixtures, delete it entirely

### Phase 7: Final Validation

1. **Run all dashboard API tests together**: `pytest tests/unit/test_dashboard_api*.py -v`
2. **Verify test count** - total number of tests should match the original count (24+ tests based on actions file)
3. **Check coverage** - ensure no tests were accidentally omitted
4. **Run linters** on all modified test files:
   - `ruff check tests/unit/test_dashboard_api*.py`
   - `black tests/unit/test_dashboard_api*.py`
   - `isort tests/unit/test_dashboard_api*.py`
   - `mypy tests/unit/test_dashboard_api*.py`
5. **Verify no circular imports** or missing dependencies

## Constraints (CRITICAL - Must Follow)

1. **Verbatim copy only**: Copy test functions exactly as they are - do NOT rewrite or refactor test logic
2. **No behavior changes**: Test assertions, mocks, and fixtures must remain identical
3. **No inline comments**: Do not add comments explaining changes within the code
4. **Delete unused code**: Remove the original `test_dashboard_api.py` if it becomes empty
5. **Independent test files**: Each new test file must be able to run standalone with `pytest <file>`
6. **Move-first pattern**: Copy tests to new files first, verify they work, then remove from original

## Pattern to Follow (from PR #12)

The actions file notes that PR #12 established a successful pattern:
- "Verbatim test extraction with independent fixtures, preserving all mocking and assertions"

Follow this exact approach:
1. Copy entire test function including decorators
2. Copy fixture functions used by the test
3. Copy mock setup and tear down
4. Copy test data and parametrize arguments
5. Ensure all imports are present
6. Verify tests pass independently before removing from original file

## Success Criteria

- `test_dashboard_api_loop_actions.py` contains all 10 loop action tests (3 existing + 7 new)
- `test_dashboard_api_loop_status.py` created with 16 loop status tests
- `test_dashboard_api_auto_resume.py` created with 2 auto-resume tests
- `test_dashboard_api_auto_link.py` created with 3 auto-link tests
- `test_dashboard_api_cognitive_tasks.py` created with cognitive tasks tests
- Original `test_dashboard_api.py` deleted (or contains only unrelated tests if any exist)
- All tests pass with identical coverage: `pytest tests/unit/test_dashboard_api*.py -v`
- All test files pass linting (ruff, black, isort, mypy)
- Each test file can run independently
- Total line count across all test files equals or is close to original 2109 lines (accounting for some duplication of fixtures)

## Notes / Risks

- **Fixture duplication**: Some fixtures may need to be duplicated across test files. This is acceptable for test independence. Consider extracting truly shared fixtures to a `conftest.py` if duplication becomes excessive.
- **Mock patching**: Ensure mock patch paths are correct - they should point to where the function is used, not where it's defined
- **Test isolation**: Each test file should be independently runnable without requiring other test files
- **Incremental commits**: Commit after each new test file is created and verified to work
- **Original file preservation**: Keep the original `test_dashboard_api.py` until all tests are extracted and verified

## Reference

- Source review: `.agent-orchestrator/reviews/review-2026-01-05-refactor-large-files.md`
- Actions tracking: `.agent-orchestrator/reviews/review-2026-01-05-refactor-large-files.actions.md`
- Prior PR: #12 (merged 2026-01-05) - established the pattern for test file splits

