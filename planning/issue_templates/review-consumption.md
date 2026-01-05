# Review Intake / Consumption Task Template

## Convert critique into the next achievable work item

### Purpose
Translate a review document into **one** concrete task that can be delivered in **one PR**.

### Inputs
- Source review: `{{REVIEW_PATH}}`
- Review actions/completions (may be missing/empty): `{{REVIEW_ACTIONS_PATH}}`

---

### Completion Check (Mandatory)
Before producing any queue artefact, answer this question:

> **Is there at least one concrete, unaddressed critique item in the source review that is not already recorded as completed (or explicitly in-progress) in the actions/completions file?**

- If **NO**:
	- **Do not create any file**
	- **Do not output anything**
	- Terminate the task immediately

- If **YES**:
	- Proceed to select the next PR-sized batch of related items

### Task
1. Read the review carefully and extract distinct critique items.
2. Compare against the actions/completions document to avoid duplicating already-addressed items.
3. Choose the **next best batch of related items** that can be delivered in **one PR**.
	 - Prefer batching multiple items when they share contextual similarity or can easily
       be done at the same time without conflict. 
	 - Avoid a grab-bag of unrelated changes.
4. Produce one queue artefact describing the task.

### Constraints
- Do not modify code.
- Do not fix issues.
- Do not create GitHub issues directly.
- Do not produce multiple tasks.

### Output
- Create **exactly one** new file in `/planning/issue_queue/pending/`.
- Filename must start with `review-`.
- The file’s first line must be a friendly task name.
- Clearly list which review items this task intends to address and give detailed,
    verbose instructions on addressing them.

### Refactor safety rule (mandatory)
If the resulting task involves refactoring or moving code across files:
1. Move code verbatim first into it's new location.
2. Update imports/call sites to make it run, address visibility, scope and parameterization as a fix on the migrated code.
3. Only then do targeted improvements.

### Constraints
1. Do not change the logic of code unless it has been identified as a clear bug
2. Do not maintain legacy endpoints for backwards compatibility
3. Always delete any leftover, unused code
4. Do not leave comments on changes made within the code
5. Do not rewrite functions from scratch during refactors.

### Tone
Faithful to the review, pragmatic, and neutral. No new ideas beyond the review.
