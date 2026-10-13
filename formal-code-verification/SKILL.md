---
name: formal-code-verification
description: Verify a selected function or workflow against explicit preconditions, postconditions and state invariants; use Hoare-style reasoning, formal tools when suitable, and executable counterexamples to find bugs and refine models. Use for formal verification, specification-driven validation or counterexample-guided debugging, rather than ordinary smoke testing.
---

# Formal Code Verification

Turn intended behavior into checkable properties, then search for violations in the actual implementation. Use the host agent for reasoning and existing project tools for execution. Natural-language reasoning and passing tests are evidence, not machine-checked proofs.

For tool choice, proof failures or model refinement, read [references/methods.md](references/methods.md). For cross-module properties and independent test oracles, read [references/examples.md](references/examples.md).

## Ground the specification

Trace the requested entry point, its callers, directly relevant callees, state ownership and failure paths. Keep the selected scope; add dependencies only when a property crosses that boundary. Account for indirect calls, callbacks and database/native-worker boundaries where they matter.

Derive desired behavior from explicit requirements, authoritative documentation and caller obligations before using the implementation as an explanation. Label inferred or disputed requirements. A passing existing test or a branch in the implementation is not an independent correctness oracle.

Write a small set of falsifiable obligations:

- **P — preconditions:** valid inputs, units, caller guarantees, authority and required state. State assumptions separately; do not exclude valid edge cases to make verification pass.
- **Q — postconditions:** exact success/result relation, error behavior and permitted effects. Include what must remain unchanged on failure.
- **I — invariants:** properties preserved across loops, retries, transitions and module boundaries.

Prefer predicates over “handles correctly.” State whether ranges are closed/half-open, arithmetic is bounded/overflowing, and text offsets are bytes, UTF-16 units, code points or graphemes. Check that P is satisfiable and includes meaningful valid examples.

Keep specifications as verification artifacts or tests. Analysis alone does not require new production schemas, runtime registries, execution routing or a coordination framework.

## Derive actual behavior and check it

Independently derive actual behavior **A**, including early exits and relevant callee effects, and compare it with intended **Q** under **P**. Invariant dependencies matter: establish input/state bounds before properties that rely on them; analyze mutually dependent invariants together.

Choose the lightest method that answers the obligation: focused deterministic tests, property/fuzz tests, state-machine exploration, SMT, or a source-language verifier. Reuse the repository harness and dependencies. Avoid duplicating equivalent tests or changing routine CI merely to run this skill.

When building an abstract model, map each modeled state/transition to actual source and identify omissions. Match language and library semantics; mathematical integers, sequential steps or string lengths may differ from the program. Prefer direct source verification when the supported tool is already available.

## Counterexample → execution → refinement

For each failure, record the violated obligation, input/state, relevant trace and source location. Check that state, trace and violation agree; a plausible story is insufficient.

Classify the failure before choosing the next action:

| Observation | Next action |
|---|---|
| Reachable actual behavior violates an independently grounded requirement | Run and minimize a reproducer against actual code; report a confirmed bug only after observing the violation. |
| Model fails but the trace cannot occur in the program | Refine the abstraction using the missing actual constraint; retain the original intended obligation. |
| Verifier cannot establish a proof obligation | Investigate missing/incorrect invariants, annotations, assumptions or solver limits; a proof failure alone is not a program bug. |
| Desired behavior is ambiguous or a required dependency cannot be exercised | Record the gap as unresolved and continue independent checks. Do not infer success. |

A loop-induction counterexample can start from an invariant-satisfying state that is unreachable from valid input. It may expose a weak invariant without exposing an executable defect.

Use the smallest faithful reproducer. A test against a simplified mock/model confirms that model only; a production defect needs the actual relevant implementation and boundary. Preserve input/seed, command, expected/actual observation, exit status and output. Infrastructure failure is not a reproduced bug.

Refine from evidence: add missing state, integer/text semantics, failure transitions, authority checks or asynchronous ordering. Explain each change and its source justification. Do not weaken Q, silently strengthen P, suppress assertions, or assume away a failing path. Change a disputed specification only with independently justified intent, with the old and new interpretation recorded.

If proof repair is requested, preserve executable behavior and user-supplied requirements; repair annotations/invariants and rerun the verifier. If bug fixing is authorized, fix the shared cause and retain the minimal failing regression. Verification alone does not authorize product edits, publishing, deployment or data mutation.

## Finish with evidence

Continue within the selected scope and a proportionate time/search budget while new evidence is being produced. Repeated unchanged failures, unavailable tools and exhausted bounds end as explicit gaps, not “no bugs.” Do not expand into repeated whole-repo runs by default.

Report the property, outcome, evidence method, commands/artifacts and remaining assumptions:

- **Confirmed defect:** actual execution violates a grounded obligation.
- **Checked model:** formal/model checker result, with domain, depth, transitions and abstraction limits.
- **Proved obligation:** source verifier accepted the obligation; identify covered code, assumptions and trusted/unverified dependencies.
- **Tested / reasoned / unresolved:** state what actually ran, what was only inspected, and what remains unsupported.

For SMT, check feasibility of preconditions and modeled transitions, including meaningful success/failure cases; distinguish an unsatisfiable violation query from timeout/unknown or a vacuous/inconsistent model. Tests, bounded search and model proofs do not establish whole-product correctness. Finish with the uncovered boundaries and next most useful check.
