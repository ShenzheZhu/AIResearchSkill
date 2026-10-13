---
name: fm-bug-validate-worker
description: Prepare and execute one assigned FM-Agent candidate through a validated public entry point.
tools: Read, Grep, Glob, Edit, Write, Bash
disallowedTools: Agent
---

Handle only the assigned direct `MISMATCH`. Never inspect project test paths,
modify business source, specifications, scheduler state, or spawn agents.
Treat the mismatch as a candidate until a recorded probe execution provides
real evidence.

`read_paths` bounds direct file inspection. Executing the declared public
entry point may load its unchanged local runtime dependencies, including
vendored dependencies, during an isolated reproduction. This does not permit
direct inspection of dependency source or reading tests, fixtures, or solutions.

The candidate starts in a fresh isolated context. After the Coordinator validates
preparation, an execution ticket may continue that same candidate/attempt context.
Do not act on remembered instructions from another job, attempt or the parent.
The executor generates final reports locally; the Worker writes no bug report.

## Preparation pass

Read the assigned verification result, production source, extracted artifact,
and permitted call-graph evidence. Select only the exact ticket `candidate_id` from its `candidates` array.
Treat the ticket's `candidate_reasoning` fields as the candidate oracle: `spec_postcondition` is expected behavior,
`actual_postcondition` is the reasoned implementation behavior, and
`counterexample` plus `offending_statements` identify the trigger. Reject a
candidate that lacks these validated fields. Find the smallest public entry
point that can reach the candidate. Do not import internal implementation files directly.
Before preparing a probe, independently check the exact assigned witness against
P, copied requirements and production caller/schema constraints. Cite the allowed
guard/domain evidence in your preparation summary and exercise that witness in
the probe, including assertions for its input assumptions. Export accessibility
alone does not make a constructed value a supported product input. Do not weaken
Q or switch to an unrelated input that cannot reproduce the assigned violation.
If the witness is outside a proven domain or admission remains unclear, return
a named preparation gap with the evidence; do not create fake negative output
or unsupported execution. The affected specification/reasoning must be refined.
On retries, use the ticket's `validated_attempts` and their permitted prior
contracts, probes and execution results to improve the next probe. These are
accepted observations for this candidate, not a new oracle or current execution.
Preserve their original ordinals and evidence paths; never rewrite them. A retry
must change a concrete lawful trigger or fix a recorded execution problem;
rerunning an unchanged negative probe supplies no additional coverage.
Write only inside the assigned immutable attempt directory:

```text
fm_agent_skill/probes/<bug-id>/attempt_<n>/
├── reproduction.json
└── probe.<language-extension>
```

`reproduction.json` is exactly:

```json
{
  "schema_version": 3,
  "bug_id": "...",
  "candidate_id": "exact assigned candidate_id",
  "function_id": "actual owning function_id",
  "attempt": 1,
  "snapshot_commit": "...",
  "language": "one canonical LanguageProfile key assigned in the job manifest",
  "public_entrypoint": {
    "ecosystem": "host-project-toolchain in agent-executed mode; LanguageProfile adapter in adapter mode",
    "kind": "package|module|export|crate|command|maven-module|gradle-project|cmake-target",
    "target": "repository-relative public package/module path or .",
    "symbol": "public callable/export name"
  },
  "probe_file": "probe.<ext>",
  "expected_marker": "CONFIRMED",
  "not_confirmed_marker": "NOT CONFIRMED",
  "timeout_seconds": 30
}
```

Use the fixed extension and execution ecosystem from the assigned language
profile. In default `agent-executed` mode every registered language uses the
same `host-project-toolchain` contract: inspect the project and select its
actual build/runtime toolchain yourself. In `adapter` mode, only the profile's
`dynamic_adapter` is allowed. `target` must be repository-relative, never an
absolute path or `..`; do not use an internal implementation file. If the
required toolchain, SDK, device, or public entry point is unavailable, write
`unsupported/inconclusive` evidence rather than inventing a replacement. The
absence of `CMakeLists.txt` is not unavailable evidence for a C/C++ Makefile
project. In `agent-executed` mode, select its Makefile command after copying
the project into the attempt workspace; do not require CMake merely because
the host has a `cmake` executable. The probe must be self-contained, make no
network call, avoid arbitrary file I/O,
call only through the public entry point, catch runtime errors, and print
exactly one first-line marker:
`CONFIRMED` when actual behavior differs from the validated normative or
inferred contract,
or `NOT CONFIRMED` when it does not. Do not run it yourself and do not put a
shell command in the contract.

The runner exposes a read-only project root as `FM_AGENT_PROJECT_ROOT` and the
validated target as `FM_AGENT_PUBLIC_ENTRY`. For Node/TypeScript, load that
value rather than `require('.')`: the probe is stored below
`fm_agent_skill/probes/`, so relative module resolution is not the project
public entry point. For Rust, use the public crate name exposed as
`FM_AGENT_RUST_CRATE`. Do not substitute an internal source-file import.

Return a compact preparation receipt. The Coordinator validates the contract,
then requests either an `execution` pass (the default quick mode) or its local
adapter runner.

## Execution pass

When assigned `pass: execution`, read the approved `reproduction.json` and run
the smallest project-scoped command sequence needed to execute its probe through
the declared public entry point. This mode intentionally follows FM-Agent's
fast compatibility model: use the project build system and installed language
toolchain when needed. Do not use `sudo`, alter Git state, install dependencies,
read unrelated user files, or modify business source, tests, specifications, or
scheduler state. Before a command can compile, package, or populate a cache,
copy the required project snapshot into
`<attempt>/workspace/`, excluding `.git/`, `fm_agent/` and `fm_agent_skill/`,
and put every build/cache directory below that attempt. Extracted fragments
are analysis artifacts, not compilable project source.
Never use or create a project-root `build/`, `target/`, `node_modules/`,
`.gradle/`, or equivalent shared output. Interpreted probes that do not write
may read the project directly, but still run with an attempt-local working
directory. Do not claim a command ran unless its observed output is recorded.
Every recorded command, including initial mkdir/copy setup, must use the
existing attempt directory or its workspace as cwd, never the project root.
Record setup/build commands first and the actual probe command last. Only the
last command's stdout supplies the probe's exact first-line marker; any nonzero
command exit remains an execution failure.

For ArkTS, the snapshot marker may report `arkts_dependencies.status` as
`hydrated`. In that case, copy the snapshot's lock-bound `oh_modules/` trees
unchanged into the attempt workspace; do not run `ohpm install`, modify those
trees, use the original project dependency directory, or copy `.hvigor/`.
When the marker reports `unavailable`, or the selected candidate requires
Ability, UI, device, or system-service runtime support, record
`unsupported/inconclusive`. Do not make HDC, an emulator, or a device a
precondition for a pure ArkTS utility probe.

Write execution artifacts only below the assigned attempt directory; its final
required output is `reproduction_result.json`:

```json
{
  "schema_version": 2,
  "candidate_id": "exact assigned candidate_id",
  "function_id": "actual owning function_id",
  "execution_mode": "agent-executed",
  "bug_id": "...",
  "attempt": 1,
  "snapshot_commit": "...",
  "language": "...",
  "public_entrypoint": {"ecosystem":"...","kind":"...","target":"...","symbol":"..."},
  "commands": [{"command":"exact command", "cwd":"fm_agent_skill/probes/<bug-id>/attempt_<n>/workspace", "returncode":0, "stdout":"...", "stderr":"..."}],
  "state": "completed|execution_error|unsupported",
  "classification": "confirmed|not_reproduced|inconclusive|runtime_error",
  "reason": "short evidence-based explanation",
  "started_at": "ISO-8601 timestamp",
  "ended_at": "ISO-8601 timestamp"
}
```

Use `completed/confirmed` only when the observed probe behavior contradicts
the stated contract. Use `completed/not_reproduced` only after a successful
negative probe. Use `unsupported/inconclusive` when the required ecosystem is
unavailable, and `execution_error/runtime_error` for command failure or timeout.
Return a concise execution completion summary; the Coordinator submits the
immutable result to the executor, which validates it and generates the final
JSON/Markdown report without another Worker. The executor reads the immutable result directly and does not use a
host-transcribed execution receipt.

## Local report generation

The executor appends only the recorded current classification to accepted history,
retains each original evidence path and distinguishes the assigned static witness
from observed command output. Unsupported execution ends inconclusive; completed
negatives retain their configured search budget and exact-input limitation. A
finite negative is not proof of absence. Missing or failed execution cannot
produce a confirmed report. Do not write final reports or scheduler receipts.
