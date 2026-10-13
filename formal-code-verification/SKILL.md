---
name: formal-code-verification
description: Autonomously discover verification targets in a repository or change scope, then run FM-Agent's Hoare-style correctness pipeline using current Codex and native subagents. Map business flows, derive caller-grounded specifications, execute counterexamples and track coverage gaps. Use for specification-driven verification, not ordinary smoke testing.
---

# FM-Agent for Codex

Use the bundled [official FM-Agent Skill implementation](runtime/skills/run/instructions.md). This packages its working pipeline rather than replacing it with a review checklist. Read that entry completely, then follow its phase driver, Worker tickets and completion gates, subject to this wrapper's scope below.

**All semantic work uses the current Codex session and its native subagents.** Never call an external model provider, ask for an API key, launch a nested Codex/Claude CLI, or fall back to the original remote-model pipeline. Python runs local deterministic tools only.

## Default: discover what needs verification

The user only needs to name a repository or change scope. Read [autonomous-discovery.md](references/autonomous-discovery.md) and perform its four steps: map real flows, discover realistic obligations and missing tests, generate independent business-grounded specifications and execute counterexamples, then reconcile the coverage ledger. Do not ask the user to supply a function list or specifications.

Use a read-only scout for discovery when useful. It may inventory existing tests; immutable FM-Agent semantic Workers do not read those tests or their solutions. Derive intended behavior from requirements and callers, keep uncertain intent unresolved, and never weaken a postcondition to fit the implementation. Record distinct obligations once, link their evidence, and revisit actual affected consumers after a counterexample or model refinement.

Keep the user's source untouched. Prepare an independent external analysis checkout including the requested current working-tree changes, then keep discovery, coverage and runtime artifacts there. Every new audit/batch uses a fresh checkout without copied `fm_agent/` or `fm_agent_skill/` baselines. **This wrapper supports full analysis and resuming an interrupted full run; upstream incremental/no-op scheduling is not supported.** Verify initial inspection selects `full`. Continue an interrupted run in its existing checkout rather than restarting it. Scope new batches to remaining or changed obligations to avoid duplicate verification.

## Packaging and invocation

Set `FM_AGENT_SKILL_ROOT` to the absolute `runtime/` directory beside this file. This overrides the upstream location-discovery example: its five embedded skill entries are named `instructions.md` to avoid registering generic `run`, `help` and `config` skills globally. Their relative references and the executable runtime are preserved.

Take the target Git repository and scope from the user's request. Discover the source directories needed for each batch, including actually affected consumers, and pass them through `--submodule`; the runtime accepts directories, not single-file arguments. Pass distilled requirements through `--knowledge`. Pass `--host codex` to the phase driver and Worker dispatch/claim commands. Use the host's available worker slots; do not request more workers than it can run. No new provider configuration or application dependency is required.

Give each Worker its complete ticket and immutable definition, plus the dispatch scope when its manifest lacks scope inputs. Every receipt needs `job_id`, a non-empty `status`, exact `outputs` and a short summary. Submit planning/static-edge receipts through `scheduler.py complete`, specification/verification receipts through `semantic_executor.py submit`, and Bug Validation passes through the executor's returned action.

Example request:

```text
Use $formal-code-verification to autonomously verify /path/to/repo.
Discover verification targets and omissions, work in risk-based batches,
reproduce counterexamples and maintain coverage evidence.
```

The method follows `{P} C {Q}`: derive intended P/Q independently, propagate assertions through the implementation to obtain actual A, and seek a concrete `P ∧ A ∧ ¬Q` witness. Keep callee dependency risks separate from direct violations. Every direct candidate goes through real-code Bug Validation before being reported as confirmed.

The runtime keeps local analysis artifacts and continuation state; it does not modify product source or introduce product execution routing. Its LLM reasoning is not a sound machine-checked proof. Report the selected scope, normative assumptions, actual dynamic results and uncovered boundaries.

For a repeatable public-repository example, read [references/public-case.md](references/public-case.md). For source provenance and packaging changes, read [UPSTREAM.md](UPSTREAM.md).
