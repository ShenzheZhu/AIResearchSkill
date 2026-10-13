---
name: formal-code-verification
description: Autonomously discover verification targets in a repository or change scope, then run FM-Agent's Hoare-style correctness pipeline using current Codex and native subagents. Map business flows, derive caller-grounded specifications, execute counterexamples and track coverage gaps. Use for specification-driven verification, not ordinary smoke testing.
---

# FM-Agent for Codex

Use the bundled [official FM-Agent Skill implementation](runtime/skills/run/instructions.md). This packages its working pipeline rather than replacing it with a review checklist. Read that entry completely, then follow its phase driver, Worker tickets and completion gates, subject to this wrapper's scope below.

**All semantic work uses the current Codex session and its native subagents.** Never call an external model provider, ask for an API key, launch a nested Codex/Claude CLI, or fall back to the original remote-model pipeline. Python runs local deterministic tools only.

## Default: discover what needs verification

The user only needs to name a repository or change scope. Read [autonomous-discovery.md](references/autonomous-discovery.md) and perform its four steps: map real flows, discover realistic obligations and missing tests, generate independent business-grounded specifications and execute counterexamples, then reconcile the coverage ledger. Do not ask the user to supply a function list or specifications.

Use a read-only scout for discovery when useful. It may inventory existing tests; start semantic Workers with `fork_turns="none"`, passing only complete tickets, immutable definitions and permitted evidence. Spec and Verify use independent fresh contexts. After the executor validates Bug preparation, its execution ticket may continue that same isolated Worker through `collaboration.followup_task` only for the identical project, job, candidate, attempt and input hash. Otherwise launch a fresh execution Worker. Never reuse contexts across jobs or inherit parent history, tests or solutions. If fresh native contexts are unavailable, leave execution blocked rather than doing semantic work in the contaminated parent. Derive intended behavior from requirements and callers, keep uncertain intent unresolved, and never weaken a postcondition to fit the implementation.

Keep the user's source untouched. Prepare an independent external analysis checkout including the requested current working-tree changes, then keep discovery, coverage and runtime artifacts there. Group obligations by their actual analyzed source first: flows sharing `scripts/shop.py`, for example, belong to one source batch with separate ledger rows and shared evidence. Do not repeatedly verify the same directory for different flow names. Every distinct new source batch starts in a fresh checkout without unrelated `fm_agent/` or `fm_agent_skill/` baselines. Verify first inspection selects `full`. Subsequent changes to that same scope may use its qualified completed baseline; resume an interrupted analysis in its existing checkout.

For later code or requirement changes, read [incremental-and-candidates.md](references/incremental-and-candidates.md). Treat resume, incremental and no-op as different outcomes. Incremental selection uses both code differences and the developer's goal, including necessary changes the patch omitted. Keep unchanged evidence at its original origin; never relabel an old result's snapshot as new execution.

## Packaging and invocation

Set `FM_AGENT_SKILL_ROOT` to the absolute `runtime/` directory beside this file. This overrides the upstream location-discovery example: its five embedded skill entries are named `instructions.md` to avoid registering generic `run`, `help` and `config` skills globally. Their relative references and the executable runtime are preserved.

Take the target Git repository and scope from the user's request. Discover the source directories needed for each batch, including actually affected consumers, and pass them through `--submodule`; the runtime accepts directories, not single-file arguments. Pass distilled requirements through `--knowledge`. Pass `--host codex` to the phase driver and Worker dispatch/claim commands. Use the host's available worker slots; do not request more workers than it can run. No new provider configuration or application dependency is required.

Give each Worker its complete ticket and immutable definition, plus the dispatch scope when its manifest lacks scope inputs. Every receipt needs `job_id`, a non-empty `status`, exact `outputs` and a short summary. Submit planning/static-edge receipts through `scheduler.py complete`, specification/verification receipts through `semantic_executor.py submit`, and Bug Validation passes through the executor's returned action.

Bug Validation uses preparation and execution turns; the runtime generates reports and receipts deterministically from validated immutable execution and accepted attempt history. This reduces the expected model turns per attempt from 3 to 2, and native context starts from 3 to 1 when safe continuation is available (otherwise 2). These are lifecycle counts, not measured wall-clock savings. Valid unsupported execution ends inconclusive after its first attempt; runtime failures and completed negative probes retain their existing budgets. Retry with a distinct lawful witness or fix the actual execution error; an identical missing-runtime retry adds no evidence.

State explicitly that the launched subagent is the assigned Worker and the parent is the sole Coordinator. The ticket's host-launch metadata is Coordinator guidance, not an instruction for the Worker to spawn another agent. Preserve the complete ticket and definition; do not replace them with a paraphrased task.

Use `--all-bugs` for a repository audit or a request to find all independent defects. Each function completes its reasoning before candidate acceptance; each candidate receives its own probe, accepted receipt and result. Functions with loops also require parser-grounded initialization, invariant preservation, normal-exit and relevant abrupt-exit arguments. Missing loop evidence is a reasoning gap, not a conclusive match. These natural-language arguments remain model reasoning rather than machine proofs.

Example request:

```text
Use $formal-code-verification to autonomously verify /path/to/repo.
Discover verification targets and omissions, work in risk-based batches,
reproduce counterexamples and maintain coverage evidence.
```

The method follows `{P} C {Q}`: derive intended P/Q independently, propagate assertions through the implementation to obtain actual A, and seek a concrete `P ∧ A ∧ ¬Q` witness. Verify and Bug preparation receive the copied requirements and permitted caller evidence. If a witness's input domain is invalid or unclear, name the gap; never invent a negative output or weaken Q. Keep callee dependency risks separate from direct violations. Every direct candidate goes through real-code Bug Validation before being reported as confirmed. Finite probes support only their recorded inputs and schedules.

This workflow is project independent. Check the actual extraction/execution capabilities of the target environment; a language profile, supplied source span or passing example does not establish compatibility for another language, flow or repository. Preserve missing parsers, unsupported source forms and unavailable integration/verifier environments as gaps. Every qualified coverage row must refer to the exact requirement and execution it actually checks.

Select one available Python 3.10+ interpreter and parser environment at preflight, and use it consistently for the run. Do not assume a previous session's temporary parser installation exists or switch interpreters after a parser failure; report the missing capability explicitly.

The runtime keeps local analysis artifacts and continuation state; it does not modify product source or introduce product execution routing. Its LLM reasoning is not a sound machine-checked proof. Report the selected scope, normative assumptions, actual dynamic results and uncovered boundaries.

For a repeatable public-repository example, read [references/public-case.md](references/public-case.md). For source provenance and packaging changes, read [UPSTREAM.md](UPSTREAM.md).
