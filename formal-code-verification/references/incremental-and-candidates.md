# Incremental reuse and independent candidates

Read this for a code/requirement update after a completed analysis, for `--all-bugs`, or for interpreting loop evidence. The method follows FM-Agent's [incremental reasoning](https://arxiv.org/html/2604.11556v2#S7) and [loop obligations](https://arxiv.org/html/2604.11556v2#S5). The deterministic runtime still delegates semantic work only to fresh native Codex Workers.

## Select the actual mode

- **Full:** first analysis of an independent source batch, or no compatible qualified baseline. Store native specifications, callee expectations, reasoning results and accepted dynamic evidence.
- **Resume:** continue the same interrupted snapshot, scope, inputs and reasoning mode. It does not apply a new developer goal or analyze newly edited code. Explicit all-bugs mode changes cannot reuse an interrupted run.
- **Incremental:** compare a new captured source against a completed baseline and supply the intended modification. `orchestrate.py dispatch --project "$PROJECT" --incremental /absolute/intent.md --all-bugs` takes a Markdown goal; `--note` can also express the goal. Intent-only changes must enter selection even if the code manifest is unchanged. An explicit incremental request without a compatible baseline fails with the reason.
- **No-op:** compatible completed evidence, unchanged source, and no new intent. Report reuse and its original scope/limits; do not describe it as another execution.

The first full and later incremental runs must keep the same analysis configuration and reasoning mode. Reuse requires the current artifact schemas, qualified accepted evidence and compatible scope; there is no automatic runtime-upgrade migration. Inspect the returned action rather than assuming a mode from command text.

## Find relevant functions before changing specifications

Use the existing phase driver and native module/file/function selectors. Give them immutable developer intent, current source/index, code differences and caller/callee context; no tests or known-bug answers. Selection must include consumers that should change to satisfy the goal even when the patch left their bodies untouched. Record why each function is reviewed, included for reasoning, or excluded.

For example, changing delivery policy may require reviewing the fee, final order total and payment amount validation. A disconnected old total calculator cannot be excluded merely because it does not call the newly edited fee helper.

Review contracts in caller-to-callee order. Keep applicable spec/info values exactly unchanged; restoring JSON may normalize its formatting. New functions need new specifications. Apply accepted plans serially, compare actual spec/info values, propagate changed caller expectations downward, and reconcile affected callers when callee requirements change. New intent supersedes the policy clauses it changes; unaffected prior requirements remain in force. Never weaken Q to make buggy code pass.

Review scope and verification scope are different. A relevant function whose source and reasoning contracts remain applicable may retain its existing conclusion. Changed body/source context, changed specification, changed callee expectations or removed dependencies invalidate the affected conclusion. Stable contracts stop propagation; do not automatically reverify the entire connected graph.

The current source boundary is conservative: changing a production file rechecks its functions, including byte-identical siblings, because imports, constants, types and global state can affect them. Unchanged files with qualified inputs can reuse evidence. Do not promise exact minimum function-granular rechecking.

## Qualify evidence without rewriting its origin

The runtime records `control/retained_evidence.json` against the new analysis, with each reusable function's original source blob, exact native spec/info, verification bytes and verification snapshot. Dynamic entries keep their individual candidate, job, snapshot, input fingerprint and accepted result path. Qualification checks the current inputs and original durable receipt/attempt/output/probe evidence. A report file alone is insufficient.

Keep original result snapshots and probe/receipt bytes unchanged. A changed or deleted function loses reuse; a changed reasoning contract invalidates its old conclusion. Preserve unaffected old authority while creating run-qualified new jobs and evidence paths, so a new result cannot overwrite another origin. Recursively retained evidence continues to name the actual original execution, not the most recent baseline label.

A modular MATCH is conditional on its recorded callee expectations. When a callee body changes but its intended contract does not, the caller's conditional proof may remain applicable while the current callee fails verification. Report that dependency failure separately; never describe the caller's retained MATCH as current end-to-end acceptance.

## Complete and validate every candidate

Current verification format separates a function from its direct candidates. `reasoning_complete` records whether all assigned reasoning finished; each candidate has a function-bound `candidate_id` and its own A/B witness. In `--all-bugs` mode, continue after the first mismatch and deduplicate repeated descriptions of one cause. Callee-only failures stay `DEPENDENCY_RISK` rather than becoming another direct local bug.

Bug Validation planning, tickets, commands, finalization, gates, reports and ledger entries bind both `candidate_id` and the actual `function_id`. One confirmed candidate cannot confirm another. Confirmation, rejection and unavailable execution remain separate outcomes. Partial MATCH/MISMATCH results and pending candidates block completion; accepted INCONCLUSIVE/DEPENDENCY_RISK results remain explicit gaps. Multiple probes for one candidate do not increase the number of independent defects.

The phase driver's next action requeues current-run retryable jobs through the existing scheduler transition before dispatch. A rejected batch retains its valid siblings and repairs only invalid outputs; retries retain accepted attempt history, live leases and the existing runtime/negative budgets. Exhausted jobs remain terminal failures.

## Explicit loop obligations

Conclusive reasoning must account for each parser-identified loop in its owning callable, including supported comprehension iterations. Record the invariant, why P establishes it, why a body iteration preserves it, and why normal termination implies the loop's required postcondition. Give separate arguments for relevant break/continue/return/throw paths. Nested callable bodies belong to their own verification.

If the parser or required evidence is unavailable, name that gap and use `INCONCLUSIVE`; do not substitute an empty inventory or a generic assertion. Structural validation establishes that the required arguments are present and source-grounded. It does not prove those natural-language arguments true. SMT integration is optional and is not supplied by this extension.

## Acceptance evidence

Keep deterministic runtime checks separate from fresh native forward testing. The forward test must actually run a full baseline, change code/intent, resume an interrupted phase, validate multiple independently derived candidates, and inspect reuse of untouched artifacts plus discovery of an omitted consumer. Give semantic Workers only their permitted neutral artifacts. Record actual outcomes and gaps before advertising or globally installing a new runtime.

### Observed native calibration: 2026-10-14

This is an isolated Python pricing fixture, not a public-repository discovery. Workers received neutral API requirements and their assigned tickets in fresh contexts. Operator expectations stayed outside their inputs. It checks the wrapper's actual native pipeline; the original external-provider incremental pipeline was not run.

The five baseline functions expose quote totals, a delivery-policy query, its legacy query, a final order total and independent quantity conversion. The quote implementation overwrites its accumulator and subtracts shipping. Separate witnesses isolate the two causes:

| Pass | Observed native result |
| --- | --- |
| Full, `--all-bugs` | Five functions reasoned; quote yields two separate candidates and explicit loop obligations. |
| Accumulation probe | Prices `[3,4]`, shipping `0`: subtotal/total `4`, required `7`. |
| Shipping probe | Price `[10]`, shipping `2`: total `8`, required `12`. |
| Source update | Only change delivery query to `500` and remove its legacy query; leave order total unchanged. |
| Incremental selection | Finds both the changed query and the unchanged order total from the new flat-fee goal. |
| Affected reasoning | Only those two functions receive fresh verification; quote and quantity reuse qualified original conclusions. |
| Omitted-consumer probe | `order_total(0)` returns `0`, required `500`; a new candidate is accepted. |
| Evidence reuse | Two old quote confirmations retain their original execution origins; no probe or verification result is relabeled or overwritten. |
| Interrupted resume | Resumes after the sealed diff at graph rebuilding, without repeating completed gates. |
| Unchanged inspect | Returns `noop`; no additional analysis executes. |

The full nine-stage and incremental ten-stage pipelines completed. The incremental report contains four current functions and three confirmed candidates: one fresh and two retained. Its business ledger has three failed and three unknown obligations, so its status is `completed_with_gaps`. The runtime regression suite passed 119 checks with the selected Python/parser environment; missing parser environments are not covered by that result.

To repeat this pattern on another repository, use the same orchestrator and phase driver rather than a second workflow. Set `FM_AGENT_PYTHON` to the selected interpreter and `PROJECT` to the independent analysis checkout; `FM_AGENT_SKILL_ROOT` is the bundled runtime root resolved by the skill entry:

```sh
"$FM_AGENT_PYTHON" "$FM_AGENT_SKILL_ROOT/scripts/orchestrate.py" dispatch --project "$PROJECT" --all-bugs
# Complete every returned native Coordinator action before editing the source.
"$FM_AGENT_PYTHON" "$FM_AGENT_SKILL_ROOT/scripts/orchestrate.py" dispatch --project "$PROJECT" --incremental /absolute/intent.md --all-bugs
"$FM_AGENT_PYTHON" "$FM_AGENT_SKILL_ROOT/scripts/orchestrate.py" resume --project "$PROJECT"
"$FM_AGENT_PYTHON" "$FM_AGENT_SKILL_ROOT/scripts/orchestrate.py" inspect --project "$PROJECT"
```

Resume is used only after an actual interruption; inspect is used after completion. These commands dispatch native work, not an unattended external-provider runner. This Python calibration does not establish native incremental acceptance for every other language, complex cycle or integration environment; caller/callee propagation also has separate deterministic regressions.
