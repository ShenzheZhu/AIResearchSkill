# Upstream implementation

This skill redistributes the official [FM-Agent Skill](https://github.com/fmagent-project/FM-Agent-Skill) plugin subtree from commit `266269557489fee37dcc0af1d484642f11b8f2d8`, fetched on 2026-10-13. Its source is under `runtime/`; the upstream Apache-2.0 license is retained at [runtime/LICENSE](runtime/LICENSE).

The upstream Skill is the project's host-native implementation of the staged reasoning in [FM-Agent](https://github.com/fmagent-project/FM-Agent) and [its paper](https://arxiv.org/abs/2604.11556). It dispatches reasoning to the current host's subagents instead of invoking the original remote-provider pipeline.

Packaging changes and local fixes:

- Rename the five `skills/*/SKILL.md` files to `instructions.md` so global discovery exposes only `formal-code-verification`.
- Supply this Codex-only entry and its explicit `runtime/` root path.
- Add a selected public-source evaluation fixture and native-package regression replay.
- Repair `scripts/phase_driver.py` so the `agent-static` graph phase must run its existing semantic edge Worker, validate the returned edges, and build layers before it can pass. Add a focused regression check for that gate.
- Pass the requested `--submodule` values from the phase driver to extraction. The public pilot exposed unrelated native-package functions being extracted without these arguments; a regression checks that unrelated source remains excluded.
- Validate static-edge output during scheduler receipt acceptance, so a malformed edge enters the existing retry path rather than stranding a successful job.
- Keep accepted jobs, receipts and immutable probe evidence at successful completion. Upstream transient cleanup removed them before publication; a regression covers cleanup, publication, terminal confirmation and deletion only on the next explicit full reset.
- Correct the embedded Claude plugin's license metadata to match the retained Apache-2.0 license.
- Add autonomous business-flow discovery and coverage accounting before full analysis. Run new batches in independent external checkouts; only interrupted full runs resume. Upstream incremental/no-op scheduling is excluded because its phase driver does not execute all required incremental stages.
- Canonicalize accepted directory scopes before source filtering and reuse that effective configuration after snapshot relocation. Root scope selects the whole repository; relative and absolute in-repository scopes select the same source.
- Recognize standard colocated JavaScript/TypeScript test names and `__tests__` through the shared test-source predicate. Extraction reuses that predicate instead of maintaining a second copy.
- Bind Bug Validation final report identity to the assigned function before successful receipt acceptance, keeping malformed metadata repairable through the existing retry path.
- Validate published terminal results against the accepted snapshot identity rather than the current source checkout HEAD.
- Reuse the native output classifier to reject execution records that contradict exit codes or probe markers. Recheck durable SQLite receipts, current attempts and exact accepted evidence before publishing a dynamic conclusion; missing or unreadable authority stays unavailable.
- Require fresh Codex Worker/Coordinator contexts with `fork_turns="none"`; pass only assigned tickets, immutable definitions and permitted evidence. Disable semantic work in a parent that may have seen answer keys.
- Supply complete phase-specific Bug Validator tickets for fresh contexts, and retain unrelated accepted candidate receipts when explicitly revalidating one candidate.
- Let explicitly selected production directories override default inventory skips, and carry that scope through preflight, extraction and graph gates. Keep unselected dependency/generated siblings and analysis metadata excluded.
- Report reasoning gaps, dynamic outcomes and the canonical business-coverage ledger separately. Missing/invalid coverage cannot complete an audit; unresolved rows remain visible. Merge overlapping source batches while preserving separate business obligations.
- Resolve temporary fixture roots so default macOS Python commands work without a `TMPDIR` workaround.
- Stop a failed DAG once independent ready/live work has drained. Do not wait for a completion event when no Worker can produce one.
- Reject source parsing failures, clear stale re-extraction inventories, use the TSX grammar for TSX, and preserve ordinary named function-expression/literal bindings. Unsupported callable shapes remain explicit gaps.
- Extract unbound JavaScript/TypeScript/TSX anonymous callbacks, IIFEs and anonymous declarations with readable Tree-sitter source-position identities; preserve inner named callback expressions and original manifest paths, line spans and source slices. Retain explicit rejection of ambiguous Go bindings, destructured callable bindings and unsupported Python shapes.
- Treat vendored dependency directories as advisory inventory exclusions; explicit `vendor` selection still includes their actual source, including when nested in a selected production `dist` directory.
- Classify only the final probe command using its exact first-line marker. Setup/verifier success messages are not candidate reproduction; any command failure still prevents confirmation.
- Retain unsupported/inconclusive retry outcomes, include dynamic gaps in the audit status, and bind qualified native coverage to its assigned function, exact specification, accepted receipt and recorded attempt. Native evidence cannot acquire an integration or machine-proof label.

Local runtime changes cover the documented scripts (`phase_driver.py`, `durable_executor.py`, `scheduler.py`, `reset_full_artifacts.py`, `orchestrate.py`, `executor.py`, `terminal_report.py`, `bug_summary.py`, `bug_validation_executor.py`, `reproduction_runner.py`, `semantic_executor.py`, `preflight.py`, `stage_gate.py`), shared state/language/Worker/Coordinator contracts, Bug Validator/run/Coordinator instructions, regression checks, and Claude license metadata. Remaining upstream implementation is unchanged. To update the runtime, inspect the upstream changes, retain or retire the documented fixes as appropriate, repeat the five entry filename changes, and rerun its checks plus the public case before updating this record. Expand supported scheduling only after its actual host pipeline passes.
