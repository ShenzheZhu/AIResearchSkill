#!/usr/bin/env python3
# Modified by AIResearchSkill: preserve snapshot identity, require accepted evidence and expose reasoning/business gaps.
"""The sole deterministic authority for terminal FM-Agent reporting."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import project, state
import checkpoint
from isolation import marker


def _phase_manifests(target: Path) -> list[dict]:
    phases = checkpoint.root(target) / "phases"
    values = [state.read_json(path, {}) for path in sorted(phases.glob("*.json"))] if phases.is_dir() else []
    return [
        value for value in values
        if isinstance(value, dict) and value.get("schema_version") == checkpoint.CHECKPOINT_SCHEMA_VERSION
    ]


def _analysis_target(target: Path) -> Path:
    """Read live artifacts from the isolated snapshot when it still exists."""
    data = marker(target)
    snapshot = data.get("snapshot") if isinstance(data, dict) else None
    if isinstance(snapshot, str) and Path(snapshot).is_dir():
        return Path(snapshot).resolve()
    return target


def _verification_results(target: Path, snapshot_commit: str) -> list[dict]:
    root = state.fm_dir(target) / "logic_verification_results"
    index = state.source_index(target) or {}
    functions = {
        item.get("artifact"): item for item in index.get("functions", [])
        if isinstance(item, dict) and isinstance(item.get("artifact"), str)
    }
    results = []
    for path in sorted(root.rglob("*.json")) if root.is_dir() else []:
        relative = path.relative_to(root).with_suffix("").as_posix()
        item = functions.get(relative) or functions.get(relative + path.suffix)
        if item is None:
            # Result paths are formed by replacing the extracted artifact
            # suffix, so compare against that canonical transformation.
            item = next((
                value for artifact, value in functions.items()
                if Path(artifact).with_suffix(".json").as_posix() == path.relative_to(root).as_posix()
            ), None)
        payload = state.read_json(path, None)
        if not isinstance(item, dict) or not isinstance(payload, dict):
            continue
        artifact = state.fm_dir(target) / "extracted_functions" / item["artifact"]
        valid, _ = state.verification_result_ready(target, artifact, item.get("id"), payload, snapshot_commit)
        if valid and payload.get("snapshot_commit") == snapshot_commit:
            results.append(payload)
    return results


def _bug_results(target: Path, snapshot_commit: str, candidates: set[str]) -> list[dict]:
    import scheduler
    fingerprint = state.active_record(target).get("fingerprint", "")
    plan = state.read_json(state.control_dir(target) / "job_plans" / "bug_validation.json", {})
    entries = plan.get("entries") if isinstance(plan, dict) else None
    results = []
    for function_id in sorted(candidates):
        # Use the persisted plan's identity, never accept an unregistered file.
        if not isinstance(entries, list):
            raise ValueError(f"accepted Bug Validation evidence unavailable for {function_id}: missing job plan")
        entry = next((item for item in entries if isinstance(item, dict) and item.get("function_id") == function_id), None)
        if not isinstance(entry, dict) or not isinstance(entry.get("job_id"), str):
            raise ValueError(f"accepted Bug Validation evidence unavailable for {function_id}: missing job plan")
        job = scheduler.accepted_job(target, entry["job_id"], snapshot_commit=snapshot_commit, input_fingerprint=fingerprint)
        if job.get("input", {}).get("function_id") != function_id:
            raise ValueError(f"accepted Bug Validation identity does not match {function_id}")
        relative = job["bug_result_path"]
        payload = state.read_json(target / relative, None)
        status = payload.get("confirmation_status")
        attempts = payload.get("attempts")
        if status not in state.BUG_FINAL_STATUSES or not isinstance(attempts, list) or not attempts:
            continue
        dynamic = []
        for attempt in attempts:
            valid, _ = state._dynamic_attempt_ready(target, attempt, snapshot_commit)
            if valid:
                dynamic.append(attempt)
        if not dynamic:
            continue
        if status == "confirmed" and not any(item.get("classification") == "confirmed" for item in dynamic):
            continue
        if status == "rejected" and any(item.get("classification") == "confirmed" for item in dynamic):
            continue
        attempt_evidence = []
        for attempt in dynamic:
            result_path = attempt["dynamic_evidence"]["reproduction_result"]
            reproduction = state.read_json(target / result_path, {})
            evidence_reason = reproduction.get("reason")
            if not isinstance(evidence_reason, str) or not evidence_reason.strip():
                evidence_reason = "recorded dynamic evidence did not provide a more specific reason"
            attempt_evidence.append({
                "ordinal": attempt["ordinal"], "classification": attempt["classification"],
                "state": reproduction.get("state"), "reason": evidence_reason,
            })
        if status == "rejected":
            interpretation = "not reproduced by the recorded sufficient dynamic attempts; this does not prove that no defect exists"
        elif status == "inconclusive":
            interpretation = "dynamic validation is inconclusive; the candidate remains unresolved"
        else:
            interpretation = "dynamic execution reproduced the contract violation"
        results.append({
            "function_id": function_id,
            "status": status,
            "attempt_count": len(dynamic),
            "attempts": attempt_evidence,
            "result_path": relative,
            "evidence_reason": attempt_evidence[-1]["reason"],
            "interpretation": interpretation,
        })
    return results


def _scheduler_aggregate(target: Path) -> dict:
    import scheduler
    try:
        result = scheduler.aggregate_readonly(target)
        if not result.get("groups") or not result.get("converged"):
            return {**result, "status": "unavailable", "reason": "current scheduler run is empty or has unfinished/failed jobs"}
        return result
    except (OSError, ValueError, RuntimeError, scheduler.sqlite3.Error) as exc:
        return {"status": "unavailable", "converged": False, "reason": str(exc)}


def _business_coverage(target: Path, snapshot_commit: str) -> dict:
    path = state.control_dir(target) / "business_coverage.json"
    value = state.read_json(path, None)
    missing = {"status": "missing", "path": path.relative_to(target).as_posix(), "counts": {}, "rows": [], "reason": "business coverage ledger was not recorded"}
    if value is None:
        return missing
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("snapshot_commit") != snapshot_commit or not isinstance(value.get("rows"), list) or not value["rows"]:
        return {**missing, "status": "invalid", "reason": "coverage ledger is empty, invalid or belongs to another snapshot"}
    counts = {"passed": 0, "failed": 0, "unknown": 0}
    seen = set()
    for row in value["rows"]:
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key].strip() for key in ("id", "flow", "requirement", "limitation")) or row.get("status") not in counts or row["id"] in seen:
            return {**missing, "status": "invalid", "reason": "coverage rows need distinct identities, requirements, statuses and explicit limits"}
        evidence = row.get("evidence", [])
        if not isinstance(evidence, list):
            return {**missing, "status": "invalid", "reason": "coverage evidence must be a list"}
        levels, outcomes = set(), set()
        native_job, recorded_attempts, function = None, set(), None
        for item in evidence:
            if not isinstance(item, dict) or item.get("level") not in {"reasoning", "actual-code", "integration", "machine-verifier"}:
                return {**missing, "status": "invalid", "reason": "coverage evidence has an invalid level"}
            evidence_path = state._project_relative(target, item.get("path"))
            if evidence_path is None or not evidence_path.is_file():
                return {**missing, "status": "invalid", "reason": "coverage evidence file is unavailable"}
            levels.add(item["level"])
            if row["status"] != "unknown" and item["level"] != "reasoning":
                import bug_validation_executor
                import scheduler
                if item["level"] != "actual-code":
                    return {**missing, "status": "invalid", "reason": "native Bug Validation qualifies only actual-code; unvalidated integration or machine-verifier coverage must remain unknown"}
                result = state.read_json(evidence_path, {})
                try:
                    if native_job is None:
                        function_id = row.get("function_id")
                        index = state.source_index(target) or {}
                        function = next((entry for entry in index.get("functions", []) if isinstance(entry, dict) and entry.get("id") == function_id), None)
                        if not isinstance(function_id, str) or not function_id or index.get("schema_version") != 2 or index.get("snapshot_commit") != snapshot_commit or not isinstance(function, dict):
                            raise ValueError("coverage function is absent from the current source index")
                        artifact = state.fm_dir(target) / "extracted_functions" / function["artifact"]
                        spec = state.read_json(Path(f"{artifact}.spec.json"), {})
                        verification = state.read_json(state.fm_dir(target) / "logic_verification_results" / Path(function["artifact"]).with_suffix(".json"), {})
                        valid, _ = state.verification_result_ready(target, artifact, function_id, verification, snapshot_commit)
                        if not valid or verification.get("verdict") != "MISMATCH" or row["requirement"] != spec.get("post_condition"):
                            raise ValueError("coverage requirement must equal the assigned validated specification postcondition")
                        plan = state.read_json(state.control_dir(target) / "job_plans" / "bug_validation.json", {})
                        entry = next((value for value in plan.get("entries", []) if isinstance(value, dict) and value.get("function_id") == function_id), None)
                        if plan.get("schema_version") != 1 or plan.get("phase") != "bug_validation" or plan.get("snapshot_commit") != snapshot_commit or not isinstance(entry, dict):
                            raise ValueError("coverage function has no current planned Bug Validation job")
                        native_job = scheduler.accepted_job(target, entry["job_id"], snapshot_commit=snapshot_commit, input_fingerprint=state.active_record(target).get("fingerprint", ""))
                        if native_job["input"]["function_id"] != function_id:
                            raise ValueError("coverage function does not own the accepted Bug Validation job")
                        report = state.read_json(target / native_job["bug_result_path"], {})
                        recorded_attempts = {(attempt["ordinal"], attempt["dynamic_evidence"]["reproduction_result"]) for attempt in report["attempts"]}
                    bug_id, attempt = result["bug_id"], result["attempt"]
                    expected = bug_validation_executor.attempt_dir(target, bug_id, attempt) / "reproduction_result.json"
                    if bug_id != native_job["input"]["bug_id"] or evidence_path != expected or (attempt, evidence_path.relative_to(target).as_posix()) not in recorded_attempts or result.get("state") != "completed" or result.get("language") != function.get("language"):
                        raise ValueError("execution does not belong to the assigned accepted Bug Validation attempt")
                    outcomes.add(result["classification"])
                except (KeyError, TypeError, ValueError, OSError) as exc:
                    return {**missing, "status": "invalid", "reason": f"passed/failed coverage requires assigned accepted execution evidence: {exc}"}
        if row["status"] != "unknown" and not levels.intersection({"actual-code", "integration", "machine-verifier"}):
            return {**missing, "status": "invalid", "reason": "passed/failed business rows require execution evidence, not reasoning alone"}
        if (row["status"] == "passed" and ("not_reproduced" not in outcomes or "confirmed" in outcomes)) or (row["status"] == "failed" and "confirmed" not in outcomes):
            return {**missing, "status": "invalid", "reason": "coverage status contradicts the recorded execution outcome"}
        seen.add(row["id"])
        counts[row["status"]] += 1
    return {"status": "available", "path": path.relative_to(target).as_posix(), "counts": counts, "rows": value["rows"], "reason": None}


def official_result_available(target: Path) -> tuple[bool, str | None]:
    authority = state.read_json(checkpoint.root(target) / "official_result.json", {})
    if not isinstance(authority, dict) or authority.get("official_result_available") is not True:
        reason = authority.get("reason") if isinstance(authority, dict) else None
        return False, reason or "the complete FM-Agent DAG and finalize gate have not succeeded"
    return True, None


def build(target: Path) -> dict:
    target = _analysis_target(target)
    checked = checkpoint.validate(target)
    manifests = _phase_manifests(target)
    scheduler = _scheduler_aggregate(target)
    verification = _verification_results(target, checked["snapshot_commit"])
    reasoning_counts = {verdict: sum(item.get("verdict") == verdict for item in verification) for verdict in sorted(state.VERDICTS)}
    reasoning_gaps = [{"function_id": item["function_id"], "verdict": item["verdict"], "details": item.get("gaps") or item.get("error") or item.get("reasoning")} for item in verification if item.get("verdict") in {"INCONCLUSIVE", "DEPENDENCY_RISK", "ERROR"}]
    coverage = _business_coverage(target, checked["snapshot_commit"])
    mismatches = {
        result["function_id"] for result in verification
        if result.get("verdict") == "MISMATCH" and isinstance(result.get("function_id"), str)
    }
    acceptance_error = None
    try:
        bug_results = _bug_results(target, checked["snapshot_commit"], mismatches)
    except (OSError, ValueError, RuntimeError) as exc:
        bug_results, acceptance_error = [], str(exc)
    confirmed = [item for item in bug_results if item["status"] == "confirmed"]
    rejected = [item for item in bug_results if item["status"] == "rejected"]
    inconclusive = [item for item in bug_results if item["status"] == "inconclusive"]
    bv_function_ids = {item["function_id"] for item in bug_results}
    # MISMATCH with no Bug Validation result is a static finding, not
    # inconclusive.  It carries its concrete counterexample and source quote
    # from the Verification Worker.
    static_finding_ids = mismatches - bv_function_ids
    static_findings = [
        {"function_id": fid, "status": "static_finding",
         "interpretation": "high-confidence static identification with concrete counterexample and exact source quote; not dynamically confirmed"}
        for fid in sorted(static_finding_ids)
    ]
    official, reason = official_result_available(target)
    authority_unavailable = bool(acceptance_error or scheduler.get("status") == "unavailable")
    if authority_unavailable:
        official, reason = False, acceptance_error or scheduler["reason"]
    # Never report partial dynamic evidence as confirmed bugs. It remains in
    # the durable attempt artifacts for a later accepted completion.
    report_confirmed = confirmed if official else []
    report_rejected = rejected if official else []
    report_inconclusive = inconclusive if official else []
    report_static = static_findings if official else []
    report = {
        "schema_version": 1,
        "official_result_available": official,
        "status": "unavailable" if authority_unavailable else "official" if official else "incomplete",
        "audit_status": "incomplete" if not official or coverage["status"] != "available" else "completed_with_gaps" if reasoning_gaps or report_inconclusive or coverage["counts"]["unknown"] else "completed",
        "reason": reason,
        "snapshot_commit": checked["snapshot_commit"],
        "analysis_fingerprint": state.active_record(target).get("fingerprint"),
        "checkpoint_head": checked["checkpoint_id"],
        "phase_manifests": [
            {
                "phase": item.get("phase"), "ordinal": item.get("ordinal"),
                "status": item.get("status"), "checkpoint_id": item.get("checkpoint_id"),
            } for item in manifests
        ],
        "scheduler": scheduler,
        "counts": {
            "verification_results": len(verification),
            "candidates": len(mismatches),
            "static_findings": len(report_static) if not authority_unavailable else None,
            "confirmed": len(report_confirmed) if not authority_unavailable else None,
            "rejected": len(report_rejected) if not authority_unavailable else None,
            "dynamic_inconclusive": len(report_inconclusive) if not authority_unavailable else None,
        },
        "reasoning": {"counts": reasoning_counts, "gaps": reasoning_gaps},
        "business_coverage": coverage,
        "authority_rules": {
            "candidate_requires_schema_valid_mismatch": True,
            "confirmed_requires_dynamic_evidence": True,
            "static_finding_is_not_confirmed": True,
            "specification_is_not_bug_evidence": True,
            "rejected_is_not_absence_proof": True,
            "inconclusive_retains_dynamic_evidence_reason": True,
        },
    }
    # An incomplete run deliberately exposes no finding list.  This prevents a
    # Coordinator from laundering static observations into an official answer.
    if official:
        report["findings"] = {
            "candidates": sorted(mismatches),
            "static_findings": report_static,
            "confirmed": report_confirmed,
            "rejected": report_rejected,
            "inconclusive": report_inconclusive,
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit the authoritative FM-Agent terminal report.")
    parser.add_argument("--project", required=True)
    args = parser.parse_args(); target = project(args)
    try:
        result, code = build(target), 0
        if result.get("audit_status") == "incomplete":
            code = 2
    except (checkpoint.CheckpointError, OSError, ValueError, RuntimeError) as exc:
        result, code = {
            "schema_version": 1, "official_result_available": False,
            "status": "unavailable", "reason": str(exc),
            "audit_status": "incomplete", "counts": None,
        }, 2
    # Persist the exact structured report so later resume and diagnose actions
    # can distinguish an intentional phase failure from an unverified chat summary.
    try:
        state.atomic_json(state.control_dir(target) / "terminal_report.json", result)
    except OSError as exc:
        result = {
            "schema_version": 1, "official_result_available": False,
            "status": "unavailable", "reason": f"could not persist terminal report: {exc}",
            "audit_status": "incomplete", "counts": None,
        }
        code = 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
