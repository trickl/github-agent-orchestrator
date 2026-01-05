Address architectural blockers for dashboard_router.py module extraction

## Context

This task addresses the remaining work from **Review Item A (Phase 2)** in `review-2026-01-05-refactor-large-files.md`. 

The review identified that `dashboard_router.py` (currently 4661 lines) is acting as a "god-module" mixing HTTP route declarations with extensive supporting logic. Phase 1 successfully extracted pure utility functions into `text_utilities.py` (85 line reduction). However, Phase 2—extracting complex helper modules—was deferred due to architectural blockers.

## Review Items Addressed

From `review-2026-01-05-refactor-large-files.md`, this task addresses:

### Review Item A: Continue splitting `dashboard_router.py` by concern (Phase 2 - Complex Helpers)

**Specific extractions originally recommended** (all currently deferred):

1. `server/dashboard/github_issue_pr_helpers.py` - Timeline/listing helpers and PR evaluation functions
2. `server/dashboard/automation_auto_link.py` - Auto-link helpers  
3. `server/dashboard/automation_auto_resume.py` - Auto-resume helpers
4. `server/dashboard/loop_actions.py` - Promote/merge helpers
5. `server/dashboard/loop_status.py` - Loop-stage computation helpers

**Why these were deferred** (from actions file):

The extractions are blocked by three interconnected architectural issues:

1. **Circular imports**: Extracted modules need dashboard_router helpers, and dashboard_router would import from the extracted modules
2. **Test mocking breaks**: Tests patch `dashboard_router._get_pull_request` and other helpers, but if functions move to a separate module, tests can't patch the local copy used by that module
3. **Helper function duplication**: Would require duplicating helper functions to avoid circular dependencies

## Detailed Task Instructions

### Goal

Refactor `dashboard_router.py` to enable safe extraction of the 5 complex helper modules identified in the review, without introducing circular dependencies or breaking existing test mocking patterns.

### Approach: Dependency Injection Pattern

The root cause of the architectural blockers is tight coupling through direct function calls and test patching of module-level functions. The solution is to introduce a dependency injection pattern that:

1. Makes dependencies explicit through parameters or class-based dependency injection
2. Allows tests to inject mocks without relying on module-level patching
3. Eliminates circular dependencies by inverting control flow

### Phase 1: Identify and Document Dependency Graph

**Step 1.1**: Analyze `dashboard_router.py` to identify:
- Which functions are currently called by which route handlers
- Which shared helper functions create coupling (e.g., `_get_pull_request`, timeline helpers, GitHub API calls)
- Which functions would need to be in extracted modules vs. stay in dashboard_router
- Map out the dependency relationships that would create circular imports

**Step 1.2**: Document the dependency graph in a temporary analysis file (in `/tmp/dashboard_router_dependencies.md`) showing:
- Current direct dependencies between functions
- Proposed module boundaries (5 modules from review)
- Identified circular dependency chains
- Shared utilities that multiple modules need

### Phase 2: Design Dependency Injection Strategy

**Step 2.1**: Choose a dependency injection approach. Recommended options:

**Option A - Function Parameter Injection** (simpler, lighter weight):
- Extract helper functions into modules as planned
- Route handlers receive dependencies as parameters (either individual functions or a simple container object)
- Tests can provide mock functions directly as parameters
- No class restructuring needed

**Option B - Class-Based Dependency Injection** (more structured):
- Create a `DashboardServices` or `DashboardHelpers` class that encapsulates shared GitHub operations
- Extract helper modules as before
- Route handlers receive the services class instance
- Tests can provide a mock services instance
- More boilerplate but clearer structure

**Recommended**: Start with **Option A** (function parameter injection) as it's the minimal change that solves the problem while preserving the current functional style.

**Step 2.2**: Design the injection points:
- Identify which route handlers need which dependencies
- Determine if dependencies should be passed individually or as a grouped structure
- Plan how to initialize and wire dependencies at FastAPI router creation time

### Phase 3: Implement Dependency Injection Foundation

**Step 3.1**: Create a shared GitHub operations interface/helper structure:
- Create `server/dashboard/github_operations.py` as a central place for GitHub API operations that multiple modules need
- Move GitHub API wrapper functions (like `_get_pull_request`, `_list_pull_requests`, etc.) into this module
- These become the "services" that will be injected

**Step 3.2**: Update route handlers to accept dependencies:
- Modify route handler signatures to accept dependencies (either as individual parameters or as a dependency container)
- Use FastAPI's `Depends()` mechanism to inject dependencies
- Keep the changes minimal: just add the dependency parameters and use them instead of direct module-level function calls

**Step 3.3**: Update tests to inject mocks:
- Instead of patching `dashboard_router._get_pull_request`, tests now create a mock GitHub operations object and inject it
- Update existing test fixtures to provide mock dependencies
- Verify all tests still pass with the new injection pattern

### Phase 4: Extract Helper Modules

**Step 4.1**: Now that circular dependencies are eliminated, extract modules one at a time:

**Extract in this order** (least coupled to most coupled):

1. **`server/dashboard/loop_status.py`** first
   - Move loop-stage computation helpers verbatim
   - These functions are relatively self-contained
   - Update imports in dashboard_router.py
   - Run tests after each extraction

2. **`server/dashboard/github_issue_pr_helpers.py`** second
   - Move timeline/listing helpers and PR evaluation functions verbatim
   - Update imports in dashboard_router.py
   - Run tests

3. **`server/dashboard/loop_actions.py`** third
   - Move promote/merge helpers verbatim
   - Update imports in dashboard_router.py
   - Run tests

4. **`server/dashboard/automation_auto_resume.py`** fourth
   - Move auto-resume helpers verbatim
   - Update imports in dashboard_router.py
   - Run tests

5. **`server/dashboard/automation_auto_link.py`** fifth
   - Move auto-link helpers verbatim
   - Update imports in dashboard_router.py
   - Run tests

**Step 4.2**: After each extraction:
- Verify `dashboard_router.py` still contains only route registrations and thin orchestration
- Run the full test suite
- Verify no circular imports exist
- Check line count reduction progress

### Refactor Safety Rules (Mandatory)

Following the review's "move-first, patch-second" constraint:

1. **Move code verbatim first**: Copy functions exactly as-is into new modules, no logic changes
2. **Update imports/call sites**: Make it run, adjust visibility, scope, parameterization
3. **Only then do targeted improvements**: Fix any obvious issues in the migrated code

### Constraints (from task template)

1. Do not change the logic of code unless it has been identified as a clear bug
2. Do not maintain legacy endpoints for backwards compatibility  
3. Always delete any leftover, unused code
4. Do not leave comments on changes made within the code
5. Do not rewrite functions from scratch during refactors

### Acceptance Criteria

- [ ] Dependency injection pattern implemented that eliminates circular dependency risk
- [ ] Tests updated to inject mocks instead of module-level patching where necessary
- [ ] All 5 helper modules extracted from review successfully created:
  - [ ] `server/dashboard/github_issue_pr_helpers.py`
  - [ ] `server/dashboard/automation_auto_link.py`
  - [ ] `server/dashboard/automation_auto_resume.py`
  - [ ] `server/dashboard/loop_actions.py`
  - [ ] `server/dashboard/loop_status.py`
- [ ] `dashboard_router.py` keeps route registrations + thin orchestration only
- [ ] No behavior changes; all tests pass
- [ ] No circular imports exist
- [ ] Line count of `dashboard_router.py` significantly reduced (target: under 2000 lines)
- [ ] Extracted modules are leaf-style utilities with minimal coupling

### Expected Outcome

- `dashboard_router.py`: Reduced from 4661 lines to under 2000 lines (targeting 55%+ reduction)
- 5 new focused helper modules created
- Architecture supports future extractions without circular dependency issues
- Tests remain comprehensive and pass completely
- Code maintainability significantly improved

### Notes

- This is a significant architectural refactoring, not just a file split
- The dependency injection pattern is the key innovation that unblocks the extractions
- Take incremental steps and verify tests pass after each module extraction
- If dependency injection proves too complex, an alternative is to consolidate shared operations into a single shared module that all extracted modules can import (but this is less clean)
- Avoid the temptation to rewrite functions during extraction; keep moves verbatim per the review guidance
