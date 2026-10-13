#!/usr/bin/env python3
# Added by AIResearchSkill: unavailable attempts cannot become sufficient negative evidence.
"""Keep unresolved retry schedules visible after the negative-attempt budget ends."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from fm_agent_core import state
import bug_validation_executor as validator
import scheduler


class MixedValidationOutcomesTest(unittest.TestCase):
    def test_two_unavailable_attempts_then_one_negative_remain_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            state.atomic_json(state.skill_dir(target) / "active.json", {
                "snapshot_commit": "unversioned", "fingerprint": "mixed-check",
                "phases": ["bug_validation"], "current_phase": "bug_validation",
            })
            (target / "calc.py").write_text("def inc(x): return x + 1\n")
            output = "fm_agent/bug_validation/mixed.result.json"
            job = scheduler.create(target, {
                "id": "bug-validation-mixed", "phase": "bug_validation", "type": "bug_validate",
                "artifacts": [], "depends_on": [], "required_outputs": [output], "negative_retries": 2,
                "input": {"candidate_id": state.candidate_id("calc.py::inc"), "bug_id": "mixed", "function_id": "calc.py::inc", "mode": "full"},
            })
            attempts = []
            for ordinal in range(1, 4):
                job = scheduler.transition(target, job["id"], "start", None, None, "execution")
                root = validator.attempt_dir(target, "mixed", ordinal)
                entry = {"ecosystem": "host-project-toolchain", "kind": "module", "target": "calc.py", "symbol": "inc"}
                state.atomic_json(root / "reproduction.json", {"function_id": "calc.py::inc", "candidate_id": state.candidate_id("calc.py::inc"),
                    "schema_version": 3, "bug_id": "mixed", "attempt": ordinal, "snapshot_commit": "unversioned",
                    "language": "python", "public_entrypoint": entry, "probe_file": "probe.py", "timeout_seconds": 30,
                    "expected_marker": "CONFIRMED", "not_confirmed_marker": "NOT CONFIRMED",
                })
                probe = root / "probe.py"
                probe.write_text("import sys\nsys.path.insert(0, sys.argv[1])\nfrom calc import inc\nprint('NOT CONFIRMED' if inc(1) == 2 else 'CONFIRMED')\n")
                commands = []
                if ordinal == 3:
                    result = subprocess.run([sys.executable, "-B", str(probe), str(target)], cwd=root, text=True, capture_output=True, check=True)
                    commands = [{"command": f"{sys.executable} -B {probe} {target}", "cwd": root.relative_to(target).as_posix(),
                                 "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}]
                classification = "not_reproduced" if commands else "inconclusive"
                evidence = (root / "reproduction_result.json").relative_to(target).as_posix()
                state.atomic_json(target / evidence, {"function_id": "calc.py::inc", "candidate_id": state.candidate_id("calc.py::inc"),
                    "schema_version": 2, "execution_mode": "agent-executed", "bug_id": "mixed", "attempt": ordinal,
                    "snapshot_commit": "unversioned", "language": "python", "public_entrypoint": entry,
                    "state": "completed" if commands else "unsupported", "classification": classification,
                    "commands": commands, "reason": "Public probe ran" if commands else "Required service unavailable",
                })
                attempts.append({"ordinal": ordinal, "classification": classification, "dynamic_evidence": {"reproduction_result": evidence}})
                report = {"candidate_id": state.candidate_id("calc.py::inc"), "schema_version": 2, "bug_id": "mixed", "function_id": "calc.py::inc", "snapshot_commit": "unversioned",
                          "confirmation_status": "inconclusive", "attempts": attempts}
                state.atomic_json(target / output, report)
                receipt = validator.canonical_finalization_receipt(target, job)
                if ordinal == 3:
                    state.atomic_json(target / output, {**report, "confirmation_status": "rejected"})
                    self.assertIn("inconclusive attempts", scheduler._validate(target, job, receipt))
                    state.atomic_json(target / output, report)
                job = scheduler.transition(target, job["id"], "complete", receipt, None, "execution")
                if ordinal < 3:
                    self.assertEqual(job["status"], "retryable")
                    scheduler.transition(target, job["id"], "retry", None, None, "execution")
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(state.read_json(target / output, {})["confirmation_status"], "inconclusive")
            self.assertEqual(scheduler.accepted_job(target, job["id"], snapshot_commit="unversioned", input_fingerprint="mixed-check")["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
