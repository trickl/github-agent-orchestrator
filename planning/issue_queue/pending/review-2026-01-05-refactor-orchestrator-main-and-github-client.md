Extract CLI subcommand handlers and GitHub client helpers into focused modules

## Context
This task addresses **Review Item C** from review `planning/reviews/review-2026-01-05-refactor-large-files.md`.

The review identified that:
- `orchestrator/main.py` (1135 lines) contains extensive CLI wiring and a long command dispatch chain
- `orchestrator/github/client.py` (1192 lines) is a multi-concern facade mixing URLs, pagination, parsing, and higher-level operations

Both files are large and likely to grow, making them harder to maintain and test.

## Review Item Being Addressed

**Review Item C**: Tackle `orchestrator/main.py` and `orchestrator/github/client.py`

The review recommends:
1. Extract CLI subcommand handler functions into `orchestrator/commands/*`
2. For the GitHub client, move helpers into modules (urls/pagination/parsing) while keeping `GitHubClient` as the facade

Acceptance criteria:
- Public CLI behavior unchanged
- Public `GitHubClient` behavior unchanged

## Current Structure Analysis

### orchestrator/main.py (1135 lines)
The file contains:
- `_parse_labels()` - utility function
- `build_parser()` - builds the argparse parser with 10+ subcommands
- `main()` - dispatches to subcommand handlers

The `main()` function contains inline handlers for these subcommands:
1. `create-issue` - Create a GitHub issue
2. `assign-copilot` - Assign an existing issue to Copilot
3. `monitor-prs` - Poll for pull requests linked to an issue
4. `merge-linked-prs` - Wait for linked PRs and merge them
5. `gap-analysis-cycle` - Create a gap analysis issue and merge its PR
6. `promote-issue-queue` - Promote a queue file to a GitHub issue
7. `system-capabilities-after-merge` - Create system capabilities update issue
8. `complete-issue-queue-item` - Move queue item to complete
9. `auto-resume-copilot` - Auto-resume Copilot after rate limit
10. `auto-link-issue-pr` - Auto-link issue to PR

### orchestrator/github/client.py (1192 lines)
The file contains:
- 7 dataclass definitions (CreatedIssue, IssueDetails, LinkedPullRequest, etc.)
- `GitHubClient` class with ~50+ methods covering:
  - Issue operations (create, get, update, assign, comment)
  - PR operations (create, get, merge, convert draft, delete branch)
  - Repository operations (get file, create branch, etc.)
  - Timeline/discussion operations
  - Low-level REST API operations

## Detailed Instructions

### Phase 1: Extract CLI subcommand handlers from orchestrator/main.py

Create a new directory `src/github_agent_orchestrator/orchestrator/commands/` with one module per subcommand handler.

For each of the 10 subcommands, extract its handler logic into a dedicated module (paths below are relative to `src/github_agent_orchestrator/` for brevity):

1. **Create `orchestrator/commands/create_issue.py`**
   - Move the `create-issue` command handler logic verbatim
   - Handler should accept parsed args and settings
   - Return appropriate exit code

2. **Create `orchestrator/commands/assign_copilot.py`**
   - Move the `assign-copilot` command handler logic verbatim
   - Handler should accept parsed args and settings
   - Return appropriate exit code

3. **Create `orchestrator/commands/monitor_prs.py`**
   - Move the `monitor-prs` command handler logic verbatim
   - Handler should accept parsed args and settings
   - Return appropriate exit code

4. **Create `orchestrator/commands/merge_linked_prs.py`**
   - Move the `merge-linked-prs` command handler logic verbatim
   - Handler should accept parsed args and settings
   - Return appropriate exit code

5. **Create `orchestrator/commands/gap_analysis_cycle.py`**
   - Move the `gap-analysis-cycle` command handler logic verbatim
   - Handler should accept parsed args and settings
   - Return appropriate exit code

6. **Create `orchestrator/commands/promote_issue_queue.py`**
   - Move the `promote-issue-queue` command handler logic verbatim
   - Handler should accept parsed args and settings
   - Return appropriate exit code

7. **Create `orchestrator/commands/system_capabilities_after_merge.py`**
   - Move the `system-capabilities-after-merge` command handler logic verbatim
   - Handler should accept parsed args and settings
   - Return appropriate exit code

8. **Create `orchestrator/commands/complete_issue_queue_item.py`**
   - Move the `complete-issue-queue-item` command handler logic verbatim
   - Handler should accept parsed args and settings
   - Return appropriate exit code

9. **Create `orchestrator/commands/auto_resume_copilot.py`**
   - Move the `auto-resume-copilot` command handler logic verbatim
   - Handler should accept parsed args and settings
   - Return appropriate exit code

10. **Create `orchestrator/commands/auto_link_issue_pr.py`**
    - Move the `auto-link-issue-pr` command handler logic verbatim
    - Handler should accept parsed args and settings
    - Return appropriate exit code

11. **Create `orchestrator/commands/__init__.py`**
    - Import all command handlers
    - Optionally provide a command registry dict mapping command names to handler functions

After extraction:
- Update `main()` in `orchestrator/main.py` to dispatch to the extracted handlers
- `build_parser()` stays in `main.py` (it defines the CLI interface)
- The `main()` function becomes a thin dispatcher that:
  1. Parses arguments
  2. Loads settings
  3. Configures logging
  4. Dispatches to the appropriate command handler
  5. Handles common exceptions

Expected result:
- `orchestrator/main.py` reduced from 1135 lines to ~200-300 lines
- 10 new focused command handler modules (~50-100 lines each)
- No behavior changes; CLI works identically

### Phase 2: Extract GitHub client helpers into focused modules

Create new modules within `src/github_agent_orchestrator/orchestrator/github/` to organize helper functionality:

1. **Create `orchestrator/github/models.py`**
   - Move all dataclass definitions verbatim:
     - CreatedIssue
     - IssueDetails
     - LinkedPullRequest
     - PullRequestDetails
     - PullRequestContent
     - PullRequestDiscussionItem
     - MergeResult
     - PullRequestCreated
   - These are pure data models with no logic

2. **Keep `orchestrator/github/client.py` as the main facade**
   - Import dataclasses from `models.py`
   - Keep the `GitHubClient` class as the public interface
   - All methods remain in `GitHubClient` (no method extraction in this phase)
   - Update imports to use models from `models.py`

After extraction:
- Update all imports of these dataclasses throughout the codebase to use `orchestrator/github/models.py`
- `client.py` imports from `models.py` and re-exports them for backwards compatibility if needed
- No functional changes; all tests pass

Expected result:
- `orchestrator/github/client.py` reduced from 1192 lines to ~1100 lines (mostly removing dataclass definitions)
- New `orchestrator/github/models.py` with ~90 lines of dataclass definitions
- No behavior changes; all GitHub operations work identically

### Phase 3: Validation and Cleanup

1. **Run tests** to ensure no behavior changes:
   ```bash
   pytest tests/unit/test_orchestrator*.py -v
   pytest tests/integration/ -v  # if integration tests exist
   ```

2. **Verify CLI behavior** by running help for each subcommand:
   ```bash
   orchestrator --help
   orchestrator create-issue --help
   orchestrator assign-copilot --help
   # ... etc for all subcommands
   ```
   
   Or if not installed, use:
   ```bash
   python -m github_agent_orchestrator.orchestrator.main --help
   ```

3. **Check imports** throughout the codebase:
   - Ensure all imports of dataclasses are updated
   - Ensure no circular import issues
   - Run `mypy` to verify type checking still works

4. **Run linters**:
   ```bash
   ruff check .
   black --check .
   isort --check .
   mypy src/github_agent_orchestrator/orchestrator/
   ```

5. **Check line counts** to verify reduction:
   ```bash
   wc -l src/github_agent_orchestrator/orchestrator/main.py
   wc -l src/github_agent_orchestrator/orchestrator/github/client.py
   ```

## Implementation Approach: Move-First, Patch-Second

**Critical**: Follow the move-first, patch-second pattern for each extraction:

1. **Move code verbatim** into the new module file
   - Copy the exact function/class definition
   - Include all docstrings, type hints, and implementation
   - Do NOT refactor or change logic

2. **Add necessary imports** to the new module
   - Import only what's needed for the extracted code to run
   - Keep imports minimal and focused

3. **Update the source file** to use the extracted code
   - Import the moved functions/classes
   - Replace the original definition with the import
   - Update call sites if needed

4. **Test after each extraction** to ensure it works
   - Run relevant unit tests
   - Verify CLI behavior for affected commands
   - Check for import errors

5. **Only then make targeted improvements** (if needed)
   - Fix any issues that arose from the move
   - Adjust visibility, scope, parameterization as needed
   - Do NOT rewrite or refactor beyond what's necessary

## Constraints (CRITICAL - Must Follow)

1. **Move-first, patch-second**: Always move code verbatim to new location first, then update imports/call sites as fixes
2. **No logic changes**: Do not change the logic of code unless it has been identified as a clear bug
3. **No backwards compatibility layers**: Do not maintain legacy endpoints
4. **Delete unused code**: Always delete any leftover, unused code after extraction
5. **No inline comments**: Do not leave comments on changes made within the code
6. **No rewrites**: Do not rewrite functions from scratch during refactors
7. **Preserve behavior**: CLI and GitHub client behavior must be identical after refactoring

## Risks / Notes

- **Import cycles**: Keep command modules independent; they should only import from orchestrator core modules, not from each other
- **Command handler signature**: Design a consistent signature for all command handlers (e.g., `def handle_command(args: argparse.Namespace, settings: OrchestratorSettings) -> int`)
- **Dataclass re-exports**: Consider re-exporting dataclasses from `client.py` for backwards compatibility, but update all internal imports to use `models.py`
- **Test isolation**: Each command handler should be testable independently
- **Incremental approach**: Extract one command handler at a time, test, then move to the next
- **Git commits**: Use `report_progress` after each successful extraction to create a clear audit trail

## Success Criteria

- `orchestrator/main.py` reduced from 1135 lines to ~200-300 lines (parser + thin dispatcher)
- 10 new command handler modules created in `orchestrator/commands/` (~50-100 lines each)
- `orchestrator/github/client.py` reduced from 1192 lines to ~1100 lines
- New `orchestrator/github/models.py` created with dataclass definitions (~90 lines)
- All CLI subcommands work identically (no behavior changes)
- All GitHub client operations work identically (no behavior changes)
- All tests pass
- All files pass linting (ruff, black, isort, mypy)
- No circular import issues
- Clear separation of concerns: CLI wiring vs. command logic vs. GitHub operations
