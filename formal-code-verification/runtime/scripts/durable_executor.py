#!/usr/bin/env python3
"""Bounded, event-driven Coordinator actions over the durable DAG."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import project, state
from fm_agent_core import coordinator_contract
from fm_agent_core import worker_contracts
import bug_validation_executor
import checkpoint
import scheduler
import semantic_executor


SEMANTIC_TYPES = {"domain_context", "spec_batch", "verify_function", "verify_batch"}


def earliest_incomplete(target: Path) -> str:
    record = state.active_record(target)
    run_id, _, _ = scheduler._run_id(target)
    connection = scheduler._connect(target)
    rows = connection.execute(
        "SELECT phase, SUM(CASE WHEN status='succeeded' THEN 0 ELSE 1 END) AS pending "
        "FROM jobs WHERE run_id=? GROUP BY phase", (run_id,)
    ).fetchall()
    connection.close()
    pending = {row["phase"] for row in rows if row["pending"]}
    return next((phase for phase in record.get("phases", []) if phase in pending), record.get("current_phase", "finalize"))


def _claim_descriptor(job: dict, action: str = "claim_worker") -> dict:
    """A small, non-leasing candidate descriptor safe for host tool output."""
    return {
        "action": action,
        "job_id": job["id"],
        "type": job["type"],
        "phase": job["phase"],
    }


def _ticket_reference(ticket: dict) -> dict:
    """Keep parent tool output compact; the Worker reads the immutable ticket."""
    return {
        "action": "host_worker",
        "job_id": ticket["job_id"],
        "attempt": ticket["attempt"],
        "worker": ticket["worker"],
        "worker_definition": ticket["worker_definition"],
        "ticket_path": ticket["ticket_path"],
        "host_invocation": ticket["host_invocation"],
    }


def claim(target: Path, job_id: str, host: str = "auto") -> dict:
    """Atomically lease exactly one ready job immediately before launch.

    ``next`` intentionally never leases a batch.  If a client truncates or
    fails to parse a multi-ticket response, no worker slot is left occupied by
    tickets it never launched.
    """
    job = scheduler._load(target, job_id)
    if job.get("type") == "bug_validate" and job.get("status") == "running" and job.get("bug_validation_stage") == "ready_to_finalize":
        # The execution evidence has already released its primary slot.  This
        # atomically reserves only a bounded finalization slot.
        finalized = scheduler.claim_bug_validation_finalization(target, job_id)
        return bug_validation_executor.worker_request(target, finalized, "finalization", host)
    if not any(item.get("id") == job_id for item in scheduler.admissible(target)["jobs"]):
        raise ValueError("job is not scheduler-admissible")
    started = scheduler.transition(target, job_id, "start", None, None, "execution")
    if started["type"] in SEMANTIC_TYPES:
        return _ticket_reference(semantic_executor._ticket(target, started, host))
    if started["type"] == "bug_validate":
        return bug_validation_executor.next_action(target, job_id, host)
    worker = worker_contracts.for_job_type(started["type"])
    contract = worker_contracts.invocation(worker, host)
    return {
        "action": "host_worker", "job_id": started["id"], "type": started["type"],
        "attempt": started["attempts"],
        "job_manifest": f"fm_agent_skill/jobs/{started['id']}.json",
        "write_paths": started.get("required_outputs", []), "host_invocation": contract,
    }


def next_actions(target: Path, limit: int, offset: int = 0, turn_budget_remaining: int | None = None, host: str = "auto") -> dict:
    if limit < 1: raise ValueError("dispatch limit must be positive")
    # A durable checkpoint is an implementation detail, not a terminal
    # scheduler action. This script cannot start host subagents itself, so a
    # `checkpoint_and_yield` response used to make the Coordinator stop even
    # though ready work remained. Keep the argument for CLI compatibility,
    # but never convert an ordinary low-context signal into a halted run.
    _ = turn_budget_remaining
    finalizations = scheduler.admissible_bug_validation_finalizations(target, limit=limit)
    capacity_after_finalizations = scheduler._capacity(target)["active"] + len(finalizations)
    primary_budget = max(0, min(limit - len(finalizations), scheduler._caps(target)["max_active_subagents"] - capacity_after_finalizations))
    admitted = scheduler.admissible(target)["jobs"]
    selected = admitted[offset:offset + primary_budget]
    actions = [
        *[_claim_descriptor(job, "claim_finalization") for job in finalizations],
        *[_claim_descriptor(job) for job in selected],
    ]
    aggregate = scheduler.aggregate(target)
    action = "dispatch" if actions else "wait_for_completion_event" if aggregate["pending"] else "dag_converged"
    return {
        "action": action,
        "dispatches": actions,
        "page": {"offset": offset, "limit": limit, "returned": len(actions)},
        "backpressure": scheduler._capacity(target),
        "earliest_incomplete_phase": earliest_incomplete(target),
        "scheduler": aggregate,
        "coordinator": {
            **coordinator_contract.invocation(host),
            "continuation_required": action != "dag_converged",
            "next_step": (
                "claim one returned candidate or finalization pass, launch its Worker immediately, then repeat until every returned descriptor is claimed"
                if action == "dispatch" else
                "wait only for an already-running Worker receipt, then call next"
                if action == "wait_for_completion_event" else
                "join the current phase through its receipt and gate; this is not terminal analysis completion"
            ),
        },
        "continuation": "claim and launch each returned candidate immediately; submit each completion, then call next again to fill the free slot",
    }


def barrier(target: Path, phase: str = "bug_validation") -> dict:
    """Return the machine-readable join point for a host-coordinated phase.

    This never infers completion from result files.  The scheduler status is
    authoritative; callers may read reports only after ``dag_converged``.
    """
    jobs = [
        job for job in scheduler.current_jobs_for_phase(target, phase)
        if job.get("type") == "bug_validate" and not job.get("legacy_contract")
    ]
    by_status = {
        status: sum(1 for job in jobs if job.get("status") == status)
        for status in ("queued", "running", "retryable", "failed", "succeeded")
    }
    pending = [
        {"job_id": job.get("id"), "status": job.get("status"), "attempt": job.get("attempts", 0)}
        for job in jobs if job.get("status") != "succeeded"
    ]
    if by_status["failed"]:
        action = "phase_failed"
    elif pending:
        action = "wait_for_completion_event"
    else:
        action = "dag_converged"
    return {
        "action": action,
        "phase": phase,
        "dag_converged": action == "dag_converged",
        "jobs": by_status,
        "pending": pending,
        "rule": "Only dag_converged permits bug_summary.py and pipeline phase-complete.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Return bounded FM-Agent Coordinator actions.")
    parser.add_argument("action", choices=("next", "claim", "barrier", "checkpoint"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--job-id")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--turn-budget-remaining", type=int)
    parser.add_argument("--host", choices=("auto", "claude", "codex", "portable"), default="auto")
    args = parser.parse_args(); target = project(args)
    try:
        if args.action == "barrier":
            result = barrier(target)
        elif args.action == "claim":
            if not args.job_id:
                raise ValueError("claim requires --job-id")
            result = claim(target, args.job_id, args.host)
        elif args.action == "checkpoint":
            phase = earliest_incomplete(target)
            result = checkpoint.commit(target, phase, "running", active_record=state.active_record(target))
        else:
            result = next_actions(target, args.limit, args.offset, args.turn_budget_remaining, args.host)
        code = 0
    except (ValueError, RuntimeError, OSError) as exc:
        result, code = {"ok": False, "error": str(exc)}, 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
