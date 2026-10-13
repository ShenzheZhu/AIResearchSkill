---
name: run
description: Run or safely resume an FM-Agent full, incremental, or no-op correctness analysis for a Git project. Use when the user asks to analyze code, continue an interrupted FM-Agent run, generate behavioral specifications, verify implementation against specifications, or assess changes for formal-methods bugs.
---

# FM-Agent analysis

Modified by AIResearchSkill: isolate semantic Workers and continue only validated same-attempt Bug execution.

This is the sole public analysis entry point. Execute it directly in Claude
Code or Codex using that host's worker/subagent capability. Never launch,
import, or shell out to the original FM-Agent project or its remote-LLM
pipeline. The bundled deterministic executor and the host Coordinator together
are this Skill's implementation.

All reasoning uses the current Codex or Claude Code host session. Never call
an external model service, request or read an API key, invoke a nested Codex or
Claude CLI, or add a model SDK dependency. Python tools only manage local
snapshots, artifacts, validation, and durable state.

The Coordinator is the Skill's equivalent of FM-Agent's original `main.py`.
It coordinates local deterministic tools and dispatches canonical Worker
contracts through the current host's subagent mechanism; it never performs a worker's semantic
task inline. Read
[subagent-scheduler.md](../../references/subagent-scheduler.md) in addition to
[agent-orchestration.md](../../references/agent-orchestration.md) before
starting. Read [durable-execution.md](../../references/durable-execution.md)
for checkpoint, automatic continuation, DAG, and terminal authority rules.

Never create or run a Dynamic Workflow, generated JavaScript workflow, or
another ad-hoc orchestration script for an FM-Agent semantic phase. Such a
script cannot substitute for a registered Worker and must not restate, shorten,
or reinterpret a Worker contract. Use the bundled deterministic semantic
executor described below; this prohibition applies even when the host offers a
Workflow tool.

Before invoking a script, read [runtime-path.md](../../references/runtime-path.md)
and resolve `FM_AGENT_SKILL_ROOT`; never use `CLAUDE_SKILL_DIR`.

Read [progress-reporting.md](../../references/progress-reporting.md) before any
stateful action. User-visible phase progress is mandatory; do not rely on a
client to infer it from tool output.

Read [agent-coordinator.md](../../references/agent-coordinator.md) before
dispatching any Worker. The current Claude/Codex parent Agent is the
Coordinator; a Worker subagent is never allowed to take that role or end an
active analysis.

## Output ownership

Write FM-Agent-compatible analysis artifacts only below `fm_agent/` and mutable
Skill control state only below `fm_agent_skill/`. Do not derive a target-project
directory name from the Skill's installation or marketplace packaging. Before
dispatching a worker, give it only the output paths listed in its job manifest.

## Public parameters

Codex selects this skill from a natural-language request; this skill directory
does not create a Codex slash command. When a client exposes a command entry,
it may pass the following arguments to the same workflow:

```text
[natural-language change note]
  [--submodule path ...] [--one-phase]
  [--extra-edge file-or-dir] [--knowledge file ...] [--resume]
  [--incremental intent.md] [--all-bugs | --no-all-bugs]
  [--validate function-or-candidate-id]
```

Treat all text not matching an option as the change note. Resolve paths relative
to the target repository. Do not invent `$PROJECT` or a scope: the caller
supplies the project and `orchestrate.py dispatch` returns the current analysis
state, merged configuration, and mode as JSON.

## Resume, dispatch, and cleanup

Parse the supplied argument list before dispatching.  Do **not** pass
`$ARGUMENTS` verbatim as `--note`: split these public options from the
natural-language change note:

- `--submodule PATH` (repeatable)
- `--knowledge FILE` (repeatable)
- `--extra-edge FILE_OR_DIR`
- `--one-phase`
- `--resume`
- `--incremental INTENT.md`
- `--all-bugs` or `--no-all-bugs` (omit to inherit saved defaults/mode)
- `--validate FUNCTION_OR_CANDIDATE_ID`

`--validate` requires a completed baseline with existing verification results.
It runs only Bug Validation for one existing candidate without repeating earlier
stages. A function ID resolves only when it has exactly one candidate; with
multiple candidates, supply the explicit `<function-id>::bug-001` identity.
Its report and private probe evidence are merged into
the current baseline's Bug Validation result set; validating another candidate
does not discard an earlier candidate's accepted result. It is incompatible with a new change note,
`--submodule`, `--knowledge`, `--extra-edge`, `--incremental`, and `--one-phase`.

The baseline is content-addressed: a run begun with uncommitted source changes
remains eligible for `--validate` if the current production-source manifest is
identical to its private snapshot. If source files changed afterwards, run an
incremental analysis first; Git `HEAD` equality alone is not sufficient.

`--incremental INTENT.md` requires a compatible completed baseline and accepts
a non-empty Markdown developer goal. `--note` adds captured text. New intent
can select incremental mode without a source diff and overrides older knowledge
only on the clauses it changes. Unchanged source plus no new intent is a no-op;
a completed identical captured intent is not new. `--all-bugs` continues complete
reasoning after each independent mismatch and records separate candidates;
`--no-all-bugs` uses the default single-candidate mode. These modes do not mix on
resume.

All remaining text is the change note. Preserve every option value and pass
each option separately. First perform this read-only inspection. It never
acquires a lock, writes state, or rebuilds CodeGraph:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/orchestrate.py" inspect \
  --project "$PROJECT" \
  [--submodule "$PATH"]... [--knowledge "$FILE"]... \
  [--extra-edge "$FILE_OR_DIR"] [--one-phase] [--note "$CHANGE_NOTE"] \
  [--incremental "$INTENT_FILE"] [--all-bugs | --no-all-bugs]
```

### Explicit resume

`--resume` means continue the interrupted `full` or `incremental` analysis;
it never changes its saved scope or
configuration. It is mutually exclusive with `--submodule`, `--knowledge`,
`--extra-edge`, `--one-phase`, `--incremental`, and a new change note. Omitted
`--all-bugs` inherits the saved reasoning mode; an explicit contrary value is
rejected. Read
[resume-contract.md](../../references/resume-contract.md), then inspect it
before any ordinary mode selection or CodeGraph action:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/orchestrate.py" resume-inspect \
  --project "$PROJECT" [--all-bugs | --no-all-bugs]
```

If this returns an error, report its reason and do not start a fresh analysis.
It rejects changed auxiliary inputs, an already completed run, a missing active
Git ref/checkpoint, and legacy runs without a Git snapshot. A missing temporary
worktree is rebuilt from the durable checkpoint. If the interrupted
run's lock has a fresh heartbeat, report that another agent may still be
working. Ask the user whether to take over; only after an explicit affirmative
reply may the agent append `--take-over` below.

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/orchestrate.py" resume \
  --project "$PROJECT" [--take-over] [--all-bugs | --no-all-bugs]
```

Retain the returned `config` and `resume_from_phase`. Execute only the current
analysis's first incomplete phase and later phases. If the returned analysis
contains `validation_scope`, continue only its `validation_job_id` through the
on-demand Bug Validation loop and finish with `orchestrate.py validate-complete`
on the original project; do not enter full-analysis finalize. Do not call ordinary
`inspect` or `dispatch`, do not call `pipeline.py prepare`, and do not run a
full cleanup when a previous `phase_cleanup` succeeded. Revalidate every
function-level artifact in a resumed specification, verification, or bug
validation phase; retain only snapshot-compatible valid artifacts and produce only
the missing or invalid ones. Refresh the lock heartbeat before and after each
phase through the existing `pipeline.py` transitions.

Before beginning the resumed phase, emit the required `Resuming` status from
[progress-reporting.md](../../references/progress-reporting.md). It is also the
user-visible announcement for that phase; announce every later phase normally.

Keep the original call-graph backend for the resumed run. If the first
incomplete phase is `call_graph` or `rebuild_graph` and its saved backend is
CodeGraph, check the existing index; reuse it when readable and rebuild only
when missing or invalid. If an already-completed graph phase is valid, do not
touch `.codegraph/`. Never silently replace a CodeGraph-selected resumed run
with `agent-static`.

### On-demand Bug Validation

`--validate FUNCTION_OR_CANDIDATE_ID` runs dynamic Bug Validation for one
schema-v3 direct candidate from a completed baseline. A function ID is accepted
only when its candidate is unique; otherwise use the candidate ID returned by
inspection. It creates a private probe snapshot without repeating earlier
analysis stages.  It is mutually exclusive with `--submodule`, `--knowledge`,
`--extra-edge`, `--one-phase`, `--incremental`, `--resume`, and a new change note.

First verify the baseline and locate the candidate:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/orchestrate.py" validate-inspect \
  --project "$PROJECT" --function-id "$FUNCTION_OR_CANDIDATE_ID"
```

If inspection rejects the baseline, conflicting active snapshot or ambiguous
function identity, report its reason. An already accepted candidate can be
revalidated in a new private job without overwriting other accepted origins.

On success, dispatch exactly one Bug Validation job for the resolved candidate:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/orchestrate.py" validate-dispatch \
  --project "$PROJECT" --function-id "$FUNCTION_OR_CANDIDATE_ID"
```

This creates a private snapshot from the saved baseline commit and returns
`project`, `job_id`, `bug_id`, `candidate_id`, `function_id`, and `config`.  Then enter the standard single-function
Bug Validation loop below, starting from `durable_executor.py next`.  A single
function with at most `bug_validation_max_attempts` probes (default 5) and
`bug_validation_negative_retries + 1` negative attempts (default 3) is bounded
enough to complete in one turn under normal conditions.

On `dag_converged`, call `orchestrate.py validate-complete --project "$PROJECT"`
against the original project to publish only that candidate's result and release
the temporary snapshot. Do not run `bug_summary.py` or re-report static
findings from the baseline.

### Ordinary analysis through verification

Without `--resume` or `--validate`, ordinary `dispatch` automatically continues
a compatible checkpoint; no manual flag is required.

If inspection returns `noop`, report a user-visible no-op status and its
baseline commit, then finish. Do not run `codegraph.py status` or dispatch a
worktree.

Only when inspection returns `full` or `incremental`, inspect CodeGraph:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/codegraph.py" status --project "$PROJECT"
```

If it is available, include the internal `--codegraph` option below and rebuild
`$PROJECT/.codegraph/` automatically. Proceed directly. If it is
not available, do not install software; dispatch without `--codegraph`, use
`agent-static`, and record the fallback reason. A selected CodeGraph rebuild
failure fails the run; do not silently change backend.

After determining availability, run exactly one stateful dispatch command:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/orchestrate.py" dispatch \
  --project "$PROJECT" \
  --note "$CHANGE_NOTE" \
  [--submodule "$PATH"]... \
  [--knowledge "$FILE"]... \
  [--extra-edge "$FILE_OR_DIR"] [--one-phase] [--codegraph] \
  [--incremental "$INTENT_FILE"] [--all-bugs | --no-all-bugs]
```

The bracketed terms are placeholders, not literal shell text: omit an option
when absent.  For example, `review checkout changes --submodule backend
--knowledge payments.md` must dispatch with note `review checkout changes`,
`--submodule backend`, and `--knowledge payments.md` as distinct arguments.

`dispatch` should return the inspected non-noop mode. Retain its current-analysis state, emit
the required `Started` status from
[progress-reporting.md](../../references/progress-reporting.md), and execute only the selected
pipeline. If `--codegraph` was selected, rebuild its generated index while the
run lock is held before extraction or graph construction:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/codegraph.py" init --rebuild --project "$PROJECT"
```

For every non-noop dispatch, replace `$PROJECT` for every subsequent command
with the `project` path returned by `dispatch`. It is a temporary detached Git
worktree at a private snapshot commit; the user's original worktree may be
edited or committed independently. Each gate checkpoints into the original
project. `pipeline.py complete` alone publishes `fm_agent/`, promotes the Git
baseline, and removes the temporary worktree. Failure preserves the durable
checkpoint even when the temporary worktree disappears.

After a CodeGraph rebuild and before extraction, export its normalized function
and edge data into Skill control state. Supply the same file to both
`executor.py extract` (for authoritative function spans) and `executor.py graph`:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/codegraph.py" export --project "$PROJECT" \
  --output "$PROJECT/fm_agent_skill/control/codegraph_export.json"
```

For a full or incremental run, drive all phase transitions through
`phase_driver.py`; do not manually call `pipeline.py phase-start` or
`phase-complete`. It starts only the current phase, creates the mandatory Phase
Plan ticket, seals every passed gate, and writes the durable progress state:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/phase_driver.py" next \
  --project "$PROJECT" --limit <HOST_SLOTS>
```

On `run_deterministic`, call the same command with `execute`; on
`dispatch_workers`, launch exactly the returned tickets, submit receipts, then
call `next` again. On `validation_ready_to_publish`, run its returned
`orchestrate.py validate-complete` command against the original project; never
promote targeted validation through full-analysis `pipeline.py complete`.
Every job carries its semantic phase, but `current_phase`
enforces phase ordering. Do not plan or launch verification until the
specification gate has passed; incremental verification additionally requires
all contract-update and reconciliation frontiers to converge. Never let a
Worker mutate scheduler state.

Give a worker only its dispatch-ticket inputs and direct evidence. It writes
full evidence to its assigned output and returns a ≤4 KiB JSON receipt with
matching `job_id`, `status`, the exact manifest `required_outputs`, optional
verdict/counts, and one-sentence summary. After
joining the jobs required by a phase, call
`scheduler.py phase-receipt --project "$PROJECT" --phase "$PHASE"`; use that
small receipt as the normal fan-in. Read detailed worker artifacts only for
listed escalations (`MISMATCH`, `DEPENDENCY_RISK`, `INCONCLUSIVE`, `ERROR`, or
failure), then call the phase driver again; it writes the phase receipt and
seals the gate automatically. A failed gate means do not enter the next phase. On every exception, tool failure, or user-requested stop, run
`pipeline.py fail`; when the current phase is still running this records an
`interrupted` resumable state, while an already recorded failed phase remains
terminal. It releases its owned lock while preserving artifacts and the active
analysis state. `pipeline.py complete` likewise releases its owned lock.
Report the last completed phase and the phase that did not finish.

When `pipeline.py phase-start` begins `phase_cleanup` in a `full` run, it
automatically clears only old derived artifacts; it never removes business
source or the current `fm_agent/phases.json`. Do not bypass this phase.

## Full and incremental execution

Read [stage-gates.md](../../references/stage-gates.md) before starting. Then use
[full-pipeline.md](../../references/full-pipeline.md) or
[incremental-pipeline.md](../../references/incremental-pipeline.md) according
to dispatch. Use [artifact-contract.md](../../references/artifact-contract.md)
whenever writing an artifact.

For specification work, read [specification-rules.md](../../references/specification-rules.md).
For verification, read [hoare-reasoning.md](../../references/hoare-reasoning.md).
For every `MISMATCH`, read [bug-validation.md](../../references/bug-validation.md).

Every ticket identifies one canonical Worker contract. Claude may invoke its
registered Worker by the canonical name. Codex must invoke a **generic
subagent** using the ticket's `host_invocation` object: it receives the
immutable `worker_definition`, exact inputs, and assigned paths. It must read
the ticket and definition completely, without paraphrasing either contract.
Pass each worker the project path, job id, exact inputs, assigned
outputs, and required reference files. A worker must return its concise JSON
receipt; workers cannot spawn other workers. The Coordinator is the only
writer of `fm_agent_skill/jobs/`, phase receipts, and all other control state.

Immediately after starting the full `specification` phase, or the incremental
`update_specs` phase before any domain/spec Worker, materialize the immutable
knowledge inputs deterministically:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/knowledge.py" materialize --project "$PROJECT"
```

If this rejects a changed or missing knowledge file, fail the phase. Workers
may cite user requirements only through the resulting manifest-bound copies.
Verify and Bug preparation tickets include these copied requirements and permitted
caller evidence. An invalid or unclear witness domain is a named gap; never
invent a negative output, substitute an unrelated witness or weaken Q.

On resume, if a prior Phase Plan Worker was accepted by an older Skill version
but its `phases.json` does not satisfy the current schema, the pipeline
automatically removes that stale output and requeues only the current
`phase_plan` job. Do not hand-edit the plan or mark the old job successful.

The driver calls this deterministic planner for its current phase; the same
command is available for explicit recovery:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/job_planner.py" \
  --project "$PROJECT" --phase "$PHASE"
```

For full analysis, the driver plans `specification`, then `verification`, then
`bug_validation` only after each preceding gate succeeds. Full specification
registers every scoped function with caller-first dependencies and adaptive
batches. No verification or Bug Validator work is created from a partial prior
phase. Never manufacture semantic manifests.

For incremental `select_scope` and `update_specs`, repeated driver calls create
only the next module/file selector or top-down review/reconciliation frontier.
Accepted plans are applied serially; actual native pair differences determine
invalidation and propagation. A relevant unchanged pair keeps its qualified
proof. The driver sets `update_complete` only after every frontier settles, then
plans `verify_affected`. Read [incremental-pipeline.md](../../references/incremental-pipeline.md).

The driver also calls `semantic_executor.py prepare` for its current semantic
phase. Explicit planning/preparation are idempotent recovery entry points:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/semantic_executor.py" prepare \
  --project "$PROJECT" --phase "$PHASE"
```

Preparation removes only unassigned verification JSON from the private
snapshot. It never derives a semantic verdict: every planned verification job,
including an `unavailable` contract, must be dispatched to the registered
FM-Agent reasoner Worker. A zero `worker_jobs_remaining` is valid only when all
planned artifacts already have current, schema-valid results.

List ready work in the current durable DAG in a host-sized bounded group. This
does not lease any ticket:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/durable_executor.py" next \
  --project "$PROJECT" --limit <HOST_SLOTS>
```

For each returned `claim_worker` candidate, claim exactly that job immediately
before launching it:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/durable_executor.py" claim \
  --project "$PROJECT" --job-id "$JOB_ID"
```

The claim returns a compact reference to the immutable Worker ticket, which
contains the Worker-definition hash, job manifest, allowed read paths, exact
write paths, and a `host_invocation` object. Claude
uses `registered_worker`; Codex uses `generic_subagent` through the exact
`host_invocation.native_launch_tool`—normally
`collaboration.spawn_agent`—and passes its fixed `developer_instruction`
unchanged, with `native_launch_arguments` (`fork_turns="none"`). Spec and Verify
always start independently. Only a returned Bug execution ticket may use
`host_invocation.native_followup_tool` (`collaboration.followup_task`) on its
matching isolated preparation Worker after validated preparation. Check the
identical project/job/candidate/attempt/input hash and that the context received
no parent history, tests, answers or unrelated task messages. If the matching
context or followup tool is unavailable, use the fresh launch metadata. Supply
only the complete ticket, immutable definition and permitted evidence; never
reuse another job, candidate or attempt. For Codex, use a distinct task name
derived from each `job_id`,
claim it, then launch its returned ticket in parallel. The lack of a named-plugin Worker
registry is not evidence that native subagents are unavailable. Never paste
or paraphrase the contract, ask an Agent to read the job plan, generate a
Workflow script, or launch more workers than returned tickets.

If a fresh native Worker cannot be launched, preserve the ticket as blocked.
Do not substitute parent semantic execution, inherited context, or a nested CLI.
If the turn ends after a submitted ticket, preserve the durable state and report the
exact next `phase_driver.py next` action as **incomplete**, never as an
analysis result. The next ordinary FM-Agent request resumes the same job set.

Replace `<HOST_SLOTS>` with a positive integer no larger than the host's
currently available native subagent slots or the configured phase cap.
The default global cap is 16 (`max_active_subagents`); each phase type has
its own concurrency limit: specification batches 8, verification 12, Bug
Validation 4, incremental plans 4, and all other workers 1 each. Use the
tightest applicable bound: for specification, `min(<available subagents>,
8)`, and for Bug Validation, `min(<available subagents>, 4)`. It is never
an error to use a smaller number when fewer host slots are free.

Submit semantic receipts only through:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/semantic_executor.py" submit \
  --project "$PROJECT" --job-id "$JOB_ID" --receipt-json "$RECEIPT_JSON"
```

An invalid artifact or receipt returns `retry_required`; call
`semantic_executor.py retry --job-id "$JOB_ID"` before obtaining a new ticket.
Report a timeout or tool failure through `semantic_executor.py fail`; process
Bug Validator actions through its executor below. After every normal-analysis completion call `phase_driver.py next` immediately:
it applies accepted incremental plans and creates the next frontier before
refilling the free slot. On-demand validation uses `durable_executor.py next`. A checkpoint
is only a durable write; it is never a normal reason to end an analysis.
Continue the loop until the DAG converges, then finish each phase with its
scheduler receipt; only DAG convergence plus all gates permits finalization.
Never end because a phase is large, a queue is nonempty, a Worker is slow, or
the Coordinator estimates low context. If the host itself forces a hand-off,
the next ordinary Skill invocation automatically reclaims the compatible
checkpoint; do not ask the user to supply `--resume`.

For each specification job, follow FM-Agent's intended-behavior process. First
derive condition B from domain role, public interface, callers, paired APIs,
types, and cross-function invariants; then inspect the body as implementation
observation A. Generated domain context guides inference but is not quoted
evidence. Do not read test files. Require the Worker to emit original FM-Agent's
native three-field spec (`signature`, `pre_condition`, `post_condition`) plus
native callee info. The scheduler converts harmless legacy/identity fields at
the boundary; it does not ask an Agent to repair metadata that the A→B reasoner
never consumes. Every valid native B proceeds to A→B Verification.

For incremental planning, give `fm-agent-skill:fm-incremental-spec-plan-worker` exactly one
assigned output: `fm_agent_skill/worker_reports/<job-id>.json`. It writes the
full update plan there and returns only its receipt naming `plan_path`. After
validation, serially apply that path before scheduling caller reconciliation.
Do not let two active workers write the same artifact or report path.

After each selector record is validated, merge it only through:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/incremental.py" merge-selection \
  --project "$PROJECT" --record "$SELECTOR_OUTPUT" --reason caller-propagation
```

Use `callee-propagation` or `spec-change` when that is the actual reason. Apply
an accepted incremental-plan report only through:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/incremental.py" apply-plan \
  --project "$PROJECT" --plan "$PLAN_PATH"
```

When an Agent call fails, classify it before scheduling anything downstream.
`execution` (timeout, rate limit, tool crash), `output` (missing or invalid
artifact), and `interrupted` are retryable. For specification and verification,
use `semantic_executor.py fail/retry`; for other jobs use `scheduler.py
fail/retry`. Retain the same job id and stop at configured
`retries`. For a spec layer with any newly valid sidecar, retry remaining
batches immediately through completion events. A retried
spec batch uses the ticket's `repair_artifacts`, `preserve_artifacts`, and
`validation_message`: preserve valid pairs and repair every invalid pair in one
pass. Extra fields are removed deterministically; only missing/empty native
fields, malformed JSON, or invalid callee entries require another Agent call.
Never restart all specification
jobs because one batch failed. A verification-level failure is a valid `ERROR` result, not a retry;
retry only when the Agent or result artifact itself failed. In default
`agent-executed` mode, a Bug Validator job uses preparation and execution passes;
optional `adapter` mode uses the Coordinator-owned dynamic runner after
preparation. Reports and canonical receipts are generated locally from validated
immutable execution and accepted history. Up to four Bug Validator
jobs may run concurrently, but each uses only its own attempt-local workspace
and cache. Its runtime failures retry up to five attempts by default. A
completed `not_reproduced` or ambiguous `inconclusive` result is not a runtime
failure:
requeue its same job immediately until it has three completed negative probes
by default, preserving each probe in the result's `attempts` array. Use a distinct
lawful witness/trigger within the candidate claim for a retry or fix the actual
execution error. Exact-input claims remain limited to that input and schedule.
Valid unsupported evidence finishes inconclusive on its first attempt; repeating
an identical missing-runtime probe adds no evidence. A `confirmed` result finishes
immediately. Every new Bug Validator job must
assign exactly one `fm_agent/bug_validation/*.result.json` required output;
each completion appends the current attempt with the receipt classification.
`input`, `semantic`, and `cancelled`
failures are terminal: leave dependents unscheduled and call `pipeline.py fail`.
On resume call `scheduler.py recover` before `scheduler.py ready`; it retains a
stale running job only if current outputs validate, otherwise requeues it in
place when attempts remain.

During `call_graph` or `rebuild_graph`, write one native top-down layer artifact
for each phase in `fm_agent/phases.json`: `phase_01_topdown_layers.json`, then
`phase_02_topdown_layers.json`, and so on. A layer entry must retain its
original repository-relative `source_file`, so it can be checked against its
phase. Do not merge phases unless `--one-phase` was selected. For CodeGraph,
call `executor.py graph` with the exported control file; it records `exact`
only after mapping exported nodes and edges to current extracted artifacts.
Without that file, dispatch `fm-agent-skill:fm-agent-static-edge-worker` first. It writes a
candidate below `fm_agent/`; validate and promote it, then rerun graph:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/executor.py" record-agent-edges \
  --project "$PROJECT" --edges-file "$PROJECT/fm_agent/agent_static_edges_candidate.json"
<python3> "$FM_AGENT_SKILL_ROOT/scripts/executor.py" graph --project "$PROJECT"
```

This records `agent-static/best-effort` and makes only validated edges available
to layer construction and incremental propagation.

Immediately after `fm-agent-skill:fm-phase-plan-worker` returns, normalize and validate its
output before completing `project_understanding` or `refresh_plan`:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/executor.py" normalize-phases \
  --project "$PROJECT"
```

The normalized file must use `modules[].source_files` and `depends_on_phases`.
Test paths are excluded from every analysis stage, and no pseudo-function is
created for a declaration-only header.

Build the Skill control index after extraction:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/executor.py" extract --project "$PROJECT" \
  [--codegraph-export "$PROJECT/fm_agent_skill/control/codegraph_export.json"]
```

Build native phase-layer artifacts after a valid `phases.json`:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/executor.py" graph --project "$PROJECT" \
  [--codegraph-export "$PROJECT/fm_agent_skill/control/codegraph_export.json"]
```

Write `MISMATCH` only for a function's own specification violation. If the
function is affected solely by a mismatching callee, write `DEPENDENCY_RISK`
with the affected callee IDs and do not send it to Bug Validator. Require the
Verification Worker to derive actual postcondition A and return the exact
schema-v3 result envelope from `artifact-contract.md`. A `MISMATCH` without a
normative or inferred B, a concrete counterexample, non-empty reason, and an
exact offending source quote is invalid: retry it and never schedule it for Bug
Validator. Do not complete Verification when fewer than half the selected
functions have an independent contract, fewer than half reach MATCH/MISMATCH,
or any result is `ERROR`; the stage gate reports `insufficient_specification` or
`verification_incomplete`. In default `agent-executed` mode, do **not** call
`probe_runner.py detect`. It is a fixed-argv restricted-adapter detector and a
C++ Makefile project correctly reports no CMake adapter even when `cmake` is
installed. The named Bug Validator Worker must instead select and record the
real project toolchain in its attempt-local workspace, as original FM-Agent
does. Run `probe_runner.py detect` only when configuration explicitly selects
`bug_validation_execution: adapter`.

For every Bug Validator job, use the host-coordinated deterministic state
machine; do not manually sequence its preparation, execution, report, or
summary scripts. A manifest must include `input.bug_id` and `input.mode`.
Semantic phases are strictly ordered: do not plan or start Verification until
the Specification gate succeeds, and do not plan or start Bug Validation until
the Verification gate succeeds. Partial downstream artifacts are retained for
diagnostics but never constitute permission to advance the pipeline.
`durable_executor.py claim` atomically starts each admitted Bug Validator after
`next` lists it, then returns exactly one next action; do not call
`bug_validation_executor.py start` again for that ticket. On `host_worker`, invoke only the named
`fm-agent-skill:fm-bug-validate-worker` pass through Codex/Claude's native subagent mechanism.
Pass the returned `job_id`, `attempt`, allowed paths, and pass name to that
Worker; do not let it reconstruct them from a prior attempt. After preparation,
call `next`. In default `agent-executed` mode, process the returned `execution`
Worker pass, then call `submit-agent-execution`; the Worker must have written
its immutable `reproduction_result.json`. In optional `adapter` mode,
`run_dynamic` instead requires `run-dynamic`. The executor validates the immutable
execution and accepted history, generates the assigned report, and submits the
canonical scheduler receipt locally. It does not request another Worker.
Process one
returned action at a time: a report path alone is never evidence that an
attempt finished. Runtime errors requeue through the same state machine;
terminal phase summaries are written by it after all Bug Validator jobs finish.
`agent-executed` allows the Worker to choose project-scoped commands in the
FM-Agent compatibility model. Up to four Bug Validator jobs run concurrently by
default; each Worker must use only its assigned attempt-local workspace and
cache, never a project-root build output. `build_result.json` can never confirm or reject a defect. Read
[bug-validation.md](../../references/bug-validation.md) for the full contract.

Expected lifecycle counts fall from three to two model turns per attempt and
from three to one native context starts when safe continuation is available
(otherwise two). These counts provide no measured wall-clock guarantee and do not establish
completion of any repository audit.

## Automatic Bug Validation

### Default: validate every direct MISMATCH

Bug Validation runs automatically after the verification gate (stage 8 for a
full run; stage 9 for an incremental run). The Coordinator must run
`job_planner.py --phase bug_validation` once, then dispatch one dynamic Worker
job for every current direct candidate, each carrying separate candidate and function IDs. A candidate is not reported as
confirmed until its public-entry probe has completed with matching evidence.
When there are no candidates, the planner records an empty plan and the phase
completes without Workers.

Do not call `pipeline.py complete` until every Bug Validation job has
converged, the Bug Validation gate has passed, and the `finalize` gate has
completed.

### On-demand Bug Validation via --validate

When the user supplies `--validate FUNCTION_OR_CANDIDATE_ID`, resolve exactly
one existing MISMATCH candidate, then rerun Bug Validation **only** for that
candidate, preserving
accepted results for other candidates on the same baseline. It must still
follow the full state-machine loop because a single function can require
multiple attempts:

1. Call `durable_executor.py next --limit 1`, claim the returned descriptor,
   launch its Worker pass, and submit the receipt.
2. Advance through exactly the returned executor action — `host_worker`,
   `wait_for_completion_event`, `submit_agent_execution`, or
   `scheduler_retry` — and immediately call `next` again.
3. Continue until the executor returns `dag_converged` for that job or an
   explicit exhausted-job failure.
4. Once the assigned candidate job succeeds with its accepted receipt, call
   `orchestrate.py validate-complete` against the original project. Do not use
   full-analysis `pipeline.py complete` or a full-scope Bug Validation gate for
   this targeted publication.

A single-function validation retains the bounded runtime and completed-negative
budgets. If the host reaches a
context or tool-call limit mid-validation, checkpoint the durable state and
let the next ordinary run or explicit `--resume` continue that exact job id
and attempt.

### Coordinator non-termination guard (all active phases)

When any analysis phase is active, the Coordinator must treat every
non-terminal executor response as a continuation request. This applies to
specification, verification, and Bug Validation (including legacy batched and
`--validate` jobs):

- `host_worker`, `wait_for_completion_event`, `scheduler_retry`, and
  `submit_agent_execution` are **not** terminal responses;
- a report file, a confirmed subset, or a static `inconclusive` explanation is
  not evidence that a job finished;
- never stop because the analysis is taking a long time or because one batch
  has completed.

After each response, persist any required Worker output, immediately call the
executor again, and continue until `dag_converged` or an explicit
exhausted-job failure.  If the host is approaching a context or execution
limit, do not summarize: leave the durable state intact and return the exact
continuation action so the next Coordinator turn can continue the same run.

If the host safety classifier or model router reports temporary unavailability,
do not launch the same Worker/attempt again and do not mark it failed. Preserve
the durable ticket, wait or hand off to a later Coordinator turn, then resume
that exact `job_id` and `attempt`.

Do not install a Stop hook or launch a nested host CLI for continuation. The
durable checkpoint is the sole continuation mechanism: a later ordinary run
automatically resumes compatible work, and an explicit `--resume` request
continues the saved analysis. If a turn must end before convergence, preserve
the exact next action and tell the user how to resume it.

### Bug Validation loop (single or legacy batch)

When Bug Validation is active, remain in this loop:

1. Call `durable_executor.py next`, claim and launch every returned descriptor
   (`claim_worker`), and wait for every launched Worker
   receipt.
2. Advance each job through exactly the returned executor action, submit its
   receipt, and immediately call `next` to fill each available slot.
3. If it returns `wait_for_completion_event`, wait for an existing Worker and
   call `next` after its completion. Do not issue another analysis report.
4. Only on `dag_converged`, write `scheduler.py phase-receipt --phase
   bug_validation`; call `pipeline.py phase-complete` when `gate_ready`.
5. If a Worker lacks a usable toolchain, it must still complete its own job
   by recording valid `unsupported/inconclusive` evidence and a receipt.

Before reading Bug Validator reports or calling Finalize after an active Bug
Validation run, call `durable_executor.py barrier --project "$PROJECT"`.
Only `dag_converged: true` permits summary generation.
`wait_for_completion_event` means the Coordinator must wait or continue from
the exact pending tickets; `phase_failed` means the phase gate failed and
must be reported as incomplete.

Calling `pipeline.py complete`, reporting any bug list, or claiming the
analysis has concluded while Scheduler has any `queued`, `running`, or
`retryable` Bug Validator job is a protocol violation.

### Terminal report and findings

Immediately before any terminal user report, run `terminal_report.py --project`
on the original user worktree.  Generate the response only from its structured
output; never supplement its findings.  If `official_result_available` is false,
report only the incomplete state and reason.

Keep `reasoning.counts/gaps`, dynamic counts and `business_coverage` separate.
Missing or invalid business coverage makes `audit_status` incomplete; unresolved
reasoning or business rows remain visible as `completed_with_gaps`. A saved
report cannot replace the current accepted scheduler receipt and execution
evidence. Missing, empty, unreadable or unfinished scheduler authority is
unavailable even when a previous completion file exists.

A function may appear under **confirmed bugs** only when its direct `MISMATCH`
has a `bug_validation/*.result.json` whose status is `confirmed` and whose
latest attempt names matching dynamic evidence.  A function with a schema-v3
Verification `MISMATCH` but no Bug Validation result is a **static finding**
(`confirmation_status: static_finding`) — it carries a concrete counterexample
and exact source quote, but has not been dynamically reproduced.  Report static
findings and confirmed bugs in separate sections; never relabel a static finding
as confirmed.  Never relabel specification text, implementation observations,
source comments, benchmark manifests, or host suspicions as discovered bugs.

If any phase exhausts its retries or fails its gate, the FM-Agent analysis is
incomplete. Record `phase-fail`, call `pipeline.py fail`, and stop the analysis
workflow. Do not switch to direct source auditing, ad-hoc bug hunting, manual
test execution, or an alternative report in the same run. The final response for
a failed run contains only the completed phase, failed phase, exact
scheduler/gate reason, and retained automatic-continuation location. `--resume`
is optional diagnostic syntax, not a required user recovery step.
