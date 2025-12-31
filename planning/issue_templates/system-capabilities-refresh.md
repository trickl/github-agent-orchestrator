# System Capabilities Refresh Issue Template

## Define or refresh the current system capabilities document

### Context
This repository maintains an explicit description of what the system currently does.
This description is used as an input for planning, reviews, and gap analysis.

The file `/planning/state/system_capabilities.md` is either missing, outdated, or no longer
accurately reflects the system.

### Inputs
- The full repository (code, tests, configuration, workflows)
- Existing planning documents, if present
- CI configuration and test coverage

### Task
1. Examine the repository as it exists today.
2. Identify the concrete capabilities the system demonstrably has.
3. Describe those capabilities clearly and accurately, without speculation.
4. Describe notable constraints, assumptions, and limitations.
5. Avoid describing future plans, intentions, or hypothetical behaviour.

### Constraints
- Do not modify code.
- Do not invent capabilities.
- Do not restate the project vision or goals.
- Do not describe how the system *should* work — only how it *does* work.

### Output
- Create or update `/planning/state/system_capabilities.md`.
- The document should reflect the system as it exists at the time of writing.
- The first line must be a friendly, human-readable title.

### Tone
Factual, neutral, and precise. This is a snapshot of reality, not a roadmap.
