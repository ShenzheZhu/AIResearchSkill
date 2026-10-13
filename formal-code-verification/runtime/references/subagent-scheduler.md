# Host subagent scheduler

This scheduler maps each original FM-Agent semantic LLM/OpenCode worker to one
canonical Worker contract. Claude invokes the registered name; Codex invokes a
generic subagent using the ticketed definition. It never starts
or imports the original FM-Agent. The Coordinator alone owns `fm_agent_skill/`
control state, phase transitions, lock heartbeats, and user-visible status.

## Job lifecycle

At the start of specification, verification, or Bug Validation, the
phase driver calls `job_planner.py` for the current phase. Full semantic phases
plan their complete scope; incremental selection and updates plan the next
selector or caller-first review/reconciliation frontier after accepted changes. The Coordinator does not hand-author semantic manifests or bypass the deterministic frontier.
The planner rejects any phase other than the active earliest incomplete phase;
Verification and Bug Validation cannot be seeded from partial downstream
artifacts.
Then obtain `durable_executor.py next`. Claim one returned descriptor through
`durable_executor.py claim` immediately before launching its native Worker.
The claim atomically calls the scheduler admission point and creates the exact
dispatch ticket. Never launch a Worker merely because it was listed as ready.
After each receipt, call the phase driver again so accepted incremental plans
are applied and new frontiers are queued before a phase can finish.

For `specification`, `verification`, `verify_affected`, `select_scope`, and `update_specs`, the Coordinator
must use `semantic_executor.py prepare/dispatch/submit` instead of calling those
scheduler transitions directly. The executor removes only unassigned, unqualified result files and issues an
exact dispatch ticket after the atomic lease claim. It never
derives a semantic verdict or skips an `unavailable` contract; every pending
verification job reaches the original FM-Agent-style reasoner. Never use a
generated JavaScript/Dynamic Workflow for these jobs, ask an Agent to parse the
plan, or reproduce a Worker prompt in workflow source.

The worker writes detailed evidence only to its assigned artifact or, for an
incremental plan, to `fm_agent_skill/worker_reports/<job-id>.json`. Its final
response is a JSON receipt of at most 4 KiB with `job_id`, `status`, output
paths, counts, an optional verdict, and at most a one-sentence summary. The
receipt `outputs` must exactly equal the job's `required_outputs`. The
Coordinator passes planned-phase receipts to `semantic_executor.py submit` and
other receipts to `scheduler.py complete`; it does not paste
worker reasoning or source excerpts into its own context. Every new
`verify_function` job owns exactly one extracted artifact and its matching
result path. `complete` validates the schema-v3 A→B result immediately; a bare
or weakly evidenced `MISMATCH` becomes an output retry and cannot enter Bug
Validator. Workers never write
job manifests, phase receipts, locks, or other control state.

Retain the same job id for retries. `execution`, `output`, and `interrupted`
failures use `scheduler.py fail`; if retryable, call `scheduler.py retry` under
the configured retry policy. For a specification layer, retry
remaining batches immediately when any paired sidecar became valid; otherwise
wait 10 seconds. The next deterministic ticket carries `repair_artifacts`,
`preserve_artifacts`, and the exact validation message. Repair every rejected
pair together and never rewrite a preserved pair. Harmless extra fields are
converted to the native FM-Agent schema before validation; missing native
fields remain an `output` failure and are not a reason to abandon
other batches or bypass the phase. `input`, `semantic`, and `cancelled` are
terminal. A semantic verification error is recorded as `ERROR`, but the
Verification gate cannot create an official baseline while any ERROR remains.
A Bug Validator job has preparation and execution passes in the default
`agent-executed` mode; the optional `adapter` mode retains Coordinator-owned
dynamic execution. Reports and canonical receipts are generated locally from
validated immutable execution and accepted history. Spec and Verify always
start fresh independently. After preparation validation, Bug execution may
continue the matching isolated preparation Worker through
`collaboration.followup_task` for identical project/job/candidate/attempt/input
hash; otherwise launch fresh. No context crosses jobs or inherits parent history.
Runtime failures retry up to five attempts by default. A completed negative
Bug Validator result requeues the same job immediately twice by default,
yielding three preserved probes; use a distinct lawful witness/trigger for each
retry or fix the actual execution error. A confirmation finishes immediately,
and valid unsupported evidence finishes inconclusive on its first attempt.
On resume, call
`scheduler.py recover` before
`scheduler.py ready`; valid stale outputs finish their job, invalid stale jobs
requeue in place when attempts remain.

SQLite WAL at `fm_agent_skill/checkpoint/state.db` is authoritative. Compact
job JSON files are Worker-readable mirrors and legacy diagnostics, never the
ready-query index.
Concurrent jobs cannot share an output path. After joining a phase, the
Coordinator runs `scheduler.py phase-receipt --phase <phase>`; it writes the
small aggregate record at `fm_agent_skill/control/phase_receipts/<phase>.json`.
The Coordinator reads that receipt, then reads detailed artifacts only for an
escalation (`MISMATCH`, `DEPENDENCY_RISK`, `INCONCLUSIVE`, `ERROR`, or worker
failure) before its normal gate.

## Worker mapping

| Original FM-Agent semantic worker | Skill worker | Dispatch rule |
| --- | --- | --- |
| phase generation | `fm-agent-skill:fm-phase-plan-worker` | one job, then gate |
| phase post-processing | `fm-agent-skill:fm-phase-refine-worker` | only when needed |
| domain context generation | `fm-agent-skill:fm-domain-context-worker` | after valid phases |
| static edge resolution without CodeGraph | `fm-agent-skill:fm-agent-static-edge-worker` | one bounded candidate, then deterministic validation |
| specification batch generation | `fm-agent-skill:fm-spec-batch-worker` | same layer batches in parallel |
| function Hoare reasoner | `fm-agent-skill:fm-verify-function-worker` | one compatibility function or adaptive batch; each function writes independent A→B output |
| Bug Validator | `fm-agent-skill:fm-bug-validate-worker` | one direct candidate ID per run-qualified job/probe directory |
| incremental module selection | `fm-agent-skill:fm-select-relevant-modules-worker` | one job |
| incremental file selection | `fm-agent-skill:fm-select-relevant-files-worker` | after module selection |
| incremental spec update planning | `fm-agent-skill:fm-incremental-spec-plan-worker` | parallel read-only plans |
| caller reconciliation | `fm-agent-skill:fm-reconcile-caller-info-worker` | one caller per job |

## Concurrency

The default bounded profile is deliberately conservative for a context-limited
Coordinator:

| Work type | Maximum active jobs |
| --- | ---: |
| all host subagents | 16 |
| `spec_batch` | 8 |
| `verify_function` | 12 |
| `bug_validate` | 4 |
| `incremental_spec_plan` | 4 |
| phase/refine/domain/edge/select/reconcile workers | 1 each |

The corresponding configuration keys are `max_active_subagents`,
`spec_concurrency`, `verify_concurrency`, `bug_validation_concurrency`, and
`read_only_plan_concurrency`. They are operational limits, not semantic inputs:
changing them does not invalidate an otherwise valid Git baseline. Parallel Bug
Validator Workers may read the same snapshot but must use only their own
attempt-local workspace and caches; they cannot share project-root build
outputs. Use `scheduler.py capacity` to inspect leases. Phases are aggregate
gates and ordering boundaries: complete specification unlocks verification;
complete verification unlocks candidate validation. Incremental verification
additionally requires `update_complete` after every actual sidecar difference
and caller reconciliation has settled. Stable reviewed pairs retain original
proof origins, and changed caller expectations enqueue only relevant direct
callees. Finalization waits for DAG convergence. Within a capacity window, admission is deterministic and
fair: ready jobs are selected in ascending job-id order, and later jobs are
admitted on the next call after earlier jobs finish or release capacity. The
host supplies subagent calls; the Skill enforces artifact contracts on Claude
Code and Codex.
