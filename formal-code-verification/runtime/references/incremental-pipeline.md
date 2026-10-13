# Incremental pipeline

Enter only with a compatible completed baseline and changed supported source or
a new captured developer goal. `--incremental INTENT.md` supplies a non-empty
Markdown goal; `--note` adds a note. A goal-only run can discover necessary work
omitted from unchanged functions. The captured ticket `developer_intent` is
normative and overrides the older knowledge clauses it changes. Generated
context and Git summaries remain observational.

Drive every phase through `phase_driver.py next/execute`, using the returned
analysis checkout. The driver owns deterministic actions and planning; the host
claims and starts returned native Workers with `fork_turns="none"` and submits
their exact receipts. Spec and Verify have independent fresh contexts. Only a
Bug execution ticket may continue its matching isolated preparation Worker
after validation, for the same project/job/candidate/attempt/input hash; otherwise
start fresh. Do not manufacture selector or contract-update jobs.

1. `validate_baseline`: `executor.py validate-baseline` checks the original
   inventory, specifications, results, accepted candidate evidence, Git ref and
   pure configuration fingerprint. It writes the snapshot-bound
   `control/baseline_validation.json` receipt before later phases replace that
   inventory. Resume validates this sealed receipt and exact baseline record.
2. `refresh_plan`: the Phase Plan Worker refreshes the scoped source/module
   plan. Normalization and its gate retain `modules[].source_files` and phase
   dependencies. Incremental cleanup removes transient selectors, decisions,
   phase receipts and update records; it preserves original jobs, accepted
   receipts, reports, private probes and their originating run identities.
3. `preserve_specs`: capture the complete old inventory, graph and native pairs.
   `retained_evidence.json` records unchanged-file proof bytes, source blobs,
   exact spec/info and accepted Bug Validation origins. Reused evidence keeps
   its original verification/execution snapshot, including recursive reuse.
4. `diff`: freshly extract the requested scope, then compare against the saved
   inventory. Every current function in a changed file is invalidated, even
   when its body bytes are unchanged: imports, constants, types and global state
   can alter its behavior. Deleted functions lose results and cannot be reused.
   This is a conservative file boundary, not exact body-only minimum selection.
5. `rebuild_graph`: rebuild current top-down layers. With CodeGraph, use the same
   validated export for extraction and graph construction. Otherwise a fresh
   static-edge Worker emits the candidate; promote validated edges and retain
   the `agent-static/best-effort` precision label.
6. `select_scope`: seed changed-file/new functions and callers of deleted
   callees. A module Worker considers every assigned module against the goal;
   the file/function Worker narrows selected modules and identifies relevant
   unchanged contracts. Their selected/excluded arrays account for every
   assigned ID. Accepted selections add **review** work; they do not immediately
   invalidate unchanged proofs. `selection_complete` seals the exact current
   included/excluded verification partition.
7. `update_specs`: restore existing native pairs as review inputs, materialize
   immutable knowledge and regenerate observational domain context. Read-only
   specification Workers review caller-first frontiers and write only assigned
   `worker_reports/<job-id>.json` plans. The planner serially applies accepted
   plans, compares actual spec/info changes, and retains applicable unchanged
   pairs exactly. Changed caller expectations enqueue their direct callees;
   changed callee contracts invalidate and reconcile their direct callers.
   Reconciliation owns one caller info file and keeps its original before-pair
   across retries. A stale caller context is reviewed again before convergence.
   Stable contracts stop propagation; do not expand to the entire connected
   graph. `incremental_updated_specs.json` records changed/reviewed artifacts
   and `update_complete` only when all frontiers have settled.
8. `verify_affected`: only after `update_complete`, plan and dispatch current
   verification for changed-file, spec, info or callee-contract affected IDs.
   Never pre-plan or stream verification while any contract/reconciliation can
   still mutate its inputs. Applicable unchanged qualified proofs retain their
   original snapshot. Use `DEPENDENCY_RISK` for a callee-only risk, never invent
   a caller's direct mismatch. Every conclusive result uses schema 3, complete
   A→B reasoning, candidate identities and required loop obligations.
9. `bug_validation`: create one run-qualified job and private probe directory
   per selected direct candidate ID, with both `candidate_id` and actual
   `function_id` in its input. Follow the executor's preparation and execution
   actions; it generates reports and receipts locally from validated immutable
   evidence and accepted history. Valid unsupported evidence ends inconclusive
   on its first attempt; existing runtime and completed-negative budgets remain.
   Only accepted real probe evidence confirms/rejects a
   candidate. Preserve unrelated original evidence; the current summary counts
   qualified current and retained candidate outcomes without double counting.
10. `finalize`: validate all current/reused function artifacts and every accepted
    direct candidate, then save the completed baseline. Store pure configuration
    compatibility separately from the exact evidence-producing run fingerprint.

Explicit CLI selection/plan application accepts only the assigned output of a
succeeded current Worker; resolve receipt paths relative to `--project`.
The phase driver performs these applications automatically. Do not rewrite old
result snapshots, receipts or probes to make retained evidence look current.

## Resume

Continue the same snapshot, goal and reasoning mode at the first incomplete
phase. Do not recompute completed diff/selection/preservation records or widen
scope. Omitted `--all-bugs` inherits the run's saved value; an explicit contrary
`--all-bugs` or `--no-all-bugs` is rejected. Failed gates remain incomplete.
Read [resume-contract.md](resume-contract.md) for recovery and lock ownership.
