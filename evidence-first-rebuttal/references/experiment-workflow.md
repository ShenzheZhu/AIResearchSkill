# Rebuttal Experiment Workflow

Use this reference when reviewers ask for ablations, sensitivity checks, human validation, OOD tests, cost estimates, or other empirical additions.

## 1. Decide Whether the Experiment Is Needed

Create a small decision table before running anything:

| Reviewer issue | Current evidence | Missing causal/empirical piece | Candidate experiment | Cost/risk | Rebuttal use |
| --- | --- | --- | --- | --- | --- |

Run the experiment only if it can change the rebuttal in a concrete way. Good reasons:

- The reviewer explicitly says a claim rests on weak evidence.
- The requested result can be answered with a compact table.
- Existing paper evidence is not enough and a clarification alone would look evasive.
- A negative or mixed result can still support a scoped limitation.

Do not run it when the issue is only a definition, a figure-layout request, or a result already reported in the appendix.

## 2. Prefer Low-Cost Evidence First

Before training or launching annotation:

1. Search paper and appendix for an existing table or limitation.
2. Search local repo outputs, JSON/CSV files, logs, and visualization folders.
3. Run cheap descriptive analyses from existing data.
4. Only then consider new model inference, human validation, or training.

Keep derived outputs reproducible: put scripts in an analysis or rebuttal folder, write outputs as CSV/JSON/Markdown, and record the command that produced each table.

## 3. Preflight for Data Analyses

Before trusting a local analysis:

- Identify the exact source files.
- Confirm row counts match paper counts or explain the subset.
- Check unique IDs, duplicates, missing fields, and join keys.
- Keep train/test/eval splits aligned with the paper when the analysis compares models or judge variants.
- Save both raw output and a small Markdown table for the rebuttal.
- Re-run after code edits; do not copy stale numbers.

## 4. Preflight for Training or Ablations

Training is expensive and easy to misalign. Before opening a GPU:

1. Locate the paper's exact train/test split or the closest released split.
2. Locate the published checkpoint or baseline config if comparison to paper numbers matters.
3. Write expected counts: total instances, train/dev/test instances, labels per item, dimensions, and any filtering.
4. Write a preflight script that fails on count mismatch, missing files, wrong split, wrong label scale, or missing checkpoint.
5. Run CPU/package preflight first.
6. Run a tiny GPU smoke test that exercises data loading, tokenization, forward/backward pass, checkpoint save, and evaluation.
7. Only then launch the full run.

Do not let a smoke run become rebuttal evidence. Its only job is to catch package, path, memory, and schema failures.

## 5. Config Parity

When an ablation compares against the paper:

- Use the same held-out set whenever possible.
- Match the paper's model family, max length, target scale, dimensions, checkpoint-selection rule, and metric definitions.
- If a parameter differs for cost or runtime reasons, state the difference privately and decide whether it is reviewer-safe.
- Prefer best-checkpoint evaluation if the paper used best-checkpoint selection.
- Keep random seeds fixed for data construction. Multiple training seeds are useful but not required unless the reviewer asked about variance or the result is unstable.

If parity is impossible, frame the result as a diagnostic or sensitivity check, not as a replacement for the paper result.

## 6. Remote / GPU Runs

For remote training:

- Copy code, data, configs, and preflight scripts before opening a costly GPU.
- Record remote paths and output paths.
- Use environment setup commands only in the shell/session, not in committed files when they contain secrets.
- Never put API keys, SSH passwords, or tokens into repo files.
- Monitor logs for run name, step/epoch, GPU memory/utilization, eval metrics, checkpoint path, and errors.
- Do not modify a live run unless the user explicitly asks. Monitoring is read-only.

If a run fails, preserve logs and classify the failure: package/env, data/schema, OOM, config mismatch, checkpoint selection, or modeling result. Only modeling results belong in a rebuttal.

## 7. Human Validation

Use a small human study when a central claim could be a judge artifact or requires human preference evidence.

Design rules:

- Match conditions on obvious confounds such as topic, length, model, summary, or semantic similarity.
- Blind annotators to the condition label.
- Use clear Likert anchors and examples.
- Use 2-3 labels per item when budget is tight.
- Report number of items, labels per item, means, gaps, confidence intervals, and p-values if appropriate.
- State exactly which claim the study validates and which claims remain judge-based.

If using Prolific, use the separate `prolific-human-validation` skill for draft creation, pulling results, and aggregation.

## 8. Reporting Experiments in the Rebuttal

Every new experiment should produce one of:

- a compact Markdown table
- a one-paragraph result with sample size and metric
- a scoped limitation if results are mixed

Use this order:

1. Why the experiment addresses the reviewer concern.
2. What was held fixed and what varied.
3. Sample size and evaluation metric.
4. Result table.
5. Interpretation and scope.

Avoid causal language stronger than the design supports. For example, if a controlled-diversity analysis only preserves coarse cluster proportions, say "coarse viewpoint profile" rather than "viewpoint diversity is fully fixed."

## 9. Author / Coauthor Task Brief

When delegating, give a brief that a coauthor can execute:

```text
Task:
Reviewer issue:
Data/source:
Split:
Model/config:
Metrics:
Expected output:
Where to save logs/results:
How the rebuttal will use it:
Failure modes to check:
```

Keep it concrete. Do not ask a coauthor to "run the ablation" without naming the split, checkpoint, metric, and output table.
