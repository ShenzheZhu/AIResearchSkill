#!/usr/bin/env python3
"""Local reports retain the execution identity and bounded retry contract."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from fm_agent_core import state
import bug_validation_executor
import scheduler
import test_bug_worker_ticket as ticket_fixture


class FinalizationIdentityTest(unittest.TestCase):
    def write_execution(self, target: Path, attempt: int) -> str:
        root = target / f"fm_agent_skill/probes/candidate/attempt_{attempt:03d}"
        entrypoint = {"ecosystem": "host-project-toolchain", "kind": "module", "target": "calc.py", "symbol": "inc"}
        state.atomic_json(root / "reproduction.json", {"function_id": "calc.py::inc", "candidate_id": state.candidate_id("calc.py::inc"),
            "schema_version": 3, "bug_id": "candidate", "attempt": attempt,
            "snapshot_commit": "unversioned", "language": "python", "public_entrypoint": entrypoint,
            "probe_file": "probe.py", "expected_marker": "CONFIRMED",
            "not_confirmed_marker": "NOT CONFIRMED", "timeout_seconds": 30,
        })
        (root / "probe.py").write_text('print("CONFIRMED")\n', encoding="utf-8")
        state.atomic_json(root / "reproduction_result.json", {"function_id": "calc.py::inc", "candidate_id": state.candidate_id("calc.py::inc"),
            "schema_version": 2, "execution_mode": "agent-executed", "bug_id": "candidate",
            "attempt": attempt, "snapshot_commit": "unversioned", "language": "python",
            "public_entrypoint": entrypoint, "state": "completed", "classification": "confirmed",
            "reason": "The executed probe reproduced the mismatch",
            "commands": [{"command": "python3 probe.py", "cwd": root.relative_to(target).as_posix(),
                          "returncode": 0, "stdout": "CONFIRMED\n", "stderr": ""}],
        })
        return (root / "reproduction_result.json").relative_to(target).as_posix()

    def test_missing_or_wrong_execution_identity_retries_then_valid_execution_succeeds(self) -> None:
        for invalid_identity in (None, "calc.py::other"):
            with self.subTest(identity=invalid_identity), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                job = ticket_fixture.BugWorkerTicketTest().prepare(target)
                record = state.active_record(target)
                state.atomic_json(state.skill_dir(target) / "active.json", {**record, "validation_scope": ["calc.py::inc"]})
                evidence = self.write_execution(target, 1)
                result = state.read_json(target / evidence, {})
                result.pop("function_id", None)
                if invalid_identity is not None:
                    result["function_id"] = invalid_identity
                state.atomic_json(target / evidence, result)
                with self.assertRaisesRegex(ValueError, "identity or outcome evidence"):
                    bug_validation_executor.submit_agent_execution(target, job["id"])
                self.assertFalse((target / job["bug_result_path"]).exists())
                response = bug_validation_executor.submit_finalization(target, job["id"])
                self.assertEqual(response["action"], "scheduler_start")
                rejected = scheduler._load(target, job["id"])
                self.assertEqual(rejected["status"], "queued")
                self.assertEqual(rejected["failure_class"], "execution")
                self.assertIn("identity or outcome evidence", rejected["message"])
                self.assertEqual(rejected["runtime_attempts"], 1)

                scheduler.transition(target, job["id"], "start", None, None, "execution")
                evidence = self.write_execution(target, 2)
                accepted = bug_validation_executor.submit_agent_execution(target, job["id"])
                self.assertEqual(accepted["status"], "succeeded")
                self.assertEqual(scheduler._load(target, job["id"])["result"]["classification"], "confirmed")
                report = state.read_json(target / job["bug_result_path"], {})
                self.assertEqual(report["function_id"], "calc.py::inc")
                self.assertEqual(report["attempts"], [{"ordinal": 2, "classification": "confirmed", "dynamic_evidence": {"reproduction_result": evidence}}])


if __name__ == "__main__":
    unittest.main()
