# Full pipeline

Follow the listed order. Start and complete every phase through `pipeline.py`;
the corresponding gate in [stage-gates.md](stage-gates.md) is the acceptance
authority.

1. `preflight`: validate Git, source files, merged settings, and lock ownership.
2. `project_understanding`: dispatch `fm-agent-skill:fm-phase-plan-worker`, then run `executor.py normalize-phases --project "$PROJECT"` before gating native-style `phases.json`. It writes `modules[].source_files` and `depends_on_phases`, rejects missing sources, and excludes test paths from all analysis. Separate headers/types, implementation, and entry points when their dependencies differ: implementation depends on headers/types and CLI/entry points depend on implementation. Name each phase after functions assigned to that phase's source files, not functions that merely call into it; a phase must not claim ownership of a REPL, parser, or other function assigned to another phase.
3. `phase_cleanup`: reset old derived artifacts without expanding the selected scope. Its `pipeline.py phase-start` transition preserves the current `phases.json` and removes old derived extraction, specification, verification, Bug Validator, trace, and Skill-control artifacts. It does not semantically rewrite, remove empty, or merge phases. A full run must not reuse semantic outputs from an earlier run.
4. `extraction`: when CodeGraph is selected, first run `codegraph.py export --output "$PROJECT/fm_agent_skill/control/codegraph_export.json"`, then run `executor.py extract --project "$PROJECT" --codegraph-export "$PROJECT/fm_agent_skill/control/codegraph_export.json"` (plus every selected `--submodule`). Otherwise omit that option. Extraction uses mapped CodeGraph spans first, Tree-sitter when installed, then the profile-declared language-specific fallback. ArkTS deliberately uses its FM-Agent-compatible `arkts-brace` extractor because CodeGraph does not support `.ets`. It writes immutable function copies and the `fm_agent_skill` control inventory without calling FM-Agent. Never analyze test paths, emit a pseudo-function for declaration-only headers, hash-name artifacts, or write inline `[SPEC]`/`[INFO]` into copied source.
5. `call_graph`: when CodeGraph is selected, reuse that same export with `executor.py graph --project "$PROJECT" --codegraph-export "$PROJECT/fm_agent_skill/control/codegraph_export.json"`. It maps exported nodes/edges to current extracted artifacts and records `exact` only then. Without CodeGraph, dispatch `fm-agent-skill:fm-agent-static-edge-worker`, validate its `fm_agent/agent_static_edges_candidate.json` through `executor.py record-agent-edges`, then rerun `executor.py graph`; only validated edges are used and the backend remains `agent-static/best-effort`.
6. `specification`: after knowledge materialization, run `job_planner.py --phase specification` once, then `semantic_executor.py prepare`. It registers domain context plus every function across all phases/layers before execution, using caller-first dependencies and batches of up to eight by default. Dispatch only exact tickets for `fm-agent-skill:fm-domain-context-worker` and `fm-agent-skill:fm-spec-batch-worker`; never generate a Workflow script. Each Worker follows original FM-Agent semantics: derive intended condition B from domain/interface/caller relations before inspecting implementation details. Same-layer batches may run concurrently; each writes native three-field `.spec.json` and native `.info.json` sidecars without changing source copies. The deterministic boundary strips harmless legacy/identity fields, reports every invalid pair in the batch at once, and redispatches only rejected pairs.
7. `verification`: only after the specification gate succeeds, run `job_planner.py --phase verification` once, then `semantic_executor.py prepare`. Dispatch exact `fm-agent-skill:fm-verify-function-worker` tickets covering every pending function; the executor never substitutes a confidence shortcut. The existing partitioner groups small functions up to the default eight-function cap while retaining the complexity-token and source-byte limits; large or branch-heavy functions still partition. Each function has its own result and validation. The Worker independently derives actual postcondition A and performs FM-Agent's structured A→B check against the native spec B. Schema 3 records explicit completion, loop obligations and candidate identities; `--all-bugs` continues after independent mismatches, while default mode admits one candidate per function. Mark a direct local violation `MISMATCH` only with a concrete counterexample and exact source quote; mark callers affected only through an invalid callee `DEPENDENCY_RISK`, not `MISMATCH`. Retry malformed output and never treat it as semantic evidence. Do not pass the phase when fewer than half the scope reaches MATCH/MISMATCH or any result is ERROR.
8. `bug_validation`: run `job_planner.py --phase bug_validation` once after
   verification. It creates one dynamic-validation job for every current direct
   candidate ID; each job carries its candidate and actual function ID; when there are no candidates, it records an empty completed plan.
   Use `durable_executor.py next`
   continuously. Up to four independent jobs may run at once by default, subject
   to host capacity. In default `agent-executed` mode, do not call
   `probe_runner.py detect`: every registered language uses the Worker-selected
   `host-project-toolchain` execution pass. The Worker records a real
   public-entry probe using only an attempt-local workspace and cache. After
   validated preparation, the execution ticket may continue the same isolated
   preparation Worker for identical project/job/candidate/attempt/input hash;
   otherwise launch fresh. The runtime generates reports and canonical receipts
   locally from validated immutable execution and accepted history. It selects
   the project's
   actual command, including Makefile projects; a missing SDK, device, compiler,
   cache, or public entry produces `unsupported/inconclusive` only after the
   Worker records that evidence. In optional `adapter` mode only, the
   Coordinator may run `probe_runner.py detect`, `probe_runner.py run`, and
   `reproduction_runner.py run`; C/C++ CMake adaptation additionally requires
   `CMakeLists.txt`, not merely a `cmake` executable. A build/syntax result
   cannot confirm a defect. An execution error requeues the same job within its
   existing budget; valid unsupported evidence finishes inconclusive after the
   first attempt. Completed negative probes retain their budget and require a
   distinct lawful witness or trigger. Candidate reports follow accepted evidence;
   write the current summary only after every Bug Validator job has
   scheduler-successfully completed. Verify and Bug preparation receive the copied
   requirements and permitted caller evidence; an invalid or unclear witness
   domain remains a named gap, never invented negative output or weakened Q.
9. `finalize`: write summaries and a successful baseline after every previous
   gate passed. A schema-v3 `MISMATCH` is a static finding only while its
   automatic dynamic-validation job remains incomplete; after the phase
   converges, the report records its confirmed, rejected, or inconclusive
   dynamic status.

The host must use `phase_driver.py next` for this sequence. The driver creates
the `project_understanding` Phase Plan job, never exposes extraction before
`phase_cleanup` seals, and automatically checkpoints each passed gate. The
host only executes returned deterministic actions or launches returned native
Worker tickets. Do not pre-plan or dispatch verification from partial
specification outputs, or Bug Validation from partial verification outputs.

If a phase fails, record `phase-fail`, retain its outputs, then run
`pipeline.py fail`, which releases the owned lock. Retrying is bounded by the configured retry count; do not
silently bypass a missing artifact. A failed pipeline has no FM-Agent bug
result. Do not replace the failed phase or any later phase with direct source
auditing, and do not report static suspicions as findings from this run.

## Resume

For an explicit resume, read [resume-contract.md](resume-contract.md). Start
at the active analysis's first incomplete phase, not at `preflight`. Keep all
earlier gate-validated work. Within the resumed phase, retain only artifacts
from the saved snapshot commit and create missing work. Do not repeat
`phase_cleanup` after it has succeeded. Reuse a readable same-snapshot
CodeGraph index only when resuming the incomplete `call_graph` phase.

The host Coordinator dispatches the semantic work to the named workers
instead of calling FM-Agent's original remote-LLM pipeline. Read
[agent-orchestration.md](agent-orchestration.md) and
[subagent-scheduler.md](subagent-scheduler.md) before beginning.

When snapshot creation finds ArkTS source, it additionally performs the
LanguageProfile-declared, read-only dependency hydration: project-local,
lock-bound `oh_modules/` is copied into the private snapshot while `.hvigor/`
is excluded. A missing or unsafe tree is recorded as unavailable without
blocking static analysis; the later dynamic Worker must be inconclusive rather
than install dependencies or use HDC.
