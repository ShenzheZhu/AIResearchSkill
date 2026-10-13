#!/usr/bin/env python3
# Modified by AIResearchSkill: issue complete bounded Worker tickets and validate durable command evidence.
"""Deterministic Bug Validator state machine for a Codex/Claude Coordinator.

This script never starts an LLM, imports FM-Agent, or executes an Agent-provided
command.  It exposes exactly the next host-worker request and owns local
admission, evidence identity checks, retries, and the terminal summary.  In
the default ``agent-executed`` mode, the Coordinator invokes the Worker for
preparation, project-scoped execution, and finalization; ``adapter`` retains
the controlled local-runner path.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common import project, state
from fm_agent_core import worker_contracts
from fm_agent_core.languages import execution_ecosystems, profile_for_key
import scheduler
from bug_summary import write_summary
from probe_runner import configured_adapter, run_probe
from reproduction_runner import attempt_dir, output_classification, read_contract, run as run_reproduction


EXECUTION_MODES = {"agent-executed", "adapter"}


def load_job(target: Path, job_id: str) -> dict:
    job = scheduler._load(target, job_id)
    if job.get("type") != "bug_validate" or job.get("legacy_contract"):
        raise ValueError("bug-validation executor requires a current bug_validate job")
    return job


def context(job: dict) -> tuple[str, str]:
    payload = job.get("input") if isinstance(job.get("input"), dict) else {}
    bug_id, mode = payload.get("bug_id"), payload.get("mode")
    if not isinstance(bug_id, str) or not bug_id:
        raise ValueError("bug_validate job input requires a non-empty bug_id")
    if mode not in {"full", "incremental"}:
        raise ValueError("bug_validate job input requires mode full or incremental")
    return bug_id, mode


def execution_mode(target: Path) -> str:
    config = state.read_json(state.skill_dir(target) / "config.json", {})
    value = config.get("bug_validation_execution", "agent-executed") if isinstance(config, dict) else "agent-executed"
    if value not in EXECUTION_MODES:
        raise ValueError(f"unsupported bug_validation_execution mode: {value}")
    return value


def worker_request(target: Path, job: dict, pass_name: str, host: str = "auto") -> dict:
    bug_id, mode = context(job)
    attempt = int(job.get("attempts", 0))
    if attempt < 1:
        raise ValueError("running Bug Validator job has no attempt")
    function_id = job.get("input", {}).get("function_id")
    if not isinstance(function_id, str) or not function_id:
        raise ValueError("Bug Validator ticket requires its assigned function identity")
    root = attempt_dir(target, bug_id, attempt).relative_to(target).as_posix()
    manifest = f"fm_agent_skill/jobs/{job['id']}.json"
    reads = {manifest}
    execution = execution_mode(target)
    index = state.source_index(target) or {}
    item = next((entry for entry in index.get("functions", []) if isinstance(entry, dict) and entry.get("id") == function_id), None)
    if pass_name == "preparation":
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) for key in ("path", "artifact", "language")):
            raise ValueError("Bug Validator preparation requires its current source-index entry")
        from semantic_executor import _related_artifacts
        assigned = {item["artifact"]} | _related_artifacts(target, [item["artifact"]])
        for entry in index["functions"]:
            if not isinstance(entry, dict) or entry.get("artifact") not in assigned:
                continue
            artifact = f"fm_agent/extracted_functions/{entry['artifact']}"
            reads.update({entry["path"], artifact, artifact + ".spec.json", artifact + ".info.json"})
        verification = f"fm_agent/logic_verification_results/{Path(item['artifact']).with_suffix('.json').as_posix()}"
        reads.update({verification, "fm_agent_skill/control/analysis_index.json", "fm_agent_skill/control/graph_edges.json"})
        if not all((target / path).is_file() for path in (item["path"], f"fm_agent/extracted_functions/{item['artifact']}", verification)):
            raise ValueError("Bug Validator preparation is missing assigned source or verification evidence")
        language = item["language"]
        public_entrypoint = None
    else:
        _, approved = read_contract(target, bug_id, attempt, execution)
        language, public_entrypoint = approved["language"], approved["public_entrypoint"]
        reads.update({f"{root}/reproduction.json", f"{root}/{approved['probe_file']}"})
        if pass_name == "execution":
            public_path = target / public_entrypoint["target"]
            source_root = public_path.parent if public_path.is_file() else public_path
            reads.update(path.relative_to(target).as_posix() for path in state.source_files(target, [source_root.relative_to(target).as_posix()]))
        elif pass_name == "finalization":
            result_path = f"{root}/reproduction_result.json"
            if not (target / result_path).is_file():
                raise ValueError("Bug Validator finalization requires its recorded execution result")
            reads.update({result_path, job["bug_result_path"]})
        else:
            raise ValueError(f"unsupported Bug Validator Worker pass: {pass_name}")
    profile = profile_for_key(language)
    if profile is None or profile.probe_extension is None:
        raise ValueError(f"Bug Validator ticket has unsupported language: {language}")
    if pass_name != "finalization":
        metadata_roots = {target, (target / item["path"]).parent} if pass_name == "preparation" else {target, source_root}
        if pass_name == "preparation":
            for directory in tuple(metadata_roots):
                reads.update((directory / name).relative_to(target).as_posix() for name in ("README", "README.md", "README.rst", "README.txt"))
            for initializer in state.source_files(target):
                if initializer.name == "__init__.py":
                    reads.add(initializer.relative_to(target).as_posix())
                    metadata_roots.update(parent for parent in initializer.parents if parent == target or target in parent.parents)
        for directory in metadata_roots:
            reads.update((directory / name).relative_to(target).as_posix() for name in (*profile.build_detectors, "Makefile", "makefile", "GNUmakefile"))
    outputs = {
        "preparation": [f"{root}/reproduction.json", f"{root}/probe{profile.probe_extension}"],
        "execution": [f"{root}/reproduction_result.json"],
        "finalization": list(job["required_outputs"]),
    }[pass_name]
    writes = list(outputs)
    if pass_name == "execution":
        writes.append(f"{root}/workspace/")
    elif pass_name == "finalization":
        detail = job["bug_result_path"].removesuffix(".result.json") + ".md"
        if detail not in writes:
            writes.append(detail)
    invocation = worker_contracts.invocation("fm-agent-skill:fm-bug-validate-worker", host)
    ticket = {
        "schema_version": 2,
        "action": "host_worker",
        "worker": "fm-agent-skill:fm-bug-validate-worker",
        "worker_definition": invocation["worker_definition"],
        "worker_definition_sha256": invocation["worker_definition_sha256"],
        "host_invocation": invocation,
        "project": str(target.resolve()),
        "job_manifest": manifest,
        "input_hash": job.get("input_hash"),
        "validation_message": job.get("message"),
        "phase": job["phase"],
        "function_id": function_id,
        "snapshot_commit": state.current_snapshot_commit(target),
        "language": language,
        "execution_mode": execution,
        "execution_ecosystems": list(execution_ecosystems(profile, execution)),
        "public_entrypoint": public_entrypoint,
        "pass": pass_name,
        "job_id": job["id"],
        "mode": mode,
        "bug_id": bug_id,
        "attempt": attempt,
        "attempt_dir": root,
        "read_paths": sorted(path for path in reads if (target / path).is_file()),
        "write_paths": writes,
        "required_outputs": outputs,
        "rule": (
            "Invoke this only through the active Codex/Claude host worker mechanism; do not run FM-Agent."
            if pass_name != "execution" else
            "Invoke this through the active host worker mechanism. The Worker may run project-scoped reproduction commands and must persist their exact evidence."
        ),
    }
    path = state.control_dir(target) / "dispatches" / f"{job['id']}-attempt-{attempt:03d}-{pass_name}.json"
    state.atomic_json(path, ticket)
    return {"ticket_path": path.relative_to(target).as_posix(), **ticket}


def agent_execution_result_valid(target: Path, job: dict, *, snapshot_commit: str | None = None) -> bool:
    """Validate identity and outcome before a fast-mode Worker may finalize."""
    bug_id, _ = context(job); attempt = int(job["attempts"])
    snapshot_commit = snapshot_commit or state.current_snapshot_commit(target)
    _, contract = read_contract(target, bug_id, attempt, "agent-executed", snapshot_commit=snapshot_commit)
    result = state.read_json(attempt_dir(target, bug_id, attempt) / "reproduction_result.json", None)
    if not isinstance(result, dict):
        return False
    if any(result.get(key) != value for key, value in {
        "schema_version": 1, "execution_mode": "agent-executed", "bug_id": bug_id,
        "attempt": attempt, "snapshot_commit": snapshot_commit,
        "language": contract["language"], "public_entrypoint": contract["public_entrypoint"],
    }.items()):
        return False
    if result.get("state") not in {"completed", "execution_error", "unsupported"}:
        return False
    classification = result.get("classification")
    if classification not in {"confirmed", "not_reproduced", "inconclusive", "runtime_error"}:
        return False
    if result["state"] == "completed" and classification not in {"confirmed", "not_reproduced", "inconclusive"}:
        return False
    if result["state"] == "execution_error" and classification != "runtime_error":
        return False
    if result["state"] == "unsupported" and classification != "inconclusive":
        return False
    if contract["public_entrypoint"]["ecosystem"] == "unavailable" and (
        result["state"] != "unsupported" or classification != "inconclusive"
    ):
        return False
    if not agent_execution_commands_valid(target, attempt_dir(target, bug_id, attempt), result) or not isinstance(result.get("reason"), str):
        return False
    commands = result["commands"]
    observed, _ = output_classification(
        "\n".join(item["stdout"] for item in commands),
        next((item["returncode"] for item in commands if item["returncode"] != 0), 0),
    )
    if result["state"] == "unsupported":
        return observed in {"inconclusive", "runtime_error"}
    return classification == observed


def execution_result_valid(target: Path, job: dict, *, snapshot_commit: str | None = None) -> bool:
    """Recheck recorded execution using its original snapshot and outcome rules."""
    bug_id, _ = context(job); attempt = int(job["attempts"])
    result = state.read_json(attempt_dir(target, bug_id, attempt) / "reproduction_result.json", {})
    if not isinstance(result, dict):
        return False
    if result.get("execution_mode") == "agent-executed":
        return agent_execution_result_valid(target, job, snapshot_commit=snapshot_commit)
    snapshot_commit = snapshot_commit or state.current_snapshot_commit(target)
    _, contract = read_contract(target, bug_id, attempt, "adapter", snapshot_commit=snapshot_commit)
    if any(result.get(key) != value for key, value in {
        "schema_version": 1, "bug_id": bug_id, "attempt": attempt,
        "snapshot_commit": snapshot_commit, "language": contract["language"],
        "public_entrypoint": contract["public_entrypoint"],
    }.items()) or not isinstance(result.get("reason"), str):
        return False
    if result.get("state") == "unsupported":
        return result.get("classification") == "inconclusive" and result.get("returncode") is None and not result.get("stdout")
    if not isinstance(result.get("stdout"), str) or not isinstance(result.get("returncode"), int):
        return False
    observed, _ = output_classification(result["stdout"], result["returncode"])
    return result.get("classification") == observed and result.get("state") == ("execution_error" if observed == "runtime_error" else "completed")


def agent_execution_commands_valid(target: Path, root: Path, result: dict) -> bool:
    """Require recorded Agent commands to use only their attempt-local cwd.

    The Worker can read the immutable project snapshot, but any command that
    could build, package, or cache must operate from a copied workspace under
    its own attempt. This makes simultaneous Bug Validator jobs independent
    even in the broad ``agent-executed`` compatibility mode.
    """
    commands = result.get("commands")
    if not isinstance(commands, list):
        return False
    if result.get("state") in {"completed", "execution_error"} and not commands:
        return False
    root = root.resolve()
    for item in commands:
        if not isinstance(item, dict) or set(item) != {"command", "cwd", "returncode", "stdout", "stderr"}:
            return False
        if not isinstance(item.get("command"), str) or not item["command"].strip() or len(item["command"]) > 4096:
            return False
        cwd = item.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            return False
        candidate = Path(cwd)
        if candidate.is_absolute() or ".." in candidate.parts:
            return False
        resolved = (target / candidate).resolve()
        if not (resolved == root or root in resolved.parents):
            return False
        if not isinstance(item.get("returncode"), int):
            return False
        if not all(isinstance(item.get(field), str) and len(item[field]) <= 8000 for field in ("stdout", "stderr")):
            return False
    return True


def finalization_matches_current_attempt(target: Path, job: dict) -> bool:
    """A prior negative report never satisfies a retried dynamic attempt."""
    bug_id, _ = context(job); attempt = int(job.get("attempts", 0))
    report = state.read_json(target / job["bug_result_path"], {})
    attempts = report.get("attempts") if isinstance(report, dict) else None
    if not isinstance(attempts, list) or not attempts:
        return False
    latest = attempts[-1]
    if not isinstance(latest, dict) or latest.get("ordinal") != attempt:
        return False
    evidence = latest.get("dynamic_evidence")
    expected = attempt_dir(target, bug_id, attempt) / "reproduction_result.json"
    return isinstance(evidence, dict) and evidence.get("reproduction_result") == expected.relative_to(target).as_posix()


def request_finalization(target: Path, job: dict, host: str = "auto") -> dict:
    """Queue finalization separately after releasing the probe execution slot."""
    job = scheduler.mark_bug_validation_ready_to_finalize(target, job["id"])
    try:
        job = scheduler.claim_bug_validation_finalization(target, job["id"])
    except ValueError as exc:
        if "finalization capacity reached" not in str(exc) and "global subagent capacity reached" not in str(exc):
            raise
        return {
            "action": "wait_for_finalization_capacity",
            "job_id": job["id"],
            "rule": "Do not consume a primary Bug Validation slot while waiting for finalization capacity.",
        }
    return worker_request(target, job, "finalization", host)


def next_action(target: Path, job_id: str, host: str = "auto") -> dict:
    job = load_job(target, job_id)
    if job["status"] == "queued":
        return {"action": "scheduler_start", "job_id": job_id, "rule": "Call start only after this job appears in scheduler admissible output."}
    if job["status"] == "retryable":
        return {"action": "scheduler_retry", "job_id": job_id}
    if job["status"] != "running":
        return {"action": "terminal", "job_id": job_id, "status": job["status"]}
    bug_id, _ = context(job)
    root = attempt_dir(target, bug_id, int(job["attempts"]))
    if not (root / "reproduction.json").is_file():
        return worker_request(target, job, "preparation", host)
    # Validate the preparation contract against the selected execution mechanism.
    mode = execution_mode(target)
    read_contract(target, bug_id, int(job["attempts"]), mode)
    if not (root / "reproduction_result.json").is_file():
        if mode == "agent-executed":
            return worker_request(target, job, "execution", host)
        return {"action": "run_dynamic", "job_id": job_id, "bug_id": bug_id, "attempt": int(job["attempts"])}
    if execution_mode(target) == "agent-executed":
        if not agent_execution_result_valid(target, job):
            raise ValueError("agent-executed reproduction result is missing required identity or outcome evidence")
        return {"action": "submit_agent_execution", "job_id": job_id}
    if not finalization_matches_current_attempt(target, job):
        return request_finalization(target, job, host)
    return {"action": "submit_finalization_receipt", "job_id": job_id, "result_path": job["bug_result_path"]}


def start(target: Path, job_id: str) -> dict:
    job = load_job(target, job_id)
    if job["status"] != "queued":
        raise ValueError("only a queued Bug Validator job can start")
    admitted = scheduler.admissible(target).get("jobs", [])
    if not any(item.get("id") == job_id for item in admitted):
        raise ValueError("job is not scheduler-admissible")
    scheduler.transition(target, job_id, "start", None, None, "execution")
    return next_action(target, job_id)


def retry(target: Path, job_id: str) -> dict:
    job = load_job(target, job_id)
    if job["status"] != "retryable":
        raise ValueError("only a retryable Bug Validator job can requeue")
    scheduler.transition(target, job_id, "retry", None, None, "execution")
    return next_action(target, job_id)


def run_dynamic(target: Path, job_id: str) -> dict:
    job = load_job(target, job_id)
    if job["status"] != "running":
        raise ValueError("dynamic reproduction requires a running Bug Validator job")
    bug_id, _ = context(job); attempt = int(job["attempts"])
    if execution_mode(target) == "agent-executed":
        raise ValueError("agent-executed Bug Validator evidence must be produced by the execution Worker pass")
    root, _ = read_contract(target, bug_id, attempt)
    if not (root / "build_result.json").exists():
        run_probe(target, bug_id, attempt, configured_adapter(target, None), 120, None)
    result = run_reproduction(target, bug_id, attempt)
    if result.get("state") == "execution_error":
        failed = scheduler.transition(target, job_id, "fail", None, str(result.get("reason", "dynamic runner failed")), "execution")
        if failed.get("status") == "retryable":
            scheduler.transition(target, job_id, "retry", None, None, "execution")
            return next_action(target, job_id)
        return {"action": "terminal", "job_id": job_id, "status": failed.get("status")}
    return next_action(target, job_id)


def submit_agent_execution(target: Path, job_id: str) -> dict:
    """Accept immutable Worker evidence and preserve normal retry semantics."""
    job = load_job(target, job_id)
    if job["status"] != "running" or execution_mode(target) != "agent-executed":
        raise ValueError("submit-agent-execution requires a running agent-executed Bug Validator job")
    if not agent_execution_result_valid(target, job):
        raise ValueError("agent-executed reproduction result is missing required identity or outcome evidence")
    bug_id, _ = context(job); attempt = int(job["attempts"])
    result = state.read_json(attempt_dir(target, bug_id, attempt) / "reproduction_result.json", {})
    if result["state"] == "execution_error":
        failed = scheduler.transition(target, job_id, "fail", None, result["reason"], "execution")
        if failed.get("status") == "retryable":
            scheduler.transition(target, job_id, "retry", None, None, "execution")
            return next_action(target, job_id)
        return {"action": "terminal", "job_id": job_id, "status": failed.get("status")}
    if not finalization_matches_current_attempt(target, job):
        return request_finalization(target, job)
    return {"action": "submit_finalization_receipt", "job_id": job_id, "result_path": job["bug_result_path"]}


def all_phase_jobs_succeeded(target: Path, phase: str) -> bool:
    relevant = [job for job in scheduler.current_jobs_for_phase(target, phase) if job.get("type") == "bug_validate"]
    if not relevant or any(job.get("status") != "succeeded" for job in relevant):
        return False
    record = state.active_record(target)
    for job in relevant:
        scheduler.accepted_job(target, job["id"], snapshot_commit=state.current_snapshot_commit(target), input_fingerprint=record.get("fingerprint", ""))
    return True


def canonical_finalization_receipt(target: Path, job: dict) -> dict:
    """Build the scheduler receipt from the immutable final Worker output.

    A Bug Validator's semantic conclusion lives in its assigned report, not in
    a Coordinator-transcribed summary.  Deriving this tiny receipt prevents a
    host from turning an otherwise valid confirmed result into an output retry
    merely by omitting (or mistyping) ``classification``.
    """
    report = state.read_json(target / job["bug_result_path"], {})
    attempts = report.get("attempts") if isinstance(report, dict) else None
    latest = attempts[-1] if isinstance(attempts, list) and attempts else None
    classification = latest.get("classification") if isinstance(latest, dict) else None
    if classification not in state.BUG_ATTEMPT_CLASSIFICATIONS:
        raise ValueError("Bug Validator final report lacks a valid current attempt classification")
    return {
        "job_id": job["id"],
        "status": "completed",
        "outputs": list(job["required_outputs"]),
        "classification": classification,
    }


def submit_finalization(target: Path, job_id: str, receipt: dict | None = None) -> dict:
    job = load_job(target, job_id); _, mode = context(job)
    if not finalization_matches_current_attempt(target, job):
        # Do not leave a leased job running when a Worker wrote a static
        # report without the required immutable dynamic evidence.  Treat this
        # as an execution/protocol failure and requeue through the normal
        # bounded retry path; a report path alone is never a completion.
        failed = scheduler.transition(
            target, job_id, "fail", None,
            "no dynamic reproduction available",
            "execution",
        )
        if failed.get("status") == "retryable":
            scheduler.transition(target, job_id, "retry", None, None, "execution")
            return next_action(target, job_id)
        return {"action": "terminal", "job_id": job_id, "status": failed.get("status"), "reason": failed.get("message")}
    # Do not trust a host-transcribed finalization receipt.  The Scheduler
    # validates this canonical receipt against the report and its immutable
    # reproduction evidence before accepting it.
    canonical_receipt = canonical_finalization_receipt(target, job)
    completed = scheduler.transition(target, job_id, "complete", canonical_receipt, None, "execution")
    if completed.get("status") == "retryable":
        scheduler.transition(target, job_id, "retry", None, None, "execution")
        return next_action(target, job_id)
    response = next_action(target, job_id)
    if completed.get("status") == "succeeded" and all_phase_jobs_succeeded(target, completed["phase"]) and not state.active_record(target).get("validation_scope"):
        response["summary"] = write_summary(target, mode)
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description="Advance one host-coordinated FM-Agent Bug Validator job without invoking FM-Agent.")
    parser.add_argument("action", choices=("next", "start", "retry", "run-dynamic", "submit-agent-execution", "submit-finalization"))
    parser.add_argument("--project", required=True); parser.add_argument("--job-id", required=True); parser.add_argument("--receipt-json")
    parser.add_argument("--host", choices=("auto", "claude", "codex", "portable"), default="auto")
    args = parser.parse_args(); target = project(args)
    try:
        if args.action == "next": result = next_action(target, args.job_id, args.host)
        elif args.action == "start": result = start(target, args.job_id)
        elif args.action == "retry": result = retry(target, args.job_id)
        elif args.action == "run-dynamic": result = run_dynamic(target, args.job_id)
        elif args.action == "submit-agent-execution": result = submit_agent_execution(target, args.job_id)
        else:
            # ``--receipt-json`` is accepted for compatibility with an active
            # Coordinator, but the executor derives the authoritative receipt
            # from the final report and does not consume host-authored fields.
            receipt = json.loads(args.receipt_json) if args.receipt_json else None
            result = submit_finalization(target, args.job_id, receipt)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)); raise SystemExit(2)


if __name__ == "__main__": main()
