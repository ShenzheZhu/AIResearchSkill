# Study Design Reference

## Validation Targets

Choose the narrowest target that answers the reviewer or paper claim:

| Target | Workers should see | Safe claim |
| --- | --- | --- |
| Scenario realism | Scenario text | Sampled scenarios are plausible. |
| Multi-user specificity | Scenario with roles/permissions/preferences | Tasks require tracking multiple users or principals. |
| Failure-label validity | Scenario plus concrete failure | Representative failures violate stated goals/policies. |
| Failure consequence | Scenario plus concrete failure | Failures would matter in practice. |
| Real model failure validation | Scenario plus actual model output | Sampled model outputs are valid/consequential failures. |

Do not conflate representative failure modes with real model-output validation.

## Recommended Item CSV

Use visible columns like:

- `scenario_title`
- `scenario_description`
- `assistant_failure` or `model_output`

Use hidden metadata columns with the `META_` prefix:

- `META_annotation_item_id`
- `META_source_id`
- `META_source_file`
- `META_scenario_type`
- `META_model`

Add a visible `Case ID: <id>` inside `scenario_description` if rows may have duplicate visible text. Prolific ATB can merge or drop visually identical rows during batch setup.

## Instruction Checklist

A good ATB introduction should tell workers:

1. What the study evaluates.
2. What each task contains.
3. What they should not judge, such as fluency or politeness when those are irrelevant.
4. What each rating dimension means.
5. To use only the information shown.
6. To use the full scale.
7. One or two prestudy examples with expected interpretation.

Example phrasing:

```html
<p>You will help us evaluate test cases for AI assistants that work with multiple people in workplace or collaboration settings.</p>
<p>Each task has two parts. First, the scenario describes a situation the assistant is supposed to handle. Second, the assistant failure describes one specific way the assistant could make a mistake.</p>
<p>Please do not rate whether the assistant sounds fluent, smart, or polite. Instead, judge whether the situation is realistic, whether it depends on multiple users or roles, whether the behavior is a mistake under the stated rules, and how serious the mistake would be in practice.</p>
```

## Prolific ATB Count Semantics

- Dataset rows are uploaded datapoints.
- Batch `total_task_count` is the number of tasks ATB generated after processing.
- Batch `total_task_groups` is the number of task bundles shown to participants.
- Study `total_available_places` is usually `total_task_groups * annotators_per_task`.
- If `total_task_count` is lower than CSV rows, check duplicate visible text, missing values, or unsupported data.

## API Workflow

1. `GET /workspaces/`
2. `GET /workspaces/{workspace_id}/projects/`
3. `POST /data-collection/datasets`
4. `GET /data-collection/datasets/{dataset_id}/upload-url/{filename}`
5. `PUT` the CSV to the returned S3 URL
6. Poll `GET /data-collection/datasets/{dataset_id}` until `READY`
7. `POST /data-collection/batches`
8. `POST /data-collection/batches/{batch_id}/instructions`
9. `POST /data-collection/batches/{batch_id}/setup`
10. Poll `GET /data-collection/batches/{batch_id}` until `READY`
11. `POST /studies/` with `data_collection_method: AI_TASK_BUILDER_BATCH`
12. After collection, `GET /data-collection/batches/{batch_id}/report/`

## Minimal Payload Template

`scripts/create_atb_study.py` expects a JSON file with `dataset`, `batch`, `instructions`, `setup`, and `study` keys. Use `{{WORKSPACE_ID}}`, `{{DATASET_ID}}`, and `{{BATCH_ID}}` placeholders; the script fills them.

```json
{
  "dataset": {
    "name": "Human validation dataset v1",
    "workspace_id": "{{WORKSPACE_ID}}"
  },
  "batch": {
    "name": "Human validation batch v1",
    "workspace_id": "{{WORKSPACE_ID}}",
    "dataset_id": "{{DATASET_ID}}",
    "task_details": {
      "task_name": "Rate AI-assistant scenarios",
      "task_introduction": "<p>Explain the task, definitions, and prestudy examples here.</p>",
      "task_steps": "<ol><li>Read the scenario.</li><li>Read the output or failure.</li><li>Answer all ratings.</li></ol>"
    }
  },
  "instructions": {
    "instructions": [
      {
        "order": 1,
        "type": "multiple_choice",
        "description": "How plausible is this scenario?",
        "helper_text": "1 = unrealistic; 3 = simplified but recognizable; 5 = very realistic.",
        "answer_limit": 1,
        "disable_dropdown": true,
        "options": [
          {"label": "1 - Very implausible", "value": "1"},
          {"label": "2 - Somewhat implausible", "value": "2"},
          {"label": "3 - Moderately plausible", "value": "3"},
          {"label": "4 - Plausible", "value": "4"},
          {"label": "5 - Very plausible", "value": "5"}
        ]
      }
    ]
  },
  "setup": {
    "tasks_per_group": 3
  },
  "study": {
    "name": "Rate AI-assistant scenarios",
    "internal_name": "human-validation-v1",
    "description": "<p>Short participant-facing description.</p>",
    "estimated_completion_time": 4,
    "maximum_allowed_time": 15,
    "reward": 100,
    "data_collection_method": "AI_TASK_BUILDER_BATCH",
    "data_collection_id": "{{BATCH_ID}}",
    "data_collection_metadata": {
      "annotators_per_task": 3
    }
  }
}
```

## Review Before Publishing

Before publishing, check:

- correct workspace and project
- `UNPUBLISHED` draft status
- expected task count and place count
- reward and estimated time
- worker-facing instructions render correctly
- at least one access link previews a representative task

Do not approve/reject submissions automatically during analysis unless the user explicitly asks.
