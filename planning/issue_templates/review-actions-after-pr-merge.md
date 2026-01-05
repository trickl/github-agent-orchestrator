Update review actions based on merged PR #{{PR_NUMBER}}

This issue is automatically created after a pull request has been merged.

The goal is to update the review actions/completions artefact for the relevant review so it accurately reflects what was addressed by the merged change.

Target files:
- Source review: {{REVIEW_PATH}}
- Actions/completions: {{REVIEW_ACTIONS_PATH}}

Instructions:
- Review the merged pull request and its discussion.
- Identify which review items (from the source review) were addressed by this PR.
- Update the actions/completions file:
  - Record what changed, where, and which review items are now resolved.
  - If an item was partially addressed, record the remaining follow-up explicitly.
- Do not speculate or describe unrelated future work.
- If no update is required, explicitly state why and leave the file unchanged.

Merged PR summary:
- PR number: {{PR_NUMBER}}
- PR title: {{PR_TITLE}}
- Queue artefact: {{QUEUE_PATH}}

PR description:

{{PR_DESCRIPTION}}

PR comments and discussion (chronological):

{{PR_COMMENTS}}

---

<!-- {{MARKER}} -->
