#!/usr/bin/env python3
"""Pull Prolific ATB study status, responses JSON, and batch report CSV."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import time

import requests


API_ROOT = "https://api.prolific.com/api/v1"


def api_get(session: requests.Session, path: str) -> dict:
    response = session.get(f"{API_ROOT}{path}", timeout=120)
    if not response.ok:
        raise RuntimeError(f"GET {path} failed: {response.status_code} {response.text}")
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", type=pathlib.Path, required=True)
    parser.add_argument("--token-env", default="PROLIFIC_API_TOKEN")
    parser.add_argument("--status-output", type=pathlib.Path, default=pathlib.Path("prolific_status.json"))
    parser.add_argument("--responses-output", type=pathlib.Path, default=pathlib.Path("prolific_responses.json"))
    parser.add_argument("--report-output", type=pathlib.Path, default=pathlib.Path("prolific_report.csv"))
    parser.add_argument("--report-timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    token = os.environ.get(args.token_env)
    if not token:
        raise RuntimeError(f"Set {args.token_env} in the environment.")
    ids = json.loads(args.ids.read_text())
    session = requests.Session()
    session.headers.update({"Authorization": f"Token {token}", "Content-Type": "application/json"})

    status = {
        "study": api_get(session, f"/studies/{ids['study_id']}/"),
        "batch": api_get(session, f"/data-collection/batches/{ids['batch_id']}"),
        "dataset": api_get(session, f"/data-collection/datasets/{ids['dataset_id']}"),
    }
    args.status_output.write_text(json.dumps(status, indent=2) + "\n")
    print(f"Wrote {args.status_output}")
    print(
        "Study:",
        status["study"].get("status"),
        "places",
        status["study"].get("places_taken"),
        "/",
        status["study"].get("total_available_places"),
    )
    print(
        "Batch tasks/groups:",
        status["batch"].get("total_task_count"),
        status["batch"].get("total_task_groups"),
    )

    responses = api_get(session, f"/data-collection/batches/{ids['batch_id']}/responses")
    args.responses_output.write_text(json.dumps(responses, indent=2) + "\n")
    print(f"Wrote {args.responses_output}")

    deadline = time.time() + args.report_timeout_seconds
    report = {}
    while time.time() < deadline:
        report = api_get(session, f"/data-collection/batches/{ids['batch_id']}/report/")
        if report.get("url"):
            break
        print(f"Report status: {report}")
        time.sleep(5)
    if not report.get("url"):
        raise TimeoutError(f"Batch report was not ready: {report}")
    download = requests.get(report["url"], timeout=120)
    if not download.ok:
        raise RuntimeError(f"Report download failed: {download.status_code} {download.text}")
    args.report_output.write_bytes(download.content)
    print(f"Wrote {args.report_output}")


if __name__ == "__main__":
    main()
