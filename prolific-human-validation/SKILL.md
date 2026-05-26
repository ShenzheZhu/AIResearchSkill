---
name: prolific-human-validation
description: Design, launch, monitor, pull, and analyze Prolific human-validation studies for AI research claims, benchmarks, rebuttals, and reviewer requests. Use when Codex needs Prolific API or AI Task Builder Batch workflows, scenario/failure realism validation, annotator rubric design, draft-study creation, result export, or Markdown tables for papers/rebuttals.
---

# Prolific Human Validation

Use this skill to turn reviewer concerns or benchmark-validation needs into a small, defensible Prolific study. Prefer Prolific AI Task Builder Batch (ATB) when each participant should label several structured items from a CSV.

## Workflow

1. Define the claim being validated.
   Be precise: scenario plausibility, multi-user specificity, failure-label validity, consequence severity, human preference, etc. Do not claim that a study validates real model outputs unless workers saw those exact outputs.

2. Create a Prolific-ready item CSV.
   Include visible task fields plus `META_` columns for analysis. Add a visible `Case ID` or unique visible text; ATB may merge rows with identical visible content.

3. Write worker instructions before launching.
   Include task purpose, definitions of what is shown, what workers should not judge, 1/3/5 anchors for each Likert scale, and one or two prestudy examples that calibrate ratings. For patterns, read `references/study-design.md`.

4. Create a draft study, not a published study.
   Use `scripts/create_atb_study.py`. Always pass explicit `--workspace-id` and `--project-id`; otherwise Prolific may attach the study to an unexpected default project.

5. Verify counts before publishing.
   Check dataset rows, batch task count, task groups, and study places. Expected places are normally `task_groups * annotators_per_task`, not the raw row count. If task count is lower than CSV rows, inspect duplicate visible content.

6. Pull results and analyze.
   Use `scripts/pull_atb_results.py` to download the ATB report CSV. Use `scripts/analyze_atb_report.py` to summarize wide ATB reports into mean ratings by condition.

## Commands

Create a draft ATB study:

```bash
export PROLIFIC_API_TOKEN='...'
python scripts/create_atb_study.py \
  --workspace-id 6419ed232a173e110e8e21f9 \
  --project-id 6a147c80006d958225c26440 \
  --dataset-csv reviewer_items.csv \
  --payloads payload_templates.json \
  --ids-output prolific_created_ids.json
```

Pull results:

```bash
python scripts/pull_atb_results.py \
  --ids prolific_created_ids.json \
  --report-output prolific_report.csv \
  --responses-output prolific_responses.json
```

Analyze a report:

```bash
python scripts/analyze_atb_report.py \
  --report prolific_report.csv \
  --metrics-json metrics.json \
  --output summary.csv
```

Example `metrics.json`:

```json
{
  "plausibility": ["plausible"],
  "multi_user_specificity": ["distinguishing multiple", "roles, permissions"],
  "failure_label_validity": ["violate the stated", "policy or goal"],
  "failure_severity": ["consequential"]
}
```

## Rules

- Never publish, approve, reject, or reallocate submissions unless explicitly asked.
- Never put Prolific tokens into files or committed command arguments.
- Use explicit workspace/project ids.
- Keep study names/version tags clear; delete bad unpublished drafts to avoid UI confusion.
- Report limitations honestly: sampled scenarios, representative failures, and actual model outputs are different validation targets.
- In rebuttals, prefer concise tables with `items`, `labels`, and per-dimension means; include percentage of ratings >= 4 when useful.

## Resources

- `references/study-design.md`: validation design, worker instruction checklist, and common pitfalls.
- `scripts/create_atb_study.py`: create dataset, upload CSV, create batch/instructions/setup, and create draft study.
- `scripts/pull_atb_results.py`: inspect status and download responses/report.
- `scripts/analyze_atb_report.py`: summarize ATB report CSV into rebuttal-ready tables.
