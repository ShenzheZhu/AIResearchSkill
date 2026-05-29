# AIResearchSkill

This repository stores reusable agent skills for common AI research usage.

It is designed to work across agents:

- Codex can use each folder as a native skill source.
- Claude Code and other coding agents can read the same folders as reusable playbooks and run the bundled scripts directly.
- The `scripts/` and `references/` folders are agent-agnostic; `SKILL.md` is the Codex-oriented entrypoint.

The repository root is also a router skill:

- `SKILL.md`
  An umbrella router that chooses the right focused skill for OpenReview submissions, reviewer rebuttals, human validation, LaTeX page reduction, GitHub publishing, API-first web automation, and multi-PR research engineering.

## Structure

- `openreview-submit/`
  OpenReview automation for inspecting submissions, resolving author profile IDs, filling author lists, and batch submission/edit workflows.

- `auto-github/`
  GitHub automation for creating repositories with `gh`, initializing git when needed, attaching `origin`, and pushing local projects safely.

- `api-first-web-automation/`
  Web-task automation guidance that first searches for official APIs, docs, direct URLs, and likely endpoints before falling back to browser automation.

- `latex-page-reduction/`
  Reduce a LaTeX conference paper to a hard page limit (e.g., 9 pages for COLM/ICLR/ICML). Covers priority-ordered trimming techniques (syntactic tightening → removing redundant examples → negative vspace → structural moves), hard rules (never change `[H]` float, no em dashes, no content deletion without approval), Overleaf merge-conflict handling, and common pitfalls.

- `multi-pr-feature-shipping/`
  Discipline and workflow for shipping a multi-issue feature as a series of small sub-PRs into a long-lived integration branch. Covers branch strategy (per-issue worktrees off `feat/<feature>`), the six-step cycle (setup → implement → self-check → commit → push → PR), always-ask gates, eight discipline rules (honest reporting, strict scope, no fabrication, anti-self-inflation, …), common failure modes with cause/prevention pairs, and a boundary-log debugging methodology.

- `prolific-human-validation/`
  Design and run Prolific human-validation studies for AI research claims and rebuttals, especially AI Task Builder Batch workflows for scenario realism, failure-label validity, multi-user specificity, and failure-severity validation. Includes scripts for creating draft studies, pulling ATB reports, and summarizing results into rebuttal-ready tables.

- `evidence-first-rebuttal/`
  Draft, audit, run supporting experiments for, and polish OpenReview-style paper rebuttals with a full final-response Markdown format, reviewer-by-reviewer structure, evidence ledgers, paper-aligned preflight/smoke/full-run discipline, Markdown-ready tables, page-limit handling, agent-style review, and direct non-sycophantic wording.

## Usage

For Codex:

- Copy or symlink the whole repo into `~/.codex/skills/AIResearchSkill/` to use the root router skill.
- Copy a skill folder into `~/.codex/skills/`
- Or clone this repo and copy the specific folders you want

For Claude Code or other agents:

- Read the skill folder's `SKILL.md` for the workflow
- Run the scripts in `scripts/`
- Use `references/` as supporting documentation

The repository is intentionally simple so the same folder can be consumed by multiple agents without format conversion.

Each skill contains:

- `SKILL.md`
- `agents/openai.yaml`
- `scripts/`
- `references/`

Some lightweight skills may omit `scripts/` or `references/` when the workflow does not need bundled resources.
