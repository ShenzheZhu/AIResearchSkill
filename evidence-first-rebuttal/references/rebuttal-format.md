# Rebuttal Format

Use this as the default structure for OpenReview-style rebuttals. It separates the messy author working draft from the final reviewer-facing Markdown.

## 1. File Roles

Use two files when the rebuttal is complex:

- `rebuttal.md`: working notes, reviewer issue map, TODOs, author-side experiment plans, raw tables, and unresolved verification.
- `formal_rebuttal.md`: final OpenReview-facing response. It should contain no raw TODOs, no private notes, and no unsupported claims.

Keep numbers synchronized between the two files. If an experiment is unfinished, it belongs in `rebuttal.md`, not in the final response.

## 2. Final Markdown Skeleton

```markdown
# Formal Rebuttal

## Response to Page-Limit / Presentation Concerns

[Use only if multiple reviewers raised density, clarity, or page-limit issues.
State that the paper is comprehensive, the rebuttal cannot revise the PDF,
and the final revision will move key clarifications into the main text or limitations.]

## Response to Reviewer <ID>

[Optional one-sentence local framing if this reviewer repeatedly asks for clarity,
scope, or methodological details.]

### Weaknesses

**W1: <short concern label>.** <Direct answer. Current evidence or appendix reference.
Scope/limitation if needed. Final-revision change if needed.>

> <Optional paper-ready text that can be copied into the final revision.>

| <Compact table if needed> |  |
| --- | ---: |
| <row> | <value> |

**W2: <short concern label>.** <Direct answer...>

### Questions

**Q1: <short question label>.** <Direct answer. Evidence. Revision action.>

**Q2: <short question label>.** <Direct answer. Evidence. Revision action.>

## Response to Reviewer <ID>

...
```

## 3. Reviewer Section Rules

- Preserve reviewer IDs exactly enough for authors to map responses back to OpenReview.
- If the review has explicit `Reasons To Reject` and `Questions To Authors`, use `### Weaknesses` and `### Questions`.
- If the review has weaknesses but no explicit question section, use only `### Weaknesses` or `### Weaknesses and Clarifications`.
- Do not invent a question section for a reviewer who did not ask questions.
- Keep accept reasons in mind, but do not spend rebuttal space thanking the reviewer for them unless the venue expects it.

## 4. Global Page-Limit Response

Use a global response only when several reviewers say the paper is dense or unclear because of a short page limit.

Good shape:

```markdown
## Response to Page-Limit Concerns

Several reviewers note that the 9-page submission compresses too much information. The density reflects the scope of the work: [dataset], [model/judge], [benchmark], and [analysis]. The rebuttal cannot revise the PDF, so we clarify the main design points below. In the final revision, the additional page allowance will let us move key clarifications into the main text and limitations. We ask reviewers to assess the contribution and evidence separately from presentation constraints that can be fixed in revision.
```

Adapt the bracketed phrases to the paper. Do not overuse this paragraph. Reviewer-specific details still need local answers.

## 5. Standard Response Unit

Each concern should fit this pattern:

```markdown
**W3: <issue>.** <Answer first.> <Evidence or source.> <Interpretation.> <Revision action or limitation.>
```

Order matters:

1. Direct answer.
2. Evidence or existing paper reference.
3. Scope/limitation.
4. Final-revision change.

Do not start with "We agree" or "Thank you" unless the user explicitly wants a softer tone.

## 6. Paper-Ready Quotes

Use block quotes for text that could appear in the revised paper.

Good:

```markdown
> Policy-use acceptability measures whether a deliberation participant would approve of the summary being used by policymakers as a representation of the deliberation. It is not intended to measure whether the underlying policy is correct.
```

Bad:

```markdown
> In the revised manuscript, we will clarify that policy approval means policy-use acceptability.
```

The quote should be manuscript text, not a promise about the manuscript.

## 7. Tables

Use tables for new or targeted rebuttal evidence:

```markdown
| Model | Training labels | Test labels | n | Avg. Spearman | Norm. MAE |
| --- | --- | --- | ---: | ---: | ---: |
| Full model | direct + comparison-derived | direct rating only | 900 | **0.731** | **0.067** |
| Rating-only | direct rating only | direct rating only | 900 | 0.286 | 0.090 |
```

Do not redraw an existing paper table unless the reviewer needs a targeted slice. Prefer:

```markdown
Appendix J.2, Table 8 already reports the backbone comparison under the same split and hyperparameter search. We will move the relevant conclusion into the main limitations.
```

## 8. Common Section Types

### Method Clarification

```markdown
**W1: <term/design confusion>.** <Definition.> <Why the design is used.> <What evidence or appendix section supports it.> <Paper-ready wording if useful.>
```

### Missing Experiment or Validation

```markdown
**W2: <missing validation>.** <Whether current paper already has evidence.> <If not, describe the small new experiment or why it is infeasible during rebuttal.> <Report compact result or limitation.>
```

### Reviewer Asks for a Figure or Layout Change

```markdown
**Q4: Figure readability.** The rebuttal interface cannot modify the submitted PDF. We will enlarge the figure font in the revised PDF.
```

### OOD or Generalization Concern

```markdown
**W3: OOD scope.** The evaluator should not be read as topic-universal. <Existing OOD evidence or limitation.> <Narrow intended use.> <Final-revision change.>
```

### Annotation Reliability

```markdown
**W4: Annotation reliability.** <Define the annotation unit.> <Explain whether repeated-instance IAA applies.> <Describe process-level quality controls.> <State limitation if exact repeated labels are absent.>
```

## 9. Final Review Checklist

Before posting:

- The global response is short and only used when needed.
- Each reviewer has a distinct section.
- Each reviewer with questions has `### Weaknesses` and `### Questions`.
- Reviewers without explicit questions do not get an invented question section.
- Each concern starts with a bold label.
- Existing paper evidence is cited by section/table instead of duplicated.
- New rebuttal experiments have sample size, metric, source, and scope.
- PDF-only fixes are clearly marked as final-revision actions.
- Paper-ready quotes contain manuscript text, not process language.
- No private TODOs, placeholders, API keys, or author-only notes remain.
- `agent-style` polish did not change numeric claims, scope, or reviewer coverage.
