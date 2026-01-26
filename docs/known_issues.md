# Known issues

## Copilot session logs are UI-only

**Status:** Open

Copilot SWE Agent session logs visible in the GitHub UI are not available via public REST/GraphQL APIs.
The only programmatic signals available today are issue/PR events (for example,
`copilot_work_started` and `copilot_work_finished_failure`) and any GitHub Actions logs
that ran on the PR.

**Impact:** The orchestrator cannot fetch the detailed Copilot session log programmatically.

**Workaround:** Use the UI log and/or the Support request ID displayed in the UI when
engaging GitHub Support.

---

## Copilot agent loop can fail with CAPI 400 + callback 404 and missing base branch

**Status:** Open

Some Copilot runs fail with:

- `Request to agent callback .../agents/swe/agent/jobs failed with status 404`
- `CAPIError: 400 400 Bad Request`
- `fatal: ambiguous argument 'main': unknown revision or path not in the working tree`

These errors occur inside the Copilot action runner and can halt the agent loop.
The `git diff` error indicates the base branch is not present in the local checkout
(e.g., shallow checkout or missing `origin/main`).

**Impact:** Copilot stops mid-run and leaves the PR partially updated.

**Workarounds:**

1. **Retry by reassigning Copilot** (or posting a “try again” comment) after the run fails.
2. **Ensure the base branch exists in the checkout** by fetching it before diffing.
   For example, configure the repo workflow/checkout to fetch the base branch or
   use a full fetch depth.
3. **Make sure the base branch passed to Copilot matches the repo default**
   (avoid hardcoding `main` if the repo uses a different default branch).
