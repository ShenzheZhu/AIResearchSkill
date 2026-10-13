# Reusable public case: more-itertools `seekable`

Use this case to evaluate the Hoare-style workflow on real upstream code. It is a historical reproduction with upstream fixed and current-source controls, not a claim that this skill discovered a new defect. Do not give this answer document or the fixed version to the agent analyzing the historical version.

## Prepare a small analysis target

Use an installed Python 3.10 or newer. Run the commands from this skill folder, or use the script's absolute path. The script uses only Python's standard library and Git; it does not install packages or call a model provider. Select a new output directory for each evaluation:

```sh
python3 scripts/public_case.py prepare /tmp/seekable-evaluation
```

The fixture contains:

- `analysis/selected/more.py`: an unchanged excerpt of `SequenceView` and `seekable`, including upstream API docstrings. `analysis/` is a small Git repository suitable for the official FM-Agent host pipeline.
- `analysis/README.md`: neutral source mapping and instructions for importing the complete native package. It contains no issue, patch or expected failure.
- `analysis/native/more_itertools`: the unchanged historical package travels with the analysis repository, so isolated Bug Validation can import its public entry point. Restrict FM-Agent analysis to `--submodule selected`; this directory is runtime evidence, not an expanded analysis scope.
- `native/{historical,fixed,latest}/more_itertools`: the actual unchanged upstream package, used for executing counterexamples against the public entry point.
- `case.json`: exact immutable revisions and original source line mapping. `latest` is resolved at preparation time, then retained for repeatable replay.

Give the evaluator only the `analysis/` target with `--submodule selected` and its neutral native-import instructions. The excerpt narrows analysis scope; it does not validate the whole repository. A counterexample against a reimplemented class or abstract model alone is insufficient: execute `from more_itertools import seekable` against the included `analysis/native` package.

## Intended Hoare obligations

Let `R(s)` be the sequence that repeated `next(s)` calls would yield from the current public iterator position. It is a logical observation, not the physical `_source` iterator alone. Let `old(R)` denote its value before a call.

**P:** a finite ordinary iterable; one caller at a time; no external advancement or mutation of its underlying iterator; `maxlen` is `None` or a nonnegative integer. Include empty input, zero cache capacity and falsy values. Do not exclude a supported value merely because it triggers a failure.

**I:** history storage has at most `maxlen` items when bounded; its representation together with the pending source preserves `R(s)`. Derive representation details from actual code. Peeking may populate the cache, so “all fields unchanged” would be an incorrect frame condition.

```text
{ P ∧ I ∧ old(R) ≠ [] }
value = s.peek()
{ value = head(old(R)) ∧ R(s) = old(R) ∧ I }

{ P ∧ I }
present = bool(s)
{ present ↔ old(R) ≠ [] ∧ R(s) = old(R) ∧ I }
```

For empty `R`, `peek()` raises `StopIteration`, or returns the supplied default, and leaves `R` empty. These requirements come from the original API docstrings: `peek` looks ahead without advancing; the truthiness example leaves iteration intact; `maxlen` limits history size. Trace `__bool__ → peek → __next__` to derive actual effects rather than treating methods independently.

## Answer key and actual replay

[Upstream issue #1268](https://github.com/more-itertools/more-itertools/issues/1268) and [fix PR #1269](https://github.com/more-itertools/more-itertools/pull/1269) record a real state-loss defect. At historical revision `1da45ae4b61a832ed080f08a8833784aad0a9534`, `peek()` and `bool()` with `maxlen=0` consume an item that the cache cannot retain. For `[10, 20, 30]`, subsequent iteration yields `[20, 30]` rather than the original sequence. Repeated peeking also changes the observed head.

Upstream fixed revision `b5e3886a37209bb880f17d82fbf4ba00ece0e41e` retains the sequence. Preparation separately resolves the latest commit and records its actual result. No upstream source is modified.

```sh
python3 scripts/public_case.py replay /tmp/seekable-evaluation
```

Replay executes eight focused public API cases against each complete native package. `replay.json` contains inputs, expected/actual observations and control outcomes; `replay-*.log` retains raw process output. Exit zero means the historical failure was reproduced and fixed/latest controls passed. It does **not** mean all revisions satisfy the requirements, or that the skill found the bug independently. Any infrastructure failure or unexpected current-source result prevents a passing replay.

Evaluate independent discovery separately: have the agent derive P/Q/I and actual behavior from the neutral historical code, generate its own counterexample, and preserve its reasoning and native execution output before revealing this answer key. This combines Hoare-style reasoning with concrete bug validation; it is not a sound SMT proof or full-repository audit.

## Observed Codex pipeline run: 2026-10-13

This observed run used the earlier single-candidate verification format. It is historical acceptance evidence, not a forward test of the newer incremental, multi-candidate or loop-evidence schema. Preserve its original artifacts; a new format requires a fresh compatible analysis.

The packaged runtime completed all nine full-analysis stages on the 13 selected functions using only current Codex/native Workers. Specification and implementation Workers received the neutral source and assigned artifacts, without this answer key, upstream issues or fixed-source controls.

| Result | Count | Interpretation |
| --- | ---: | --- |
| `MATCH` | 10 | Model-derived satisfaction of the generated requirements; no universal proof. |
| `MISMATCH` | 1 | `peek` locally violates sequence preservation at zero cache capacity. |
| `DEPENDENCY_RISK` | 1 | `__bool__` inherits the same bad `peek` behavior; not counted as another bug. |
| `INCONCLUSIVE` | 1 | `seek` calls out-of-scope `consume`; its behavior was not assumed. |

The independent witness used two distinct objects `a` and `b`, not the replay script's numeric example. From an initialized `seekable(iter([a, b]), maxlen=0)`, P holds. Intended Q requires `peek()` followed by `next()` to return the same object. Reasoning derived actual A: fetching `a` drops it from the zero-capacity deque, then the local restoration writes index `-1` into that empty deque. The native public-entry probe printed:

```text
CONFIRMED
peek_is_a=True; next_is_a=False; next_is_b=True
```

The original report recorded a confirmation, but later reliability checks found that cleanup had erased its durable scheduler receipt. Restoring probe files from a checkpoint did not restore acceptance authority. Under the corrected gate that old record is unavailable; it cannot be promoted from the report file alone.

The same unchanged candidate was then revalidated through actual native preparation, execution and finalization Workers, each launched with `fork_turns="none"`. The new public-entry probe again exited zero with `CONFIRMED`: `peek_returned_first=true`, `next_returned_peeked=false`, `next_returned_second=true`. Its new receipt passed the shared SQLite acceptance check before publication. This reran Bug Validation, not the preceding 13-function semantic analysis.

The resulting terminal report contains `official_result_available: true`, one dynamically confirmed candidate, one reasoning `INCONCLUSIVE`, and one `DEPENDENCY_RISK`. Its canonical business ledger has 11 obligations: one failed by actual-code evidence and ten unknown. It therefore reports **`audit_status: completed_with_gaps`**, never full business coverage. Dynamic `inconclusive: 0` is now named `dynamic_inconclusive`; it does not erase reasoning or business gaps. Keep the native probe, output and durable acceptance together.

Expected artifact paths in the analysis checkout:

- `fm_agent/extracted_functions/selected/more-peek-9.py.spec.json`: independently derived P/Q.
- `fm_agent/logic_verification_results/selected/more-peek-9.json`: actual A, witness and offending statements.
- `fm_agent_skill/probes/09610e65f45dd0d9/attempt_001/`: executable public-package probe and recorded command/output.
- `fm_agent_skill/control/terminal_report.json`: accepted final classification.
- `fm_agent_skill/control/business_coverage.json`: independent obligations, evidence levels and visible uncovered boundaries.
- `fm_agent_skill/checkpoint/state.db`: current accepted job/attempt/receipt and artifact identities; a report file alone cannot replace these records.

The separate replay observed historical 4/8 passing, fixed 8/8 and recorded current 8/8. Four historical failing scenarios exercise one root defect. This trial does not cover other components, languages or integration environments.

A separate cold-start discovery pass received only the neutral repository and the new skill entry, with no supplied function list or answer key. It identified 11 distinct obligations from the selected APIs and their real dependencies/consumers, proposed risk batches, and left unexecuted behavior and uncertain intent unknown. It did not invent database, network or permission flows for an in-process iterator library. This checks autonomous discovery and honest coverage accounting; it does not turn those additional obligations into verified results.
