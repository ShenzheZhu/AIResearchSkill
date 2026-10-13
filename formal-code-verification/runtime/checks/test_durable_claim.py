#!/usr/bin/env python3
"""Regression checks for claim-before-launch durable dispatch."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import bug_validation_executor as validator  # noqa: E402
import complexity  # noqa: E402
import durable_executor  # noqa: E402
import scheduler  # noqa: E402
import semantic_executor  # noqa: E402
import test_bug_worker_ticket as ticket_fixture  # noqa: E402
from fm_agent_core import state  # noqa: E402
from config import DEFAULTS  # noqa: E402
from result_fixture import verification_result  # noqa: E402


class DurableClaimTest(unittest.TestCase):
    def test_next_lists_without_leasing_and_claim_leases_one_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            state.atomic_json(target / "fm_agent_skill" / "active.json", {
                "snapshot_commit": "unversioned", "fingerprint": "test",
                "phases": ["specification"], "current_phase": "specification",
            })
            scheduler.create(target, {
                "id": "context", "phase": "specification", "type": "domain_context",
                "depends_on": [], "required_outputs": [], "artifacts": [],
            })
            listed = durable_executor.next_actions(target, limit=4)
            self.assertEqual(listed["action"], "dispatch")
            self.assertEqual(listed["dispatches"], [{
                "action": "claim_worker", "job_id": "context",
                "type": "domain_context", "phase": "specification",
            }])
            self.assertEqual(scheduler._load(target, "context")["status"], "queued")

            claimed = durable_executor.claim(target, "context")
            self.assertEqual(claimed["action"], "host_worker")
            self.assertEqual(claimed["job_id"], "context")
            self.assertEqual(scheduler._load(target, "context")["status"], "running")

    def test_small_functions_share_batches_without_losing_any_function(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            artifacts = [f"calc-f{index}-1.py" for index in range(24)]
            extracted = state.fm_dir(target) / "extracted_functions"
            extracted.mkdir(parents=True)
            for artifact in artifacts:
                (extracted / artifact).write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
            for phase in ("spec_batch", "verify_function"):
                with self.subTest(phase=phase):
                    old = complexity.partition(target, artifacts, {**DEFAULTS, "worker_max_functions": 3}, phase)
                    grouped = complexity.partition(target, artifacts, DEFAULTS, phase)
                    self.assertEqual((len(old), len(grouped)), (8, 3))
                    self.assertEqual([item for batch in grouped for item in batch["artifacts"]], artifacts)
                    self.assertTrue(all(batch["estimated_tokens"] <= DEFAULTS["worker_target_tokens"] for batch in grouped))

    def test_batching_preserves_complexity_and_source_byte_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            extracted = state.fm_dir(target) / "extracted_functions"
            extracted.mkdir(parents=True)
            simple = "def f(x):\n    return x + 1\n"
            (extracted / "calc-small-1.py").write_text(simple, encoding="utf-8")
            (extracted / "calc-branching-1.py").write_text(
                "def f(x):\n" + "    if x > 0: x -= 1\n" * 160 + "    return x\n", encoding="utf-8",
            )
            (extracted / "calc-other-1.py").write_text(simple, encoding="utf-8")
            artifacts = ["calc-small-1.py", "calc-branching-1.py", "calc-other-1.py"]
            batches = complexity.partition(target, artifacts, DEFAULTS, "verify_function")
            self.assertEqual([batch["artifacts"] for batch in batches], [[item] for item in artifacts])
            self.assertGreater(batches[1]["estimated_tokens"], DEFAULTS["worker_target_tokens"])
            small = [artifacts[0], artifacts[2]]
            byte_limited = complexity.partition(target, small, {**DEFAULTS, "worker_max_source_bytes": len(simple.encode())}, "spec_batch")
            self.assertEqual([batch["artifacts"] for batch in byte_limited], [[item] for item in small])


class DurableRetryTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.target = Path(temporary.name).resolve()
        self.record = {
            "snapshot_commit": "unversioned", "fingerprint": "retry-test",
            "phases": ["specification", "verification"], "current_phase": "verification",
        }
        state.atomic_json(state.skill_dir(self.target) / "active.json", self.record)

    def create_job(self, job_id: str, phase: str = "verification") -> dict:
        return scheduler.create(self.target, {
            "id": job_id, "phase": phase, "type": "phase_refine",
            "depends_on": [], "required_outputs": [], "artifacts": [], "max_attempts": 2,
        })

    def prepare_candidate(self, target: Path) -> dict:
        job = ticket_fixture.BugWorkerTicketTest().prepare(target)
        state.atomic_json(state.control_dir(target) / "job_plans/bug_validation.json", {
            "schema_version": 1, "snapshot_commit": "unversioned",
            "entries": [{"candidate_id": job["input"]["candidate_id"], "job_id": job["id"]}],
        })
        return job

    def test_accepted_negative_retry_preserves_history_and_enters_preparation(self) -> None:
        for outcomes in (("not_reproduced", "not_reproduced"), ("not_reproduced", "unsupported"), ("inconclusive", "not_reproduced")):
            with self.subTest(outcomes=outcomes), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                state.atomic_json(state.skill_dir(target) / "config.json", {
                    "bug_validation_max_attempts": 2, "bug_validation_negative_retries": 1,
                })
                job = self.prepare_candidate(target)
                artifact = state.fm_dir(target) / "extracted_functions/calc-inc-1.py"
                spec = state.read_json(Path(f"{artifact}.spec.json"), {})
                spec["post_condition"] = "returns value + 2 at value=0 and value + 1 otherwise"
                state.atomic_json(Path(f"{artifact}.spec.json"), spec)
                result_path = state.fm_dir(target) / "logic_verification_results/calc-inc-1.json"
                mismatch = state.read_json(result_path, {})
                mismatch["reasoning"]["spec_postcondition"] = spec["post_condition"]
                state.atomic_json(result_path, verification_result("calc.py::inc", "unversioned", "MISMATCH", reasoning=mismatch["reasoning"]))
                job = scheduler.transition(target, job["id"], "fail", None, "Worker interrupted", "execution")
                self.assertEqual((job["runtime_attempts"], job["negative_attempts"]), (1, 0))
                history = []
                first_bytes = {}
                first_receipt = None
                for ordinal, outcome in enumerate(outcomes, 2):
                    listed = durable_executor.next_actions(target, 4, host="codex")
                    self.assertEqual(listed["action"], "dispatch")
                    self.assertEqual([item["job_id"] for item in listed["dispatches"]], [job["id"]])
                    requeued = scheduler._load(target, job["id"])
                    self.assertEqual((requeued["attempts"], requeued["runtime_attempts"], requeued["negative_attempts"]), (ordinal - 1, 1, ordinal - 2))
                    self.assertEqual(requeued.get("validated_attempts", []), history)
                    ticket = durable_executor.claim(target, job["id"], "codex")
                    self.assertEqual((ticket["pass"], ticket["attempt"]), ("preparation", ordinal))
                    root = validator.attempt_dir(target, "candidate", ordinal)
                    self.assertEqual(ticket["required_outputs"], [
                        (root / "reproduction.json").relative_to(target).as_posix(),
                        (root / "probe.py").relative_to(target).as_posix(),
                    ])
                    job = scheduler._load(target, job["id"])
                    identity = {"bug_id": "candidate", "candidate_id": job["input"]["candidate_id"],
                                "function_id": job["input"]["function_id"], "attempt": ordinal, "snapshot_commit": "unversioned"}
                    entry = {"ecosystem": "host-project-toolchain", "kind": "module", "target": "calc.py", "symbol": "inc"}
                    state.atomic_json(root / "reproduction.json", {"schema_version": 3, **identity, "language": "python",
                        "public_entrypoint": entry, "probe_file": "probe.py", "timeout_seconds": 30,
                        "expected_marker": "CONFIRMED", "not_confirmed_marker": "NOT CONFIRMED"})
                    probe = root / "probe.py"
                    output = "NO MARKER" if outcome == "inconclusive" else "NOT CONFIRMED"
                    probe.write_text(f"import sys\nsys.path.insert(0, sys.argv[1])\nfrom calc import inc\nassert inc(1) == 2\nprint({output!r})\n", encoding="utf-8")
                    unsupported = outcome == "unsupported"
                    commands = []
                    if not unsupported:
                        result = subprocess.run([sys.executable, "-B", str(probe), str(target)], cwd=root, text=True, capture_output=True, check=True)
                        self.assertEqual(result.stdout, output + "\n")
                        commands = [{"command": f"{sys.executable} -B {probe} {target}", "cwd": root.relative_to(target).as_posix(),
                                     "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}]
                    classification = "inconclusive" if unsupported else outcome
                    evidence = (root / "reproduction_result.json").relative_to(target).as_posix()
                    state.atomic_json(target / evidence, {"schema_version": 2, **identity, "execution_mode": "agent-executed",
                        "language": "python", "public_entrypoint": entry, "state": "unsupported" if unsupported else "completed",
                        "classification": classification, "commands": commands, "reason": "Service unavailable" if unsupported else "Public probe ran"})
                    completed = validator.submit_agent_execution(target, job["id"])
                    history.append({"ordinal": ordinal, "classification": classification, "dynamic_evidence": {"reproduction_result": evidence}})
                    job = scheduler._load(target, job["id"])
                    self.assertEqual(completed["action"], "scheduler_start" if ordinal == 2 else "terminal")
                    self.assertEqual(job["status"], "queued" if ordinal == 2 else "succeeded")
                    status = "rejected" if ordinal == 3 and all(item["classification"] == "not_reproduced" for item in history) else "inconclusive"
                    report = state.read_json(target / job["bug_result_path"], {})
                    self.assertEqual(report["confirmation_status"], status)
                    self.assertEqual(report["attempts"], history)
                    connection = scheduler._connect(target)
                    receipts = [dict(row) for row in connection.execute("SELECT * FROM receipts WHERE job_id=? ORDER BY attempt", (job["id"],))]
                    connection.close()
                    self.assertEqual(len(receipts), ordinal - 1)
                    if ordinal == 2:
                        first_receipt = receipts[0]
                        first_bytes = {path: path.read_bytes() for path in root.iterdir() if path.is_file()}
                    else:
                        self.assertEqual(receipts[0], first_receipt)
                        for path, accepted_bytes in first_bytes.items():
                            self.assertEqual(path.read_bytes(), accepted_bytes)
                self.assertEqual((job["attempts"], job["runtime_attempts"], job["negative_attempts"]), (3, 1, 2))
                self.assertEqual(bool(job.get("negative_validation_exhausted")), outcomes[-1] != "unsupported")
                accepted = scheduler.accepted_job(target, job["id"], snapshot_commit="unversioned", input_fingerprint="ticket-check")
                self.assertEqual(accepted["validated_attempts"], history)
                self.assertEqual(durable_executor.next_actions(target, 4)["action"], "dag_converged")

    def test_first_unsupported_attempt_is_terminal_and_preserves_its_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            state.atomic_json(state.skill_dir(target) / "config.json", {"bug_validation_negative_retries": 2})
            job = self.prepare_candidate(target)
            root = ticket_fixture.BugWorkerTicketTest().execution(target)
            execution_path = root / "reproduction_result.json"
            execution = state.read_json(execution_path, {})
            execution.update(state="unsupported", classification="inconclusive", commands=[], reason="Required runtime unavailable")
            state.atomic_json(execution_path, execution)
            completed = validator.submit_agent_execution(target, job["id"])
            self.assertEqual((completed["action"], completed["status"]), ("terminal", "succeeded"))
            accepted = scheduler.accepted_job(target, job["id"], snapshot_commit="unversioned", input_fingerprint="ticket-check")
            self.assertEqual((accepted["attempts"], accepted["runtime_attempts"], accepted["negative_attempts"]), (1, 0, 1))
            self.assertNotIn("negative_validation_exhausted", accepted)
            self.assertEqual(state.read_json(target / accepted["bug_result_path"], {})["confirmation_status"], "inconclusive")
            evidence_bytes = execution_path.read_bytes()
            for _ in range(2):
                self.assertEqual(durable_executor.next_actions(target, 4)["action"], "dag_converged")
                self.assertEqual(scheduler._load(target, job["id"]), accepted)
                self.assertEqual(execution_path.read_bytes(), evidence_bytes)
            connection = scheduler._connect(target)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM receipts WHERE job_id=?", (job["id"],)).fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM leases WHERE job_id=?", (job["id"],)).fetchone()[0], 0)
            connection.close()

    def test_recorded_runtime_errors_retry_without_consuming_negative_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            state.atomic_json(state.skill_dir(target) / "config.json", {"bug_validation_max_attempts": 2})
            job = self.prepare_candidate(target)
            for ordinal in (1, 2):
                if ordinal == 1:
                    root = ticket_fixture.BugWorkerTicketTest().execution(target)
                else:
                    durable_executor.claim(target, job["id"])
                    root = validator.attempt_dir(target, "candidate", ordinal)
                    contract = state.read_json(validator.attempt_dir(target, "candidate", 1) / "reproduction.json", {})
                    state.atomic_json(root / "reproduction.json", dict(contract, attempt=ordinal))
                probe = root / "probe.py"
                probe.write_text("raise RuntimeError('runtime failed')\n", encoding="utf-8")
                result = subprocess.run([sys.executable, "-B", str(probe)], cwd=root, text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                execution = state.read_json(validator.attempt_dir(target, "candidate", 1) / "reproduction_result.json", {})
                execution.update(attempt=ordinal, state="execution_error", classification="runtime_error", reason="Runtime command failed",
                    commands=[{"command": f"{sys.executable} -B {probe}", "cwd": root.relative_to(target).as_posix(),
                               "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}])
                state.atomic_json(root / "reproduction_result.json", execution)
                completed = validator.submit_agent_execution(target, job["id"])
                self.assertEqual(completed["action"], "scheduler_start" if ordinal == 1 else "terminal")
                job = scheduler._load(target, job["id"])
                self.assertEqual(job["status"], "queued" if ordinal == 1 else "failed")
                self.assertEqual((job["runtime_attempts"], job["negative_attempts"]), (ordinal, 0))
                self.assertEqual(job.get("validated_attempts", []), [])
            connection = scheduler._connect(target)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM receipts WHERE job_id=?", (job["id"],)).fetchone()[0], 0)
            connection.close()

    def test_rejected_partial_batch_dispatches_only_invalid_outputs(self) -> None:
        artifacts = ["valid.py", "invalid.py"]
        outputs = [f"fm_agent/logic_verification_results/{Path(item).with_suffix('.json')}" for item in artifacts]
        state.atomic_json(state.control_dir(self.target) / "analysis_index.json", {
            "functions": [{"id": f"{item}::value", "artifact": item} for item in artifacts],
        })
        results = []
        for artifact_name in artifacts:
            artifact = state.fm_dir(self.target) / "extracted_functions" / artifact_name
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("def value(x):\n    return x + 1\n", encoding="utf-8")
            state.atomic_json(Path(f"{artifact}.spec.json"), {
                "signature": "value(x)", "pre_condition": "x is an integer", "post_condition": "returns x + 1",
            })
            state.atomic_json(Path(f"{artifact}.info.json"), {"callees": []})
            results.append(verification_result(f"{artifact_name}::value", "unversioned", "MATCH", reasoning={
                "actual_postcondition": "returns x + 1", "spec_postcondition": "returns x + 1",
                "counterexample": None, "offending_statements": None, "reason": "The return expression establishes the result",
            }))
        state.atomic_json(self.target / outputs[0], results[0])
        invalid = dict(results[1], reasoning={})
        state.atomic_json(self.target / outputs[1], invalid)
        valid_bytes = (self.target / outputs[0]).read_bytes()
        scheduler.create(self.target, {
            "id": "verify-batch", "phase": "verification", "type": "verify_batch",
            "depends_on": [], "required_outputs": outputs, "artifacts": artifacts, "max_attempts": 2,
        })
        durable_executor.claim(self.target, "verify-batch", "codex")
        rejected = semantic_executor.submit(self.target, "verify-batch", {
            "job_id": "verify-batch", "status": "completed", "outputs": outputs,
        })
        self.assertEqual(rejected["job"]["status"], "retryable")
        self.assertEqual(rejected["job"]["completed_artifacts"], ["valid.py"])

        listed = durable_executor.next_actions(self.target, 4, host="codex")
        self.assertEqual(listed["action"], "dispatch")
        self.assertEqual([item["job_id"] for item in listed["dispatches"]], ["verify-batch"])
        requeued = scheduler._load(self.target, "verify-batch")
        self.assertEqual(requeued["status"], "queued")
        self.assertEqual(requeued["attempts"], 1)
        self.assertEqual(requeued["required_outputs"], outputs[1:])
        self.assertEqual(requeued["artifacts"], ["invalid.py"])
        claimed = durable_executor.claim(self.target, "verify-batch", "codex")
        ticket = state.read_json(self.target / claimed["ticket_path"], {})
        self.assertEqual(ticket["write_paths"], outputs[1:])
        self.assertEqual((self.target / outputs[0]).read_bytes(), valid_bytes)

        state.atomic_json(self.target / outputs[1], results[1])
        accepted = semantic_executor.submit(self.target, "verify-batch", {
            "job_id": "verify-batch", "status": "completed", "outputs": outputs[1:],
        })
        self.assertEqual(accepted["job"]["status"], "succeeded")
        self.assertEqual(accepted["job"]["attempts"], 2)
        self.assertEqual((self.target / outputs[0]).read_bytes(), valid_bytes)
        self.assertEqual(durable_executor.next_actions(self.target, 4)["action"], "dag_converged")

    def test_exhausted_retry_budget_stays_terminal(self) -> None:
        self.create_job("exhausted")
        for attempt in (1, 2):
            durable_executor.claim(self.target, "exhausted")
            failed = scheduler.transition(self.target, "exhausted", "fail", None, "Worker failed", "execution")
            self.assertEqual(failed["attempts"], attempt)
            listed = durable_executor.next_actions(self.target, 4)
            self.assertEqual(listed["action"], "dispatch" if attempt == 1 else "phase_failed")
        terminal = scheduler._load(self.target, "exhausted")
        self.assertEqual(terminal["status"], "failed")
        self.assertEqual(durable_executor.next_actions(self.target, 4)["action"], "phase_failed")
        self.assertEqual(scheduler._load(self.target, "exhausted"), terminal)

    def test_retry_is_current_run_only_and_keeps_live_lease_and_capacity(self) -> None:
        self.create_job("old")
        durable_executor.claim(self.target, "old")
        scheduler.transition(self.target, "old", "fail", None, "Old failure", "output")
        old = scheduler._load(self.target, "old")
        state.atomic_json(state.skill_dir(self.target) / "active.json", dict(self.record, fingerprint="new-run"))
        for job_id, phase in (("retry-spec", "specification"), ("retry-verify", "verification")):
            self.create_job(job_id, phase)
            durable_executor.claim(self.target, job_id)
            scheduler.transition(self.target, job_id, "fail", None, "Retry output", "output")
        self.create_job("live")
        durable_executor.claim(self.target, "live")
        live = scheduler._load(self.target, "live")
        connection = scheduler._connect(self.target)
        lease = dict(connection.execute("SELECT * FROM leases WHERE job_id='live'").fetchone())
        connection.close()
        state.atomic_json(state.skill_dir(self.target) / "config.json", {"max_active_subagents": 1})

        listed = durable_executor.next_actions(self.target, 4)
        self.assertEqual(listed["action"], "wait_for_completion_event")
        self.assertEqual(listed["dispatches"], [])
        self.assertEqual(listed["backpressure"]["active"], 1)
        self.assertEqual(scheduler._load(self.target, "old"), old)
        self.assertEqual(scheduler._load(self.target, "live"), live)
        for job_id in ("retry-spec", "retry-verify"):
            job = scheduler._load(self.target, job_id)
            self.assertEqual(job["status"], "queued")
            self.assertEqual(job["attempts"], 1)
        connection = scheduler._connect(self.target)
        self.assertEqual(dict(connection.execute("SELECT * FROM leases WHERE job_id='live'").fetchone()), lease)
        connection.close()
        scheduler.transition(self.target, "live", "complete", {
            "job_id": "live", "status": "completed", "outputs": [],
        }, None, "execution")
        self.assertEqual(len(durable_executor.next_actions(self.target, 4)["dispatches"]), 1)


if __name__ == "__main__":
    unittest.main()
