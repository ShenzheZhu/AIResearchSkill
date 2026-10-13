# Incremental reuse and independent candidates

Read this for a code/requirement update after a completed analysis, for `--all-bugs`, or for interpreting loop evidence. The method follows FM-Agent's [incremental reasoning](https://arxiv.org/html/2604.11556v2#S7) and [loop obligations](https://arxiv.org/html/2604.11556v2#S5). The deterministic runtime still delegates semantic work only to fresh native Codex Workers.

## Select the actual mode

- **Full:** first analysis of an independent source batch, or no compatible qualified baseline. Store native specifications, callee expectations, reasoning results and accepted dynamic evidence.
- **Resume:** continue the same interrupted snapshot, scope, inputs and reasoning mode. It does not apply a new developer goal or analyze newly edited code. Explicit all-bugs mode changes cannot reuse an interrupted run.
- **Incremental:** compare a new captured source against a completed baseline and supply the intended modification. `orchestrate.py dispatch --project "$PROJECT" --incremental /absolute/intent.md --all-bugs` takes a Markdown goal; `--note` can also express the goal. Intent-only changes must enter selection even if the code manifest is unchanged. An explicit incremental request without a compatible baseline fails with the reason.
- **No-op:** compatible completed evidence, unchanged source, and no new intent. Report reuse and its original scope/limits; do not describe it as another execution.

The first full and later incremental runs must keep the same analysis configuration and reasoning mode. A changed runtime/schema or incompatible scope invalidates reuse; preserve old evidence as history instead of fabricating an upgrade. Inspect the returned action rather than assuming a mode from command text.

## Find relevant functions before changing specifications

Use the existing phase driver and native module/file/function selectors. Give them immutable developer intent, current source/index, code differences and caller/callee context; no tests or known-bug answers. Selection must include consumers that should change to satisfy the goal even when the patch left their bodies untouched. Record why each function is reviewed, included for reasoning, or excluded.

For example, changing delivery policy may require reviewing the fee, final order total and payment amount validation. A disconnected old total calculator cannot be excluded merely because it does not call the newly edited fee helper.

Review contracts in caller-to-callee order. Keep an applicable specification byte-for-byte when its intended meaning is unchanged. New functions need new specifications. Apply accepted plans serially, compare actual spec/info values, propagate changed caller expectations downward, and reconcile affected callers when callee requirements change. New intent supersedes the policy clauses it changes; unaffected prior requirements remain in force. Never weaken Q to make buggy code pass.

Review scope and verification scope are different. A relevant function whose source and reasoning contracts remain applicable may retain its existing conclusion. Changed body/source context, changed specification, changed callee expectations or removed dependencies invalidate the affected conclusion. Stable contracts stop propagation; do not automatically reverify the entire connected graph.

The current source boundary is conservative: changing a production file rechecks its functions, including byte-identical siblings, because imports, constants, types and global state can affect them. Unchanged files with qualified inputs can reuse evidence. Do not promise exact minimum function-granular rechecking.

## Qualify evidence without rewriting its origin

The runtime records `control/retained_evidence.json` against the new analysis, with each reusable function's original source blob, exact native spec/info, verification bytes and verification snapshot. Dynamic entries keep their individual candidate, job, snapshot, input fingerprint and accepted result path. Qualification checks the current inputs and original durable receipt/attempt/output/probe evidence. A report file alone is insufficient.

Keep original result snapshots and probe/receipt bytes unchanged. A changed or deleted function loses reuse; a changed reasoning contract invalidates its old conclusion. Preserve unaffected old authority while creating run-qualified new jobs and evidence paths, so a new result cannot overwrite another origin. Recursively retained evidence continues to name the actual original execution, not the most recent baseline label.

## Complete and validate every candidate

Current verification format separates a function from its direct candidates. `reasoning_complete` records whether all assigned reasoning finished; each candidate has a function-bound `candidate_id` and its own A/B witness. In `--all-bugs` mode, continue after the first mismatch and deduplicate repeated descriptions of one cause. Callee-only failures stay `DEPENDENCY_RISK` rather than becoming another direct local bug.

Bug Validation planning, tickets, commands, finalization, gates, reports and ledger entries bind both `candidate_id` and the actual `function_id`. One confirmed candidate cannot confirm another. Confirmation, rejection and unavailable execution remain separate outcomes. An incomplete function or pending candidate blocks completion; multiple probes for one candidate do not increase the number of independent defects.

## Explicit loop obligations

Conclusive reasoning must account for each parser-identified loop in its owning callable, including supported comprehension iterations. Record the invariant, why P establishes it, why a body iteration preserves it, and why normal termination implies the loop's required postcondition. Give separate arguments for relevant break/continue/return/throw paths. Nested callable bodies belong to their own verification.

If the parser or required evidence is unavailable, name that gap and use `INCONCLUSIVE`; do not substitute an empty inventory or a generic assertion. Structural validation establishes that the required arguments are present and source-grounded. It does not prove those natural-language arguments true. SMT integration is optional and is not supplied by this extension.

## Acceptance evidence

Keep deterministic runtime checks separate from fresh native forward testing. The forward test must actually run a full baseline, change code/intent, resume an interrupted phase, validate multiple independently derived candidates, and inspect reuse of untouched artifacts plus discovery of an omitted consumer. Give semantic Workers only their permitted neutral artifacts. Record actual outcomes and gaps before advertising or globally installing a new runtime.
