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
semantic Worker inputs. Immutable Spec, Verify, and Bug Workers never read
project tests. Give them distilled requirements and caller intent with source
citations, never test solutions, expected bug triggers, or known-bug answer keys.
Keep their full definitions, tickets, allowed paths, and runtime gates unchanged.

## Four steps

1. **Map the product.** Read requirements, public documentation, entrypoints,
   callers and call chains, persistence writes, transaction boundaries, external
   integrations, and background jobs. Identify observable outcomes and who owns
   each state transition. Record source evidence rather than guessing from names.
   For a whole repository, enumerate all critical flows and process them in
   batches; retain unprocessed or unsupported flows visibly. For a change scope,
   expand only to dependencies and consumers whose behavior the change affects,
   recording why each added path belongs. Do not silently shrink the request.
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
   runtime's existing Bug Validation execution. After a real reproduction,
   correct mistaken model assumptions, revisit affected callers/flows, and
   rerun the relevant existing stages. Preserve the governing requirement and
   prior evidence; do not repair a violated Q by redefining intended behavior.
4. **Account for coverage.** Maintain the ledger below as evidence arrives.
   Deduplicate by business obligation, observable path, and failure mode: several
   functions or probes may support one row. Split rows only for distinct outcomes
   or boundaries. Reuse linked evidence; never count duplicate executions as
   broader coverage. Retain unknown, failed, and passed rows with their limits.

## Discovery and ledger template

Write `discovery.md` and `coverage.md` at the external analysis checkout root;
link existing runtime artifacts instead of creating another execution system.
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
remaining flows, unknown requirements, and skipped execution explicitly. Never
claim zero bugs, universal correctness, or whole-repository coverage from a
clean batch, reasoning MATCH, or passing tests.
