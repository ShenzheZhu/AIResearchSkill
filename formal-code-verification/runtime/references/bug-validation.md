# Bug validation

A schema-v3 direct reasoning `MISMATCH` is a candidate only after the gate has
validated normative or inferred specification B, reasoned actual postcondition A, a
concrete `A ∧ ¬B` counterexample, and an exact offending source quote. It is
never a confirmed defect. Do not
read project tests or run the full test suite. Instead, reproduce the candidate
through the production package's public entry point with one minimal generated
probe. `DEPENDENCY_RISK` is not a bug candidate.

## Evidence levels

Structured code/spec reasoning creates the candidate. A build or syntax probe only checks
that a snapshot is buildable; it is not behavioral evidence. Only an executed
minimal probe whose actual output differs from the validated normative or inferred contract
may produce `confirmed`.

In default `agent-executed` mode, do **not** run `probe_runner.py detect` and
do not treat a missing fixed adapter as an unavailable runtime. The Worker
chooses the repository's actual toolchain (including a Makefile) and records
its execution evidence. Run `probe_runner.py detect` only in the optional
restricted `adapter` mode; its profile at
`fm_agent_skill/control/build_profile.json` selects an optional safe build
adapter. A later adapter-mode `probe_runner.py run` writes its profile beside
that attempt rather than to this shared discovery path. A C/C++ CMake adapter
requires `CMakeLists.txt`; a system `cmake` executable alone cannot build a
Makefile project. Language capabilities are defined once in
`src/fm_agent_core/languages.py`: canonical names, file extensions, CodeGraph
names, Tree-sitter grammar names, span extractor, public-entry strategy, build
metadata detector, build adapter, dynamic adapter, and support level must all
come from that registry. Do not add a parallel extension or ecosystem map in a
runner. The registry separates `dynamic_adapter` (a controlled fixed-argv
adapter) from `agent_execution_ecosystems`. All registered profiles use the
same `host-project-toolchain` ecosystem in `agent-executed` mode, matching the
original FM-Agent Bug Validator: the Worker identifies Maven, CMake, NVCC,
Hvigor, Erlang/OTP, or another project toolchain from the project itself.
`dynamic_adapter` remains separate and may be absent in restricted `adapter`
mode. ArkTS has an explicit FM-Agent-compatible brace extractor because
CodeGraph does not index `.ets`; CUDA and Erlang still need their upstream
capability support before they can produce a Bug Validator candidate. Any
candidate that exists uses this same dynamic execution contract.

For static extraction, CodeGraph spans are authoritative. Without a matching
CodeGraph span, use the declared Tree-sitter grammar; Python may use its native
AST and C/C++ may use their profile-declared Clang AST when that grammar is
unavailable. ArkTS is the explicit exception: its profile declares the
FM-Agent-compatible `arkts-brace` extractor because CodeGraph has no ArkTS
backend. There is no generic regular-expression boundary fallback.

### ArkTS dependency hydration

ArkTS declares an `oh_modules` hydration policy in its LanguageProfile. Git
does not include this ignored dependency tree in the analysis snapshot, so
snapshot creation scans only project-local `oh_modules/` directories that have
an adjacent `oh-package-lock.json5` (or legacy `oh-package-lock.json`). It
parses the lockfile and checks every installed `oh-package.json5` name/version
against it, rejects symbolic links, records a lockfile SHA-256 in the snapshot
marker, then copies the verified tree into the private snapshot. Each Worker
copies that snapshot into its own attempt workspace before Hvigor runs.

This is a read-only dependency transfer, not dependency installation: it never
invokes `ohpm install`, contacts a registry, reads a global cache, or copies
`.hvigor/`. Missing, malformed, stale, or unsafe dependency trees leave static
analysis intact but require ArkTS dynamic validation to report
`unsupported/inconclusive`. Pure host-runnable utilities may be probed; code
requiring Ability, UI, device, or system-service runtime support is likewise
inconclusive and must not cause HDC/emulator setup.

For JavaScript and TypeScript, Tree-sitter extraction includes named arrow
functions declared through a `variable_declarator`, such as
`export const parse = (input) => { ... }`. The emitted span covers its owning
single declaration (including `const`/`export`) and is keyed by `parse`.
Build adapters run only fixed commands and may not be mistaken for a
reproduction.

## Fast agent-executed reproduction

For each independent `candidate_id` and attempt (keeping its actual owning
`function_id` separate):

1. Obtain a candidate descriptor through `durable_executor.py next`, claim it
   immediately with `durable_executor.py claim`,
   then invoke `fm-agent-skill:fm-bug-validate-worker` in its
   preparation pass. It writes `reproduction.json` and `probe.<ext>` under its
   assigned `fm_agent_skill/probes/<bug-id>/attempt_<n>/` directory. Do not
   call `bug_validation_executor.py start` again: the durable executor already
   owns the atomic scheduler start transition.
2. Validate that the schema-3 contract names its candidate, actual function,
   attempt and current snapshot, a structured public
   entry point (`ecosystem`, `kind`, repository-relative `target`, `symbol`),
   a fixed language extension, no shell command, and fixed `CONFIRMED` /
   `NOT CONFIRMED` markers. In `agent-executed` mode every profile uses the
   registry's `host-project-toolchain` ecosystem; in `adapter` mode, it must
   equal the profile's `dynamic_adapter`. The default
   `bug_validation_execution: agent-executed` returns an execution ticket.
   After preparation validation, use its `candidate_continuation` metadata and
   `collaboration.followup_task` only for the same preparation Worker that
   started with `fork_turns="none"` and has handled only this exact
   project/job/candidate/attempt/input hash. Pass the complete execution ticket
   and immutable definition. If the matching isolated context or followup tool
   is unavailable, launch a fresh execution Worker. Never reuse another job,
   candidate or attempt, or a context that received parent history, tests,
   answers or unrelated messages. It uses the repository's real toolchain and
   build system,
   records every command, exit code and bounded output in
   `reproduction_result.json`, and may support any FM-Agent language. Up to
   `bug_validation_concurrency` candidate probes (four by default) may execute
   together. Report and receipt generation is local deterministic work and
   consumes no Worker slot. Every recorded command must use a working directory
   below that attempt, and
   any build workspace or cache must be private to it.
3. Submit that immutable execution evidence to the executor. If it records
   `execution_error`, the executor requeues the same job; do not write a
   semantic result.
4. Otherwise the executor validates the immutable execution result and accepted
   history, writes the candidate report, and submits its canonical scheduler
   receipt locally. The Coordinator must not invent report fields or transcribe
   classifications. Valid `unsupported/inconclusive` evidence ends the job on
   that first accepted attempt.

The final report's last `attempts[]` item must have `ordinal` equal to the
current overall job attempt and must point at that exact attempt's
`reproduction_result.json`. A prior negative report never completes a retried
probe; the runtime appends only validated current dynamic evidence. Preserve the
exact ordered prefix of accepted
semantic attempts; duplicates, reordering or a dropped inconclusive attempt
cannot exhaust the negative budget. Each accepted negative outcome seals its
probe/contract/execution/build records through the same SQLite artifact identity
as terminal acceptance. Runtime failures may leave ordinal gaps.

The expected lifecycle is two model turns per attempt (preparation and
execution), down from three. Safe continuation reduces native context starts
from three to one; a fresh execution Worker uses two. These counts do not
establish measured wall-clock savings or completion of a repository audit.

Preparation receives manifest-bound copied requirements and permitted caller
evidence alongside the candidate. Establish that the witness satisfies P and
the governing input domain before probing. An invalid or unclear domain is a
named inconclusive gap; do not invent `NOT CONFIRMED` output, substitute an
unrelated input, or weaken Q to fit the implementation. A successful negative
probe supports only its actual input and schedule, never the entire domain.

`agent-executed` is FM-Agent-compatible quick mode, not a sandbox guarantee.
The Worker may execute project-scoped commands for any registered language,
including Python, JavaScript/TypeScript, Go, Rust, Java, C/C++, CUDA, ArkTS,
and Erlang. It must select the project's actual toolchain, and when a required
SDK, device, compiler, dependency cache, or public entry point is absent it
must write `unsupported/inconclusive`, not a false negative. It must not use
`sudo`, install packages, alter Git state or
read unrelated user files; it must build only from its private attempt
workspace rather than a shared project-root output directory, and its report
must retain exact command evidence.
Use `bug_validation_execution: adapter` only when the controlled local adapter
is required: that mode uses Bubblewrap, fixed argv, no network, a read-only
project and private scratch, but recognizes fewer ecosystems.

## Host-coordinated state machine

The Coordinator must not end its turn after launching a partial batch. Every
non-terminal action (`host_worker`, `wait_for_completion_event`, retry, or
execution receipt) requires another executor call. If the Coordinator reaches
its context or time limit, it must preserve the durable run and continue from
`next`/`resume`; a partial Bug Validator batch is never a completed phase.
Temporary safety-classifier or model-router unavailability is handled the same
way: pause the exact ticket and attempt, do not duplicate-dispatch it, and
resume later. It is not evidence of an unsupported project or a probe failure.

The dynamic lifecycle is driven by `bug_validation_executor.py`, not a manual
sequence of ad-hoc runner calls. It never invokes an Agent itself. Instead it
returns an exact `host_worker` request for the active Codex/Claude Coordinator
at the preparation and execution boundaries. The Coordinator must invoke the
named Worker through its native subagent mechanism, then return its compact
receipt to the state machine. The state machine owns admission, contract
validation, execution evidence, deterministic reports, retry/requeue, receipt
validation, and the terminal summary.

For each job, the Coordinator must process exactly one returned action at a
time. Independent admitted Bug Validator jobs may progress concurrently. After
preparation receipt, call `next`; after an execution receipt, call
`submit-agent-execution`; adapter mode alone uses `run-dynamic`. Continue
processing the returned action until the accepted job is terminal. Never infer
completion from a
report path and never launch the next Worker for that job before the executor
returns its request.

The probe must be self-contained, avoid network access and unrelated file I/O,
use a public entry point rather than an internal module, catch errors, and print
one unambiguous marker. `reproduction_result.json` retains its command, exit
code, stdout, stderr, source snapshot, and classification.

## Classification and retry

A named witness/domain preparation gap is a semantic failure, not an execution
attempt. Record it with `scheduler.py fail --failure-class semantic --message`
and its evidence; keep the coverage row unverified. Refine the governing
specification/reasoning before replanning that candidate. Do not repeatedly
redispatch the unchanged preparation or manufacture an execution result.

| Validated execution result | Canonical receipt | Final report status |
| --- | --- | --- |
| completed `CONFIRMED` | `confirmed` | `confirmed`; stop |
| completed `NOT CONFIRMED` | `not_reproduced` | `inconclusive` until the last negative attempt, then `rejected` |
| valid `unsupported` evidence | `inconclusive` | `inconclusive`; stop after the first accepted attempt |
| completed ambiguous output | `inconclusive` | `inconclusive`; completed-negative budget applies |
| timeout, command/tool failure, missing result | no receipt | retryable runtime failure |

Runtime failure retries up to `bug_validation_max_attempts` (default five).
A completed `not_reproduced` or ambiguous `inconclusive` attempt repeats under
the same job ID until `bug_validation_negative_retries + 1` attempts (default three),
preserving every immutable attempt. Valid unsupported execution does not repeat.
For a retry, use a distinct lawful witness/trigger within the assigned candidate
claim or fix the actual execution error; an identical unavailable-runtime probe
adds no evidence. Keep candidate identity and source snapshot fixed. An exact-input
claim cannot become a broader claim by varying the probe. A build failure is runtime
probe evidence only; it cannot reject or confirm a semantic candidate.

On-demand `--validate` identifies one candidate (a function ID is sufficient
only when it resolves to one candidate). It preserves other accepted candidate
reports and private probe evidence on the compatible baseline. A new probe uses
its own run-qualified job/report/attempt paths; it cannot overwrite an older
accepted candidate's authority.

Incremental planning validates newly affected direct candidates. The summary
also resolves unchanged candidates through their explicit retained origins and
original accepted receipts. Never relabel their old snapshots or claim they
were executed again. Historical reports not selected by a current candidate's
accepted job path are ignored. Replacing the current summary does not erase
historical probes or accepted receipts:

```bash
<python3> "$FM_AGENT_SKILL_ROOT/scripts/bug_summary.py" \
  --project "$PROJECT" --mode "$MODE"
```
