# Methods and counterexample-guided refinement

Read only the portions relevant to the selected obligation.

## Select the evidence mechanism

| Need | Suitable existing mechanism | Limit to report |
|---|---|---|
| Go behavior, parsers, retry rules, numeric/text edges | Table tests and native testing.F fuzzing; race detector for concrete concurrent execution | Inputs/time/seeds explored; a race-free run is not a proof of all schedules. |
| TS/JS transformations, source attribution, UI lifecycles | Existing unit harness and installed property-testing library; otherwise independently generated deterministic cases | Number/string semantics and mocked boundaries; browser rendering still needs browser evidence. |
| Ownership, queues, atomicity and late completions | A small explicit transition model; existing TLA+/TLC or another model checker when available | Initial states, finite domains, schedules/depth, failure/atomicity assumptions. |
| Arithmetic or finite symbolic state | Existing SMT solver such as Z3; ask for P ∧ actual-transition ∧ ¬Q | Exact modeled bit width/sign, arithmetic, domain, abstractions and solver result. |
| Rust or Go source proofs | Existing Verus for supported Rust or Gobra for supported Go | Coverage of actual source versus external/trusted functions, annotations and tool-supported features. |

Check installed tools and repository conventions before adding anything. Do not translate the target program into Rust just to use Verus. If a useful solver is absent, identify it; use a temporary verification environment only when justified by the task, without adding application dependencies. Do not install an entire agent suite or call an external model service by default.

### Go example commands

Adapt the package and names to actual source, and run from its module:

```sh
go test ./path/to/package -run '^TestSpecificProperty$' -count=1
go test ./path/to/package -run '^$' -fuzz '^FuzzSpecificProperty$' -fuzztime=10s -parallel=1
go test -race ./path/to/package -run '^TestConcurrentProperty$' -count=1
```

Fuzz fixtures should use an independent oracle, valid boundary seeds, and the actual target. Record the generated failing seed. Do not fill invalid configuration with bypasses and then call the resulting crash a product bug.

## What a formal result means

For a pure symbolic check, show that P and meaningful P ∧ transition cases are satisfiable, and compare transition presence with actual success/failure paths. Then solve the violation formula. SAT yields a model counterexample; UNSAT excludes violations in the encoded model; UNKNOWN/timeout does neither. Never count omitted transitions or inconsistent constraints as correctness. Any direct-code proof still depends on the verifier's supported semantics and explicitly trusted boundaries.

For loops, separately check initialization, preservation and sufficiency for the postcondition. A state satisfying an incomplete invariant can be impossible to reach from entry. Such a counterexample is evidence about the proof attempt, not automatically about the executable program.

For stateful flows, distinguish safety from liveness. “At most one owner” does not prove eventual reconnect. To check liveness, define fair scheduling/retry assumptions and termination conditions; never infer it from a short trace with no failure.

Check arithmetic and units before interpreting a solver result:
- Go fixed-width arithmetic must not be modeled as unbounded integers without explaining the correspondence.
- JS Number is not an arbitrary-precision integer; Unicode byte/code-point/UTF-16/grapheme counts differ.
- Splitting one real atomic transaction into several model steps can invent impossible partial commits; collapsing real non-atomic effects can hide failures.

## Refinement record

Maintain this small table only when the abstraction changes:

| Iteration | Failure / trace | Actual-code reproduction | Classification | Model or proof change and source justification | Obligation retained? |
|---|---|---|---|---|---|

Concrete counterexamples should have a consistent **state → executed transition(s) → violated predicate**. Fix prerequisite invariants first, but verify each proposed dependency rather than inventing a graph from wording. Group mutually inductive invariants if single clauses cannot establish one another.

Keep at least one actual-code differential/property check connecting an abstraction to implementation. If a primitive, concurrency boundary, integer domain or error path lacks correspondence, retain that gap. No amount of model refinement alone establishes that the model equals the program.

Deduplicate by violated property and shared root cause. Use one minimized regression plus boundary/metamorphic cases that test distinct obligations. A fix requires rerunning the relevant connected properties, not restarting every successful unrelated test.

## Sources and adaptation boundary

- [FM-Agent paper](https://arxiv.org/abs/2604.11556) and [official explanation](https://fm-agent.ai/blog/what-is-fm-agent): caller-grounded specifications, compositional Hoare-style LLM reasoning and executable bug diagnosis. The paper distinguishes this from a sound formal verifier; reasoning confidence is not a proof.
- [ExVerus](https://arxiv.org/abs/2603.25810): validated counterexamples make failed proof obligations actionable and guide inductive-invariant repair. Borrow this diagnostic loop; do not label a missing proof annotation an executable bug.
- [TopoVerus preprint](https://etha-sun.github.io/papers/TopoVerus.pdf), Curriculum Proof Repair with Learned Counterexamples: state/trace/violation diagnostics, prerequisite invariant ordering, and preservation of executable code and user specifications during proof repair. This skill does not reproduce its training or claim its benchmark results.
- [Go fuzzing](https://go.dev/doc/security/fuzz/), [Z3](https://github.com/Z3Prover/z3), [TLA+/TLC](https://github.com/tlaplus/tlaplus), [Verus](https://github.com/verus-lang/verus), [Gobra](https://github.com/viperproject/gobra): consult the selected tool's primary documentation for exact commands and supported semantics.

The original [FM-Agent](https://github.com/fmagent-project/FM-Agent) and [official skill](https://github.com/fmagent-project/FM-Agent-Skill) are optional separate tools. This is an independently written, focused workflow; it does not install, copy or run their pipeline, private source snapshots, graph scheduler or checkpoint infrastructure. The supplied Dameng case's reported cost and defect totals are not estimates for the current codebase.
