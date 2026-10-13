#!/usr/bin/env python3
# Modified by AIResearchSkill: preserve extraction scope and require semantic static graph edges.
"""One-step, recovery-safe phase controller for a full FM-Agent analysis.

The host Coordinator owns Worker invocation, but it must not have to remember
phase-start/phase-complete calls or manufacture the project-understanding job.
This controller exposes exactly one legal next action and seals a phase as soon
as its deterministic gate is satisfied.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from _common import project, state
import durable_executor
import executor
import scheduler
import checkpoint
import job_planner
from stage_gate import validate


def _pipeline(target: Path, action: str, phase: str | None = None) -> dict:
    command = [sys.executable, str(Path(__file__).with_name("pipeline.py")), action, "--project", str(target)]
    if phase:
        command += ["--phase", phase]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return json.loads(completed.stdout)


def _phase_plan(target: Path, phase: str) -> dict:
    jobs = scheduler.current_jobs_for_phase(target, phase)
    current = [job for job in jobs if job.get("type") == "phase_plan"]
    if current:
        return current[0]
    return scheduler.create(target, {
        "id": job_planner._qualified_id(target, f"{phase.replace('_', '-')}-phase-plan"),
        "phase": phase,
        "type": "phase_plan",
        "depends_on": [],
        "required_outputs": ["fm_agent/phases.json"],
        "artifacts": [],
    })


def _static_edges(target: Path, phase: str) -> dict:
    jobs = scheduler.current_jobs_for_phase(target, phase)
    current = [job for job in jobs if job.get("type") == "resolve_agent_static_edges"]
    if current:
        return current[0]
    manifest = state.read_json(state.fm_dir(target) / "extraction_manifest.json", {})
    functions = manifest.get("functions")
    if not isinstance(functions, list):
        raise ValueError("static edge resolution requires the current extraction manifest")
    return scheduler.create(target, {
        "id": job_planner._qualified_id(target, f"{phase.replace('_', '-')}-static-edges"),
        "phase": phase,
        "type": "resolve_agent_static_edges",
        "depends_on": [],
        "required_outputs": ["fm_agent/agent_static_edges_candidate.json"],
        "artifacts": [item["artifact"] for item in functions],
        "input": {
            "extraction_manifest": "fm_agent/extraction_manifest.json",
            "source_paths": sorted({item["source_path"] for item in functions}),
        },
    })


def _deterministic_action(target: Path, record: dict, phase: str) -> dict | None:
    """Return the only non-Worker action a parent may perform for this phase."""
    if phase == "validate_baseline":
        return {"action": "run_deterministic", "phase": phase, "kind": "validate_baseline", "argv": [
            sys.executable, str(Path(__file__).with_name("executor.py")), "validate-baseline", "--project", str(target)]}
    if phase == "preserve_specs":
        return {"action": "run_deterministic", "phase": phase, "kind": "preserve_specs", "argv": [
            sys.executable, str(Path(__file__).with_name("executor.py")), "preserve-specs", "--project", str(target)]}
    if phase == "select_scope":
        return {"action": "run_deterministic", "phase": phase, "kind": "select_seed", "argv": [
            sys.executable, str(Path(__file__).with_name("executor.py")), "select", "--project", str(target)]}
    if phase in {"extraction", "diff"}:
        command = [sys.executable, str(Path(__file__).with_name("executor.py")), "extract", "--project", str(target)]
        for source in record.get("inputs", {}).get("submodules", []):
            command += ["--submodule", source]
        config = record.get("inputs", {}).get("config", {})
        if config.get("call_graph_backend") == "codegraph":
            export = state.control_dir(target) / "codegraph_export.json"
            if not export.is_file():
                return {"action": "run_deterministic", "phase": phase, "kind": "codegraph_export", "command": "codegraph export is required before extraction"}
            command += ["--codegraph-export", str(export)]
        if phase == "diff":
            return {"action": "run_deterministic", "phase": phase, "kind": "extract_and_diff", "argv": [command,
                [sys.executable, str(Path(__file__).with_name("executor.py")), "diff", "--project", str(target)]]}
        return {"action": "run_deterministic", "phase": phase, "kind": "extract", "argv": command}
    if phase in {"call_graph", "rebuild_graph"}:
        command = [sys.executable, str(Path(__file__).with_name("executor.py")), "graph", "--project", str(target)]
        config = record.get("inputs", {}).get("config", {})
        if config.get("call_graph_backend") == "codegraph":
            export = state.control_dir(target) / "codegraph_export.json"
            if not export.is_file():
                return {"action": "run_deterministic", "phase": phase, "kind": "codegraph_export", "command": "codegraph export is required before graph construction"}
            command += ["--codegraph-export", str(export)]
        else:
            promote = [sys.executable, str(Path(__file__).with_name("executor.py")), "record-agent-edges", "--project", str(target), "--edges-file", str(state.fm_dir(target) / "agent_static_edges_candidate.json")]
            return {"action": "run_deterministic", "phase": phase, "kind": "graph", "argv": [promote, command]}
        return {"action": "run_deterministic", "phase": phase, "kind": "graph", "argv": command}
    if phase in {"specification", "verification", "verify_affected", "update_specs"}:
        return {
            "action": "run_deterministic", "phase": phase, "kind": "plan_and_prepare",
            "argv": [
                [sys.executable, str(Path(__file__).with_name("job_planner.py")), "--project", str(target), "--phase", phase],
                [sys.executable, str(Path(__file__).with_name("semantic_executor.py")), "prepare", "--project", str(target), "--phase", phase],
            ],
        }
    if phase == "bug_validation":
        return {
            "action": "run_deterministic", "phase": phase, "kind": "plan_bug_validation",
            "argv": [[sys.executable, str(Path(__file__).with_name("job_planner.py")), "--project", str(target), "--phase", phase]],
        }
    return None


def _run_action(action: dict) -> None:
    commands = action.get("argv")
    if not isinstance(commands, list) or not commands:
        raise RuntimeError("current phase action cannot be executed automatically")
    if commands and isinstance(commands[0], str):
        commands = [commands]
    for command in commands:
        if not isinstance(command, list) or not all(isinstance(value, str) for value in command):
            raise RuntimeError("phase action has an invalid argv contract")
        completed = subprocess.run(command, text=True, capture_output=True)
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "deterministic phase action failed")


def next_step(target: Path, limit: int, host: str) -> dict:
    record = state.active_record(target)
    if not record or record.get("status") != "running":
        raise RuntimeError("no running FM-Agent analysis")
    if isinstance(record.get("validation_scope"), list) and record.get("validation_job_id"):
        job = scheduler._load(target, record["validation_job_id"])
        if job.get("status") == "succeeded":
            source = checkpoint.source_project(target)
            return {"action": "validation_ready_to_publish", "phase": "bug_validation", "job_id": job["id"],
                    "candidate_id": job["input"]["candidate_id"], "source_project": str(source),
                    "argv": [sys.executable, str(Path(__file__).with_name("orchestrate.py")),
                             "validate-complete", "--project", str(source)]}
    if all(record.get("phase_status", {}).get(name, {}).get("status") == "succeeded" for name in record.get("phases", [])):
        record = _pipeline(target, "complete")
        return {"action": "analysis_completed", "analysis": record}
    phase = record.get("current_phase")
    if phase not in record.get("phases", []):
        raise RuntimeError("active analysis has no valid current phase")
    phase_state = record.get("phase_status", {}).get(phase, {})
    if phase_state.get("status") != "running":
        record = _pipeline(target, "phase-start", phase)
        return {"action": "phase_started", "phase": phase, "analysis": record, "next": "call phase_driver next again"}

    if phase in {"preserve_specs", "diff", "select_scope"}:
        filename = {"preserve_specs": "preserved_specs.json", "diff": "diff.json", "select_scope": "incremental_decision.json"}[phase]
        artifact = state.read_json(state.control_dir(target) / filename, {})
        if artifact.get("snapshot_commit") != record["snapshot_commit"]:
            return _deterministic_action(target, record, phase)
    if phase in {"specification", "update_specs"} and not scheduler.current_jobs_for_phase(target, phase) and not state._knowledge_manifest_ready(target)[0]:
        return {"action": "run_deterministic", "phase": phase, "kind": "materialize_knowledge", "argv": [
            sys.executable, str(Path(__file__).with_name("knowledge.py")), "materialize", "--project", str(target)]}
    if phase == "select_scope":
        job_planner._select_scope(target, record, phase)
        import semantic_executor
        semantic_executor.prepare(target, phase)
    elif phase == "update_specs":
        job_planner._update_specs(target, record, phase)
        import semantic_executor
        semantic_executor.prepare(target, phase)

    # Phase Plan is a first-class Worker job, never an instruction the parent
    # must remember to synthesize.
    if phase in {"project_understanding", "refresh_plan"}:
        _phase_plan(target, phase)
    static_job = None
    if phase in {"call_graph", "rebuild_graph"} and record.get("inputs", {}).get("config", {}).get("call_graph_backend") != "codegraph":
        static_job = _static_edges(target, phase)

    scheduled = durable_executor.next_actions(target, limit, host=host)
    if scheduled["action"] == "dispatch":
        return {**scheduled, "action": "dispatch_workers", "phase": phase}
    if scheduled["action"] in {"wait_for_completion_event", "phase_failed"}:
        return {**scheduled, "phase": phase}

    if static_job is not None:
        if static_job.get("status") != "succeeded":
            return {"action": "phase_blocked", "phase": phase, "reason": "static edge Worker has not succeeded", "analysis": record}
        edges = executor._validate_edges(target, state.read_json(target / static_job["required_outputs"][0], {}))
        promoted = state.read_json(state.control_dir(target) / "agent_static_edges.json", {})
        graph = state.read_json(state.control_dir(target) / "graph_edges.json", {})
        # Existing layer files cannot bypass the semantic caller/callee pass.
        if promoted.get("backend") != "agent-static" or promoted.get("edges") != edges or graph.get("backend") != "agent-static" or graph.get("edges") != edges:
            return _deterministic_action(target, record, phase)

    if phase == "finalize":
        command = [sys.executable, str(Path(__file__).with_name("bug_summary.py")), "--project", str(target), "--mode", record["mode"]]
        completed = subprocess.run(command, text=True, capture_output=True)
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "could not write Bug Validator summary")
    gate = validate(target, record["mode"], phase, record.get("inputs", {}).get("submodules", []))
    if gate["ok"]:
        # ``pipeline phase-complete`` requires the durable scheduler fan-in
        # receipt for every phase that owned Worker jobs.  DAG convergence
        # alone is not that receipt; emit it here before sealing the phase.
        scheduler.phase_receipt(target, phase)
        record = _pipeline(target, "phase-complete", phase)
        return {"action": "phase_completed", "phase": phase, "analysis": record, "next": "call phase_driver next again"}

    deterministic = _deterministic_action(target, record, phase)
    if deterministic is not None:
        deterministic["gate_reason"] = gate["reason"]
        return deterministic
    return {"action": "phase_blocked", "phase": phase, "reason": gate["reason"], "analysis": record}


def main() -> None:
    parser = argparse.ArgumentParser(description="Return the one legal next full/incremental FM-Agent phase action.")
    parser.add_argument("action", choices=("next", "execute"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--host", choices=("auto", "claude", "codex", "portable"), default="auto")
    args = parser.parse_args()
    try:
        target = project(args)
        if args.action == "execute":
            action = next_step(target, args.limit, args.host)
            if action.get("action") != "run_deterministic":
                raise RuntimeError("the current phase does not have an executable deterministic action")
            _run_action(action)
            result = next_step(target, args.limit, args.host)
        else:
            result = next_step(target, args.limit, args.host)
        code = 0
    except (OSError, RuntimeError, ValueError) as exc:
        result, code = {"ok": False, "error": str(exc)}, 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
