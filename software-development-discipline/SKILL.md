---
name: software-development-discipline
description: Use when starting or continuing non-trivial software development work, especially tasks involving GitHub issues, PRs, commits, CI, integration branches, release trains, regressions, subagents, or project-wide engineering process. Provides a general software-project development contract for keeping work scoped, traceable, verified, and reviewable across repositories.
---

# Software Development Discipline

This is the default development contract for serious software work. Use the
repository's own `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, docs, and user
instructions first; use this skill as the general discipline layer when those
docs are missing, vague, or need reinforcement.

Core principle: keep work traceable, scoped, verified, and easy to review.

## 1. Start Of Work

Before coding:

1. Check branch and worktree state.
2. Read the repo's local agent/development docs.
3. Identify the target branch and whether the work should be a hotfix, normal
   PR, integration train, or docs/process-only change.
4. Inspect active issues/PRs when the task touches ongoing work.
5. Reuse or create an issue for product bugs/features unless the user explicitly
   says the change does not need one.
6. Convert vague issues into actionable ones before implementation.
7. Search the codebase and read nearby code before inventing new patterns.

If the user asks for planning, produce a compact plan. If the user asks to
implement, proceed after the above checks without turning the plan into a
blocking ritual.

## 2. Issue And Scope Discipline

Use one issue for one coherent feature or bug. Keep closely coupled frontend,
backend, and test changes together only when they are one user-visible flow.
Split work when the pieces can be developed, reviewed, shipped, or reverted
independently.

Issue bodies for real bugs/features should include:

- target branch
- classification
- problem statement
- expected behavior
- repro or trigger
- suspected failure path
- scope
- acceptance criteria
- out-of-scope boundaries
- relevant files and references

If user feedback reveals legitimate work outside the current PR, open a
follow-up issue and link it. Do not expand the active PR unless the user says
the new finding blocks the current work.

## 3. Branch Strategy

Choose the lightest branch model that preserves stability:

| Path | Use When | Merge Target |
| --- | --- | --- |
| Direct hotfix | urgent production bug, narrow blast radius | `main` |
| Normal PR | one coherent change ready to ship | `main` |
| Integration train | 3+ related issues or several PRs should ship together | `integration/<theme>` or `release/<theme>` |
| Docs/process only | durable docs or workflow updates | repo default unless docs-only deploy rules say otherwise |

For an integration train:

1. Create the integration branch from current `main`.
2. Open sub-PRs into the integration branch.
3. Keep each sub-PR small and reviewable.
4. Rebase or merge `main` into the train every few sub-PRs to avoid drift.
5. Open one final release PR from the integration branch to `main`.

Do not batch unrelated risky fixes merely to reduce deploy count.

## 4. Per-Issue Cycle

For each issue or sub-issue:

1. Setup: branch from the correct target and copy acceptance criteria into the
   working checklist when useful.
2. Implement: make focused changes using existing local patterns.
3. Self-check: run targeted tests/typecheck/lint/build as appropriate.
4. Review: read the staged diff before committing.
5. Commit: use a logical message with the issue number when available.
6. Push/PR: open or update the PR at a coherent review/deploy boundary.

Prefer small logical commits. Do not claim completion without matching
verification evidence.

## 5. Commit, Push, PR, And Merge Gates

Default gates:

- Reading, searching, editing active-scope code, and running tests are allowed.
- Ask before installing dependencies, changing schema/migrations, editing
  production config, force-pushing, rewriting history, or destructive git ops.
- If the user has explicitly authorized automatic commit/push/PR/merge for the
  current task class, you may proceed, but still report what changed and what was
  verified.
- If no automation authorization exists, ask before first push, PR creation, and
  merge.

PR body should include:

- `Closes #<issue>` or explicit `Refs #<issue>`
- summary of behavior changed
- acceptance criteria or test coverage
- verification commands/results
- known limitations and linked follow-ups

Do not hide unfinished behavior behind vague "future work" language.

## 6. Verification Ladder

Pick the smallest verification that proves the change:

- Docs/process: diff check, stale-reference search, syntax/link checks when
  relevant.
- Backend logic: targeted unit/contract tests, then broader tests if shared
  behavior changed.
- Frontend visible UX: local preview or browser smoke when the user needs visual
  confidence.
- Auth/session/security/data persistence: targeted regression plus adjacent
  happy path.
- AI/provider/prompt behavior: live or harness execution with traces, not only
  typecheck.
- Deployment/proxy/TLS: deployed smoke against actual URLs.
- Release train: broader build/test suite and a final regression pass.

State verification precisely:

- "verified working" means the relevant flow was exercised.
- "tests pass" means automated tests passed, not the product flow.
- "not run" must be explicit.

## 7. Regression Handling

When a bug is found:

1. Search prior issues/PRs/docs for the same symptom.
2. Classify as old unresolved bug, regression, or new bug.
3. Open/update an issue with concrete evidence.
4. Fix in the smallest coherent scope.
5. Add a regression lock when practical.
6. Retest the affected flow and adjacent happy path.

The goal is not to promise no bugs. The goal is to make repeated bugs visible,
prevent silent reappearance, and make new bugs genuinely new.

## 8. Subagent Delegation

The main agent owns issue triage, plan, critical-path coding, final review,
commit, PR, and merge judgment.

Good subagent tasks:

- scout: find code paths, prior issues, failure paths, or similar patterns
- worker: implement a bounded change with disjoint file ownership
- verifier: run focused tests, QA probes, or edge-case audits
- docs/copy: issue upgrades, PR body drafts, test reports, copy review

Avoid subagents for tiny hotfixes, tightly coupled auth/session/security/AI-core
changes, live design iteration requiring user feedback, or any task that blocks
the next immediate local action.

When delegating code work, specify owned files/modules, warn not to revert
unrelated work, and require changed files plus verification in the return. The
main agent must review the output before committing.

## 9. Multi-Issue Checkpoints

Every third closed issue/PR in one feature train, pause and re-review:

- planned vs actual shipped work
- merged PRs, open PRs, unresolved issues
- target branch correctness
- hidden coupling or duplicated work
- scope creep and follow-up issues
- remaining verification gap

Any user "wait", "are you sure", "等一下", or similar interruption is also a
checkpoint. Stop and re-evaluate rather than continuing on stale momentum.

## 10. Debugging Method

When behavior is wrong:

1. Reproduce on a clean reload or clean command.
2. Add diagnostics at API/process boundaries, with clear prefixes.
3. Use logs to locate the failing boundary before changing broad code.
4. If two attempts fail without new evidence, stop retrying and reframe the
   diagnosis.
5. Remove temporary logs in the same fix unless they are intentionally promoted
   to durable observability.

For unfamiliar APIs or libraries, inspect installed types/docs or run a minimal
probe before building around assumptions.

## 11. Hard Stops

Stop and ask or report before proceeding when:

- the user says `STOP`, "wait", "等一下", or challenges the direction
- the work requires destructive git operations
- a migration or auth/session/security semantic change is needed
- test results contradict the expected behavior
- the implementation would exceed the issue's scope
- you cannot make meaningful progress without external input

This skill replaces the previous feature-shipping playbook with a repository-
agnostic engineering workflow.
