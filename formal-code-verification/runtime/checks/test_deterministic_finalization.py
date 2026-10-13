#!/usr/bin/env python3
"""Reports and canonical receipts need no finalization Worker or host input."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from fm_agent_core import state
import bug_validation_executor as validator
import scheduler
import test_bug_worker_ticket as ticket_fixture


class DeterministicFinalizationTest(unittest.TestCase):
    def prepare(self, target: Path, **config) -> dict:
        state.atomic_json(state.skill_dir(target) / "config.json", config)
        job = ticket_fixture.BugWorkerTicketTest().prepare(target)
        record = state.active_record(target)
        state.atomic_json(state.skill_dir(target) / "active.json", {**record, "validation_scope": ["calc.py::inc"]})
        return job

    def execution(self, target: Path, job: dict, classification="confirmed", mode="agent-executed") -> Path:
        root = validator.attempt_dir(target, job["input"]["bug_id"], job["attempts"])
        identity = {key: job["input"][key] for key in ("bug_id", "candidate_id", "function_id")}
        identity.update({"attempt": job["attempts"], "snapshot_commit": "unversioned", "language": "python"})
        entry = {"ecosystem": "host-project-toolchain" if mode == "agent-executed" else "python-packaging",
                 "kind": "module", "target": "calc.py", "symbol": "inc"}
        state.atomic_json(root / "reproduction.json", {
            **identity, "schema_version": 3, "public_entrypoint": entry, "probe_file": "probe.py",
            "timeout_seconds": 30, "expected_marker": "CONFIRMED", "not_confirmed_marker": "NOT CONFIRMED",
        })
        stdout = "CONFIRMED\nobserved fixture input=7\n" if classification == "confirmed" else "NOT CONFIRMED\n"
        (root / "probe.py").write_text(f"print({stdout.rstrip()!r})\n", encoding="utf-8")
        result = {**identity, "schema_version": 2, "execution_mode": mode, "public_entrypoint": entry,
                  "state": "completed", "classification": classification, "reason": "Recorded fixture outcome"}
        command = {"command": "python3 probe.py", "cwd": root.relative_to(target).as_posix(),
                   "returncode": 0, "stdout": stdout, "stderr": "fixture diagnostic\n"}
        result.update({"commands": [command]} if mode == "agent-executed" else {
            "command": ["python3", "probe.py"], **{key: command[key] for key in ("returncode", "stdout", "stderr")},
        })
        path = root / "reproduction_result.json"
        # Noncanonical whitespace is evidence too and must remain unchanged.
        path.write_text(json.dumps(result, ensure_ascii=False, indent=3) + "\n\n", encoding="utf-8")
        return path

    def test_confirmed_submission_writes_honest_report_once_without_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve(); job = self.prepare(target)
            evidence = self.execution(target, job); original = evidence.read_bytes()
            with patch.object(validator, "worker_request", side_effect=AssertionError("unexpected Worker")):
                accepted = validator.submit_agent_execution(target, job["id"])
            self.assertEqual(accepted["status"], "succeeded")
            result = target / job["bug_result_path"]
            detail = result.with_name("candidate.md")
            report = state.read_json(result, {})
            self.assertEqual(report["confirmation_status"], "confirmed")
            self.assertEqual(report["candidate_reasoning"], state.direct_candidates(target)[job["input"]["candidate_id"]]["reasoning"])
            self.assertIn("Assigned candidate witness (static reasoning)", detail.read_text())
            self.assertIn("not a record of the input used by execution", detail.read_text())
            self.assertIn("observed fixture input=7", detail.read_text())
            self.assertEqual(evidence.read_bytes(), original)
            persisted = [(path.read_bytes(), path.stat().st_mtime_ns) for path in (result, detail, evidence)]
            validator.submit_agent_execution(target, job["id"])
            validator.submit_finalization(target, job["id"])
            self.assertEqual(persisted, [(path.read_bytes(), path.stat().st_mtime_ns) for path in (result, detail, evidence)])
            self.assertFalse(list((state.control_dir(target) / "dispatches").glob("*-finalization.json")))

    def test_repeated_submission_rejects_changed_accepted_report_without_rewriting_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve(); job = self.prepare(target)
            self.execution(target, job); validator.submit_agent_execution(target, job["id"])
            result = target / job["bug_result_path"]
            changed = result.read_bytes() + b" \n"
            result.write_bytes(changed)
            with self.assertRaisesRegex(ValueError, "identical receipt"):
                validator.submit_agent_execution(target, job["id"])
            self.assertEqual(result.read_bytes(), changed)

    def test_duplicate_submission_preserves_phase_summary_and_all_evidence_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job = ticket_fixture.BugWorkerTicketTest().prepare(target)
            self.assertNotIn("validation_scope", state.active_record(target))
            state.atomic_json(state.control_dir(target) / "job_plans/bug_validation.json", {
                "schema_version": 1, "snapshot_commit": "unversioned",
                "entries": [{"candidate_id": job["input"]["candidate_id"], "job_id": job["id"]}],
            })
            evidence = self.execution(target, job)
            accepted = validator.submit_agent_execution(target, job["id"])
            self.assertEqual(accepted["summary"]["total_confirmed"], 1)
            result = target / job["bug_result_path"]
            paths = [result, result.with_name("candidate.md"), state.fm_dir(target) / "bug_validation/summary.json",
                     *sorted(path for path in evidence.parent.iterdir() if path.is_file())]
            persisted = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
            with patch.object(validator, "write_summary", side_effect=AssertionError("duplicate summary write")):
                self.assertEqual(validator.submit_agent_execution(target, job["id"])["status"], "succeeded")
                self.assertEqual(validator.submit_finalization(target, job["id"])["status"], "succeeded")
            self.assertEqual(persisted, [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths])
            changed = evidence.read_bytes() + b" \n"
            evidence.write_bytes(changed)
            with self.assertRaisesRegex(ValueError, "identical receipt"):
                validator.submit_agent_execution(target, job["id"])
            self.assertEqual(evidence.read_bytes(), changed)

    def test_completed_negatives_preserve_exact_history_and_original_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve(); job = self.prepare(target, bug_validation_negative_retries=1)
            first = self.execution(target, job, "not_reproduced"); original = first.read_bytes()
            self.assertEqual(validator.submit_agent_execution(target, job["id"])["action"], "scheduler_start")
            prior = scheduler._load(target, job["id"])["validated_attempts"]
            self.assertEqual(state.read_json(target / job["bug_result_path"], {})["confirmation_status"], "inconclusive")
            job = scheduler.transition(target, job["id"], "start", None, None, "execution")
            self.execution(target, job, "not_reproduced")
            self.assertEqual(validator.submit_agent_execution(target, job["id"])["status"], "succeeded")
            report = state.read_json(target / job["bug_result_path"], {})
            self.assertEqual(report["attempts"][:-1], prior)
            self.assertEqual(report["confirmation_status"], "rejected")
            self.assertEqual(first.read_bytes(), original)
            self.assertEqual(scheduler._load(target, job["id"])["negative_attempts"], 2)

    def test_adapter_next_finalizes_recorded_execution_without_dispatch_or_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve(); job = self.prepare(target, bug_validation_execution="adapter")
            evidence = self.execution(target, job, mode="adapter"); original = evidence.read_bytes()
            with patch.object(validator, "worker_request", side_effect=AssertionError("unexpected Worker")), \
                 patch.object(validator, "run_reproduction", side_effect=AssertionError("unexpected reproduction")):
                self.assertEqual(validator.next_action(target, job["id"])["status"], "succeeded")
            self.assertEqual(evidence.read_bytes(), original)

    def test_independent_candidates_keep_separate_reports_and_witnesses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve(); first = self.prepare(target)
            verification_path = state.fm_dir(target) / "logic_verification_results/calc-inc-1.json"
            verification = state.read_json(verification_path, {})
            second_id = state.candidate_id("calc.py::inc", 2)
            reasoning = {**verification["reasoning"], "counterexample": "value=4 is a separate assigned witness"}
            verification["candidates"].append({"candidate_id": second_id, "reasoning": reasoning})
            state.atomic_json(verification_path, verification)
            record = state.active_record(target)
            record.setdefault("inputs", {}).setdefault("config", {})["all_bugs"] = True
            state.atomic_json(state.skill_dir(target) / "active.json", record)
            second = scheduler.create(target, {
                "id": "bug-validation-second", "type": "bug_validate", "phase": "bug_validation",
                "depends_on": [], "artifacts": [], "required_outputs": ["fm_agent/bug_validation/second.result.json"],
                "input": {**first["input"], "bug_id": "second", "candidate_id": second_id},
            })
            second = scheduler.transition(target, second["id"], "start", None, None, "execution")
            first_evidence = self.execution(target, first); second_evidence = self.execution(target, second)
            for job in (second, first):
                self.assertEqual(validator.submit_agent_execution(target, job["id"])["status"], "succeeded")
            for job, evidence in ((first, first_evidence), (second, second_evidence)):
                report = state.read_json(target / job["bug_result_path"], {})
                self.assertEqual(report["candidate_id"], job["input"]["candidate_id"])
                self.assertEqual(report["attempts"][0]["dynamic_evidence"]["reproduction_result"], evidence.relative_to(target).as_posix())
            self.assertEqual(state.read_json(target / second["bug_result_path"], {})["candidate_reasoning"], reasoning)


if __name__ == "__main__":
    unittest.main()
