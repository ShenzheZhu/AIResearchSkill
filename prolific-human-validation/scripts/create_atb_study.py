#!/usr/bin/env python3
"""Create a Prolific AI Task Builder draft study from a CSV and payload JSON."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import time
from typing import Any

import requests


API_ROOT = "https://api.prolific.com/api/v1"


class ProlificClient:
    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Token {token}", "Content-Type": "application/json"}
        )

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.request(method, f"{API_ROOT}{path}", timeout=60, **kwargs)
        if not response.ok:
            raise RuntimeError(f"{method} {path} failed: {response.status_code} {response.text}")
        if not response.text:
            return {}
        return response.json()

    def upload_csv(self, upload_url: str, csv_path: pathlib.Path) -> None:
        with csv_path.open("rb") as f:
            response = requests.put(
                upload_url,
                headers={"Content-Type": "text/csv"},
                data=f,
                timeout=120,
            )
        if not response.ok:
            raise RuntimeError(f"CSV upload failed: {response.status_code} {response.text}")


def fill_placeholders(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        for key, replacement in replacements.items():
            value = value.replace(f"{{{{{key}}}}}", replacement)
        return value
    if isinstance(value, list):
        return [fill_placeholders(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: fill_placeholders(item, replacements) for key, item in value.items()}
    return value


def wait_for_status(
    client: ProlificClient,
    path: str,
    target: str = "READY",
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = client.request("GET", path)
        status = last.get("status")
        print(f"{path}: {status}")
        if status == target:
            return last
        if status == "ERROR":
            raise RuntimeError(f"{path} entered ERROR state: {last}")
        time.sleep(5)
    raise TimeoutError(f"Timed out waiting for {path} to reach {target}. Last response: {last}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-csv", type=pathlib.Path, required=True)
    parser.add_argument("--payloads", type=pathlib.Path, required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--token-env", default="PROLIFIC_API_TOKEN")
    parser.add_argument("--ids-output", type=pathlib.Path, default=pathlib.Path("prolific_created_ids.json"))
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payloads = json.loads(args.payloads.read_text())
    replacements = {"WORKSPACE_ID": args.workspace_id}

    if args.dry_run:
        print("Dry run only. No API calls made.")
        print(f"Dataset CSV: {args.dataset_csv}")
        print(json.dumps(payloads, indent=2)[:4000])
        return

    token = os.environ.get(args.token_env)
    if not token:
        raise RuntimeError(f"Set {args.token_env} in the environment, or run with --dry-run.")
    client = ProlificClient(token)

    dataset_payload = fill_placeholders(payloads["dataset"], replacements)
    dataset = client.request("POST", "/data-collection/datasets", json=dataset_payload)
    dataset_id = dataset["id"]
    print(f"Created dataset: {dataset_id}")

    upload = client.request(
        "GET", f"/data-collection/datasets/{dataset_id}/upload-url/{args.dataset_csv.name}"
    )
    client.upload_csv(upload["upload_url"], args.dataset_csv)
    print("Uploaded dataset CSV")
    dataset_status = wait_for_status(client, f"/data-collection/datasets/{dataset_id}")

    replacements["DATASET_ID"] = dataset_id
    batch_payload = fill_placeholders(payloads["batch"], replacements)
    batch = client.request("POST", "/data-collection/batches", json=batch_payload)
    batch_id = batch["id"]
    print(f"Created batch: {batch_id}")

    client.request("POST", f"/data-collection/batches/{batch_id}/instructions", json=payloads["instructions"])
    print("Created batch instructions")
    client.request("POST", f"/data-collection/batches/{batch_id}/setup", json=payloads["setup"])
    print("Started batch setup")
    batch_status = wait_for_status(client, f"/data-collection/batches/{batch_id}")

    replacements["BATCH_ID"] = batch_id
    study_payload = fill_placeholders(payloads["study"], replacements)
    study_payload["project"] = args.project_id
    study = client.request("POST", "/studies/", json=study_payload)
    study_id = study["id"]
    print(f"Created draft study: {study_id}")

    if args.publish:
        client.request("POST", f"/studies/{study_id}/transition/", json={"action": "PUBLISH"})
        print(f"Published study: {study_id}")
    else:
        print("Not published. Review the draft in Prolific before launching.")

    out = {
        "workspace_id": args.workspace_id,
        "project_id": args.project_id,
        "dataset_id": dataset_id,
        "batch_id": batch_id,
        "study_id": study_id,
        "published": bool(args.publish),
        "dataset_total_datapoint_count": dataset_status.get("total_datapoint_count"),
        "batch_total_task_count": batch_status.get("total_task_count"),
        "batch_total_task_groups": batch_status.get("total_task_groups"),
    }
    args.ids_output.parent.mkdir(parents=True, exist_ok=True)
    args.ids_output.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {args.ids_output}")


if __name__ == "__main__":
    main()
