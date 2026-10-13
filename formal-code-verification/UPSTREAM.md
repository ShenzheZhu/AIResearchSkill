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

Local runtime changes are limited to the documented scripts (`phase_driver.py`, `scheduler.py`, `reset_full_artifacts.py`, `orchestrate.py`, `executor.py`, `terminal_report.py`), the shared `src/fm_agent_core/state.py` predicate, their regression checks, and the Claude license metadata. Other upstream Python files, Worker definitions, references and plugin manifests are unchanged. To update the runtime, inspect the upstream changes, retain or retire the documented fixes as appropriate, repeat the five entry filename changes, and rerun its checks plus the public case before updating this record. Expand supported scheduling only after its actual host pipeline passes.
