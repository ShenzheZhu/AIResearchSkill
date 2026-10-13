#!/usr/bin/env python3
"""Apply native Worker selections and contract changes; preserve proof origins."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import project, state


def decision_path(target: Path) -> Path:
    return state.control_dir(target) / "incremental_decision.json"


def decision(target: Path) -> dict:
    data = state.read_json(decision_path(target), {})
    if not isinstance(data, dict) or data.get("snapshot_commit") != state.current_snapshot_commit(target):
        raise ValueError("incremental decision is missing or belongs to another snapshot")
    for key in ("included", "excluded", "review", "pending_review", "pending_reconcile", "reviewed"):
        data.setdefault(key, {})
        if not isinstance(data[key], dict):
            raise ValueError(f"incremental decision has invalid {key} map")
    data.setdefault("processed_jobs", [])
    return data


def save(target: Path, data: dict) -> None:
    data["generated_at"] = state.now()
    state.atomic_json(decision_path(target), data)


def functions(target: Path) -> dict:
    return {item["id"]: item for item in (state.source_index(target) or {}).get("functions", [])}


def validate_selection(target: Path, payload: dict, allowed_ids: set[str] | None = None) -> None:
    if not isinstance(payload, dict):
        raise ValueError("selection record must be a JSON object")
    selected, excluded = payload.get("selected_function_ids"), payload.get("excluded_function_ids")
    if not isinstance(selected, list) or not isinstance(excluded, list) or not all(isinstance(item, str) for item in selected + excluded):
        raise ValueError("selection requires selected_function_ids and excluded_function_ids string arrays")
    if len(set(selected + excluded)) != len(selected + excluded):
        raise ValueError("selection IDs must be unique and disjoint")
    known = set(functions(target)) if allowed_ids is None else allowed_ids
    if set(selected + excluded) != known:
        raise ValueError("selection must account for every assigned function exactly once")


def merge_selection(target: Path, record: Path, default_reason: str) -> dict:
    payload = state.read_json(record, {})
    validate_selection(target, payload)
    data = decision(target)
    for function_id in payload["selected_function_ids"]:
        data["review"][function_id] = default_reason
        data["pending_review"][function_id] = default_reason
    for function_id in payload["excluded_function_ids"]:
        if function_id not in data["included"]:
            data["excluded"][function_id] = "unchanged"
    data["selection_complete"] = True
    save(target, data)
    return data


def validate_plan(target: Path, plan: dict, assigned: list[str] | None = None) -> list[tuple]:
    updates = plan.get("sidecar_updates") if isinstance(plan, dict) else None
    if not isinstance(updates, dict) or assigned is not None and set(updates) != set(assigned):
        raise ValueError("plan must review exactly its assigned artifacts in sidecar_updates")
    root = (state.fm_dir(target) / "extracted_functions").resolve()
    known = {item["artifact"] for item in functions(target).values()}
    prepared = []
    for rel, update in updates.items():
        if rel not in known or not isinstance(update, dict):
            raise ValueError(f"invalid sidecar update: {rel}")
        artifact = (root / rel).resolve()
        if root not in artifact.parents or not artifact.is_file():
            raise ValueError(f"plan references missing extracted artifact: {rel}")
        spec, info = state.canonical_spec(update.get("spec"))[0], state.canonical_info(update.get("info"))[0]
        if spec is None or info is None:
            raise ValueError(f"plan update does not convert to native spec/info: {rel}")
        prepared.append((rel, artifact, spec, info))
    return prepared


def invalidate(target: Path, data: dict, function_id: str, reason: str) -> None:
    item = functions(target)[function_id]
    data["included"][function_id] = reason
    data["excluded"].pop(function_id, None)
    result = state.fm_dir(target) / "logic_verification_results" / Path(item["artifact"]).with_suffix(".json")
    result.unlink(missing_ok=True)
    path = state.control_dir(target) / "retained_evidence.json"
    retained = state.read_json(path, {})
    if isinstance(retained.get("functions"), dict) and function_id in retained["functions"]:
        retained["functions"].pop(function_id)
        state.atomic_json(path, retained)


def caller_context(target: Path, artifact: str) -> dict:
    root = state.fm_dir(target) / "extracted_functions"
    edges = state.read_json(state.control_dir(target) / "graph_edges.json", {}).get("edges", [])
    callers = {edge["caller_artifact"] for edge in edges if edge.get("callee_artifact") == artifact}
    return {rel: {"spec": state.read_json(Path(f"{root / rel}.spec.json"), None),
                  "info": state.read_json(Path(f"{root / rel}.info.json"), None)} for rel in sorted(callers)}


def _propagate(target: Path, data: dict, function_id: str, old_spec: dict | None, old_info: dict | None, spec: dict, info: dict) -> None:
    indexed = functions(target)
    by_artifact = {value["artifact"]: key for key, value in indexed.items()}
    artifact = indexed[function_id]["artifact"]
    edges = state.read_json(state.control_dir(target) / "graph_edges.json", {}).get("edges", [])
    if spec != old_spec:
        for edge in edges:
            caller = by_artifact.get(edge.get("caller_artifact"))
            if edge.get("callee_artifact") == artifact and caller:
                invalidate(target, data, caller, "callee-spec-change")
                data["pending_reconcile"][caller] = "callee-spec-change"
    if info != old_info:
        for edge in edges:
            callee_id = by_artifact.get(edge.get("callee_artifact"))
            if edge.get("caller_artifact") != artifact or not callee_id:
                continue
            item = indexed[callee_id]
            callee_spec = state.read_json(Path(f"{state.fm_dir(target) / 'extracted_functions' / item['artifact']}.spec.json"), {})
            names = {callee_id, callee_id.split("::")[-1], item.get("name"), item.get("symbol")}
            def expected(value):
                return [entry for entry in (value or {}).get("callees", [])
                        if entry.get("name") in names or entry.get("signature") == callee_spec.get("signature")]
            before, after = expected(old_info), expected(info)
            if before != after or not before and not after:
                data["review"][callee_id] = "caller-expectation-change"
                data["pending_review"][callee_id] = "caller-expectation-change"


def _record_updates(target: Path, data: dict, reviewed: list[str], changed: list[str], job_id: str | None) -> dict:
    report = state.fm_dir(target) / "incremental_updated_specs.json"
    prior = state.read_json(report, {})
    artifacts = set(prior.get("artifacts", [])) | set(changed)
    reviews = set(prior.get("reviewed_artifacts", [])) | set(reviewed)
    if job_id:
        data["processed_jobs"].append(job_id)
    data["update_complete"] = False
    save(target, data)
    result = {"schema_version": 1, "snapshot_commit": state.current_snapshot_commit(target),
              "generated_at": state.now(), "artifacts": sorted(artifacts),
              "reviewed_artifacts": sorted(reviews), "update_complete": False}
    state.atomic_json(report, result)
    return {"applied": len(changed), "artifacts": changed, "reviewed_artifacts": reviewed}


def apply_plan(target: Path, plan_path: Path, assigned: list[str] | None = None, job_id: str | None = None) -> dict:
    prepared = validate_plan(target, state.read_json(plan_path, {}), assigned)
    data = decision(target)
    if job_id and job_id in data["processed_jobs"]:
        return {"applied": 0, "already_applied": True}
    by_artifact = {item["artifact"]: key for key, item in functions(target).items()}
    ticket = state.read_json(state.control_dir(target) / "dispatches" / f"{job_id}.json", {}) if job_id else {}
    stale_context = {rel for rel, _, _, _ in prepared if job_id and
                     ticket.get("caller_context", {}).get(rel) != caller_context(target, rel)}
    changed, reviewed = [], []
    # Remove the whole frontier first; propagation may legitimately revisit one
    # of these functions after a sibling caller's expectations change.
    for rel, _, _, _ in prepared:
        data["pending_review"].pop(by_artifact[rel], None)
        data["pending_reconcile"].pop(by_artifact[rel], None)
    for rel, artifact, spec, info in prepared:
        function_id = by_artifact[rel]
        old_spec, old_info = state.read_json(Path(f"{artifact}.spec.json"), None), state.read_json(Path(f"{artifact}.info.json"), None)
        if spec != old_spec or info != old_info:
            state.atomic_json(Path(f"{artifact}.spec.json"), spec)
            state.atomic_json(Path(f"{artifact}.info.json"), info)
            invalidate(target, data, function_id, "spec-change" if spec != old_spec else "info-change")
            _propagate(target, data, function_id, old_spec, old_info, spec, info)
            changed.append(rel)
        data["reviewed"][function_id] = {"spec": spec, "info": info, "job_id": job_id}
        if rel in stale_context:
            data["pending_review"][function_id] = "caller-context-change"
        reviewed.append(rel)
    return _record_updates(target, data, reviewed, changed, job_id)


def reconcile(target: Path, job: dict, before: dict) -> dict:
    data = decision(target)
    if job["id"] in data["processed_jobs"]:
        return {"already_applied": True}
    function_id = job["input"]["function_id"]
    rel = functions(target)[function_id]["artifact"]
    artifact = state.fm_dir(target) / "extracted_functions" / rel
    spec, info = state.read_json(Path(f"{artifact}.spec.json"), None), state.read_json(Path(f"{artifact}.info.json"), None)
    if spec != before["spec"]:
        raise ValueError("caller reconciliation changed its read-only specification")
    data["pending_reconcile"].pop(function_id, None)
    changed = []
    if info != before["info"]:
        invalidate(target, data, function_id, "callee-info-change")
        _propagate(target, data, function_id, spec, before["info"], spec, info)
        changed.append(rel)
    return _record_updates(target, data, [], changed, job["id"])


def finish_updates(target: Path) -> dict:
    data = decision(target)
    if data["pending_review"] or data["pending_reconcile"]:
        raise ValueError("incremental contract frontiers have not converged")
    data["update_complete"] = True
    save(target, data)
    report = state.read_json(state.fm_dir(target) / "incremental_updated_specs.json", {})
    report.update(schema_version=1, snapshot_commit=state.current_snapshot_commit(target), generated_at=state.now(), update_complete=True)
    report.setdefault("artifacts", [])
    report.setdefault("reviewed_artifacts", [])
    state.atomic_json(state.fm_dir(target) / "incremental_updated_specs.json", report)
    return report


def accepted_output_job(target: Path, path: Path, kind: str) -> dict:
    import scheduler
    try:
        relative = path.resolve().relative_to(target.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("incremental application requires an assigned output inside the analysis checkout") from exc
    phase = "select_scope" if kind == "select_relevant_files" else "update_specs"
    matches = [job for job in scheduler.current_jobs_for_phase(target, phase)
               if job["type"] == kind and job["status"] == "succeeded" and job["required_outputs"] == [relative]]
    if len(matches) != 1:
        raise ValueError("incremental application requires one accepted current Worker output")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("merge-selection", "apply-plan", "show"))
    parser.add_argument("--project", required=True); parser.add_argument("--record"); parser.add_argument("--plan"); parser.add_argument("--reason")
    args = parser.parse_args(); target = project(args)
    try:
        if args.action == "merge-selection":
            if not args.record or not args.reason: parser.error("merge-selection requires --record and --reason")
            record_path = Path(args.record)
            record_path = record_path if record_path.is_absolute() else target / record_path
            accepted_output_job(target, record_path, "select_relevant_files")
            result = merge_selection(target, record_path, args.reason)
        elif args.action == "apply-plan":
            if not args.plan: parser.error("apply-plan requires --plan")
            plan_path = Path(args.plan)
            plan_path = plan_path if plan_path.is_absolute() else target / plan_path
            job = accepted_output_job(target, plan_path, "incremental_spec_plan")
            result = apply_plan(target, plan_path, job["artifacts"], job["id"])
        else: result = decision(target)
        code = 0
    except (OSError, ValueError) as exc:
        result, code = {"ok": False, "error": str(exc)}, 2
    print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(code)


if __name__ == "__main__": main()
