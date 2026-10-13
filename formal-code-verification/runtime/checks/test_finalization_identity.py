#!/usr/bin/env python3
"""Malformed final reports remain repairable before scheduler success."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from fm_agent_core import state
import bug_validation_executor
import scheduler


class FinalizationIdentityTest(unittest.TestCase):
    def write_execution(self, target: Path, attempt: int) -> str:
        root = target / f"fm_agent_skill/probes/candidate/attempt_{attempt:03d}"
        entrypoint = {"ecosystem": "host-project-toolchain", "kind": "module", "target": "calc.py", "symbol": "inc"}
        state.atomic_json(root / "reproduction.json", {
            "schema_version": 2, "bug_id": "candidate", "attempt": attempt,
            "snapshot_commit": "snapshot", "language": "python", "public_entrypoint": entrypoint,
            "probe_file": "probe.py", "expected_marker": "CONFIRMED",
            "not_confirmed_marker": "NOT CONFIRMED", "timeout_seconds": 30,
        })
        (root / "probe.py").write_text('print("CONFIRMED")\n', encoding="utf-8")
        state.atomic_json(root / "reproduction_result.json", {
            "schema_version": 1, "execution_mode": "agent-executed", "bug_id": "candidate",
            "attempt": attempt, "snapshot_commit": "snapshot", "language": "python",
            "public_entrypoint": entrypoint, "state": "completed", "classification": "confirmed",
            "reason": "The executed probe reproduced the mismatch",
            "commands": [{"command": "python3 probe.py", "cwd": root.relative_to(target).as_posix(),
                          "returncode": 0, "stdout": "CONFIRMED\n", "stderr": ""}],
        })
        return (root / "reproduction_result.json").relative_to(target).as_posix()

    def test_missing_or_wrong_identity_retries_then_repaired_report_succeeds(self) -> None:
        for invalid_identity in (None, "calc.py::other"):
            with self.subTest(identity=invalid_identity), tempfile.TemporaryDirectory() as temporary, \
                 patch.object(state, "current_snapshot_commit", return_value="snapshot"), \
                 patch.object(state, "direct_mismatch_ids", return_value={"calc.py::inc"}):
                target = Path(temporary).resolve()
                state.atomic_json(state.skill_dir(target) / "active.json", {
                    "mode": "full", "status": "running", "snapshot_commit": "snapshot",
                    "fingerprint": "identity-test", "phases": ["bug_validation"], "current_phase": "bug_validation",
                })
                job = scheduler.create(target, {
                    "id": "bug-validation-candidate", "phase": "bug_validation", "type": "bug_validate",
                    "depends_on": [], "artifacts": [], "required_outputs": ["fm_agent/bug_validation/candidate.result.json"],
                    "input": {"bug_id": "candidate", "function_id": "calc.py::inc", "mode": "full"},
                })
                scheduler.transition(target, job["id"], "start", None, None, "execution")
                evidence = self.write_execution(target, 1)
                self.assertEqual(bug_validation_executor.submit_agent_execution(target, job["id"])["pass"], "finalization")
                report = {
                    "snapshot_commit": "snapshot", "confirmation_status": "confirmed",
                    "attempts": [{"ordinal": 1, "classification": "confirmed", "dynamic_evidence": {"reproduction_result": evidence}}],
                }
                if invalid_identity is not None:
                    report["function_id"] = invalid_identity
                state.atomic_json(target / job["required_outputs"][0], report)
                response = bug_validation_executor.submit_finalization(target, job["id"])
                self.assertEqual(response["action"], "scheduler_start")
                rejected = scheduler._load(target, job["id"])
                self.assertEqual(rejected["status"], "queued")
                self.assertEqual(rejected["failure_class"], "output")
                self.assertIn("function identity", rejected["message"])
                self.assertEqual(rejected["runtime_attempts"], 1)

                scheduler.transition(target, job["id"], "start", None, None, "execution")
                evidence = self.write_execution(target, 2)
                self.assertEqual(bug_validation_executor.submit_agent_execution(target, job["id"])["pass"], "finalization")
                report["function_id"] = "calc.py::inc"
                report["attempts"] = [{"ordinal": 2, "classification": "confirmed", "dynamic_evidence": {"reproduction_result": evidence}}]
                state.atomic_json(target / job["required_outputs"][0], report)
                accepted = bug_validation_executor.submit_finalization(target, job["id"])
                self.assertEqual(accepted["status"], "succeeded")
                self.assertEqual(accepted["summary"]["total_confirmed"], 1)


if __name__ == "__main__":
    unittest.main()
