# Claude Code Usage

Use this repository as a cross-agent toolkit.

## How to use a skill folder

1. Read the target folder's `SKILL.md`.
2. Use the workflow in that file as the primary procedure.
3. Run scripts from `scripts/` instead of rewriting one-off commands when possible.
4. Read `references/` only when the task needs more detail.

## Skill map

- `openreview-submit/`
  Use for OpenReview inspection, author-list updates, profile-id lookup, and batch submission edits.

- `auto-github/`
  Use for creating GitHub repositories with `gh`, initializing git safely, and pushing local projects.

- `api-first-web-automation/`
  Use before browser automation. Check for official APIs, docs, direct URLs, and likely endpoints first.

- `latex-page-reduction/`
  Use when a LaTeX paper exceeds its page limit. Covers priority-ordered trimming techniques, hard rules (no [H]→[t], no content deletion, no em dashes), and merge-conflict handling with Overleaf.

- `evidence-first-rebuttal/`
  Use for OpenReview-style rebuttal drafting, experiment planning/runs, and final polish. Covers full final-response Markdown format, reviewer-by-reviewer issue mapping, evidence ledgers, paper-aligned preflight/smoke/full-run discipline, Markdown tables, page-limit constraints, agent-style review, and direct non-sycophantic wording.

## Operating rule

Prefer the stable interface in this order:

1. official API
2. official CLI or SDK
3. documented direct URL or endpoint
4. browser automation

Do not assume UI automation is necessary until the earlier options have been checked.
