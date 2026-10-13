# Hoare reasoning

Use the current function's parsed `Pre-condition` as the first block's
precondition. Split large functions at safe syntax boundaries (brace-aware for
braced languages; conservative fallback otherwise). For each block, derive its
postcondition from source, current precondition, the current function's
`.info.json` callee expectations, and domain context;
pass that postcondition as the next block's precondition.

Check each terminating block and the final block by asking whether there exists
a concrete valid input satisfying the derived actual postcondition A and
violating the specification postcondition B. In logical form, `MISMATCH`
requires `∃x. Pre(x) ∧ A(x) ∧ ¬B(x)`; `MATCH` requires the bounded reasoner to
establish `∀x. Pre(x) → (A(x) → B(x))`. A mismatch must retain a concrete
counterexample, one exact contiguous source quote, A, B, and the reason.
Malformed spec, model/tool failure, or unparseable output is `ERROR`, not
`MATCH` or `MISMATCH`; proceed with other functions.

Treat the native three-field sidecar as original FM-Agent's model-derived
condition B. Derive actual behavior A independently from the body. Verify receives
materialized copied requirements and permitted caller evidence. Check that a
counterexample satisfies P and the governing input domain. If that domain is
invalid or unclear, record a named gap rather than an invented negative output,
an unrelated witness or a weakened Q. Never turn
an observed constant, comparison, formula, field, or branch into its own proof
obligation or use it to reinterpret B. Use `INCONCLUSIVE` only after the Worker
names a genuine reasoning gap, not merely because no external prose exists.

The assigned Codex/Claude Worker is the reasoner; no local script calls a model
API. It writes one structured postcondition/spec result. On invalid output the
Coordinator requeues the same job under the configured retry bound (five total
attempts by default); do not infer a verdict from prose. Emit a verification
JSON object matching
[artifact-contract.md](artifact-contract.md): `MATCH` for a completed reasoned check,
`MISMATCH` for a reasoned local violation, `DEPENDENCY_RISK` when only a
callee's direct mismatch affects the caller's outcome, `INCONCLUSIVE` for an
unavailable or genuinely unresolvable contract, and `ERROR` for failure to reason. Do not
manufacture a caller `MISMATCH` solely from a callee result.

For an input parser/converter, reject a `MATCH` when its specification excludes
malformed input solely by assuming validity, while an in-scope caller can pass
unvalidated text or bytes. Re-open the specification using
[specification-rules.md](specification-rules.md)'s input-domain rule, then
check full-consumption and rejection paths as local behavior.

For every parser-identified loop, state the invariant and examine initialization,
preservation, normal exit, and relevant abrupt transfers. A direct mismatch may
be a failed preservation or exit obligation: record the failure and its concrete
witness, rather than inventing a successful proof or downgrading a grounded
violation merely because Q is false. The verifier checks evidence shape against
parsed loop identities; it does not machine-check these natural-language
arguments. Missing parser support or an unresolved obligation remains a gap.

Nested callable bodies belong to their own results. Python nested defaults,
decorators and annotations are considered in the defining owner; a top-level
callable's definition-time expressions belong to its enclosing definition flow,
not its invocation body. Comprehension clauses are loops. Switch-local breaks
are not loop exits, and unresolved exit targets such as goto remain explicit
capability gaps.

In `all_bugs` mode, continue after the first local mismatch and record each
independent candidate with its own witness and exact source quote. Completion
means all applicable paths were examined, not that every induction obligation
succeeded. Each candidate then owns separate dynamic validation authority.
