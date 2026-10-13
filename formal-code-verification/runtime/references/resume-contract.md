# Resume contract

Resume continues one interrupted `full` or `incremental` analysis. Every
ordinary run is recovery-first: it uses the exact same continuation path when
an active run exists. Explicit `--resume` only changes the fallback policy: it
never creates a new run when recovery is unavailable.

## Eligibility

Require all of the following:

- A live private snapshot with an active Git ref exists, **or** an active Git
  ref and a complete persistent checkpoint exist. The former permits recovery
  before the first phase is sealed; the latter permits rebuilding a lost
  temporary worktree.
- Snapshot commit, fingerprint, saved configuration, plugin source commit,
  Worker execution-contract hash, and state/scheduler schemas match. A Codex
  cachebuster-only plugin version change is recorded for audit but does not
  invalidate resume.
- No unexpired Coordinator lease exists. Require explicit takeover while a
  fresh lease may still represent live work.
- The active record has a valid phase list and first incomplete task.

Do not accept a new note, scope, knowledge, supplemental edges, `one_phase`, or
backend choice. Report every differing field; never silently start a fresh run.

## Worktree reconstruction

If the recorded detached worktree exists, verify its `HEAD` and checkpoint
HEAD. If it is missing, create a new detached worktree at the active ref,
restore `checkpoint/current/fm_agent`, then restore only recovery
`active.json`, `config.json`, `jobs/`, `control/`, and `probes/`. Verify every
manifest and SHA-256 object. Exact restoration applies tombstones, so a deleted
artifact cannot reappear. A missing active ref or complete checkpoint is
non-resumable and must be named explicitly.

## Continuation

The new parent Coordinator automatically reconciles interrupted SQLite jobs
before dispatch. It preserves a valid receipt, marks an invalid in-flight job
retryable, and immediately requeues every retryable job in the current run.
It must never return `wait_for_completion_event` for a retryable job with no
Worker. An identical receipt is idempotent; an old attempt or changed hash is
rejected. Re-enter only the first unfinished task. Do not regenerate a
schema-valid completed spec or rerun an earlier successful phase. Preserve the
saved graph backend.

The source project's `fm_agent_skill/run.json` is a discovery index for both
Codex and Claude: it records the active run, snapshot availability, current
phase, and latest sealed checkpoint. It is not recovery authority;
`checkpoint/`, `refs/fm-agent-skill/active`, and verified snapshot state are.

Only `pipeline.py complete` may promote `refs/fm-agent-skill/baseline` and
publish root `fm_agent/`. Failure releases the Coordinator lease but retains the
active ref and checkpoint for a later turn/session.
