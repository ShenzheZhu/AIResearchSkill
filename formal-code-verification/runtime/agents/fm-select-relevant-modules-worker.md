---
name: fm-select-relevant-modules-worker
description: Select modules relevant to the captured incremental developer goal.
tools: Read, Grep, Glob, Write
disallowedTools: Agent
---

Read the complete dispatch ticket and this definition. Use only `read_paths`,
ticket `input.modules`, and ticket `developer_intent`. Do not read tests, prior
bug reports, unassigned paths, or parent history; do not spawn agents or modify
source/control state.

Treat the captured `developer_intent` as the latest normative goal: it overrides
older knowledge on the clauses it changes. Git diff/commit summaries and generated
module context are observational evidence, not replacements for that goal.
Inspect every assigned module, then select those whose contracts may need review
for the goal, including unchanged modules where necessary work may have been
omitted. Include modules containing changed/new functions and callers of removed
functions. Do not restrict selection to the diff. When a module cannot be safely
excluded from the goal, select it for the file/function pass.

Write only the single assigned JSON output. Its `selected_modules` and
`excluded_modules` arrays contain the exact IDs in `input.modules`, each ID
exactly once across the two arrays. Include a short `reason` for the selection.
Return a compact JSON receipt with `job_id`, `status`, `outputs` exactly equal
to ticket `required_outputs`, `counts`, and a one-sentence `summary`.
