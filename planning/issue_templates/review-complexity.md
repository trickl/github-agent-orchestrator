# Review Task Template

## Perform a focused review of the current system

### Context
You are asked to critically review the current system from a specific perspective.

### Review focus
Identify opportunities for reducing system complexity.

Examine all files in the repo, particularly those with a larger file size, and look for
opportunities to refactor large components into smaller, more focused components.

You should view this as a purely refactoring exercise, where no functionality is lost, but
instead we are looking to separate concerns and reduce code duplication.

### Inputs
- The full codebase
- `/planning/vision/goal.md`
- `/planning/state/system_capabilities.md`
- Relevant planning documents

### Task
1. Evaluate the system strictly through the stated review lens.
2. Identify strengths, weaknesses, and risks.
3. Explain why identified issues matter.

### Constraints
- Do not modify code.
- Do not propose fixes in code.
- Do not create tasks or issues.
- Do not mix review lenses.

### Output
- Create a single review document in `/planning/reviews/`.
- The document should be clear, structured, and readable by humans.
- The first line must be a friendly review title.

### Tone
Constructive, critical, and precise. This is analysis, not execution.
