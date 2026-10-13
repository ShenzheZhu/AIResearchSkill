#!/usr/bin/env python3
# Modified by AIResearchSkill: normalize explicit scopes and require accepted validation evidence before publication.
"""Preflight, Git-snapshot mode selection, and active-analysis preparation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from _common import project, state
from config import DEFAULTS, load
from isolation import clear_failure, create as create_snapshot, discard as discard_snapshot, marker as snapshot_marker, publish_run_index
from locking import acquire, reclaim_for_resume, release
import checkpoint
import scheduler
import versioning


def valid_settings(target, config):
    issues = []
    for item in config["submodules"]:
        path = (target / item).resolve()
        if not path.is_dir() or target not in path.parents and path != target: issues.append(f"invalid --submodule: {item}")
    for item in config["knowledge"]:
        path = Path(item); path = path if path.is_absolute() else target / path
        if not path.is_file() or path.suffix.lower() not in {".md", ".markdown"}: issues.append(f"knowledge must be readable Markdown: {item}")
    if config.get("extra_edge"):
        command = [sys.executable, str(Path(__file__).with_name("call_graph_edges.py")), config["extra_edge"]]
        if subprocess.run(command, text=True, capture_output=True).returncode: issues.append("extra-edge validation failed")
    return issues


def build_config(args, target, base=None):
    candidate = dict(base if isinstance(base, dict) else load(target))
    config = {key: candidate.get(key, value) for key, value in DEFAULTS.items()}
    if args.submodules: config["submodules"] = args.submodules
    if args.knowledge: config["knowledge"] = args.knowledge
    if args.extra_edge is not None: config["extra_edge"] = args.extra_edge
    if args.codegraph: config["call_graph_backend"] = "codegraph"
    if args.one_phase: config["one_phase"] = True
    if getattr(args, "all_bugs", None) is not None:
        config["all_bugs"] = args.all_bugs
    return config


def developer_intent(target, args):
    note = getattr(args, "note", "").strip()
    intent_file = getattr(args, "incremental", None)
    if intent_file:
        path = Path(intent_file)
        path = path if path.is_absolute() else target / path
        if not path.is_file() or path.suffix.lower() not in {".md", ".markdown"}:
            raise ValueError("--incremental requires a readable Markdown intent file")
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError("incremental intent must not be empty")
        note = "\n\n".join(part for part in (text, note) if part)
    return note


def inspection_config(args, target):
    saved = state.read_json(state.skill_dir(target) / "config.json", {})
    baseline = state.read_json(state.skill_dir(target) / "baseline.json", {})
    prior = baseline.get("inputs", {}).get("config") if isinstance(baseline, dict) else None
    base = dict(prior if isinstance(prior, dict) else load(target)); base.update(saved if isinstance(saved, dict) else {})
    return build_config(args, target, base)


def inspect(target, args, config=None, intent_override=None):
    config = inspection_config(args, target) if config is None else dict(config)
    issues = valid_settings(target, config)
    if issues: return {"ok": False, "issues": issues}
    scopes = [(target / item).resolve().relative_to(target).as_posix() for item in config["submodules"]]
    config["submodules"] = [] if "." in scopes else sorted(set(scopes))
    preflight = state.preflight(target, config["submodules"])
    if not preflight["ok"]: return {"ok": False, "preflight": preflight}
    fingerprint, _ = state.fingerprint(target, config["one_phase"], config["submodules"], config.get("extra_edge"), config["knowledge"], config)
    baseline = state.inspect_baseline(target, fingerprint, config["submodules"])
    try:
        intent = developer_intent(target, args) if intent_override is None else intent_override
    except (OSError, ValueError) as exc:
        return {"ok": False, "issues": [str(exc)]}
    if getattr(args, "incremental", None) and not baseline["valid"]:
        return {"ok": False, "issues": ["incremental analysis requires a compatible completed baseline: " + baseline.get("reason", "unavailable")]}
    prior_intent = baseline.get("saved", {}).get("inputs", {}).get("config", {}).get("incremental_intent", "")
    new_intent = bool(intent) and intent != prior_intent
    mode = "noop" if baseline["valid"] and baseline.get("manifest_compatible") and not new_intent else "incremental" if baseline["valid"] else "full"
    return {"ok": True, "mode": mode, "baseline": baseline, "config": config, "intent": intent, "requires_codegraph": mode != "noop"}


def resume_overrides(args):
    return bool(args.note.strip() or getattr(args, "incremental", None) or args.submodules or args.knowledge or args.extra_edge is not None or args.one_phase or args.codegraph)


def call_pipeline(target, action, mode=None, config=None):
    command = [sys.executable, str(Path(__file__).with_name("pipeline.py")), action, "--project", str(target)]
    if mode: command += ["--mode", mode]
    if config is not None:
        command += ["--config-json", json.dumps(config)]
        for item in config["submodules"]: command += ["--submodule", item]
        if config["one_phase"]: command.append("--one-phase")
        if config.get("extra_edge"): command += ["--extra-edge", config["extra_edge"]]
        for item in config["knowledge"]: command += ["--knowledge", item]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode: raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return json.loads(completed.stdout)


def _active_ref(source_target):
    return state.git(source_target, "rev-parse", "--verify", "refs/fm-agent-skill/active", check=False)


def resume_plan(source_target, args):
    """Locate one resumable run, using a live cache or rebuilding it once.

    This is shared by ordinary dispatch and explicit resume.  A live private
    snapshot may resume before its first sealed phase; rebuilding a missing
    snapshot requires the durable checkpoint.
    """
    if resume_overrides(args):
        return {"ok": False, "reason": "resume cannot override current analysis settings"}
    marker = snapshot_marker(source_target)
    value = marker.get("snapshot") if isinstance(marker, dict) else None
    if isinstance(value, str) and Path(value).is_dir():
        target = Path(value).resolve()
        record = state.active_record(target)
        commit = _active_ref(source_target)
        if not commit:
            return {"ok": False, "reason": "active Git ref is missing for the live analysis snapshot"}
        if record.get("snapshot_commit") != commit:
            return {"ok": False, "reason": "active Git ref differs from the live analysis snapshot"}
        checked = state.inspect_resume(target)
        if not checked.get("ok"):
            return checked
        requested = getattr(args, "all_bugs", None)
        if requested is not None and requested != checked.get("config", {}).get("all_bugs", False):
            return {"ok": False, "reason": "resume cannot change the all-bugs reasoning mode"}
        checkpoint_head = checkpoint.root(source_target) / "HEAD"
        if checkpoint_head.is_file():
            try:
                versioning.require_compatible(source_target)
                sealed = checkpoint.validate(source_target)
            except Exception as exc:
                return {"ok": False, "reason": str(exc)}
            if sealed.get("snapshot_commit") != commit:
                return {"ok": False, "reason": "live snapshot differs from the durable checkpoint"}
        return {
            "ok": True, "target": target, "checked": checked,
            "source": "live_snapshot", "checkpoint": sealed if checkpoint_head.is_file() else None,
        }
    rebuilt = checkpoint.inspect_auto_resume(source_target)
    if not rebuilt.get("ok"):
        return rebuilt
    try:
        versioning.require_compatible(source_target)
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}
    target = Path(rebuilt["snapshot"]).resolve()
    checked = state.inspect_resume(target)
    if not checked.get("ok"):
        return checked
    requested = getattr(args, "all_bugs", None)
    if requested is not None and requested != checked.get("config", {}).get("all_bugs", False):
        return {"ok": False, "reason": "resume cannot change the all-bugs reasoning mode"}
    return {"ok": True, "target": target, "checked": checked, "source": "reconstructed_checkpoint", "checkpoint": rebuilt.get("checkpoint")}


def continue_current(source_target, args, *, automatic: bool):
    plan = resume_plan(source_target, args)
    if not plan.get("ok"):
        return plan
    target = plan["target"]
    try:
        lock = reclaim_for_resume(target, args.take_over)
        reconciliation = scheduler.reconcile_for_resume(target)
        record = call_pipeline(target, "resume")
        checkpoint_id = (plan.get("checkpoint") or {}).get("checkpoint_id")
        publish_run_index(target, record, checkpoint_id, "resume")
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "resume_source": plan["source"]}
    return {
        "ok": True, "mode": "resume", "auto_resume": automatic,
        "project": str(target), "source_project": str(source_target),
        "resume_source": plan["source"], "resume_from_phase": record["current_phase"],
        "config": plan["checked"]["config"], "lock": lock,
        "reconciliation": reconciliation, "analysis": record,
    }


def validate_inspect(target, identity):
    if not isinstance(identity, str) or not identity:
        return {"ok": False, "reason": "--function-id is required (a function or candidate ID)"}
    if snapshot_marker(target).get("snapshot"):
        return {"ok": False, "reason": "another FM-Agent snapshot is active"}
    preview = inspect(target, argparse.Namespace(submodules=[], knowledge=[], extra_edge=None, codegraph=False, one_phase=False))
    baseline = preview.get("baseline", {}) if isinstance(preview, dict) else {}
    if not preview.get("ok") or not baseline.get("valid"):
        return {"ok": False, "reason": "a valid completed FM-Agent baseline is required"}
    if not baseline.get("manifest_compatible"):
        return {"ok": False, "reason": baseline.get("manifest_reason") or "source changed after the baseline; run incremental analysis before dynamic validation", "changed_sources": baseline.get("changed_sources", [])}
    candidates = state.direct_candidates(target, snapshot_commit=baseline["commit"])
    matches = [key for key, item in candidates.items() if key == identity or item["function_id"] == identity]
    if len(matches) != 1:
        return {"ok": False, "reason": "choose exactly one current direct MISMATCH candidate", "candidate_ids": matches}
    candidate_id = matches[0]
    return {"ok": True, "function_id": candidates[candidate_id]["function_id"], "candidate_id": candidate_id,
            "baseline_commit": baseline["commit"], "config": preview["config"]}


def validation_bug_id(candidate_id: str, run_id: str, nonce: str) -> str:
    return hashlib.sha256(candidate_id.encode()).hexdigest()[:16] + "-" + run_id + "-" + nonce


def _replace_tree(origin: Path, destination: Path) -> None:
    """Atomically replace one private artifact tree without touching siblings."""
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    shutil.rmtree(temporary, ignore_errors=True)
    shutil.copytree(origin, temporary)
    shutil.rmtree(destination, ignore_errors=True)
    os.replace(temporary, destination)


def merge_validation_candidate(source_target: Path, snapshot: Path, job: dict) -> dict:
    """Promote only the assigned candidate report and its real probe evidence."""
    bug_id = job["input"]["bug_id"]
    origin_result = snapshot / job["bug_result_path"]
    result = state.read_json(origin_result, {})
    if result.get("function_id") != job["input"]["function_id"] or result.get("candidate_id") != job["input"]["candidate_id"]:
        raise ValueError("completed dynamic validation belongs to a different candidate")
    destination_root = state.fm_dir(source_target) / "bug_validation"
    destination_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origin_result, source_target / job["bug_result_path"])
    origin_detail = state.fm_dir(snapshot) / "bug_validation" / f"{bug_id}.md"
    if origin_detail.is_file():
        shutil.copy2(origin_detail, destination_root / origin_detail.name)
    origin_probe = state.skill_dir(snapshot) / "probes" / bug_id
    if origin_probe.is_dir():
        _replace_tree(origin_probe, state.skill_dir(source_target) / "probes" / bug_id)
    return result


def write_partial_validation_summary(target: Path) -> dict:
    snapshot = state.baseline_commit(target) or state.current_snapshot_commit(target)
    candidates = state.direct_candidates(target, snapshot_commit=snapshot)
    reports = {}
    for candidate_id in candidates:
        try:
            job = state.accepted_candidate(target, candidate_id, snapshot)
        except ValueError:
            continue
        reports[candidate_id] = state.read_json(target / job["bug_result_path"], {})
    counts = {status: sum(report.get("confirmation_status") == status for report in reports.values()) for status in state.BUG_FINAL_STATUSES}
    summary = {
        "schema_version": 2, "snapshot_commit": snapshot,
        "dynamic_validation": "partial" if reports else "not_requested", "total_candidates": len(candidates),
        "total_static_findings": len(set(candidates) - set(reports)), "total_confirmed": counts["confirmed"],
        "total_rejected": counts["rejected"], "total_inconclusive": counts["inconclusive"],
        "validated_function_ids": sorted({candidates[key]["function_id"] for key in reports}),
        "validated_candidate_ids": sorted(reports), "static_finding_ids": sorted(set(candidates) - set(reports)),
        "generated_at": state.now(),
    }
    state.atomic_json(state.fm_dir(target) / "bug_validation" / "summary.json", summary)
    return summary


def validate_dispatch(source_target, identity):
    checked = validate_inspect(source_target, identity)
    if not checked["ok"]:
        return checked
    function_id, candidate_id = checked["function_id"], checked["candidate_id"]
    snapshot_data = create_snapshot(source_target)
    target = Path(snapshot_data["snapshot"]).resolve()
    try:
        # Probe the original analyzed tree, including baselines captured from
        # uncommitted source; current source compatibility was checked above.
        if state.current_snapshot_commit(target) != checked["baseline_commit"]:
            state.git(target, "checkout", "--detach", checked["baseline_commit"])
            marker = snapshot_marker(target)
            marker["snapshot_commit"] = checked["baseline_commit"]
            state.atomic_json(state.skill_dir(target) / "isolation.json", marker)
            state.atomic_json(state.skill_dir(source_target) / "isolation.json", marker)
            state.git(source_target, "update-ref", "refs/fm-agent-skill/active", checked["baseline_commit"])
        lock = acquire(target)
        baseline = state.read_json(state.skill_dir(source_target) / "baseline.json", {})
        record = {
            "schema_version": 2, "mode": "full", "status": "running",
            "started_at": state.now(), "current_phase": "bug_validation",
            "phases": ["bug_validation"], "phase_status": {"bug_validation": {"status": "running", "started_at": state.now(), "attempt": 1}},
            "phase_history": {}, "snapshot_commit": state.current_snapshot_commit(target), "baseline_commit": checked["baseline_commit"],
            "fingerprint": baseline.get("run_fingerprint", baseline.get("fingerprint", "")),
            "inputs": baseline.get("inputs", {"config": checked["config"], "submodules": []}),
            "validation_scope": [candidate_id], "resume": {"count": 0},
        }
        state.atomic_json(state.skill_dir(target) / "active.json", record)
        bug_id = validation_bug_id(candidate_id, scheduler._run_id(target)[0], uuid.uuid4().hex[:8])
        job_id = f"bug-validation-{bug_id}"
        record["validation_job_id"] = job_id
        state.atomic_json(state.skill_dir(target) / "active.json", record)
        output = f"fm_agent/bug_validation/{bug_id}.result.json"
        scheduler.create(target, {"id": job_id, "phase": "bug_validation", "type": "bug_validate", "depends_on": [],
            "required_outputs": [output], "artifacts": [],
            "input": {"bug_id": bug_id, "candidate_id": candidate_id, "function_id": function_id, "mode": "full"}})
        state.atomic_json(state.control_dir(target) / "job_plans" / "bug_validation.json", {
            "schema_version": 1, "phase": "bug_validation", "snapshot_commit": record["snapshot_commit"],
            "entries": [{"candidate_id": candidate_id, "function_id": function_id, "job_id": job_id}], "created_jobs": 1, "total_entries": 1})
        return {"ok": True, "project": str(target), "source_project": str(source_target), "job_id": job_id,
                "bug_id": bug_id, "function_id": function_id, "candidate_id": candidate_id, "config": checked["config"], "lock": lock}
    except Exception:
        discard_snapshot(target)
        raise


def validate_complete(source_target):
    data = snapshot_marker(source_target); snapshot_value = data.get("snapshot") if isinstance(data, dict) else None
    if not isinstance(snapshot_value, str) or not Path(snapshot_value).is_dir():
        return {"ok": False, "reason": "no active dynamic-validation snapshot"}
    snapshot = Path(snapshot_value)
    record = state.active_record(snapshot)
    scope = record.get("validation_scope") if isinstance(record, dict) else None
    if not isinstance(scope, list) or len(scope) != 1:
        return {"ok": False, "reason": "dynamic validation job has not completed"}
    jobs = [job for job in scheduler.current_jobs_for_phase(snapshot, "bug_validation") if job.get("id") == record.get("validation_job_id") and job.get("input", {}).get("candidate_id") == scope[0]]
    if len(jobs) != 1 or jobs[0].get("status") != "succeeded":
        return {"ok": False, "reason": "dynamic validation job has not completed"}
    scheduler.accepted_job(snapshot, jobs[0]["id"], snapshot_commit=record["snapshot_commit"], input_fingerprint=record.get("fingerprint", ""))
    result = merge_validation_candidate(source_target, snapshot, jobs[0])
    plan_path = state.control_dir(source_target) / "job_plans" / "bug_validation.json"
    plan = state.read_json(plan_path, {})
    entries = plan.get("entries", []) if plan.get("snapshot_commit") == record["snapshot_commit"] else []
    entries = [entry for entry in entries if entry.get("candidate_id") != scope[0]]
    entries.append({"candidate_id": scope[0], "function_id": jobs[0]["input"]["function_id"], "job_id": jobs[0]["id"]})
    state.atomic_json(plan_path, {
        "schema_version": 1, "phase": "bug_validation", "snapshot_commit": record["snapshot_commit"],
        "entries": entries, "created_jobs": len(entries), "total_entries": len(entries),
    })
    summary = write_partial_validation_summary(source_target)
    discard_snapshot(snapshot)
    return {"ok": True, "candidate_id": scope[0], "function_id": jobs[0]["input"]["function_id"], "result": result, "summary": summary}


def main():
    parser = argparse.ArgumentParser(description="Prepare one FM-Agent analysis in a private Git snapshot worktree.")
    parser.add_argument("action", choices=("inspect", "dispatch", "resume-inspect", "resume", "validate-inspect", "validate-dispatch", "validate-complete")); parser.add_argument("--project", required=True); parser.add_argument("--function-id"); parser.add_argument("--note", default=""); parser.add_argument("--submodule", dest="submodules", action="append", default=[]); parser.add_argument("--one-phase", action="store_true"); parser.add_argument("--extra-edge"); parser.add_argument("--knowledge", action="append", default=[]); parser.add_argument("--codegraph", action="store_true"); parser.add_argument("--force-stale-lock", action="store_true"); parser.add_argument("--take-over", action="store_true")
    parser.add_argument("--incremental", metavar="INTENT_FILE")
    parser.add_argument("--all-bugs", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args(); source_target = project(args)
    if args.action == "validate-inspect":
        result = validate_inspect(source_target, args.function_id); print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(0 if result["ok"] else 2)
    if args.action == "validate-dispatch":
        result = validate_dispatch(source_target, args.function_id); print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(0 if result["ok"] else 2)
    if args.action == "validate-complete":
        result = validate_complete(source_target); print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(0 if result["ok"] else 2)
    if args.action == "inspect":
        result = inspect(source_target, args); print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(0 if result["ok"] else 2)
    pending = snapshot_marker(source_target)
    active_ref = _active_ref(source_target)
    has_active_run = bool(active_ref or (isinstance(pending.get("snapshot"), str) and pending.get("snapshot")))
    # Every user invocation is recovery-first.  ``--resume`` only forbids
    # creating a fresh run; it does not select a separate implementation.
    if args.action == "dispatch" and not resume_overrides(args) and has_active_run:
        result = continue_current(source_target, args, automatic=True)
        print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(0 if result.get("ok") else 2)
    if args.action == "resume-inspect":
        result = resume_plan(source_target, args)
        if result.get("ok"):
            result = {
                "ok": True, "mode": result["checked"]["mode"],
                "resume_from_phase": result["checked"]["resume_from_phase"],
                "config": result["checked"]["config"], "resume_source": result["source"],
                "snapshot": str(result["target"]),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(0 if result["ok"] else 2)
    if args.action == "resume":
        result = continue_current(source_target, args, automatic=False)
        print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(0 if result.get("ok") else 2)
    preview = inspect(source_target, args)
    if not preview["ok"]: print(json.dumps(preview, ensure_ascii=False, indent=2)); raise SystemExit(2)
    if preview["mode"] == "noop":
        clear_failure(source_target)
        record = {"schema_version": 2, "mode": "noop", "status": "noop", "started_at": state.now(), "ended_at": state.now(), "fingerprint": preview["baseline"]["saved"]["fingerprint"], "inputs": preview["baseline"]["saved"]["inputs"], "baseline_commit": preview["baseline"]["commit"]}
        state.atomic_json(state.skill_dir(source_target) / "active.json", record)
        print(json.dumps({"ok": True, "mode": "noop", "project": str(source_target), "baseline": preview["baseline"], "config": preview["config"], "analysis": record}, ensure_ascii=False, indent=2)); return
    try:
        snapshot = create_snapshot(source_target); target = Path(snapshot["snapshot"]).resolve()
        selected = inspect(target, args, preview["config"], intent_override=preview["intent"])
        if not selected["ok"]: raise RuntimeError(str(selected))
        lock = acquire(target, args.force_stale_lock)
        run_config = dict(selected["config"])
        if selected["mode"] == "incremental":
            run_config["incremental_intent"] = preview["intent"]
        record = call_pipeline(target, "prepare", selected["mode"], run_config)
        if selected["mode"] == "incremental":
            record["intent_path"] = str(state.build_intent(target, selected["baseline"]["commit"], preview["intent"])); state.atomic_json(state.skill_dir(target) / "active.json", record)
        publish_run_index(target, record, None, "dispatch")
        print(json.dumps({"ok": True, "mode": selected["mode"], "project": str(target), "source_project": str(source_target), "snapshot": snapshot, "baseline": selected["baseline"], "config": selected["config"], "lock": lock, "analysis": record}, ensure_ascii=False, indent=2))
    except Exception as exc:
        if 'target' in locals() and target != source_target:
            try: discard_snapshot(target)
            except RuntimeError: pass
        print(json.dumps({"ok": False, "reason": str(exc)}, ensure_ascii=False, indent=2)); raise SystemExit(2)


if __name__ == "__main__": main()
