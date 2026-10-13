# Artifact contract

All JSON is UTF-8 and atomically replaced. Paths are repository-relative with
forward slashes.

All mutable Skill state lives under `fm_agent_skill/`.

`fm_agent_skill/checkpoint/` is the cross-session authority: SQLite WAL,
SHA-256 objects, phase manifests, atomic HEAD, complete `current/fm_agent/`,
and the explicit `current/recovery/` allowlist. Never copy it recursively.

- `fm_agent/phases.json` uses FM-Agent's phase/module form, including source
  files and inter-phase dependencies. Test sources are excluded from this
  contract and from all analysis inputs.
- `fm_agent/fm_agent_file_list.json` is the sorted current set of extracted
  function-source paths, relative to `extracted_functions/`. Do not list
  metadata sidecars.
- `fm_agent/extracted_functions/` contains immutable function copies. Every
  `<function>.<ext>` has exactly two paired sidecars:
  `<function>.<ext>.spec.json` and `<function>.<ext>.info.json`. Include
  analyzable header-defined functions and constructors as well as implementation
  files.
- `fm_agent/spec_prompts/` contains required specification context:
  `system_prompt.md`, `domain_context/engine_overview.txt`, and one
  `domain_context/phase_XX_types.txt` for every phase. Materialize supplied
  domain knowledge through the deterministic knowledge command below.
  `knowledge.py materialize` owns that directory and binds every copied
  Markdown file to the active input hash and snapshot commit; semantic workers
  must not create or replace these files. Preserve the
  generated caller-first batch prompts and their manifest under
  `batch_prompts_<project>_phaseXX/` so work is resumable.
- `fm_agent/spec_prompts/phase_XX_topdown_layers.json` is one caller-first
  layer file per declared phase, using its zero-padded numeric phase number.
  This is the native call-graph artifact; do not add `fm_agent/call_graph.json`
  or merge phases unless `one_phase` is enabled.
- `fm_agent/logic_verification_results/` has one result per extracted function.
  A verdict is `MATCH`, direct `MISMATCH`, `DEPENDENCY_RISK`, `INCONCLUSIVE`,
  or `ERROR`. `MATCH` and `MISMATCH` compare independently derived actual
  behavior A with the native FM-Agent specification B; implementation behavior
  cannot redefine B.
  Dependency risk records affected callers but is not a direct bug candidate.
- `fm_agent/bug_validation/` is generated only when a direct `MISMATCH` is
  dynamically probed. Each current candidate owns its result JSON and assigned detail report. The
  Coordinator writes a current summary even when the candidate set is empty.
- `fm_agent/version.log`, written after a successful baseline, records the
  commit held by `refs/fm-agent-skill/baseline` for FM-Agent-compatible
  provenance.
  `fm_agent/incremental_updated_specs.json` records the current incremental
  update.
- `fm_agent/select_relevant_modules.md`, `relevant_modules.json`,
  `select_relevant_files_<n>.md`, `relevant_files_<n>.json`,
  `spec_update_<n>.md`, and `spec_update_<n>.json` are latest-run incremental
  work records. Write only records used by the selected scope; remove them
  before a new full or incremental analysis.
- `fm_agent/trace/events.jsonl` records stage and model events. Write full
  prompt/response material below `trace/payloads/` only when full tracing is
  enabled.
- `fm_agent_skill/control/analysis_index.json` is the Skill-owned function
  identity inventory for one snapshot commit. Precision, incremental
  diff/selection,
  `graph_edges.json`, and validated `agent_static_edges.json` are Skill-owned
  control artifacts. Active analysis state, locks, scheduler jobs, build profiles, and probe results also belong in
  `fm_agent_skill/`, never in `fm_agent/`. Only the Coordinator and
  deterministic scripts may write Skill-owned control state.
- `fm_agent_skill/control/job_plans/<phase>.json` is the current-snapshot,
  deterministic full-scope queue manifest. Specification, verification, and
  Bug Validation gates reject a missing, stale, partial, or hand-divergent plan.
- `fm_agent_skill/failure.json` is a small failure receipt copied to the user's
  worktree when an isolated run fails. It never promotes private semantic
  artifacts; it records that no official result exists and where resume state
  was retained.

## Sidecar schemas

`<function>.<ext>.spec.json` uses original FM-Agent's exact format:

```json
{"signature":"...","pre_condition":"...","post_condition":"..."}
```

Derive B from domain, interface, callers, paired APIs, types, and user knowledge
before reading detailed implementation behavior. Oracle markers such as
`BUG:`, `FIXME:`, `TODO:`, seeded bugs, and known defects are rejected inside
the contract. Encode observable error, exception, rejection, and sentinel
behavior inside `post_condition`. The scheduler deterministically converts
legacy/rich objects by retaining only these three valid fields and folding a
legacy `error_behavior` string into `post_condition`, so identity or evidence
metadata cannot force an otherwise valid batch to retry.

`<function>.<ext>.info.json` is exactly `{"callees": [...]}`. Every callee is
an object with string fields `name`, `signature`, `pre_condition`, and
`post_condition`. Use `[]` when there are no in-scope callees.

An extracted function artifact is its unchanged source plus both valid
sidecars. It must be addressable by `source_index.functions[].artifact`.
Sidecars are never functions: exclude them from file lists, source indices, and
stale-artifact checks.

Layer artifact: `{phase, phase_id?, phase_name, source_files, total_layers,
layers}`. `source_files` must match its phase's declared source files. Each
layer function has at least `function_id`, `artifact`, and `source_file`; a
function occurs in one phase-layer artifact only.

Verification result is exactly
`{schema_version,function_id,snapshot_commit,verdict,reasoning,gaps,error,reasoning_complete,candidates,loop_evidence}`
with `schema_version: 3`. Earlier verification formats cannot qualify a new run. `MATCH` and `MISMATCH` require `reasoning` exactly equal to
`{actual_postcondition,spec_postcondition,counterexample,offending_statements,reason}`.
The specification postcondition must equal the sidecar text. `MISMATCH` also
requires a normative or inferred contract, non-empty concrete counterexample string,
reason, and an exact contiguous source quote in `offending_statements`;
`MATCH` requires the same independent contract basis and null
counterexample/offending statements.
`MISMATCH` means a local implementation/spec violation;
`DEPENDENCY_RISK` means a caller is affected by a callee mismatch but has no
independently established local violation and uses
`gaps:{affected_callee_ids,reason}`. `INCONCLUSIVE` uses
`gaps:{missing_evidence,reason}`. `ERROR` carries a non-empty `error`. `MATCH` and `MISMATCH` require `reasoning_complete: true`. Other verdicts
have false completion and empty candidate/loop arrays. A default mismatch records
one direct candidate; `all_bugs` continues through all applicable paths and records
every independent candidate. Each `candidates[]` item is exactly
`{candidate_id,reasoning}`; its ID is `<function_id>::bug-001`, numbered
consecutively. A mismatch's primary reasoning equals its first candidate's
reasoning. Repeated reasoning is not a second independent candidate.

Every parsed loop requires one `loop_evidence` entry with exactly
`{loop_id,invariant,initialization,preservation,normal_exit,abrupt_exits}`.
Each parsed abrupt transfer needs `{exit_id,argument}`. Examine initialization,
preservation and exit obligations; an argument may demonstrate their failure
with a concrete witness. Do not fabricate successful induction to conceal a
mismatch. Missing parser/evidence remains an explicit reasoning gap. These
natural-language arguments are not machine-checked proofs.

Identity and snapshot must match the analyzed run, or the retained-origin
qualification below must establish unchanged applicability.

Finding/bug result uses `schema_version: 2` and is generated locally from
validated immutable execution and accepted history. It records
`{schema_version, bug_id, candidate_id, function_id, snapshot_commit,
confirmation_status, candidate_reasoning, attempts}`. `candidate_reasoning`
preserves the assigned static witness; it is not a record of the input actually
executed. The detail report embeds each execution record separately.
`confirmation_status` is `confirmed`,
`rejected`, or `inconclusive`; it is never inferred from a build result. Each
attempt has `{ordinal, classification, dynamic_evidence}` where classification is `confirmed`,
`not_reproduced`, or `inconclusive` and `dynamic_evidence` is exactly
`{"reproduction_result":"fm_agent_skill/probes/.../reproduction_result.json"}`.
The referred result belongs to the same snapshot and its completed
classification must match. A report can be confirmed only by `CONFIRMED` runtime
evidence; it can be rejected only by executed `NOT CONFIRMED` evidence after the
configured negative attempts, preserving every accepted outcome. Valid
unsupported execution finishes inconclusive after its first accepted attempt;
only completed negative/ambiguous probes continue through their existing budget.
Semantic attempt ordinals are distinct and ordered;
runtime failures may leave ordinal gaps but never justify dropping a prior
accepted outcome. `summary.json` is Coordinator-authored and has
at least `{snapshot_commit, total_candidates, total_confirmed, total_rejected,
total_inconclusive}`; its counts must equal the current candidate-specific accepted jobs. Historical
reports for replaced candidates are not counted.

Every new Bug Validator job assigns exactly one
`fm_agent/bug_validation/*.result.json` output. Its current receipt
classification must equal the classification in the last appended attempt.

`fm_agent_skill/probes/<bug-id>/attempt_<n>/` is immutable and contains the
worker-authored `reproduction.json`, `probe.<ext>`, optional `build_result.json`,
and the recorded `reproduction_result.json`. The contract has schema version 3;
the execution record has version 2. Both carry exact `bug_id`, `candidate_id`,
actual `function_id`, attempt and originating snapshot identities. The reproduction contract
has an approved language adapter, public-entrypoint explanation, fixed markers,
current snapshot commit, and no shell command. In adapter mode, `reproduction_runner.py` executes a fixed command. In
agent-executed mode, an isolated Worker records the actual project-scoped command
sequence. Only its same-project/job/candidate/attempt/input-hash preparation
context may continue after validated preparation; otherwise execution starts
fresh. Accepted receipt identity seals the report and each attempt's probe,
contract, execution record and available build/profile records in the existing
SQLite artifact ledger. Accepted negative retry outcomes are sealed before the
next attempt; changing those bytes invalidates authority.

`fm_agent_skill/active.json` is the sole current-analysis record. It contains
mode, phase status, inputs, fingerprint, timestamps, an immutable
`snapshot_commit`, and resume count; it is overwritten by the next analysis.
The source baseline is the Git ref `refs/fm-agent-skill/baseline`, mirrored by
the latest commit in `fm_agent/version.log`. `baseline.json` stores only the
successful configuration, source-content manifest, originating run fingerprint
and completion provenance.

`fm_agent_skill/jobs/<job-id>.json` mirrors a current host worker's phase,
type, dependencies, permitted/required outputs, attempt count, terminal status,
and a compact worker receipt. SQLite is authoritative; Workers never write these manifests. They are
retained with accepted receipts and referenced evidence after successful
completion. Incremental runs retain older authority without admitting older
jobs into the current DAG; an explicit full reset clears derived analysis state. A receipt is at most 4 KiB and includes matching
`job_id`, non-empty `status`, output paths, optional verdict, and short summary.
Detailed incremental plans are written only to their assigned
`fm_agent_skill/worker_reports/<job-id>.json`, not returned inline.


`fm_agent_skill/control/retained_evidence.json` is exactly
`{schema_version:1,snapshot_commit,functions}`. Each function row records
`artifact`, `source_path`, the originating Git `source_blob`, exact native
`spec` and `info`, `verification_snapshot_commit`, exact UTF-8
`verification_bytes`, and `bug_validations`. A dynamic origin entry is exactly
`{candidate_id,job_id,snapshot_commit,input_fingerprint,result_path}`.
The qualifier checks the unchanged complete source file, applicable sidecars,
exact verification bytes and original candidate-specific accepted receipt.
Original snapshots and evidence bytes are never relabeled as newly executed.
Changed files conservatively invalidate all of their functions; unrelated files
may retain qualified results. Historical reports remain separate from current
accepted candidate paths.

`control/baseline_validation.json` binds the successful initial baseline check
to the new snapshot, pure configuration fingerprint and exact saved baseline
record. Its sealed phase receipt remains the authority after legal incremental
re-extraction replaces the old inventory, including during resume.

`fm_agent_skill/control/phase_receipts/<phase>.json` is Coordinator-generated
and contains phase totals, gate readiness, and escalation job IDs. Verification
receipts additionally include `semantic_coverage` with contract-basis and
verdict counts plus a semantic gate reason. An all-INCONCLUSIVE receipt has
`gate_ready: false`. This is the normal Worker fan-in surface; inspect detailed
outputs only for its listed escalations.
