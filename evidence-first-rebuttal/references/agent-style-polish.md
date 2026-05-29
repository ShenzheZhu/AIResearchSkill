# Agent-Style Polish for Rebuttals

Use this after reviewer coverage and evidence checks are complete. Style polish should improve clarity without changing claims, numbers, citations, or scope.

## 1. Confirm Availability

```bash
agent-style --version
agent-style list-tools
```

If unavailable, install or enable it outside the rebuttal artifact. Do not block the rebuttal on style tooling; use the manual checklist below as fallback.

## 2. Deterministic Audit

Run an audit before editing:

```bash
agent-style review formal_rebuttal.md --audit-only --json > formal_rebuttal.agent-style.audit.json
agent-style review formal_rebuttal.md --mechanical-only --json > formal_rebuttal.agent-style.mechanical.json
```

Use audit output to find mechanical style problems, but manually judge whether each edit is safe. Rebuttal prose often needs calibrated hedges, appendix references, and reviewer-specific repetition.

## 3. Polish Pass

Try the built-in polish mode when the host supports it:

```bash
agent-style review formal_rebuttal.md --polish
```

This may produce `formal_rebuttal.reviewed.md`. If `--polish` is unsupported or errors, use the audit JSON plus the rules below and patch the original manually.

Safe polish edits:

- cut filler: "it is important to note that", "in order to", "may potentially"
- replace vague terms with concrete ones: "factor" -> named variable or design choice
- split long sentences over about 30 words
- remove sycophancy: "Thank you", "Your interpretation is exactly right", repeated "We agree"
- remove casual em dashes; use commas, colons, or new sentences
- keep terminology consistent after a definition
- calibrate verbs: "supports", "suggests", "is consistent with", not "proves"

Unsafe polish edits:

- deleting a limitation because it sounds weak
- strengthening a claim beyond the experiment design
- changing numbers, p-values, sample sizes, table references, or appendix references
- replacing a precise method term with a smoother but less accurate synonym
- merging two reviewer-specific answers that need to stay separate

## 4. Compare Drafts

If polish creates a second file, compare before adopting it:

```bash
agent-style review formal_rebuttal.md --compare formal_rebuttal.reviewed.md --json > formal_rebuttal.agent-style.compare.json
diff -u formal_rebuttal.md formal_rebuttal.reviewed.md | less
```

Accept only edits that preserve:

- reviewer coverage
- evidence strength
- limitation scope
- block quotes intended for final paper text
- Markdown table formatting

## 5. Manual Rebuttal Style Checklist

Run these searches after the polish pass:

```bash
rg -n "Thank you|exactly right|Your interpretation|We agree" formal_rebuttal.md
rg -n "prove|fully validate|universal|ground truth|state-of-the-art|paradigm" formal_rebuttal.md
rg -n "Furthermore|Moreover|Additionally|In addition" formal_rebuttal.md
rg -n "—|–" formal_rebuttal.md
rg -n "TODO|PLACEHOLDER|\\[\\[|TBD|to verify" formal_rebuttal.md
```

Not every match is wrong. Decide match-by-match, especially for reviewer quotes, table labels, and paper titles.

## 6. Final Pass Order

Use this order near deadline:

1. Coverage audit: every reviewer issue answered.
2. Evidence audit: every number has a source.
3. Experiment audit: no failed/off-split/smoke result is presented as evidence.
4. Agent-style audit/polish.
5. Read the final answer as a reviewer: direct answer first, evidence second, revision promise last.

Do not let style edits reopen settled technical decisions. If a polished sentence becomes less precise, keep the original technical wording.
