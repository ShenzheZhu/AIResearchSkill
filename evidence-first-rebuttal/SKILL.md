---
name: evidence-first-rebuttal
description: Draft, audit, and polish paper rebuttals for OpenReview or peer-review settings with reviewer-by-reviewer structure, evidence-grounded claims, scoped new experiments, Markdown-ready tables, page-limit handling, and direct non-sycophantic wording. Use when Codex is responding to reviewer weaknesses/questions, revising a rebuttal draft, deciding whether a requested experiment is necessary, or checking that rebuttal claims match local paper/repo evidence.
---

# Evidence-First Rebuttal

Use this skill when reviewers raise methodological, empirical, presentation, or scope concerns. Produce reviewer-facing text that is direct, evidence-backed, and clear about rebuttal-time constraints. Polish with agent-style without weakening claims.

## Core Workflow

1. Parse the reviews into an issue map.
   Preserve reviewer IDs. For each reviewer, split concerns into `Weaknesses` and `Questions` when the review has both; if the review only has weaknesses, do not invent a question section.

2. Build an evidence ledger before writing.
   Search the paper, appendix, repo outputs, logs, dashboards, and prior rebuttal drafts. Mark each claim as one of:
   - already in paper or appendix
   - available from local artifacts
   - quick analysis possible now
   - requires new experiment or author verification
   - impossible during rebuttal

3. Answer the reviewer first.
   Start each item with the concrete answer, then give evidence, then say what will change in the final revision. Do not start by proposing future work if current evidence already answers the concern.

4. Prefer scoped evidence over broad promises.
   If a reviewer asks for a large validation, decide whether a small targeted analysis can directly address the concern. If not, state the limitation and narrow the claim.

5. Audit before polishing.
   Check every reviewer issue is covered, no unrun experiment is implied, existing paper tables are referenced rather than duplicated, and final-revision quotes are concrete.

For the complete reviewer-facing Markdown format, read `references/rebuttal-format.md`.
For a detailed writing and audit checklist, read `references/rebuttal-checklist.md`.
For rebuttal experiments, ablations, human validations, or remote training, read `references/experiment-workflow.md`.
For final prose review with `agent-style`, read `references/agent-style-polish.md`.

## Evidence Rules

- Never present an unrun experiment, smoke test, or speculative result as completed.
- If a number comes from a local artifact, record the file/script/source while drafting. Re-run or re-open cheap sources rather than relying on memory.
- If a result is already in the paper or appendix, cite the existing table/section instead of reproducing the table unless the reviewer specifically needs a different slice.
- Distinguish direct evidence from indirect support. Example: a direct human validation of self-reported minority coverage does not automatically validate an embedding-outlier analysis.
- Do not overclaim causality from descriptive trends. If input size and diversity both change, say so and either run a controlled analysis or soften the interpretation.
- Treat conventional inter-annotator agreement carefully. If the task is personalized or perspectivist and exact items are singly labeled, do not turn same-summary or same-case ratings into true repeated-instance IAA.
- For OOD or generalization concerns, state the tested scope and limitation directly. A domain-aligned judge can be appropriate for a benchmark even if it is not topic-universal.

## Rebuttal Structure

Use this default Markdown shape:

```markdown
# Formal Rebuttal

## Response to Page-Limit / Presentation Concerns

## Response to Reviewer <ID>

### Weaknesses

**W1: Short label.** Direct answer. Evidence. Final-revision change.

### Questions

**Q1: Short label.** Direct answer. Evidence. Final-revision change.
```

Only include a global response if multiple reviewers raise the same high-level issue. Keep it short and then address details under the relevant reviewers.

## Final-Revision Text

When the rebuttal cannot modify the PDF immediately, separate current clarification from future paper text.

Use block quotes for exact text that can be moved into the final revision:

```markdown
> Policy-use acceptability measures whether a deliberation participant would approve of the summary being used for policy decision support. It is not an expert judgment of policy correctness.
```

Avoid vague process quotes such as "In the revised manuscript, we will clarify..." inside the quote. The quote should read like paper text.

## Markdown Constraints

- OpenReview rebuttals are usually Markdown-only. Use compact tables instead of figures.
- If a reviewer asks for larger figure fonts, layout moves, or extra main-text placement, say this will be handled in the final PDF revision.
- Keep tables narrow: short column names, 2-4 decimals where enough, and only the metrics needed for the concern.
- For existing paper results, write "Appendix X, Table Y reports..." rather than reprinting large tables.

## Tone

- Write as an equal scientific exchange, not as an apology.
- Avoid sycophancy: do not use "Thank you", "Your interpretation is exactly right", or excessive "We agree" framing.
- Use direct confirmations when needed: "Yes." or "This is a limitation."
- Do not concede more than the evidence requires. Prefer "This limits new-topic generalization" over "This undermines the evaluation."
- Do not hide limitations. State them, scope the claim, and explain why the remaining evidence still supports the paper contribution.

## Experiment Triage

Run or request new experiments only when they can materially change a reviewer decision.

Useful rebuttal experiments are usually:
- small direct human validations for a central claim
- ablations that isolate a reviewer-identified design choice
- sensitivity analyses that test whether a trend survives a confound
- descriptive statistics that clarify data composition, cost, or scale

Avoid opening expensive training or annotation work when:
- the result is already in the appendix
- the reviewer mainly needs a definition or design clarification
- the requested analysis cannot be completed reliably during rebuttal
- the evidence would only add a weak auxiliary claim

When an experiment is delegated to authors or coauthors, write a concrete task brief. Name the data split, model/config, metric, expected output table, and rebuttal use.

Before launching expensive experiments, complete a preflight checklist. Check the paper-matched split or sampling frame, expected row counts, baseline/checkpoint identity, metric definitions, config parity, output paths, and smoke test.

Do not use failed, off-split, or smoke-test results as reviewer-facing evidence.

## Common Response Patterns

- **Terminology confusion**: define the per-instance measurement and the aggregation/reporting procedure separately.
- **Crowd-worker expertise**: clarify what workers judge from observable text and what they are not asked to judge as domain experts.
- **Missing IAA**: explain the annotation unit; if exact repeated labels are absent, frame it as a limitation and cite process-level quality controls.
- **Judge reliability**: compare against relevant baselines, state in-domain and OOD scope, and avoid claiming universality.
- **Input-size plateau**: separate length, input count, and viewpoint diversity. If diversity is uncontrolled, call it diminishing marginal improvement under increasing coverage difficulty.
- **Pairwise comparison design**: explain whether pairs are same-size, same-question, same-source, or cross-scale, and why that choice matches training versus controlled A/B evaluation.
- **Data release/cost**: provide a concise artifact release policy and cost estimate when requested; mark items requiring author verification.

## Final Audit

Before giving the user a final rebuttal draft:

- Every reviewer weakness and question has a response.
- Reviewer-specific sections use the requested heading structure.
- Existing paper/appendix evidence is cited instead of duplicated unless a new slice is needed.
- All numeric claims have a source.
- No placeholders or TODOs remain unless the user explicitly asked to leave them.
- Any unfinished experiment is named as future work or author-side verification, not as a result.
- Limitations are scoped rather than fatalistic.
- Final-revision block quotes are actual paper-ready wording.
- The prose is direct and non-sycophantic.
- `agent-style` audit/polish has been run or consciously skipped, and any style edits preserve technical scope, numeric evidence, and reviewer coverage.

## Resources

- `references/rebuttal-checklist.md`: issue map, evidence ledger, experiment triage, and final audit checklist.
- `references/rebuttal-format.md`: complete working-draft and final OpenReview Markdown structure.
- `references/experiment-workflow.md`: how to decide, preflight, run, monitor, and report rebuttal experiments.
- `references/agent-style-polish.md`: how to run `agent-style` audit, compare, and polish safely for rebuttal prose.
