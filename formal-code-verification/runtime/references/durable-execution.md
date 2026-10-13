# Durable execution contract

## Authority and layout

Treat `/tmp/fm-agent-skill-worktree-*/project` only as a disposable detached
execution cache. The Skill first makes a private staging copy, then constructs
this Git snapshot from that copy; after capture, user edits in the source
worktree cannot affect the analysis input. The source project owns the authoritative state at
`fm_agent_skill/checkpoint/`: `state.db` is the SQLite WAL scheduler,
`objects/` is the SHA-256 object store, `current/fm_agent/` is the complete
current FM-Agent mirror, and `current/recovery/` contains only `active.json`,
`config.json`, `jobs/`, `control/`, and `probes/`. Never copy the checkpoint
directory into itself. A source-project `fm_agent/` mirror is published only
from a sealed checkpoint and is always explicitly non-official until finalize.

Every gated transition calls `checkpoint.py`. A successful phase has one
schema-version-2 manifest below `checkpoint/phases/` containing its ordinal,
snapshot commit, input fingerprint, timestamps, produced/preserved objects,
removed tombstones, scheduler receipt, and next phase. Immutable objects are
written before the temporary current mirror, manifest, SQLite transaction,
atomic HEAD, and final phase status. Validate all hashes on recovery. A
half-written checkpoint rolls back to the prior complete database row and
reconstructs `current`; restoration is exact, so tombstoned outputs cannot
reappear.

The sealed manifest (`manifest_sha256`) is the integrity authority, not a
SQLite `complete` flag. Recovery verifies its inventory against every object
and every file in `current/`; a completed database row cannot bypass a missing,
changed, or extra mirror artifact. The phase file and ledger copy must carry
the same sealed manifest hash before acceptance. `state.db` is WAL-backed, so
each checkpoint performs controlled `wal_checkpoint(FULL)` plus fsync of the
main database/WAL after each checkpoint transaction and before success is
accepted. The database is the durable ledger itself, never an untracked copy
inside `current/`.

After each sealed checkpoint, atomically publish a presentation mirror at the
source project's `fm_agent/analysis_status.json`. It is explicitly marked
`in_progress` and `official_result_available=false`; it is useful for
inspection but never an authority for findings or baseline promotion.

On successful finalize, `baseline.json` records a content-addressed manifest
of production sources from the private snapshot. Dynamic validation and no-op
selection compare this manifest with the current worktree, not merely Git
`HEAD`; a baseline created from uncommitted changes remains usable until those
source contents change. A new developer goal can still require incremental
analysis on identical source. Pure configuration compatibility omits the
captured goal, while the exact run fingerprint includes it and `all_bugs` so
old accepted evidence cannot be rebound to the new reasoning run.

Before incremental extraction replaces baseline artifacts, seal
`control/baseline_validation.json` with the analyzed snapshot, pure config
fingerprint and exact saved baseline record. Later resume validates this receipt
and baseline Git ref rather than rereading intentionally replaced old outputs.
`retained_evidence.json` records exact original proof bytes, native pairs, source
blobs and candidate receipts with their actual origin snapshots. Preserve old
jobs/reports/probes through incremental cleanup; only qualified unchanged-file
rows are reused. New plan and candidate IDs include the current run identity.
Verification waits until every contract/reconciliation frontier settles and
`update_complete` is true.

`current/` uses `copy2`, not hard links: a replaceable mirror sharing an inode
with an object could corrupt the supposedly immutable object store.

## Automatic continuation

An ordinary `orchestrate.py dispatch` automatically continues through the
same path as explicit `--resume` whenever an active run exists. A live private
snapshot can continue before its first sealed phase; when that cache is gone,
`refs/fm-agent-skill/active` and a complete checkpoint reconstruct it. In both
cases verify the snapshot, fingerprint, saved configuration (including captured goal and all-bugs mode), runtime version,
and Worker-definition hash, recover interrupted jobs, immediately requeue
retryable jobs, and continue the first unfinished task. If neither a verified
live snapshot nor a ref-plus-complete-checkpoint exists, return the exact
non-recoverable reason; never invent a resume.

Version records distinguish `worker_execution_hash` from `worker_prompt_hash`.
Until a Worker explicitly delimits a stable execution-contract region, both
hashes intentionally cover its whole document and any edit invalidates resume.
The default `worker_prompt_change_policy=invalidate` is conservative. A future
explicit `allow_prompt_only` policy may retain jobs only when execution hashes
still match; it must never waive an execution-contract change.

## SQLite DAG and bounded loop

Use SQLite tables `runs`, `phases`, `jobs`, `job_dependencies`, `leases`,
`attempts`, `artifacts`, `receipts`, and `checkpoints`. Only the Coordinator
calls scheduler mutations. Workers write only assigned artifacts and return a
compact receipt. Claim a job and lease atomically; heartbeat active work;
requeue expired leases. Accept an identical
`job_id/attempt/input_hash/artifact_hash` receipt idempotently. Reject an old
attempt or changed hash. Retry `execution`, `output`, and `interrupted`;
terminate `input`, `semantic`, and `cancelled`.

Use `durable_executor.py next` to list no more than the available bounded
slots; it does not lease them. Claim each selected job immediately before
launching its Worker, submit each completion immediately, and request another action to fill
the free slot. Do not wait for a large batch or sleep. A checkpoint is never a
normal terminal action: keep claiming ready work until the DAG converges. If a
host-enforced hand-off is unavoidable, checkpoint first; the next ordinary
dispatch automatically takes over the compatible durable state. `current_phase` is only
the earliest-incomplete display value; job dependencies decide readiness.
Specification retains caller-first dependencies, each verify job depends on
its own spec job, and Bug Validation is created only for a schema-valid direct
`MISMATCH`. Finalization waits for DAG convergence and all phase gates.

Partition spec and verification work with `worker_target_tokens`,
`worker_max_functions`, and `worker_max_source_bytes`. Verification batches
still write one schema-valid result per function. Preserve valid members of a
partially invalid batch and retry only invalid functions.

## Host boundary

The Skill persists safely across turns and the next ordinary run continues
automatically without requiring `--resume`. It does not install a Stop hook or
launch a nested host CLI. If a host turn ends because of a context, tool-call,
or worker limit, the durable checkpoint remains authoritative and a later
ordinary run or explicit `--resume` reclaims the compatible snapshot.

A host turn ending because of context, tool-call, or worker limits is therefore
an interrupted run, not a phase boundary. The Coordinator must checkpoint the
current durable state before yielding and the next invocation must reclaim the
same snapshot, job IDs, attempts, and leases. It must not treat a partial
worker batch or a report file as phase completion.

## Terminal authority

Before every terminal user answer, run `terminal_report.py --project` against
the original project. Use only its JSON. Do not add a Coordinator-authored bug
list. A schema-valid Verification `MISMATCH` is a candidate; only matching
dynamic evidence can be confirmed; exhausted negative probes are rejected;
missing runtime/evidence is inconclusive. When
`official_result_available=false`, expose no findings list or static audit.
`rejected` means only that the recorded sufficient dynamic attempts did not
reproduce the candidate; it never proves a defect is absent. Preserve the
latest dynamic-evidence reason for every `inconclusive` result.
