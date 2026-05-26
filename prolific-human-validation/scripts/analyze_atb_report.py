#!/usr/bin/env python3
"""Summarize a Prolific ATB report CSV into rebuttal-ready rating tables."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re

import pandas as pd


def to_score(value: object) -> float:
    if pd.isna(value):
        return float("nan")
    match = re.search(r"[1-5]", str(value))
    return float(match.group(0)) if match else float("nan")


def find_column(columns: list[str], patterns: list[str]) -> str:
    lowered = {column: column.lower() for column in columns}
    for pattern in patterns:
        pattern = pattern.lower()
        for column, lower in lowered.items():
            if pattern in lower:
                return column
    raise ValueError(f"Could not find column matching any of: {patterns}")


def metric_for_question(question: str, metric_patterns: dict[str, list[str]]) -> str | None:
    lower = question.lower()
    for metric, patterns in metric_patterns.items():
        if any(pattern.lower() in lower for pattern in patterns):
            return metric
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--metrics-json", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--long-output", type=pathlib.Path)
    parser.add_argument("--condition-column", default="META_SCENARIO_TYPE")
    parser.add_argument("--item-column", default="META_ANNOTATION_ITEM_ID")
    parser.add_argument("--threshold", type=float, default=4.0)
    args = parser.parse_args()

    report = pd.read_csv(args.report)
    metrics = json.loads(args.metrics_json.read_text())
    response_cols = [c for c in report.columns if c.startswith("Annotator") and c.endswith("_Response")]
    if "Question" not in report.columns or not response_cols:
        raise ValueError("Expected ATB wide report with Question and Annotator*_Response columns.")

    item_col = find_column(report.columns.tolist(), [args.item_column])
    condition_col = find_column(report.columns.tolist(), [args.condition_column])
    records: list[dict[str, object]] = []
    for _, row in report.iterrows():
        metric = metric_for_question(str(row["Question"]), metrics)
        if not metric:
            continue
        for response_col in response_cols:
            score = to_score(row[response_col])
            if pd.isna(score):
                continue
            records.append(
                {
                    "annotation_item_id": row[item_col],
                    "condition": row[condition_col],
                    "annotator_slot": response_col.replace("_Response", ""),
                    "metric": metric,
                    "score": score,
                }
            )

    long = pd.DataFrame(records)
    if long.empty:
        raise ValueError("No scored responses matched the provided metric patterns.")
    wide = (
        long.pivot_table(
            index=["annotation_item_id", "condition", "annotator_slot"],
            columns="metric",
            values="score",
            aggfunc="first",
        )
        .reset_index()
        .dropna()
    )

    rows = []
    for condition, group in list(wide.groupby("condition")) + [("overall", wide)]:
        row = {
            "condition": condition,
            "n_labels": len(group),
            "n_items": group["annotation_item_id"].nunique(),
        }
        for metric in metrics:
            values = group[metric]
            mean = values.mean()
            sd = values.std(ddof=1)
            ci = 1.96 * sd / math.sqrt(len(values)) if len(values) > 1 else float("nan")
            row[f"{metric}_mean"] = mean
            row[f"{metric}_sd"] = sd
            row[f"{metric}_ci95_halfwidth"] = ci
            row[f"{metric}_pct_ge_{int(args.threshold)}"] = (values >= args.threshold).mean() * 100
        rows.append(row)
    summary = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output, index=False)
    if args.long_output:
        wide.to_csv(args.long_output, index=False)
    print(summary.round(3).to_string(index=False))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
