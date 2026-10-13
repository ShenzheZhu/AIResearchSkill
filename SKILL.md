---
name: ai-research-skill-router
description: Route AI research and engineering tasks to the right workflow skill. Use for OpenReview submissions, reviewer rebuttals, validation studies, LaTeX page reduction, GitHub publishing, API-first web automation, specification-driven code verification, and general software-development discipline.
---

# AI Research Skill Router

Use this as the umbrella skill for AI research operations. It routes to the focused skill folders in this repository. Do not load every child skill at once; choose the smallest primary skill, then load supporting skills only when the task needs them.

## Routing Workflow

1. Classify the task.
   Identify whether the user needs submission automation, rebuttal writing, validation experiments, Prolific studies, LaTeX page reduction, GitHub publishing, web automation, formal code verification, or software-development workflow.

2. Pick one primary skill.
   Read the selected child skill folder `SKILL.md` first. Follow its workflow as the main procedure.

3. Add supporting skills only when necessary.
   Example: a rebuttal task may use `evidence-first-rebuttal` as the primary skill and `prolific-human-validation` only if the response needs a human study.

4. Keep evidence and credentials separate.
   Use local artifacts and scripts for claims. Never write API keys, passwords, tokens, or SSH secrets into repo files.

5. Validate before final output.
   Run the checks recommended by the selected child skill. For prose, use `agent-style` when the rebuttal or technical writing skill calls for it.

## Skill Router

| Task | Primary Skill | When To Use |
| --- | --- | --- |
| OpenReview submission edits | `openreview-submit/SKILL.md` | Inspect submissions, list existing notes, resolve author profile IDs, fill author lists, or batch-submit/edit papers. |
| Reviewer rebuttal writing | `evidence-first-rebuttal/SKILL.md` | Draft, audit, run supporting experiments for, and polish OpenReview-style reviewer responses. |
| Rebuttal experiment or validation | `evidence-first-rebuttal/SKILL.md` | Decide whether an experiment is needed, design preflight/smoke/full-run discipline, and report reviewer-facing evidence. |
| Prolific human study | `prolific-human-validation/SKILL.md` | Design, launch, monitor, pull, and analyze Prolific or AI Task Builder validation studies. |
| LaTeX page reduction | `latex-page-reduction/SKILL.md` | Reduce a conference paper to a strict page limit without changing scientific claims. |
| GitHub repo creation or push | `auto-github/SKILL.md` | Initialize git, create a GitHub repository, attach remotes, commit, and push safely. |
| Website task or dashboard automation | `api-first-web-automation/SKILL.md` | Search for APIs, docs, direct URLs, and stable endpoints before browser automation. |
| Formal code verification | `formal-code-verification/SKILL.md` | Check code against explicit behavioral properties, reproduce counterexamples, refine models, and distinguish tests/model checks from source proofs. |
| Software development process | `software-development-discipline/SKILL.md` | Keep non-trivial software work scoped, traceable, verified, and reviewable across issues, PRs, CI, release trains, regressions, and subagents. |

## Common Combinations

- **Rebuttal plus human validation**: start with `evidence-first-rebuttal/SKILL.md`; use `prolific-human-validation/SKILL.md` for study design and result aggregation.
- **Rebuttal plus paper compression**: start with `evidence-first-rebuttal/SKILL.md`; use `latex-page-reduction/SKILL.md` only when final revision needs to fit a page limit.
- **OpenReview plus web workflow**: start with `openreview-submit/SKILL.md`; use `api-first-web-automation/SKILL.md` if the API path is unavailable or the task needs UI verification.
- **Research repo release**: start with `auto-github/SKILL.md`; use `api-first-web-automation/SKILL.md` only for remote UI checks or marketplace/dashboard tasks.

## Routing Rules

- Prefer a specialized child skill over broad ad hoc instructions.
- Do not duplicate child-skill content in the final answer. Use it to guide the work.
- If two skills conflict, follow the task-specific skill for the active work. Example: for Prolific study launch safety, follow `prolific-human-validation`.
- If the user asks for a concrete change, implement it. Do not stop at a proposed plan unless the task needs approval, credentials, or expensive compute.
- For rebuttals, keep reviewer-facing prose evidence-first and non-sycophantic. Do not imply unrun experiments.
- For remote or paid work, run local preflight and smoke checks before spending GPU/API/human-study budget.

## Repository Map

- `openreview-submit/`: OpenReview API workflows and scripts.
- `evidence-first-rebuttal/`: rebuttal format, evidence ledger, experiment workflow, and agent-style polish.
- `prolific-human-validation/`: Prolific and AI Task Builder study workflow and scripts.
- `latex-page-reduction/`: LaTeX page-limit reduction rules.
- `auto-github/`: GitHub repo creation and publishing workflow.
- `api-first-web-automation/`: API-first approach before browser automation.
- `formal-code-verification/`: specification-driven validation, counterexample-guided refinement and evidence limits.
- `software-development-discipline/`: general software-development workflow discipline.
