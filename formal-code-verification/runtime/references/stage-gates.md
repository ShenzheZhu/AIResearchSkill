# Stage gates

| Phase | Inputs | Required output / acceptance | Failure behavior |
| --- | --- | --- | --- |
| project understanding | scope, source inventory | native-style `phases.json` with modules and dependencies | retry; then fail |
| extraction | phases, language extractors | non-empty `extracted_functions/`, Skill control analysis index | no functions/index failure: fail |
| call graph | control analysis index, optional edges | native caller-first layer files and Skill precision record | tool error: fail; fallback must be recorded |
| specification | layers, batch manifest, observational domain context | oracle-free `system_prompt.md`, marked engine/phase context, and every current source's native three-field FM-Agent `.spec.json` plus `.info.json`; intended B is derived before implementation behavior A | deterministic conversion of harmless extra fields, then bounded repair of only invalid pairs |
| verification | ready functions | schema-v3 complete result envelope per current function/snapshot; every pending function runs a Worker; MATCH/MISMATCH require structured A→B reasoning against native spec B, and MISMATCH additionally requires a concrete counterexample plus exact source quote | malformed output retries; any ERROR blocks the gate; fewer than half conclusive outcomes returns `insufficient_specification` |
| bug validation | direct `MISMATCH` results | one candidate-specific accepted dynamic result per current or qualified retained origin, deterministic report/result, and `summary.json`; preparation validates before execution; build-only evidence cannot promote a candidate. An empty plan is required when there are no candidates. | runtime failure and completed-negative budgets remain; valid unsupported evidence finishes inconclusive on its first attempt |

Incremental gates additionally require Skill-control preserved-spec, function-diff,
and inclusion/exclusion records. `pipeline.py phase-complete` invokes
these checks; state cannot advance on a failed gate. Selection must be a
completed, snapshot-bound partition of every known function. Specification
updates must settle all review/reconciliation frontiers before affected
verification can launch or seal. Finalization checks every current or qualified
retained function result and every candidate's accepted evidence. Loop-bearing
conclusive results require all parsed induction/exit obligations, including
explicit failed obligations when they establish a mismatch. Interrupted
incremental resume uses the sealed baseline-validation receipt after the old
inventory has legitimately been replaced.

## Findings classification

| Classification | Source | Meaning |
| --- | --- | --- |
| `static_finding` | Verification `MISMATCH` | High-confidence static identification with concrete counterexample and source quote; not dynamically confirmed |
| `confirmed` | Bug Validation `CONFIRMED` probe | Dynamically reproduced through the public entry point |
| `rejected` | Bug Validation exhausted negative probes | Static candidate not reproduced after sufficient dynamic attempts |
| `inconclusive` | Bug Validation with missing toolchain/evidence | Cannot be confirmed or rejected with available runtime |
