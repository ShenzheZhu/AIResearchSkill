# Rebuttal Checklist

Use this checklist when auditing or rebuilding a rebuttal draft.

## 1. Issue Map

For each reviewer, extract:

| Field | What to capture |
| --- | --- |
| Reviewer ID | Exact ID or label from the review |
| Score/confidence | If available |
| Main accept reasons | Preserve what the reviewer already values |
| Weaknesses | Method, evidence, writing, scope, missing experiment |
| Questions | Concrete questions, one row each |
| Desired evidence | Definition, table, ablation, human validation, appendix citation, limitation |
| Rebuttal status | answered / needs data / author verification / impossible during rebuttal |

Do not merge distinct reviewer concerns too early. Similar issues can share evidence, but each reviewer should still receive a local answer.

## 2. Writing Procedure

Draft in this order:

1. **Global response only if needed.**
   Use it for cross-reviewer issues such as page limits, Markdown-only rebuttal constraints, or broad scope clarification. Keep it short.

2. **Reviewer section.**
   Use the reviewer ID and preserve their concern labels internally. If the review has both weaknesses and questions, use `### Weaknesses` and `### Questions`. If it does not, do not invent headings that imply missing review structure.

3. **One concern per paragraph/table.**
   Start with a short bold label, then answer directly. A good unit is:

   ```markdown
   **W2: OOD scope of the judge.** The judge is not intended as a topic-universal evaluator. Appendix J.3 reports lower correlations on two unseen topics, so we will move this result into the limitations and describe the judge as domain-aligned for this benchmark and nearby topics.
   ```

4. **Definition before defense.**
   If a reviewer is confused by a term, define the object first, then explain the experiment. Do not make them infer notation from later paragraphs.

5. **Evidence before promise.**
   Put current evidence or appendix references before final-revision commitments. Use promises only after the answer is clear.

6. **Paper-ready quote when useful.**
   For terminology or limitation fixes, add a block quote that could be copied into the paper. Do not put process language inside that quote.

7. **Scope the answer.**
   Say exactly what the evidence supports and what it does not support. This is stronger than vague reassurance.

Good response shape:

```markdown
**Q5: Evaluating summaries without full source opinions.** Annotators did not perform an exhaustive source-grounded audit. Each participant first wrote their own opinion and then judged whether the summary reflected that perspective. Informativeness, neutrality, and policy-use acceptability are participant-level perceptions of the summary, while representativeness is conditioned on the participant opinion. We will state this annotation unit explicitly.
```

Avoid this shape:

```markdown
We thank the reviewer and agree this is an important question. We will clarify this in the revision.
```

The second version sounds polite but does not answer the methodological concern.

## 3. Evidence Ledger

Prefer evidence in this order:

1. Main paper table/figure/definition already visible to reviewers.
2. Appendix table/section already visible to reviewers.
3. Local repo artifact, script output, log, or dataset statistic.
4. New quick analysis that can be reproduced from available files.
5. New human validation or training run, only if central to the decision.
6. Limitation/future revision statement if evidence cannot be produced now.

For each numeric claim, keep a private note of:

```text
claim:
source file / table / script:
command or query:
sample size:
scope limitation:
```

## 4. When Not To Redraw Tables

Do not duplicate a table if:
- the same result is already in the paper or appendix
- the reviewer only needs to be pointed to the right location
- reprinting the table consumes rebuttal space without adding a new analysis

Do include a new compact table if:
- the reviewer asks for a per-dimension breakdown hidden by an aggregate
- the rebuttal adds a new ablation or validation
- the existing table is too broad and the reviewer needs a targeted slice

## 5. Experiment Decision Rules

Run a new experiment only if all are true:

- It targets a specific reviewer concern.
- The result can be completed and checked before rebuttal deadline.
- The output is a simple table or concise statistic.
- The interpretation is robust enough that a negative or mixed result can still be written honestly.

Otherwise, respond with clarification, appendix evidence, or a scoped limitation.

## 6. Designing Small Rebuttal Experiments

For a human validation:
- define the exact claim being validated
- blind annotators to the condition if possible
- match items on obvious confounds
- use 2-3 labels/item when budget is tight
- report items, labels/item, means, gap, confidence interval, and p-value if appropriate
- state exactly which part of the paper claim it validates

For an ablation:
- preserve the paper split/config where possible
- compare one design choice at a time
- evaluate on the same held-out set as the paper if possible
- report both central metrics and failure diagnostics when a model collapses
- avoid causal claims that the ablation cannot support

For a sensitivity analysis:
- identify the confound
- construct the most direct controlled comparison possible
- report whether the original interpretation changes
- soften language if the analysis supports a weaker claim

## 7. Rebuttal-Only vs Paper-Revision Wording

Use rebuttal prose for current constraints:

```markdown
Because the rebuttal cannot revise the PDF, we clarify the design here and will move this definition into the main text in the final revision.
```

Use block quotes for paper-ready text:

```markdown
> Representativeness is measured at the `(summary, participant opinion)` level. Model-level scores are obtained by aggregating these per-opinion scores across summaries, questions, generations, and input-size conditions.
```

Do not put meta-commentary inside the block quote.

## 8. Scope-Safe Language

Use:
- "domain-aligned evaluator for this benchmark and nearby topics"
- "diminishing marginal improvement under increasing coverage difficulty"
- "process-level annotation quality controls"
- "directly supports this subset of the claim"
- "secondary evidence"
- "we will report this as a limitation"

Avoid:
- "universal evaluator"
- "proves"
- "fully validates"
- "inter-annotator agreement" when exact repeated labels are absent
- "reviewer is correct" as a blanket concession
- "we believe" without evidence

## 9. Final Coverage Audit

Before finalizing, run these checks:

```bash
rg -n "TODO|PLACEHOLDER|\\[\\[|to verify|need to|TBD" rebuttal.md
rg -n "Thank you|exactly right|Your interpretation|We agree" rebuttal.md
rg -n "universal|prove|fully validate|ground truth" rebuttal.md
```

Then manually verify:

- One section per reviewer.
- Weakness and question headings match the review structure.
- No invented question section for reviewers without explicit questions.
- Every table has a purpose and a source.
- Existing paper tables are referenced by location when possible.
- New analyses are not mixed with old appendix evidence.
- Page-limit concerns are handled globally and locally where relevant.
- The final response is concise enough for the platform or consciously left long for author editing.
