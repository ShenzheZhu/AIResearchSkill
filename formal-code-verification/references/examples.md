# Cross-module properties and independent oracles

These are candidate obligations for different projects. Ground them in the project's actual requirements and callers; do not assume every system has the same retry, ownership or text semantics.

| Flow | Possible obligation | Actual boundary to exercise |
|---|---|---|
| Save/retry | Content, revision, events and evidence commit atomically; failed requests leave no partial durable state. Identical retries create no duplicate effects. | Transaction owner, persistence and retry comparison, including failure before/after commit. |
| Provenance transformation | Surviving characters keep their origin during moves; duplicate text with different origins cannot exchange attribution. Source fragments reconstruct the projected text. | Transformation, source projection, persistence/reload and evidence rendering. |
| Exclusive ownership | One current owner; stale refresh/detach cannot change a replacement lease. | Claim/refresh/expire/detach and write admission across the actual atomic boundaries. |
| Asynchronous UI work | A result belongs to its captured document/request; switching context cannot redirect it. | Request creation, context switch, completion handler and state update. |
| Numeric/text range | Acceptance agrees with the intended mathematical range and offset unit, including boundaries. | Actual parser/checker plus caller validation and language integer/string semantics. |

## Numeric counterexample and model correspondence

Suppose a uint32 range checker accepts when start + length <= total. First ground the intended property: the entire half-open range must lie within [0,total], allowing an empty range at total.

An unbounded-integer model can hide a defect because addition cannot wrap. A bit-vector model matches uint32 arithmetic: start=4294967295, length=1, total=0 wraps the computed end to0. The model's violation must then be reproduced by calling the actual checker, not by asserting the Python model's output.

The overflow-safe candidate uses start <= total and length <= total-start. A solver may establish equivalence to the intended range for that encoding, but a handwritten encoding is still a model. Direct-code proof or actual-code differential tests are needed to connect it to implementation.

This is an illustrative defect, not a claim about any project's current code.

## Independent provenance oracle

Represent characters with distinct identity/source labels:

```text
block-a: same [s:a-human, a:a-human, m:a-human, e:a-human]
block-b: same [s:b-agent, a:b-agent, m:b-agent, e:b-agent]
```

After swapping blocks, assert the labels move with their characters. Do not derive the expected source from identical text or use the implementation's diff as the oracle. Add Unicode, nesting, split/merge and Undo/Redo where they test distinct obligations. Distinguish content characters from structural separators.

Follow the affected cross-module boundary rather than proving just one helper:

```text
native operation → projected text + source → atomic save → reload → evidence
```

Movement may preserve text and writing volume while legitimately producing a structural event or revision. Determine these semantics independently; “no new text” does not necessarily mean “no recorded event.”

## State model versus real execution

A lease model can explore claim/refresh/expire/detach/write ordering. Match actual atomic operations and replay relevant traces through the real storage boundary. A model alone cannot establish database rollback, Redis atomicity or actual lock ordering.

For a delayed completion, a small reachable trace is often enough:

```text
begin request for A → switch context to B → complete A
```

Assert both A's result and B's unchanged state. Looking only at a successful return code misses the cross-module error.

For proof debugging, consider a loop whose actual variable stays nonnegative while an incomplete invariant says only x<=10. An inductiveness query can choose x=-1. That state may reveal a missing lower-bound invariant but not a reachable runtime failure. Add the justified invariant and rerun initialization/preservation/postcondition checks; do not “fix” correct executable code based on the impossible trace.

Formal checks complement concrete integration/browser tests. Keep signing, export, rendering, network/storage behavior and other unmodeled boundaries explicitly separate.
