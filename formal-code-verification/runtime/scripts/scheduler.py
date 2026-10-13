#!/usr/bin/env python3
# Modified by AIResearchSkill: validate static edges, Bug Validator execution, and durable acceptance receipts.
"""Durable current-job state for host FM-Agent workers; no run history."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

from _common import project, state
import checkpoint
import executor

SCHEDULER_SCHEMA_VERSION = 2
JOB_TYPES = {"phase_plan", "phase_refine", "domain_context", "resolve_agent_static_edges", "spec_batch", "verify_function", "verify_batch", "bug_validate", "select_relevant_modules", "select_relevant_files", "incremental_spec_plan", "reconcile_caller_info"}
RETRYABLE_FAILURES = {"execution", "output", "interrupted"}
FAILURE_CLASSES = RETRYABLE_FAILURES | {"input", "semantic", "cancelled"}
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
# Batch receipts must enumerate their assigned output paths exactly.  A
# verification/spec batch can legitimately contain dozens of long relative
# paths; 4 KiB rejected valid receipts before artifact validation ran.  Keep a
# bounded limit, but leave enough room for the manifest-sized output list.
MAX_REPORT_BYTES = 8192
REPORT_KEYS = {"job_id", "status", "outputs", "verdict", "classification", "escalation", "counts", "summary", "plan_path"}
BUG_CLASSIFICATIONS = {"confirmed", "not_reproduced", "rejected", "inconclusive"}
BUG_NEGATIVE_CLASSIFICATIONS = BUG_CLASSIFICATIONS - {"confirmed"}
TYPE_CAP_KEYS = {
    "spec_batch": "spec_concurrency",
    "verify_function": "verify_concurrency",
    "verify_batch": "verify_concurrency",
    "bug_validate": "bug_validation_concurrency",
    "incremental_spec_plan": "read_only_plan_concurrency",
}
DEFAULT_CAPS = {
    "max_active_subagents": 16,
    "spec_concurrency": 8,
    "verify_concurrency": 12,
    "bug_validation_concurrency": 4,
    "read_only_plan_concurrency": 4,
}

def _safe_id(value):
    if not ID.fullmatch(value or ""): raise ValueError("invalid job id")
    return value
def _path(target, job_id): return state.skill_dir(target) / "jobs" / f"{_safe_id(job_id)}.json"


def _connect(target):
    path = checkpoint.db_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, snapshot_commit TEXT NOT NULL,
            input_fingerprint TEXT NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS phases (
            run_id TEXT NOT NULL, phase TEXT NOT NULL, ordinal INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', gate_status TEXT,
            PRIMARY KEY(run_id, phase)
        );
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, phase TEXT NOT NULL,
            type TEXT NOT NULL, status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL, remaining_dependencies INTEGER NOT NULL DEFAULT 0,
            input_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
            result_json TEXT, failure_class TEXT, message TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS job_dependencies (
            job_id TEXT NOT NULL, depends_on_job_id TEXT NOT NULL,
            PRIMARY KEY(job_id, depends_on_job_id),
            FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS leases (
            job_id TEXT PRIMARY KEY, attempt INTEGER NOT NULL, owner TEXT NOT NULL,
            acquired_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS coordinator_leases (
            lease_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL, expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attempts (
            job_id TEXT NOT NULL, attempt INTEGER NOT NULL, input_hash TEXT NOT NULL,
            status TEXT NOT NULL, artifact_hash TEXT, started_at TEXT NOT NULL,
            completed_at TEXT, message TEXT, PRIMARY KEY(job_id, attempt)
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            snapshot_commit TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL,
            size INTEGER NOT NULL, job_id TEXT NOT NULL, attempt INTEGER NOT NULL,
            PRIMARY KEY(snapshot_commit, path)
        );
        CREATE TABLE IF NOT EXISTS receipts (
            job_id TEXT NOT NULL, attempt INTEGER NOT NULL, input_hash TEXT NOT NULL,
            artifact_hash TEXT NOT NULL, payload_json TEXT NOT NULL, received_at TEXT NOT NULL,
            PRIMARY KEY(job_id, attempt)
        );
        CREATE TABLE IF NOT EXISTS scheduler_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS jobs_status_phase_type ON jobs(status, phase, type);
        CREATE INDEX IF NOT EXISTS jobs_remaining_dependencies ON jobs(remaining_dependencies);
        CREATE INDEX IF NOT EXISTS leases_expires_at ON leases(expires_at);
        CREATE INDEX IF NOT EXISTS artifacts_snapshot_path ON artifacts(snapshot_commit, path);
        CREATE INDEX IF NOT EXISTS receipts_job_attempt ON receipts(job_id, attempt);
    """)
    connection.execute(
        "INSERT OR REPLACE INTO scheduler_meta(key,value) VALUES('schema_version',?)",
        (str(SCHEDULER_SCHEMA_VERSION),),
    )
    return connection


def _run_id(target):
    record = state.active_record(target)
    snapshot = record.get("snapshot_commit") or state.current_snapshot_commit(target)
    fingerprint = record.get("fingerprint", "")
    return hashlib.sha256(f"{snapshot}\0{fingerprint}".encode()).hexdigest()[:24], snapshot, fingerprint


def _payload_hash(job):
    semantic = {
        key: job.get(key) for key in
        ("id", "phase", "type", "depends_on", "required_outputs", "artifacts", "input")
    }
    return hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _load(target, job_id):
    _safe_id(job_id)
    connection = _connect(target)
    row = connection.execute("SELECT payload_json FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    connection.close()
    if row:
        value = json.loads(row["payload_json"])
        if isinstance(value, dict) and value.get("id") == job_id:
            return value
    # Old JSON runs remain diagnosable and resumable.  New scheduling never
    # scans this directory; a specifically requested legacy job is imported.
    legacy = state.read_json(_path(target, job_id), {})
    if isinstance(legacy, dict) and legacy.get("id") == job_id:
        legacy.setdefault("legacy_contract", True)
        _persist(target, legacy, insert=True)
        return legacy
    raise ValueError("job does not exist")


def _persist(target, job, insert=False):
    job["updated_at"] = state.now()
    connection = _connect(target)
    run_id, snapshot, fingerprint = _run_id(target)
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            "INSERT OR IGNORE INTO runs VALUES(?,?,?,?,?,?)",
            (run_id, snapshot, fingerprint, "running", state.now(), state.now()),
        )
        record = state.active_record(target)
        ordinal = record.get("phases", []).index(job.get("phase")) + 1 if job.get("phase") in record.get("phases", []) else 0
        connection.execute(
            "INSERT OR IGNORE INTO phases(run_id,phase,ordinal,status) VALUES(?,?,?,'pending')",
            (run_id, job.get("phase", "unspecified"), ordinal),
        )
        previous = connection.execute("SELECT status FROM jobs WHERE job_id=?", (job["id"],)).fetchone()
        remaining = sum(
            1 for dependency in job.get("depends_on", [])
            if connection.execute("SELECT status FROM jobs WHERE job_id=?", (dependency,)).fetchone() is None
            or connection.execute("SELECT status FROM jobs WHERE job_id=?", (dependency,)).fetchone()[0] != "succeeded"
        )
        connection.execute(
            "INSERT INTO jobs(job_id,run_id,phase,type,status,attempt,max_attempts,remaining_dependencies,input_hash,payload_json,result_json,failure_class,message,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,attempt=excluded.attempt,max_attempts=excluded.max_attempts,input_hash=excluded.input_hash,"
            "remaining_dependencies=excluded.remaining_dependencies,payload_json=excluded.payload_json,result_json=excluded.result_json,"
            "failure_class=excluded.failure_class,message=excluded.message,updated_at=excluded.updated_at",
            (
                job["id"], run_id, job.get("phase", "unspecified"), job["type"], job["status"],
                int(job.get("attempts", 0)), int(job.get("max_attempts", 1)), remaining,
                job.setdefault("input_hash", _payload_hash(job)), json.dumps(job, ensure_ascii=False, sort_keys=True),
                json.dumps(job.get("result"), ensure_ascii=False, sort_keys=True) if "result" in job else None,
                job.get("failure_class"), job.get("message"), job.get("created_at", state.now()), job["updated_at"],
            ),
        )
        if insert:
            for dependency in job.get("depends_on", []):
                connection.execute(
                    "INSERT OR IGNORE INTO job_dependencies(job_id,depends_on_job_id) VALUES(?,?)",
                    (job["id"], dependency),
                )
        if previous and previous["status"] != "succeeded" and job["status"] == "succeeded":
            dependents = connection.execute(
                "SELECT job_id FROM job_dependencies WHERE depends_on_job_id=?", (job["id"],)
            ).fetchall()
            for dependent in dependents:
                connection.execute(
                    "UPDATE jobs SET remaining_dependencies=(SELECT COUNT(*) FROM job_dependencies d "
                    "LEFT JOIN jobs p ON p.job_id=d.depends_on_job_id WHERE d.job_id=? AND COALESCE(p.status,'missing')!='succeeded') "
                    "WHERE job_id=?",
                    (dependent["job_id"], dependent["job_id"]),
                )
        if job["status"] != "running":
            connection.execute("DELETE FROM leases WHERE job_id=?", (job["id"],))
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        connection.close()
        raise
    connection.close()
    state.atomic_json(_path(target, job["id"]), job)


def _save(target, job):
    _persist(target, job)
def _inside(target, value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts: raise ValueError("job paths must be project-relative and cannot traverse parent directories")
    rel = path.as_posix()
    if not (rel.startswith("fm_agent/") or rel.startswith("fm_agent_skill/probes/") or rel.startswith("fm_agent_skill/worker_reports/")): raise ValueError("worker output must stay in fm_agent/, fm_agent_skill/probes/, or its assigned worker report")
    if target not in (target / path).resolve().parents: raise ValueError("job path escapes project")
    return rel
def _artifact(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts: raise ValueError("artifact paths must stay under extracted_functions")
    return path.as_posix()
def _phase(value):
    if not isinstance(value, str) or not ID.fullmatch(value): raise ValueError("phase must be a valid phase id")
    return value
def _caps(target):
    saved = state.read_json(state.skill_dir(target) / "config.json", {})
    result = dict(DEFAULT_CAPS)
    if isinstance(saved, dict):
        for key in result:
            value = saved.get(key)
            if isinstance(value, int) and value > 0: result[key] = value
    return result
def _type_cap(job_type, caps):
    return caps.get(TYPE_CAP_KEYS.get(job_type), 1)
def _running(target):
    connection = _connect(target)
    rows = connection.execute("SELECT payload_json FROM jobs WHERE run_id=? AND status='running' ORDER BY job_id", (_run_id(target)[0],)).fetchall()
    connection.close()
    return [json.loads(row["payload_json"]) for row in rows]


def _capacity(target):
    caps, running = _caps(target), _running(target)
    by_type = {
        kind: sum(1 for job in running if job.get("type") == kind)
        for kind in JOB_TYPES
    }
    return {
        "caps": caps,
        "active": len(running),
        "by_type": by_type,
    }
def _admission_error(target, job):
    capacity = _capacity(target); caps = capacity["caps"]
    if capacity["active"] >= caps["max_active_subagents"]:
        return f"global subagent capacity reached ({capacity['active']}/{caps['max_active_subagents']})"
    limit = _type_cap(job["type"], caps); active = capacity["by_type"].get(job["type"], 0)
    if active >= limit: return f"{job['type']} capacity reached ({active}/{limit})"
    return None


def _validate_report(job, result):
    # Keep interrupted analyses created by the pre-receipt scheduler resumable.
    # New manifests always carry phase + receipt requirements.
    if job.get("legacy_contract"):
        return None
    if not isinstance(result, dict): return "worker report must be a JSON object"
    try: size = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError): return "worker report must be JSON-serializable"
    if size > MAX_REPORT_BYTES: return f"worker report exceeds {MAX_REPORT_BYTES} bytes; write detail to its assigned output"
    unknown = set(result) - REPORT_KEYS
    if unknown: return "worker report has unsupported keys: " + ", ".join(sorted(unknown))
    if result.get("job_id") != job["id"]: return "worker report job_id does not match manifest"
    if not isinstance(result.get("status"), str) or not result["status"].strip(): return "worker report requires non-empty status"
    if "outputs" in result and (not isinstance(result["outputs"], list) or not all(isinstance(item, str) for item in result["outputs"])): return "worker report outputs must be a string array"
    if "outputs" in result and result["outputs"] != job.get("required_outputs", []):
        return "worker report outputs must exactly match the manifest required_outputs"
    if job["type"] in {"domain_context", "spec_batch", "verify_function", "verify_batch"} and result.get("outputs") != job.get("required_outputs", []):
        return f"{job['type']} report must include the exact manifest required_outputs"
    if "verdict" in result and result["verdict"] not in state.VERDICTS: return "worker report has invalid verdict"
    if "summary" in result and (not isinstance(result["summary"], str) or len(result["summary"]) > 500): return "worker report summary must be at most 500 characters"
    if job["type"] == "bug_validate":
        allowed = state.BUG_ATTEMPT_CLASSIFICATIONS if not job.get("legacy_contract") else BUG_CLASSIFICATIONS
        if result.get("classification") not in allowed: return "Bug Validator report requires a valid classification"
    if job["type"] == "incremental_spec_plan":
        expected = f"fm_agent_skill/worker_reports/{job['id']}.json"
        if result.get("plan_path") != expected: return "incremental plan report must name its assigned plan_path"
    return None
def _limit(target, payload):
    config = state.read_json(state.skill_dir(target) / "config.json", {})
    # Pre-receipt jobs retain their historical single Bug Validator attempt.
    default = (config.get("bug_validation_max_attempts", 5) if "phase" in payload else 1) if isinstance(config, dict) and payload.get("type") == "bug_validate" else (config.get("retries", 5) if isinstance(config, dict) else 5)
    value = payload.get("max_attempts", default)
    if not isinstance(value, int) or value < 1: raise ValueError("max_attempts must be a positive integer")
    return value
def _negative_attempts(target, payload):
    config = state.read_json(state.skill_dir(target) / "config.json", {})
    default = config.get("bug_validation_negative_retries", 2) if isinstance(config, dict) else 2
    value = payload.get("negative_retries", default)
    if not isinstance(value, int) or value < 0: raise ValueError("negative_retries must be a non-negative integer")
    return value + 1


def _bug_input(target, payload):
    data = payload.get("input", {})
    if not all(isinstance(data.get(key), str) and data[key] for key in ("function_id", "candidate_id", "bug_id")):
        raise ValueError("Bug Validator requires distinct candidate and function identities")
    _safe_id(data["bug_id"])
    connection = _connect(target)
    prior = connection.execute("SELECT job_id FROM jobs WHERE type='bug_validate' AND json_extract(payload_json,'$.input.bug_id')=?", (data["bug_id"],)).fetchone()
    connection.close()
    if prior is not None:
        raise ValueError("Bug Validator immutable attempt namespace already belongs to another job")
def _validate(target, job, result=None, *, snapshot_commit=None):
    errors = []
    missing = [item for item in job.get("required_outputs", []) if not (target / item).exists()]
    if missing: errors.append("missing required worker output: " + ", ".join(missing))
    if job["type"] in {"spec_batch", "reconcile_caller_info"}:
        if not job.get("artifacts"): return "sidecar-writing job has no assigned artifacts"
        normalized = []
        for rel in job["artifacts"]:
            artifact = target / "fm_agent" / "extracted_functions" / rel
            spec_path, info_path = Path(f"{artifact}.spec.json"), Path(f"{artifact}.info.json")
            before = (state.read_json(spec_path, None), state.read_json(info_path, None))
            ok, reason = state.sidecars_ready(artifact)
            after = (state.read_json(spec_path, None), state.read_json(info_path, None))
            if before != after:
                normalized.append(rel)
            if not ok:
                errors.append(f"{rel}: {reason}")
        if normalized:
            job["normalized_artifacts"] = sorted(set(job.get("normalized_artifacts", [])) | set(normalized))
        if errors:
            return f"invalid assigned sidecars ({len(errors)} issue(s)):\n- " + "\n- ".join(errors)
    elif errors:
        return "; ".join(errors)
    if job["type"] == "resolve_agent_static_edges":
        try:
            executor._validate_edges(target, state.read_json(target / job["required_outputs"][0], {}))
        except ValueError as exc:
            return f"invalid static edge candidate: {exc}"
    if job["type"] == "phase_plan":
        phases = state.read_json(target / "fm_agent" / "phases.json", {})
        if not isinstance(phases, dict) or not phases.get("phases"): return "phase-plan worker did not create a non-empty fm_agent/phases.json"
        try:
            executor.normalize_phases(target)
        except (OSError, ValueError, RuntimeError) as exc:
            return f"phase-plan output cannot be normalized: {exc}"
        ready, reason = state.phases_schema_ready(target)
        if not ready:
            return f"normalized phase plan is invalid: {reason}"
    if job["type"] == "domain_context":
        ok, reason = state.specification_context_ready(target)
        if not ok: return reason
    if job["type"] in {"verify_function", "verify_batch"} and not job.get("legacy_contract"):
        if job["type"] == "verify_function" and len(job.get("artifacts", [])) != 1:
            return "Verification Worker must own exactly one extracted artifact"
        expected_outputs = [
            f"fm_agent/logic_verification_results/{Path(rel).with_suffix('.json').as_posix()}"
            for rel in job.get("artifacts", [])
        ]
        if job.get("required_outputs") != expected_outputs:
            return "Verification Worker outputs do not match assigned artifacts"
        index = state.source_index(target) or {}
        invalid = []
        verdicts = []
        for rel, expected in zip(job.get("artifacts", []), expected_outputs):
            artifact = target / "fm_agent" / "extracted_functions" / rel
            item = next((entry for entry in index.get("functions", []) if isinstance(entry, dict) and entry.get("artifact") == rel), None)
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                invalid.append(f"{rel}: absent from current analysis index"); continue
            verification = state.read_json(target / expected, None)
            valid, reason = state.verification_result_ready(target, artifact, item["id"], verification)
            if not valid: invalid.append(f"{rel}: {reason}")
            else: verdicts.append(verification.get("verdict"))
        if invalid:
            job["invalid_artifacts"] = [item.split(":", 1)[0] for item in invalid]
            return f"invalid Verification Worker results ({len(invalid)} issue(s)):\n- " + "\n- ".join(invalid)
        if job["type"] == "verify_function" and result is not None and result.get("verdict") != verdicts[0]:
            return "Verification Worker receipt verdict does not match its result"
    if job["type"] == "bug_validate" and not job.get("legacy_contract"):
        snapshot_commit = snapshot_commit or state.current_snapshot_commit(target)
        report = state.read_json(target / job["bug_result_path"], {})
        function_id = job.get("input", {}).get("function_id")
        candidate_id = job.get("input", {}).get("candidate_id")
        if not isinstance(function_id, str) or not isinstance(report, dict) or report.get("function_id") != function_id:
            return "Bug Validator report function identity does not match its assigned job"
        if report.get("schema_version") != 2 or not isinstance(candidate_id, str) or report.get("candidate_id") != candidate_id or report.get("bug_id") != job.get("input", {}).get("bug_id"):
            return "Bug Validator report candidate identity does not match its assigned job"
        attempts = report.get("attempts") if isinstance(report, dict) else None
        index = int(job.get("negative_attempt_index", 1))
        if not isinstance(attempts, list) or len(attempts) < index: return "Bug Validator result must append the current probe to attempts"
        ordinals = [recorded.get("ordinal") for recorded in attempts if isinstance(recorded, dict)]
        if len(ordinals) != len(attempts) or any(not isinstance(ordinal, int) or ordinal < 1 for ordinal in ordinals) or ordinals != sorted(set(ordinals)):
            return "Bug Validator attempt ordinals must be distinct and ordered"
        prior = job.get("validated_attempts", [])
        if attempts[:len(prior)] != prior or len(attempts) != len(prior) + (job.get("status") != "succeeded"):
            return "Bug Validator must preserve every previously accepted semantic attempt"
        if report.get("snapshot_commit") != snapshot_commit: return "Bug Validator report snapshot does not match accepted analysis"
        if report.get("confirmation_status") not in state.BUG_FINAL_STATUSES: return "Bug Validator report has invalid confirmation status"
        if report["confirmation_status"] == "rejected" and any(recorded.get("classification") != "not_reproduced" for recorded in attempts if isinstance(recorded, dict)):
            return "rejected requires completed negative probes; inconclusive attempts remain unresolved"
        latest = attempts[-1] if attempts else None
        dynamic_ok, dynamic_reason = state._dynamic_attempt_ready(target, latest, snapshot_commit)
        if not dynamic_ok: return f"Bug Validator current attempt lacks valid dynamic evidence: {dynamic_reason}"
        if result is not None:
            if latest.get("classification") != result.get("classification"):
                return "Bug Validator result attempt classification does not match its receipt"
            status = report.get("confirmation_status")
            classification = result.get("classification")
            if classification == "confirmed" and status != "confirmed": return "confirmed receipt requires a confirmed report"
            if classification == "inconclusive" and status != "inconclusive": return "inconclusive receipt requires an inconclusive report"
            if classification == "not_reproduced" and status not in {"inconclusive", "rejected"}: return "non-reproduction receipt requires inconclusive or rejected report"
        import bug_validation_executor
        if not bug_validation_executor.finalization_matches_current_attempt(target, job):
            return "Bug Validator finalization does not match its accepted attempt"
        for recorded in attempts:
            dynamic_ok, dynamic_reason = state._dynamic_attempt_ready(target, recorded, snapshot_commit)
            if not dynamic_ok:
                return f"Bug Validator attempt lacks valid dynamic evidence: {dynamic_reason}"
            ordinal = recorded.get("ordinal")
            if not isinstance(ordinal, int) or ordinal < 1:
                return "Bug Validator attempt has an invalid ordinal"
            try:
                bug_id, _ = bug_validation_executor.context(job)
                expected = bug_validation_executor.attempt_dir(target, bug_id, ordinal) / "reproduction_result.json"
                if recorded["dynamic_evidence"]["reproduction_result"] != expected.relative_to(target).as_posix():
                    return "Bug Validator attempt references another attempt's execution evidence"
                if not bug_validation_executor.execution_result_valid(target, {**job, "attempts": ordinal}, snapshot_commit=snapshot_commit):
                    return "Bug Validator execution outcome contradicts its recorded command evidence"
            except ValueError as exc:
                return f"Bug Validator execution evidence is invalid: {exc}"
        # Accepted negative outcomes remain immutable while the same job retries.
        connection = sqlite3.connect(f"{checkpoint.db_path(target).resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        sealed = connection.execute("SELECT path,sha256,size FROM artifacts WHERE job_id=? AND path LIKE 'fm_agent_skill/probes/%'", (job["id"],)).fetchall()
        connection.close()
        for item in sealed:
            path = target / item["path"]
            if not path.is_file() or state.file_hash(path) != item["sha256"] or path.stat().st_size != item["size"]:
                return "previously accepted dynamic evidence bytes have changed"
    return None
def _fail(job, kind, message):
    if kind not in FAILURE_CLASSES: raise ValueError("unsupported failure class")
    if job["type"] == "bug_validate" and not job.get("legacy_contract") and kind in RETRYABLE_FAILURES:
        runtime_attempts = int(job.get("runtime_attempts", 0)) + 1
        job["runtime_attempts"] = runtime_attempts
        retryable = runtime_attempts < job["max_attempts"]
    else: retryable = kind in RETRYABLE_FAILURES and job["attempts"] < job["max_attempts"]
    job.update({"failure_class": kind, "message": message or "worker failed", "failed_at": state.now(), "status": "retryable" if retryable else "failed"})
def create(target, payload):
    if not isinstance(payload, dict): raise ValueError("job JSON must be an object")
    job_id, kind = payload.get("id"), payload.get("type"); _safe_id(job_id)
    if kind not in JOB_TYPES: raise ValueError("unsupported job type")
    connection = _connect(target)
    exists = connection.execute("SELECT 1 FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    connection.close()
    if exists or _path(target, job_id).exists(): raise ValueError("job already exists")
    legacy_contract = "phase" not in payload
    phase = _phase(payload.get("phase", "unspecified")); deps, outputs, artifacts = payload.get("depends_on", []), payload.get("required_outputs", []), payload.get("artifacts", [])
    if not all(isinstance(item, str) and ID.fullmatch(item) for item in deps): raise ValueError("invalid dependency id")
    if not all(isinstance(item, str) for item in outputs + artifacts): raise ValueError("job paths must be strings")
    outputs = [_inside(target, item) for item in outputs]
    if len(set(outputs)) != len(outputs): raise ValueError("duplicate required output")
    worker_report = f"fm_agent_skill/worker_reports/{job_id}.json"
    if worker_report in outputs and outputs.count(worker_report) != 1: raise ValueError("worker report may appear only once")
    if any(item.startswith("fm_agent_skill/worker_reports/") and item != worker_report for item in outputs): raise ValueError("worker report path must match its job id")
    if kind == "incremental_spec_plan" and not legacy_contract and outputs != [worker_report]: raise ValueError("incremental spec planning must write only its assigned worker report")
    bug_results = [item for item in outputs if item.startswith("fm_agent/bug_validation/") and item.endswith(".result.json")]
    if kind == "bug_validate" and not legacy_contract and len(bug_results) != 1: raise ValueError("Bug Validator must assign exactly one fm_agent/bug_validation/*.result.json output")
    if kind == "verify_function" and not legacy_contract:
        if len(artifacts) != 1: raise ValueError("Verification Worker must assign exactly one extracted artifact")
        expected = f"fm_agent/logic_verification_results/{Path(artifacts[0]).with_suffix('.json').as_posix()}"
        if outputs != [expected]: raise ValueError("Verification Worker must assign its matching result path")
    if kind == "verify_batch" and not legacy_contract:
        if not artifacts: raise ValueError("Verification batch must assign at least one extracted artifact")
        expected = [f"fm_agent/logic_verification_results/{Path(item).with_suffix('.json').as_posix()}" for item in artifacts]
        if outputs != expected: raise ValueError("Verification batch outputs must match its artifacts in order")
    job = {"schema_version": 2, "id": job_id, "phase": phase, "type": kind, "status": "queued", "depends_on": deps, "required_outputs": outputs, "artifacts": [_artifact(item) for item in artifacts], "attempts": 0, "max_attempts": _limit(target, payload), "created_at": state.now(), "updated_at": state.now()}
    if legacy_contract: job["legacy_contract"] = True
    elif kind == "bug_validate": job.update({"bug_result_path": bug_results[0], "negative_max_attempts": _negative_attempts(target, payload), "negative_attempts": 0, "runtime_attempts": 0})
    if isinstance(payload.get("input"), dict): job["input"] = payload["input"]
    if kind == "bug_validate" and not legacy_contract:
        _bug_input(target, payload)
    _persist(target, job, insert=True); return job


def create_many(target, payloads):
    """Atomically seed a large DAG without creating one JSON file per queued job."""
    if not isinstance(payloads, list): raise ValueError("jobs must be an array")
    run_id, snapshot, fingerprint = _run_id(target)
    now = state.now(); jobs = []
    seen = set()
    bug_ids = set()
    for payload in payloads:
        if not isinstance(payload, dict): raise ValueError("job JSON must be an object")
        job_id, kind = _safe_id(payload.get("id")), payload.get("type")
        if job_id in seen: raise ValueError(f"duplicate job id: {job_id}")
        if kind not in JOB_TYPES: raise ValueError("unsupported job type")
        if kind == "bug_validate":
            _bug_input(target, payload)
            bug_id = payload["input"]["bug_id"]
            if bug_id in bug_ids:
                raise ValueError("Bug Validator attempt namespace is duplicated in the batch")
            bug_ids.add(bug_id)
        seen.add(job_id)
        phase = _phase(payload.get("phase", "unspecified"))
        deps = payload.get("depends_on", [])
        outputs = [_inside(target, item) for item in payload.get("required_outputs", [])]
        artifacts = [_artifact(item) for item in payload.get("artifacts", [])]
        job = {
            "schema_version": 2, "id": job_id, "phase": phase, "type": kind,
            "status": "queued", "depends_on": deps, "required_outputs": outputs,
            "artifacts": artifacts, "attempts": 0, "max_attempts": _limit(target, payload),
            "created_at": now, "updated_at": now,
        }
        if isinstance(payload.get("input"), dict): job["input"] = payload["input"]
        job["input_hash"] = _payload_hash(job); jobs.append(job)
    connection = _connect(target)
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("INSERT OR IGNORE INTO runs VALUES(?,?,?,?,?,?)", (run_id, snapshot, fingerprint, "running", now, now))
        record = state.active_record(target)
        existing_status = {row[0]: row[1] for row in connection.execute("SELECT job_id,status FROM jobs").fetchall()}
        existing = seen & set(existing_status)
        if existing: raise ValueError("jobs already exist: " + ", ".join(sorted(existing)[:3]))
        all_ids = seen | set(existing_status)
        for job in jobs:
            if not all(isinstance(dep, str) and ID.fullmatch(dep) and dep in all_ids for dep in job["depends_on"]):
                raise ValueError(f"invalid dependency for {job['id']}")
            remaining = sum(1 for dependency in job["depends_on"] if existing_status.get(dependency) != "succeeded")
            connection.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job["id"], run_id, job["phase"], job["type"], "queued", 0, job["max_attempts"], remaining, job["input_hash"], json.dumps(job, ensure_ascii=False, sort_keys=True), None, None, None, now, now),
            )
            ordinal = record.get("phases", []).index(job["phase"]) + 1 if job["phase"] in record.get("phases", []) else 0
            connection.execute("INSERT OR IGNORE INTO phases(run_id,phase,ordinal,status) VALUES(?,?,?,'pending')", (run_id, job["phase"], ordinal))
            connection.executemany(
                "INSERT INTO job_dependencies VALUES(?,?)",
                [(job["id"], dep) for dep in job["depends_on"]],
            )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK"); connection.close(); raise
    connection.close()
    return {"created": len(jobs), "run_id": run_id}


def _expire_leases(target):
    connection = _connect(target)
    now = state.now()
    connection.execute("BEGIN IMMEDIATE")
    try:
        rows = connection.execute(
            "SELECT l.job_id,j.payload_json FROM leases l JOIN jobs j ON j.job_id=l.job_id "
            "WHERE l.expires_at<=? AND j.run_id=?", (now, _run_id(target)[0]),
        ).fetchall()
        expired = []
        for row in rows:
            job = json.loads(row["payload_json"])
            if job.get("status") == "running":
                job.update({"status": "queued", "failure_class": "interrupted", "message": "worker lease expired", "requeued_at": now, "updated_at": now})
                connection.execute(
                    "UPDATE jobs SET status='queued',payload_json=?,failure_class='interrupted',message=?,updated_at=? WHERE job_id=?",
                    (json.dumps(job, ensure_ascii=False, sort_keys=True), "worker lease expired", now, job["id"]),
                )
                connection.execute(
                    "UPDATE attempts SET status='expired',completed_at=?,message=? WHERE job_id=? AND attempt=?",
                    (now, "worker lease expired", job["id"], job.get("attempts", 0)),
                )
                expired.append(job)
            connection.execute("DELETE FROM leases WHERE job_id=?", (row["job_id"],))
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK"); connection.close(); raise
    connection.close()
    for job in expired: state.atomic_json(_path(target, job["id"]), job)
    return [job["id"] for job in expired]


def ready(target, limit=None, offset=0):
    _expire_leases(target)
    connection = _connect(target)
    sql = "SELECT payload_json FROM jobs WHERE run_id=? AND status='queued' AND remaining_dependencies=0 ORDER BY job_id"
    parameters = (_run_id(target)[0],)
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"; parameters += (max(0, int(limit)), max(0, int(offset)))
    rows = connection.execute(sql, parameters).fetchall()
    connection.close()
    return [json.loads(row["payload_json"]) for row in rows]
def admissible(target):
    """Return a deterministic, capacity-respecting subset of ready jobs."""
    capacity = _capacity(target); caps = capacity["caps"]; active = capacity["active"]
    by_type = dict(capacity["by_type"]); result = []
    for job in ready(target, max(caps["max_active_subagents"] * 4, 16)):
        if active >= caps["max_active_subagents"]: break
        limit = _type_cap(job["type"], caps); used = by_type.get(job["type"], 0)
        if used >= limit: continue
        result.append(job); active += 1; by_type[job["type"]] = used + 1
    return {"capacity": capacity, "jobs": result}
def phase_receipt(target, phase):
    phase = _phase(phase)
    run_id, _, _ = _run_id(target)
    connection = _connect(target)
    rows = connection.execute(
        "SELECT payload_json FROM jobs WHERE phase=? AND run_id=? ORDER BY job_id",
        (phase, run_id),
    ).fetchall()
    connection.close()
    jobs = [json.loads(row["payload_json"]) for row in rows]
    totals = {status: sum(1 for job in jobs if job.get("status") == status) for status in ("queued", "running", "retryable", "failed", "succeeded")}
    escalations = []
    outcomes = {verdict: 0 for verdict in sorted(state.VERDICTS)}
    for job in jobs:
        result = job.get("result", {}) if isinstance(job.get("result"), dict) else {}
        verdict = result.get("verdict")
        if verdict in outcomes: outcomes[verdict] += 1
        reason = None
        if job.get("status") in {"failed", "retryable"}: reason = job.get("failure_class", job.get("status"))
        elif verdict in {"MISMATCH", "DEPENDENCY_RISK", "INCONCLUSIVE", "ERROR"}: reason = verdict
        elif result.get("escalation") not in {None, "", "none", "NONE", False}: reason = "worker_escalation"
        if reason: escalations.append({"job_id": job.get("id"), "type": job.get("type"), "reason": reason})
    receipt = {"schema_version": 1, "phase": phase, "generated_at": state.now(), "totals": totals, "outcomes": outcomes, "gate_ready": totals["queued"] == totals["running"] == totals["retryable"] == totals["failed"] == 0, "escalations": escalations}
    if phase in {"verification", "verify_affected"}:
        plan = state.read_json(state.control_dir(target) / "job_plans" / f"{phase}.json", {})
        artifacts = {
            entry.get("artifact") for entry in plan.get("entries", [])
            if isinstance(entry, dict) and isinstance(entry.get("artifact"), str)
        }
        functions = [
            item for item in (state.source_index(target) or {}).get("functions", [])
            if isinstance(item, dict) and item.get("artifact") in artifacts
        ]
        receipt["semantic_coverage"] = state.verification_coverage(target, functions)
        semantic_ready, semantic_reason = state.verification_coverage_ready(target, functions) if functions else (True, "")
        receipt["semantic_gate_ready"] = semantic_ready
        receipt["semantic_gate_reason"] = semantic_reason
        receipt["gate_ready"] = receipt["gate_ready"] and semantic_ready
    path = state.control_dir(target) / "phase_receipts" / f"{phase}.json"; state.atomic_json(path, receipt)
    connection = _connect(target)
    connection.execute(
        "UPDATE phases SET status=?,gate_status=? WHERE phase=?",
        ("succeeded" if receipt["gate_ready"] else "failed" if totals["failed"] else "running", "passed" if receipt["gate_ready"] else "pending", phase),
    )
    connection.commit(); connection.close()
    return {"receipt_path": path.relative_to(target).as_posix(), **receipt}


def jobs_for_phase(target, phase, run_id=None):
    connection = _connect(target)
    if run_id is None:
        rows = connection.execute("SELECT payload_json FROM jobs WHERE phase=? ORDER BY job_id", (phase,)).fetchall()
    else:
        rows = connection.execute(
            "SELECT payload_json FROM jobs WHERE phase=? AND run_id=? ORDER BY job_id",
            (phase, run_id),
        ).fetchall()
    connection.close()
    if rows:
        return [json.loads(row["payload_json"]) for row in rows]
    # A current-run query must not fall back to the legacy directory: those
    # files have no run identity and could belong to an older snapshot.
    if run_id is not None:
        return []
    # Read-only compatibility for interrupted pre-SQLite runs. This fallback
    # is never used by ready/admissible and does not mutate legacy files.
    root = state.skill_dir(target) / "jobs"
    values = [state.read_json(path, {}) for path in sorted(root.glob("*.json"))] if root.is_dir() else []
    return [value for value in values if isinstance(value, dict) and value.get("phase") == phase]


def current_jobs_for_phase(target, phase):
    """Return jobs belonging to the active snapshot/run only.

    A SQLite scheduler database can outlive an analysis.  Consumers that
    summarize a phase must never combine jobs from an older run with the
    current candidate set.
    """
    run_id, _, _ = _run_id(target)
    return jobs_for_phase(target, phase, run_id=run_id)


def restart_invalid_phase_plan(target, phase):
    """Requeue the current phase-plan job after a rejected plan contract.

    Older Skill versions could accept malformed ``phases.json`` output and
    mark its job successful.  A resumed run must not be stranded behind that
    stale success record; the Worker gets a fresh bounded attempt and must
    rewrite the required plan artifact.
    """
    if phase not in {"project_understanding", "refresh_plan"}:
        return {"requeued": []}
    jobs = [job for job in current_jobs_for_phase(target, phase) if job.get("type") == "phase_plan"]
    plan_path = state.fm_dir(target) / "phases.json"
    if not jobs or state.phases_schema_ready(target)[0]:
        return {"requeued": []}
    if plan_path.exists():
        plan_path.unlink()
    requeued = []
    for job in jobs:
        job.update({
            "status": "queued", "attempts": 0, "runtime_attempts": 0,
            "failure_class": None, "message": "requeued after invalid phase-plan contract",
            "requeued_at": state.now(),
        })
        for key in ("result", "completed_at", "failed_at", "valid_outputs", "invalid_artifacts"):
            job.pop(key, None)
        _save(target, job)
        requeued.append(job["id"])
    return {"requeued": requeued}


def _lease_expiry(target):
    config = state.read_json(state.skill_dir(target) / "config.json", {})
    seconds = config.get("worker_lease_seconds", 900) if isinstance(config, dict) else 900
    if not isinstance(seconds, int) or seconds < 1: seconds = 900
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)).replace(microsecond=0).isoformat()


def heartbeat_lease(target, job_id, attempt=None):
    job = _load(target, job_id)
    attempt = int(job.get("attempts", 0) if attempt is None else attempt)
    connection = _connect(target)
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute("SELECT attempt FROM leases WHERE job_id=?", (job_id,)).fetchone()
        if not row or row["attempt"] != attempt: raise ValueError("worker lease is absent or stale")
        connection.execute(
            "UPDATE leases SET heartbeat_at=?,expires_at=? WHERE job_id=? AND attempt=?",
            (state.now(), _lease_expiry(target), job_id, attempt),
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK"); connection.close(); raise
    connection.close()
    return {"job_id": job_id, "attempt": attempt, "expires_at": _lease_expiry(target)}


def _artifact_identity(target, job):
    paths = set(job.get("required_outputs", []))
    if job.get("type") == "bug_validate" and not job.get("legacy_contract"):
        from reproduction_runner import attempt_dir
        for ordinal in range(1, int(job.get("attempts", 0)) + 1):
            root = attempt_dir(target, job["input"]["bug_id"], ordinal)
            paths.update(path.relative_to(target).as_posix() for path in root.glob("probe.*") if path.is_file())
            paths.update((root / name).relative_to(target).as_posix() for name in ("reproduction.json", "reproduction_result.json", "build_profile.json", "build_result.json") if (root / name).is_file())
        detail = target / (job["bug_result_path"].removesuffix(".result.json") + ".md")
        if detail.is_file():
            paths.add(detail.relative_to(target).as_posix())
    values = []
    for relative in sorted(paths):
        path = target / relative
        if not path.is_file(): continue
        digest = state.file_hash(path)
        values.append({"path": relative, "sha256": digest, "size": path.stat().st_size})
    combined = hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return combined, values


def accepted_origin(target, job_id):
    """Read the immutable run identity without importing or rebinding a job."""
    _safe_id(job_id)
    path = checkpoint.db_path(target)
    if not path.is_file():
        raise ValueError("accepted scheduler database is missing")
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as connection:
        row = connection.execute("SELECT r.snapshot_commit,r.input_fingerprint FROM jobs j JOIN runs r ON r.run_id=j.run_id WHERE j.job_id=?", (job_id,)).fetchone()
    if row is None:
        raise ValueError("accepted job has no originating run")
    return {"snapshot_commit": row[0], "input_fingerprint": row[1]}


def accepted_job(target, job_id, *, snapshot_commit, input_fingerprint):
    """Return a Bug Validator job only when its exact durable receipt still verifies."""
    _safe_id(job_id)
    path = checkpoint.db_path(target)
    if not path.is_file():
        raise ValueError(f"accepted Bug Validator receipt unavailable for {job_id}: scheduler database is missing")
    connection = None
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT j.*, r.snapshot_commit, r.input_fingerprint, "
            "a.status AS attempt_status, a.input_hash AS attempt_input_hash, a.artifact_hash AS attempt_artifact_hash, "
            "p.input_hash AS receipt_input_hash, p.artifact_hash AS receipt_artifact_hash, p.payload_json AS receipt_json "
            "FROM jobs j JOIN runs r ON r.run_id=j.run_id "
            "JOIN attempts a ON a.job_id=j.job_id AND a.attempt=j.attempt "
            "JOIN receipts p ON p.job_id=j.job_id AND p.attempt=j.attempt WHERE j.job_id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError("durable job, attempt, or receipt is missing")
        run_id = hashlib.sha256(f"{snapshot_commit}\0{input_fingerprint}".encode()).hexdigest()[:24]
        if (row["run_id"], row["snapshot_commit"], row["input_fingerprint"]) != (run_id, snapshot_commit, input_fingerprint):
            raise ValueError("receipt belongs to another analysis run")
        job, receipt = json.loads(row["payload_json"]), json.loads(row["receipt_json"])
        if not isinstance(job, dict) or job.get("schema_version") != 2 or job.get("legacy_contract") or job.get("type") != "bug_validate":
            raise ValueError("receipt does not belong to a current Bug Validator job")
        if job.get("id") != job_id or row["type"] != job["type"] or row["phase"] != job.get("phase"):
            raise ValueError("job identity differs from its durable row")
        if row["status"] != "succeeded" or job.get("status") != "succeeded" or row["attempt_status"] != "succeeded":
            raise ValueError("job or accepted attempt has not succeeded")
        if row["attempt"] < 1 or job.get("attempts") != row["attempt"]:
            raise ValueError("receipt does not match the current job attempt")
        expected_input = _payload_hash(job)
        if any(value != expected_input for value in (row["input_hash"], job.get("input_hash"), row["attempt_input_hash"], row["receipt_input_hash"])):
            raise ValueError("accepted input identity differs from the job")
        if receipt != job.get("result") or receipt != json.loads(row["result_json"]):
            raise ValueError("receipt payload differs from the accepted job result")
        error = _validate_report(job, receipt) or _validate(target, job, receipt, snapshot_commit=snapshot_commit)
        if error:
            raise ValueError(error)
        import bug_validation_executor
        if receipt != bug_validation_executor.canonical_finalization_receipt(target, job):
            raise ValueError("receipt is not the canonical finalization receipt")
        computed, artifacts = _artifact_identity(target, job)
        if computed != row["receipt_artifact_hash"] or computed != row["attempt_artifact_hash"]:
            raise ValueError("accepted output bytes have changed")
        stored = connection.execute(
            "SELECT path,sha256,size FROM artifacts WHERE snapshot_commit=? AND job_id=? AND attempt=? ORDER BY path",
            (snapshot_commit, job_id, row["attempt"]),
        ).fetchall()
        if sorted(artifacts, key=lambda item: item["path"]) != [dict(item) for item in stored]:
            raise ValueError("accepted artifact rows do not match the current outputs")
        return job
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError(f"accepted Bug Validator receipt unavailable for {job_id}: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def _record_receipt(target, job, result):
    artifact_hash, artifacts = _artifact_identity(target, job)
    input_hash = job["input_hash"]
    attempt = int(job["attempts"])
    connection = _connect(target)
    existing = connection.execute(
        "SELECT input_hash,artifact_hash,payload_json FROM receipts WHERE job_id=? AND attempt=?",
        (job["id"], attempt),
    ).fetchone()
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
    if existing:
        connection.close()
        if existing["input_hash"] == input_hash and existing["artifact_hash"] == artifact_hash and existing["payload_json"] == encoded:
            return artifact_hash, artifacts, True
        raise ValueError("conflicting duplicate receipt")
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            "INSERT INTO receipts VALUES(?,?,?,?,?,?)",
            (job["id"], attempt, input_hash, artifact_hash, encoded, state.now()),
        )
        _, snapshot, _ = _run_id(target)
        for artifact in artifacts:
            connection.execute(
                "INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?,?,?)",
                (snapshot, artifact["path"], artifact["sha256"], artifact["size"], job["id"], attempt),
            )
        connection.execute(
            "UPDATE attempts SET artifact_hash=?,status='succeeded',completed_at=? WHERE job_id=? AND attempt=?",
            (artifact_hash, state.now(), job["id"], attempt),
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK"); connection.close(); raise
    connection.close()
    return artifact_hash, artifacts, False


def transition(target, job_id, action, result, message, failure_class, attempt=None, input_hash=None, artifact_hash=None):
    job = _load(target, job_id); job.setdefault("max_attempts", _limit(target, job))
    if action == "start":
        if job["status"] != "queued" or job not in ready(target): raise ValueError("job is not ready")
        error = _admission_error(target, job)
        if error: raise ValueError(error)
        job["status"] = "running"; job["attempts"] += 1; job["started_at"] = state.now()
        if job["type"] == "bug_validate" and not job.get("legacy_contract"):
            job["negative_attempt_index"] = int(job.get("negative_attempts", 0)) + 1
        connection = _connect(target)
        connection.execute("BEGIN IMMEDIATE")
        try:
            current = connection.execute(
                "SELECT status,attempt,input_hash FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if not current or current["status"] != "queued" or current["attempt"] + 1 != job["attempts"]:
                raise ValueError("job lease was claimed concurrently")
            connection.execute(
                "INSERT OR REPLACE INTO leases VALUES(?,?,?,?,?,?)",
                (job_id, job["attempts"], "coordinator", state.now(), state.now(), _lease_expiry(target)),
            )
            connection.execute(
                "INSERT INTO attempts(job_id,attempt,input_hash,status,started_at) VALUES(?,?,?,?,?)",
                (job_id, job["attempts"], current["input_hash"], "running", state.now()),
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK"); connection.close(); raise
        connection.close()
    elif action == "complete":
        if attempt is not None and int(attempt) != int(job.get("attempts", 0)):
            raise ValueError("stale attempt receipt rejected")
        if input_hash is not None and input_hash != job.get("input_hash"):
            raise ValueError("receipt input hash mismatch")
        if job["status"] == "succeeded":
            computed, _ = _artifact_identity(target, job)
            connection = _connect(target)
            prior = connection.execute("SELECT * FROM receipts WHERE job_id=? AND attempt=?", (job_id, job["attempts"])).fetchone()
            connection.close()
            encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
            if prior and prior["input_hash"] == job.get("input_hash") and prior["artifact_hash"] == computed and prior["payload_json"] == encoded:
                return job
            raise ValueError("only an identical receipt may be resubmitted after success")
        if job["status"] != "running": raise ValueError("only a running job can complete")
        if isinstance(result, dict) and not job.get("legacy_contract"):
            extra_report_fields = sorted(set(result) - REPORT_KEYS)
            if extra_report_fields:
                job["normalized_report_fields"] = sorted(set(job.get("normalized_report_fields", [])) | set(extra_report_fields))
                result = {key: value for key, value in result.items() if key in REPORT_KEYS}
        error = _validate_report(job, result) or _validate(target, job, result)
        if error:
            if job["type"] == "verify_batch" and job.get("invalid_artifacts"):
                invalid = set(job["invalid_artifacts"])
                original_artifacts = list(job["artifacts"])
                valid_artifacts = [item for item in original_artifacts if item not in invalid]
                job["completed_artifacts"] = sorted(set(job.get("completed_artifacts", [])) | set(valid_artifacts))
                job["valid_outputs"] = [
                    f"fm_agent/logic_verification_results/{Path(item).with_suffix('.json').as_posix()}"
                    for item in valid_artifacts
                ]
                job["artifacts"] = [item for item in job["artifacts"] if item in invalid]
                job["required_outputs"] = [
                    f"fm_agent/logic_verification_results/{Path(item).with_suffix('.json').as_posix()}"
                    for item in job["artifacts"]
                ]
                job["input_hash"] = _payload_hash(job)
                job["partial_results_preserved"] = True
            _fail(job, "output", error)
        elif job["type"] == "bug_validate" and not job.get("legacy_contract") and result["classification"] in BUG_NEGATIVE_CLASSIFICATIONS:
            negative_attempts = int(job.get("negative_attempts", 0)) + 1
            job["negative_attempts"] = negative_attempts; job["result"] = result
            report = state.read_json(target / job["bug_result_path"], {})
            evidence = report["attempts"][-1]["dynamic_evidence"]["reproduction_result"]
            unsupported = state.read_json(target / evidence, {})["state"] == "unsupported"
            if unsupported:
                # Repeating an unavailable runtime cannot add execution evidence.
                job.update({"status": "succeeded", "completed_at": state.now()})
            elif negative_attempts < int(job["negative_max_attempts"]):
                job.update({"status": "retryable", "retry_reason": "negative_result", "message": "Bug Validator did not confirm the candidate; repeat probe required"})
            else: job.update({"status": "succeeded", "completed_at": state.now(), "negative_validation_exhausted": True})
        else:
            job["status"] = "succeeded"; job["completed_at"] = state.now()
            if result is not None: job["result"] = result
        accepted_semantic_attempt = error is None and job["type"] == "bug_validate" and not job.get("legacy_contract")
        if accepted_semantic_attempt:
            job["validated_attempts"] = state.read_json(target / job["bug_result_path"], {})["attempts"]
        if job["status"] == "succeeded" or accepted_semantic_attempt:
            computed, _ = _artifact_identity(target, job)
            if artifact_hash is not None and artifact_hash != computed:
                raise ValueError("receipt artifact hash mismatch")
            _record_receipt(target, job, result)
    elif action == "fail":
        if job["status"] not in {"queued", "running"}: raise ValueError("only queued or running jobs can fail")
        # A Bug Validator that reaches finalization without an immutable
        # reproduction result has not produced a semantic input error.  It is
        # an execution/protocol failure and must consume the bounded runtime
        # retry budget instead of prematurely failing the whole phase.
        if (
            job.get("type") == "bug_validate"
            and not job.get("legacy_contract")
            and failure_class == "input"
            and "dynamic reproduction" in str(message or "").lower()
        ):
            failure_class = "execution"
        _fail(job, failure_class, message)
    else:
        if job["status"] != "retryable": raise ValueError("only a retryable job can be requeued")
        job["status"] = "queued"; job["requeued_at"] = state.now()
    _save(target, job)
    return job
def recover(target):
    run_id, _, _ = _run_id(target)
    connection = _connect(target)
    rows = connection.execute(
        "SELECT payload_json FROM jobs WHERE run_id=? AND status='running' ORDER BY job_id",
        (run_id,),
    ).fetchall()
    connection.close(); succeeded, retryable = [], []
    for row in rows:
        job = json.loads(row["payload_json"])
        job.setdefault("max_attempts", _limit(target, job)); error = _validate(target, job)
        if not job.get("legacy_contract") and error is None:
            error = "interrupted job has no completed Coordinator receipt"
        if error:
            _fail(job, "interrupted", error)
            if job["status"] == "retryable": retryable.append(job["id"])
        else: job["status"] = "succeeded"; job["completed_at"] = state.now(); job["recovered"] = True; succeeded.append(job["id"])
        _save(target, job)
    return {"recovered_succeeded": succeeded, "retryable": retryable}


def reconcile_for_resume(target):
    """Make an interrupted run dispatchable by a new host Coordinator.

    Host Workers do not outlive a terminated Codex/Claude parent turn.  Their
    durable receipts are recovered when valid; every other recoverable job is
    immediately requeued.  Leaving a job in ``retryable`` would make ``next``
    wait forever because only queued jobs are admissible.
    """
    recovered = recover(target)
    run_id, _, _ = _run_id(target)
    connection = _connect(target)
    rows = connection.execute(
        "SELECT job_id FROM jobs WHERE run_id=? AND status='retryable' ORDER BY job_id",
        (run_id,),
    ).fetchall()
    connection.close()
    requeued = []
    for row in rows:
        job = transition(target, row["job_id"], "retry", None, "resume requeue", "interrupted")
        requeued.append(job["id"])
    return {**recovered, "requeued": requeued}


def aggregate(target):
    run_id, _, _ = _run_id(target)
    connection = _connect(target)
    rows = connection.execute(
        "SELECT phase,type,status,COUNT(*) AS count FROM jobs WHERE run_id=? "
        "GROUP BY phase,type,status ORDER BY phase,type,status",
        (run_id,),
    ).fetchall()
    pending = connection.execute(
        "SELECT COUNT(*) FROM jobs WHERE run_id=? AND status IN ('queued','running','retryable')",
        (run_id,),
    ).fetchone()[0]
    connection.close()
    return {
        "schema_version": SCHEDULER_SCHEMA_VERSION,
        "pending": pending,
        "groups": [dict(row) for row in rows],
        "converged": pending == 0 and not any(row["status"] == "failed" for row in rows),
    }


def aggregate_readonly(target):
    """Read the live scheduler without creating a database or changing its rows."""
    path = checkpoint.db_path(target)
    if not path.is_file():
        raise ValueError("scheduler database is missing")
    run_id, _, _ = _run_id(target)
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT phase,type,status,COUNT(*) AS count FROM jobs WHERE run_id=? "
            "GROUP BY phase,type,status ORDER BY phase,type,status",
            (run_id,),
        ).fetchall()
        pending = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE run_id=? AND status IN ('queued','running','retryable')",
            (run_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    return {
        "schema_version": SCHEDULER_SCHEMA_VERSION,
        "pending": pending,
        "groups": [dict(row) for row in rows],
        "converged": pending == 0 and not any(row["status"] == "failed" for row in rows),
    }


def reset_bug_validation_job(target, job_id):
    """Reset only the selected same-run candidate before an explicit revalidation."""
    _safe_id(job_id)
    run_id, _, _ = _run_id(target)
    connection = _connect(target)
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute("SELECT run_id,type,status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row and (row["run_id"] != run_id or row["type"] != "bug_validate" or row["status"] == "running"):
            raise ValueError("only an inactive Bug Validator candidate from this analysis may be reset")
        for table in ("receipts", "artifacts", "attempts", "jobs"):
            connection.execute(f"DELETE FROM {table} WHERE job_id=?", (job_id,))
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    _path(target, job_id).unlink(missing_ok=True)


def clear_run(target):
    connection = _connect(target)
    connection.execute("BEGIN IMMEDIATE")
    try:
        for table in ("receipts", "artifacts", "attempts", "leases", "job_dependencies", "jobs", "phases", "runs"):
            connection.execute(f"DELETE FROM {table}")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK"); connection.close(); raise
    connection.close()
    return {"cleared": True}


def main():
    parser = argparse.ArgumentParser(description="Record, admit, and validate bounded current FM-Agent host worker jobs.")
    parser.add_argument("action", choices=("create", "ready", "admissible", "capacity", "aggregate", "phase-receipt", "start", "heartbeat", "complete", "fail", "retry", "recover", "show")); parser.add_argument("--project", required=True); parser.add_argument("--job-id"); parser.add_argument("--phase"); parser.add_argument("--job-json"); parser.add_argument("--result-json"); parser.add_argument("--message"); parser.add_argument("--failure-class", choices=tuple(sorted(FAILURE_CLASSES)), default="execution"); parser.add_argument("--attempt", type=int); parser.add_argument("--input-hash"); parser.add_argument("--artifact-hash"); parser.add_argument("--limit", type=int); parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args(); target = project(args)
    try:
        if args.action == "create":
            if not args.job_json: raise ValueError("--job-json is required")
            response = create(target, json.loads(args.job_json))
        elif args.action == "ready": response = {"jobs": ready(target, args.limit, args.offset), "offset": args.offset}
        elif args.action == "admissible": response = admissible(target)
        elif args.action == "capacity": response = _capacity(target)
        elif args.action == "aggregate": response = aggregate(target)
        elif args.action == "phase-receipt":
            if not args.phase: raise ValueError("--phase is required")
            response = phase_receipt(target, args.phase)
        elif args.action == "recover": response = recover(target)
        elif args.action == "heartbeat":
            if not args.job_id: raise ValueError("--job-id is required")
            response = heartbeat_lease(target, args.job_id, args.attempt)
        else:
            if not args.job_id: raise ValueError("--job-id is required")
            response = _load(target, args.job_id) if args.action == "show" else transition(target, args.job_id, args.action, json.loads(args.result_json) if args.result_json else None, args.message, args.failure_class, args.attempt, args.input_hash, args.artifact_hash)
        print(json.dumps(response, ensure_ascii=False, indent=2))
    except (ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)); sys.exit(2)
if __name__ == "__main__": main()
