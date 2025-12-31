# Review Consumption Task Template

## Derive actionable tasks from a review document

### Context
You are asked to read an existing review and extract concrete, actionable follow-up tasks.

### Input
- A specific review file in `/planning/reviews/`

### Task
1. Read the review carefully.
2. Identify distinct, actionable concerns or recommendations.
3. For each concern, define a single, focused task that could address it.

### Constraints
- Do not modify code.
- Do not fix issues.
- Do not create GitHub issues directly.
- Do not prioritise or schedule tasks.

### Output
- Create one or more new files in `/planning/issue_queue/pending/`.
- Each file should represent exactly one actionable task.
- Each file’s first line must be a friendly task name.
- Tasks should be concrete and implementable.

### Tone
Faithful to the review, pragmatic, and neutral. No new ideas beyond the review.
