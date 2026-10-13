# Autonomous discovery and coverage

The user supplies a repository or change scope. The Coordinator discovers what
to verify; do not require a function list, hand-written contracts, or test plan.
Use the bundled FM-Agent runtime, current Codex session, and native subagents.
Do not add a scheduler, execution script, model provider, or product dependency.

## Read-only scope and output

Inspect the user's repository without changing its files, index, refs, or data.
Before stateful dispatch, use native Git/copy and official isolation to prepare
an independent external Git checkout with the requested current source, including
tracked changes and untracked source. Preserve paths; record origin revision,
dirty-scope provenance, and scope. Never silently analyze only an older HEAD.
Run the existing runtime against this checkout: it publishes artifacts and refs
to its `--project` target even though execution uses a detached snapshot. Keep
`fm_agent/`, `fm_agent_skill/`, and discovery/report files there. Verification
does not authorize product fixes; apply none unless the user requests them.

The Coordinator or a read-only scout may inspect existing tests to discover
missing coverage. Do this before FM-Agent phase planning and keep it outside
semantic Worker inputs. Start semantic Workers with `fork_turns="none"`; supply only tickets, immutable definitions and permitted evidence. Spec and Verify always use independent fresh contexts. Only Bug execution may continue its matching isolated preparation Worker after validation, with the identical project/job/candidate/attempt/input hash; otherwise start fresh. Never reuse contexts across jobs or inherit the discovery parent's test/answer history. Immutable Spec, Verify, and Bug Workers never read
project tests. Give them distilled requirements and caller intent with source
citations, never test solutions, expected bug triggers, or known-bug answer keys.
Keep their full definitions, tickets, allowed paths, and runtime gates unchanged.
The runtime includes materialized copied requirements and permitted caller
evidence in Verify and Bug preparation tickets.

## Four steps

1. **Map the product.** Read requirements, public documentation, entrypoints,
   callers and call chains, persistence writes, transaction boundaries, external
   integrations, and background jobs. Identify observable outcomes and who owns
   each state transition. Record source evidence rather than guessing from names.
   For a whole repository, enumerate all critical flows and process them in
   batches; retain unprocessed or unsupported flows visibly. For a change scope,
   expand only to dependencies and consumers whose behavior the change affects,
   recording why each added path belongs. Default inventory exclusions are advisory: inspect served/deployed entrypaths and explicitly select real production directories such as `dist/` when required. Do not silently shrink the request.
   Record excluded vendored dependency implementations separately from the
   first-party batch. An explicit directory selection can override the default
   `vendor/` exclusion when that directory contains the requested business code.
2. **Discover obligations.** Trace relevant permissions, ownership and data
   invariants, failure/recovery behavior, duplicate requests, concurrent calls,
   process restart, and state shared across modules. Follow writes through their
   readers and follow failures through retry/compensation paths. Include only
   failure modes the actual product can encounter; test-count expansion and a
   Cartesian product of every operation, role, and failure are not coverage.
3. **Specify, execute, refine.** Derive business-grounded `{P} C {Q}` and frame
   invariants from requirements and caller intent independently of the body.
   Normative behavior must not mirror current implementation or be weakened to
   bless a defect. Unsettled requirements remain explicit unknowns. A restrictive
   P needs a proven caller guard; reachable invalid inputs belong in Q's failure
   behavior. Let the unchanged FM-Agent Workers derive actual behavior and
   counterexamples, then validate candidates against actual code through the
   runtime's existing Bug Validation execution. Establish that the actual witness
   satisfies P and the governing input domain before probing. An invalid or
   unclear domain is a named gap; never invent negative output, substitute an
   unrelated witness, or weaken Q. Valid unsupported evidence finishes
   inconclusive on its first attempt. Runtime and completed-negative budgets
   remain, but retries need a distinct lawful witness/trigger or a fix for the
   actual execution error. After a real reproduction,
   correct mistaken model assumptions, revisit affected callers/flows, and
   rerun the relevant existing stages. After a completed baseline, use incremental
   selection with both the source differences and the developer's goal; include
   necessary consumers the patch omitted. Reuse qualified unchanged evidence at
   its original origin instead of repeating unrelated batches. Preserve the governing requirement and
   prior evidence; do not repair a violated Q by redefining intended behavior.
4. **Account for coverage.** Maintain the ledger below as evidence arrives.
   Deduplicate by business obligation, observable path, and failure mode: several
   functions or probes may support one row. Split rows only for distinct outcomes
   or boundaries. Group overlapping actual source directories/files into one batch before dispatch; two business flows sharing `scripts/shop.py` reuse one extraction/specification/verification run. Reuse linked evidence; never count duplicate executions as
   broader coverage. Retain unknown, failed, and passed rows with their limits.

## Discovery and ledger template

Write discovery notes outside product code. Keep the canonical ledger at `fm_agent_skill/control/business_coverage.json` in the active analysis checkout; a readable Markdown table is derived from it, not a second editable truth. Link existing runtime artifacts instead of creating another execution system.
Include source state, requested/expanded scope, critical flow inventory, batch
progress, unresolved requirements, and exclusions. Distilled requirement notes
may be external Markdown `--knowledge` inputs materialized by the runtime.

```text
Flow: <public entrypoint -> modules/jobs -> observable outcome>
Requirement: <source path/section; normative rule or explicit inference>
Obligation: <unique business obligation / path / relevant failure mode>
{P}: <reachable input/state assumptions and proven caller guards>
C: <actual entrypoint/call chain and source locations>
{Q}: <success and failure outcomes; allowed writes; invariant/frame conditions>
Counterexample: <concrete input/state/schedule violating Q, if derived>
Affected flows: <actual consumers sharing the violated contract/state>
Unknowns: <missing requirement, environment, adapter, or execution capability>
```

| Flow | Obligation / path / failure mode | Requirement and P/C/Q | Execution evidence | Result and limits |
| --- | --- | --- | --- | --- |
| `<flow>` | `<one unique obligation>` | `<discovery entry + spec>` | `<runtime artifact, source state, input/schedule, observation>` | `<unknown / failed / passed; evidence level and uncovered boundary>` |

Record the ledger before finalization. Its minimal schema is:

```json
{
  "schema_version": 1,
  "snapshot_commit": "the active analysis snapshot",
  "rows": [{
    "id": "lookahead",
    "flow": "peek -> next",
    "requirement": "public API docstring: peek preserves the next logical item",
    "status": "unknown",
    "evidence": [],
    "limitation": "actual execution has not run"
  }]
}
```

Evidence entries name a project-relative `path` and a `level`: `reasoning`,
`actual-code`, `integration`, or `machine-verifier`. A passed/failed native
Bug Validation row also names its assigned `function_id` and independent
`candidate_id`; its `requirement`
must exactly equal that function's independently derived `.spec.json`
`post_condition`. The current source index, planned job, accepted receipt and
named execution attempt must all belong to that assignment. New evidence belongs
to the active snapshot; retained evidence must have a qualified original snapshot
and exact original receipt, execution files and result bytes. Never relabel an
old execution as one performed against the new snapshot.
Reusing a budget-check probe for a persistence postcondition is invalid even
when both are part of the same flow. Native Bug Validation receipts qualify
only `actual-code`: calling one `integration` or `machine-verifier` does not
establish that evidence level. Such rows remain unknown until the runtime can
independently validate the relevant evidence type; do not invent an adapter.
`confirmed` supports the assigned failed obligation. A successful negative
probe supports only that exact postcondition for its recorded inputs and
schedule, which must be stated in `limitation`; it never passes the whole flow.
Each independently derived candidate needs its own validation. Multiple probes
for one candidate are attempts, not additional defects or broader coverage.
Unsupported, inconclusive, raw build logs and other unvalidated records keep
the obligation unknown. Unknown rows remain visible without a function
binding and may link reasoning or external-tool artifacts. After execution,
update the same row and its limits rather than creating duplicate coverage.

Keep evidence levels distinct: **LLM reasoning** is a model-derived MATCH or
static candidate; **actual-code reproduction** executes a concrete public path;
**flow integration** executes the relevant real module/job/persistence chain;
**machine verifier**, when already available, proves only its encoded model and
assumptions. A model-only counterexample is not an actual-code reproduction.
Use existing runtime-supported probes for execution; unsupported adapters or
integration environments leave the corresponding ledger rows unknown.

An unexecuted static candidate remains unknown dynamically. Mark failed when
matching actual-code evidence demonstrates a violated obligation; mark passed
only for the claim supported by the named evidence, retaining input, schedule,
model, and integration limits. Passing finite probes does not prove all inputs.
Use `terminal_report.py` as the runtime's finding authority; a failed gate yields
an incomplete report, never findings promoted from discovery notes. Report
remaining flows, unknown requirements, and skipped execution explicitly. Check `reasoning.counts/gaps`, qualified dynamic result counts, and `business_coverage` separately. Missing/invalid coverage or unavailable accepted receipts leaves `audit_status: incomplete`; do not call the audit complete. Unknown coverage or any dynamic inconclusive candidate is `completed_with_gaps`, not universal correctness. Each compact dynamic finding retains every attempt's ordinal, classification, execution state and reason so a later negative probe cannot hide earlier unavailable execution. Continue pending executable obligations before closing, and retain genuine environment/requirement blockers visibly. Never
claim zero bugs, universal correctness, or whole-repository coverage from a
clean batch, reasoning MATCH, or passing tests.
