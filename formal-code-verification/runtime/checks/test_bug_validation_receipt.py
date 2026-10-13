#!/usr/bin/env python3
# Modified by AIResearchSkill: isolate canonical receipt acceptance from subsequent Worker dispatch.
"""Regression checks for canonical Bug Validation finalization receipts."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import bug_validation_executor  # noqa: E402
import scheduler
import test_bug_worker_ticket as ticket_fixture
from result_fixture import verification_result
from fm_agent_core import state


class BugValidationReceiptTest(unittest.TestCase):
    def accepted_negative(self, target: Path) -> tuple[dict, Path]:
        fixture = ticket_fixture.BugWorkerTicketTest()
        job = fixture.prepare(target)
        artifact = state.fm_dir(target) / "extracted_functions/calc-inc-1.py"
        spec = state.read_json(Path(f"{artifact}.spec.json"), {})
        spec["post_condition"] = "returns value + 2 at value=0 and value + 1 otherwise"
        state.atomic_json(Path(f"{artifact}.spec.json"), spec)
        state.atomic_json(state.fm_dir(target) / "logic_verification_results/calc-inc-1.json", verification_result(
            "calc.py::inc", "unversioned", "MISMATCH", reasoning={
                "actual_postcondition": "returns value + 1", "spec_postcondition": spec["post_condition"],
                "counterexample": "value=0 returns 1 instead of 2", "offending_statements": "return value + 1",
                "reason": "The zero-input result differs from the required value",
            },
        ))
        root = fixture.execution(target)
        probe = root / "probe.py"
        probe.write_text("import sys\nsys.path.insert(0, sys.argv[1])\nfrom calc import inc\nprint('NOT CONFIRMED' if inc(1) == 2 else 'CONFIRMED')\n", encoding="utf-8")
        command = [sys.executable, "-B", str(probe), str(target)]
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True)
        result = state.read_json(root / "reproduction_result.json", {})
        result.update(classification="not_reproduced", commands=[{
            "command": " ".join(command), "cwd": root.relative_to(target).as_posix(),
            "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr,
        }])
        state.atomic_json(root / "reproduction_result.json", result)
        state.atomic_json(root / "build_result.json", {"state": "completed", "ok": True})
        record = {"ordinal": 1, "classification": "not_reproduced", "dynamic_evidence": {
            "reproduction_result": (root / "reproduction_result.json").relative_to(target).as_posix(),
        }}
        state.atomic_json(target / job["bug_result_path"], {
            "schema_version": 2, "bug_id": "candidate", "function_id": job["input"]["function_id"],
            "candidate_id": job["input"]["candidate_id"], "snapshot_commit": "unversioned",
            "confirmation_status": "inconclusive", "attempts": [record],
        })
        accepted = scheduler.transition(target, job["id"], "complete", bug_validation_executor.canonical_finalization_receipt(target, job), None, "execution")
        self.assertEqual(accepted["status"], "retryable")
        scheduler.transition(target, job["id"], "retry", None, None, "execution")
        return scheduler.transition(target, job["id"], "start", None, None, "execution"), root

    def test_retry_reads_only_accepted_same_candidate_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job, root = self.accepted_negative(target)
            failed_root = bug_validation_executor.attempt_dir(target, "candidate", 2)
            state.atomic_json(failed_root / "reproduction_result.json", {"reason": "Unaccepted Worker output"})
            job = scheduler.transition(target, job["id"], "fail", None, "Worker failed", "execution")
            scheduler.transition(target, job["id"], "retry", None, None, "execution")
            job = scheduler.transition(target, job["id"], "start", None, None, "execution")
            unrelated = bug_validation_executor.attempt_dir(target, "other-candidate", 1)
            state.atomic_json(unrelated / "reproduction_result.json", {"reason": "Another candidate's result"})
            ticket = bug_validation_executor.worker_request(target, job, "preparation", "codex")
            self.assertEqual(ticket["validated_attempts"], job["validated_attempts"])
            for name in ("reproduction.json", "probe.py", "reproduction_result.json", "build_result.json"):
                self.assertIn((root / name).relative_to(target).as_posix(), ticket["read_paths"])
            self.assertNotIn((failed_root / "reproduction_result.json").relative_to(target).as_posix(), ticket["read_paths"])
            self.assertNotIn((unrelated / "reproduction_result.json").relative_to(target).as_posix(), ticket["read_paths"])
            self.assertNotIn(job["bug_result_path"], ticket["read_paths"])
            self.assertEqual(ticket["attempt"], 3)
            self.assertFalse(any(path.startswith(root.relative_to(target).as_posix()) for path in ticket["write_paths"]))

    def test_retry_cannot_expose_changed_or_unaccepted_prior_evidence(self) -> None:
        for case in ("changed_probe", "missing_receipt", "foreign_candidate", "foreign_snapshot", "unaccepted_ordinal"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                job, root = self.accepted_negative(target)
                if case == "changed_probe":
                    (root / "probe.py").write_text("print('CONFIRMED')\n", encoding="utf-8")
                elif case == "missing_receipt":
                    connection = scheduler._connect(target)
                    connection.execute("DELETE FROM receipts WHERE job_id=?", (job["id"],))
                    connection.close()
                elif case == "foreign_candidate":
                    job["input"]["candidate_id"] = state.candidate_id("calc.py::inc", 2)
                elif case == "foreign_snapshot":
                    connection = scheduler._connect(target)
                    connection.execute("UPDATE runs SET snapshot_commit='other-snapshot'")
                    connection.close()
                else:
                    job["validated_attempts"][0]["ordinal"] = 2
                with self.assertRaises(ValueError):
                    bug_validation_executor.accepted_attempt_read_paths(target, job)

    def test_next_action_rejects_prior_history_after_requirements_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job, root = self.accepted_negative(target)
            ticket = bug_validation_executor.next_action(target, job["id"], "codex")
            self.assertEqual((ticket["pass"], ticket["attempt"]), ("preparation", 2))
            self.assertIn((root / "probe.py").relative_to(target).as_posix(), ticket["read_paths"])
            record = state.active_record(target)
            self.assertEqual(record["fingerprint"], "ticket-check")
            record["fingerprint"] = "different-analysis-requirements"
            state.atomic_json(state.skill_dir(target) / "active.json", record)
            with self.assertRaisesRegex(ValueError, "another analysis run"):
                bug_validation_executor.next_action(target, job["id"], "codex")

    def test_public_reproduction_can_load_vendor_without_inspection_permission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            fixture = ticket_fixture.BugWorkerTicketTest()
            job = fixture.prepare(target)
            vendor = target / "vendor"
            vendor.mkdir()
            (vendor / "arithmetic.py").write_text("def successor(value):\n    return value + 1\n", encoding="utf-8")
            (target / "calc.py").write_text("from vendor.arithmetic import successor\ndef inc(value):\n    return successor(value)\n", encoding="utf-8")
            root = fixture.execution(target)
            probe = root / "probe.py"
            probe.write_text("import sys\nsys.path.insert(0, sys.argv[1])\nfrom calc import inc\nprint('CONFIRMED' if inc(0) != 2 else 'NOT CONFIRMED')\n", encoding="utf-8")
            ticket = bug_validation_executor.worker_request(target, job, "execution", "codex")
            self.assertNotIn("vendor/arithmetic.py", ticket["read_paths"])
            self.assertNotIn("tests/test_calc.py", ticket["read_paths"])
            command = [sys.executable, "-B", str(probe), str(target)]
            completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True)
            self.assertEqual(completed.stdout, "CONFIRMED\n")
            result = state.read_json(root / "reproduction_result.json", {})
            result["commands"] = [{"command": " ".join(command), "cwd": root.relative_to(target).as_posix(),
                "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}]
            state.atomic_json(root / "reproduction_result.json", result)
            self.assertTrue(bug_validation_executor.agent_execution_result_valid(target, job))
            self.assertFalse((vendor / "__pycache__").exists())

    def test_finalization_derives_classification_from_report_not_host_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            output = "fm_agent/bug_validation/candidate.result.json"
            report_path = target / output
            report_path.parent.mkdir(parents=True)
            report_path.write_text(json.dumps({
                "confirmation_status": "confirmed",
                "attempts": [{"ordinal": 1, "classification": "confirmed"}],
            }), encoding="utf-8")
            job = {
                "id": "bug-validation-candidate",
                "phase": "bug_validation",
                "type": "bug_validate",
                "status": "running",
                "attempts": 1,
                "required_outputs": [output],
                "bug_result_path": output,
                "input": {"function_id": "calc.py::inc", "candidate_id": state.candidate_id("calc.py::inc"), "bug_id": "candidate", "mode": "full"},
            }
            captured: dict[str, object] = {}

            def transition(_target, _job_id, action, receipt, *_unused):
                captured["action"] = action
                captured["receipt"] = receipt
                return {**job, "status": "succeeded"}

            with patch.object(bug_validation_executor, "load_job", return_value=job), \
                 patch.object(bug_validation_executor, "write_finalization"), \
                 patch.object(bug_validation_executor.scheduler, "transition", side_effect=transition), \
                 patch.object(bug_validation_executor, "next_action", return_value={"action": "terminal", "status": "succeeded"}), \
                 patch.object(bug_validation_executor, "all_phase_jobs_succeeded", return_value=False):
                bug_validation_executor.submit_finalization(target, job["id"])

            self.assertEqual(captured["action"], "complete")
            self.assertEqual(captured["receipt"], {
                "job_id": job["id"],
                "status": "completed",
                "outputs": [output],
                "classification": "confirmed",
            })

    def test_finalization_rejects_report_without_current_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            output = "fm_agent/bug_validation/candidate.result.json"
            report_path = target / output
            report_path.parent.mkdir(parents=True)
            report_path.write_text(json.dumps({"attempts": [{"ordinal": 1}]}), encoding="utf-8")
            job = {"id": "bug-validation-candidate", "required_outputs": [output], "bug_result_path": output}
            with self.assertRaisesRegex(ValueError, "valid current attempt classification"):
                bug_validation_executor.canonical_finalization_receipt(target, job)


if __name__ == "__main__":
    unittest.main()
