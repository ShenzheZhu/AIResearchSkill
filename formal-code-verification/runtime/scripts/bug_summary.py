#!/usr/bin/env python3
# Modified by AIResearchSkill: require verified durable receipts before counting Bug Validator outcomes.
"""Write the current Bug Validator summary from completed result reports."""
from __future__ import annotations

import argparse
import json

from _common import project, state


def write_summary(target, mode: str) -> dict:
    candidates = state.direct_candidates(target)
    reports = {}
    for identity in sorted(candidates):
        job = state.accepted_candidate(target, identity)
        reports[identity] = state.read_json(target / job["bug_result_path"], {})
    counts = {status: sum(report.get("confirmation_status") == status for report in reports.values()) for status in state.BUG_FINAL_STATUSES}
    summary = {
        "schema_version": 2,
        "snapshot_commit": state.current_snapshot_commit(target),
        "dynamic_validation": "completed",
        "total_candidates": len(candidates),
        "total_static_findings": 0,
        "static_finding_ids": [],
        **{f"total_{status}": count for status, count in counts.items()},
        "generated_at": state.now(),
    }
    state.atomic_json(state.fm_dir(target) / "bug_validation" / "summary.json", summary)
    ready, reason = state.bug_validation_ready(target, set(candidates))
    if not ready:
        raise ValueError(reason)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a current-snapshot FM-Agent Bug Validator summary.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--mode", required=True, choices=("full", "incremental"))
    args = parser.parse_args()
    try:
        print(json.dumps(write_summary(project(args), args.mode), ensure_ascii=False, indent=2))
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
