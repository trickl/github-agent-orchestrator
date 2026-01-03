# Gap Analysis Issue Template

## Plan Alignment Analysis (Target State → Next Development Step)

### Purpose
Determine whether the current system **fully satisfies the intended target state**.  
If it does not, identify **one and only one** concrete development task that would move the system closer to that target.

---

### Title
**Evaluate plan alignment and determine the next required development step**

---

### Context
You are performing a structured comparison between the system’s intended target state and its current documented capabilities.

This task is part of a recurring planning loop.  
It is valid—and expected—for this task to conclude that **no further work is required**.

---

### Inputs
- `/planning/vision/goal.md`
- `/planning/state/system_capabilities.md`
- Any other relevant planning or architectural documents

---

### What to Compare (Critical)
Compare the **explicit requirements, assumptions, and operating expectations** expressed in the target state against the **documented, implemented, or operational capabilities** of the current system.

In particular, assess whether:

- Every required capability described in the goal exists in the system capabilities
- The system can operate end-to-end as described in the goal
- Any required functionality is missing or incomplete
- Any stated behaviour in the goal is contradicted or unsupported by current capabilities

Ignore speculative, optional, or “nice-to-have” ideas unless they are explicitly required by the goal.
Where the goal specifies an incremental development approach, choose the next development item
according to the current system capabilities.

---

### Completion Check (Mandatory)
Before proposing any task, answer the following question:

> **Does the current system, as described in `system_capabilities.md`, fully and adequately satisfy the target state defined in `goal.md`?**

- If **YES**:
  - **Do not create any file**
  - **Do not output anything**
  - Terminate the task immediately

- If **NO**:
  - Proceed to define the single most important missing or insufficient element

---

### Task (Only if the system is not complete)
1. Identify the most important *specific deficiency* preventing full alignment with the target state.
2. Formulate **one** concrete development task that would materially improve alignment.
3. Ensure the task is:
   - Necessary (not optional)
   - Clearly scoped

---

### Constraints
- Do not modify any code
- Do not create GitHub issues
- Do not propose multiple tasks
- Do not solve the task
- Do not restate or re-document existing capabilities

---

### Output (Only if a task is required)
- Create **one** new file in `/planning/issue_queue/pending/`
- The file must clearly and verbosely describe the proposed development task in as much detail as possible
- The **first line** of the file must be a short, friendly task name

---

### Tone
Analytical, precise, pragmatic, and aligned with the system’s stated mission.
The target audience for the file content is a senior, experienced software engineer. 