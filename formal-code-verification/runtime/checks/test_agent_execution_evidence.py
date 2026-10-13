#!/usr/bin/env python3
# Added by AIResearchSkill: reject outcomes contradicted by recorded execution evidence.
"""Focused checks for Agent-executed Bug Validator command outcomes."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import bug_validation_executor
from fm_agent_core import state


class AgentExecutionEvidenceTest(unittest.TestCase):
    def valid(self, *, commands, classification, result_state="completed") -> bool:
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(state, "current_snapshot_commit", return_value="snapshot"):
            target = Path(temporary)
            root = target / "fm_agent_skill/probes/candidate/attempt_001"
            entrypoint = {"ecosystem": "host-project-toolchain", "kind": "module", "target": "calc.py", "symbol": "inc"}
            state.atomic_json(root / "reproduction.json", {
                "schema_version": 2, "bug_id": "candidate", "attempt": 1,
                "snapshot_commit": "snapshot", "language": "python", "public_entrypoint": entrypoint,
                "probe_file": "probe.py", "expected_marker": "CONFIRMED",
                "not_confirmed_marker": "NOT CONFIRMED", "timeout_seconds": 30,
            })
            (root / "probe.py").write_text('print("CONFIRMED")\n', encoding="utf-8")
            state.atomic_json(root / "reproduction_result.json", {
                "schema_version": 1, "execution_mode": "agent-executed", "bug_id": "candidate",
                "attempt": 1, "snapshot_commit": "snapshot", "language": "python",
                "public_entrypoint": entrypoint, "state": result_state, "classification": classification,
                "reason": "Recorded execution outcome",
                "commands": [dict(item, cwd=root.relative_to(target).as_posix(), stderr="") for item in commands],
            })
            job = {"attempts": 1, "input": {"bug_id": "candidate", "mode": "full"}}
            return bug_validation_executor.agent_execution_result_valid(target, job)

    def command(self, output: str, returncode: int = 0, command: str = "python3 probe.py") -> dict:
        return {"command": command, "returncode": returncode, "stdout": output}

    def test_contradictory_outcomes_are_rejected(self) -> None:
        cases = [
            ([self.command("CONFIRMED\n", 1)], "confirmed"),
            ([self.command("", command="python3 -m py_compile probe.py")], "confirmed"),
            ([self.command("CONFIRMED\n")], "not_reproduced"),
            ([self.command("NOT CONFIRMED\n")], "confirmed"),
            ([self.command("", 1, "make"), self.command("CONFIRMED\n")], "confirmed"),
            ([self.command("CONFIRMED\n"), self.command("NOT CONFIRMED\n")], "confirmed"),
            ([self.command("CONFIRMED\n")], "inconclusive"),
        ]
        for commands, classification in cases:
            with self.subTest(commands=commands, classification=classification):
                self.assertFalse(self.valid(commands=commands, classification=classification))

    def test_successful_build_then_probe_uses_behavior_output(self) -> None:
        for marker, classification in (("CONFIRMED", "confirmed"), ("NOT CONFIRMED", "not_reproduced")):
            with self.subTest(classification=classification):
                self.assertTrue(self.valid(commands=[self.command("build succeeded\n", command="make"), self.command(marker + "\n")], classification=classification))

    def test_setup_output_cannot_supply_or_override_the_probe_outcome(self) -> None:
        for setup_marker in ("CONFIRMED", "NOT CONFIRMED"):
            with self.subTest(setup_marker=setup_marker):
                setup = self.command(setup_marker + "\n", command="existing-verifier")
                self.assertFalse(self.valid(commands=[setup, self.command("probe omitted its marker\n")], classification="confirmed"))
                self.assertTrue(self.valid(commands=[setup, self.command("probe omitted its marker\n")], classification="inconclusive"))
                for marker, classification in (("CONFIRMED", "confirmed"), ("NOT CONFIRMED", "not_reproduced")):
                    self.assertTrue(self.valid(commands=[setup, self.command(marker + "\n")], classification=classification))

    def test_probe_requires_one_exact_first_line_marker(self) -> None:
        for output in ("diagnostic\nCONFIRMED\n", "CONFIRMED tool success\n", "NOT CONFIRMED tool success\n", "\nCONFIRMED\n", "CONFIRMED\nCONFIRMED\n"):
            with self.subTest(output=output):
                self.assertFalse(self.valid(commands=[self.command(output)], classification="confirmed"))
                self.assertFalse(self.valid(commands=[self.command(output)], classification="not_reproduced"))
                self.assertTrue(self.valid(commands=[self.command(output)], classification="inconclusive"))
        self.assertTrue(self.valid(commands=[self.command("CONFIRMED\nobserved balance: 2\n")], classification="confirmed"))

    def test_recorded_runtime_error_and_inconclusive_evidence_remain_valid(self) -> None:
        self.assertTrue(self.valid(commands=[self.command("CONFIRMED\n", 1)], classification="runtime_error", result_state="execution_error"))
        self.assertTrue(self.valid(commands=[self.command("output without a required marker\n")], classification="inconclusive"))
        self.assertTrue(self.valid(commands=[self.command("CONFIRMED\nNOT CONFIRMED\n")], classification="inconclusive"))
        self.assertTrue(self.valid(commands=[], classification="inconclusive", result_state="unsupported"))
        self.assertTrue(self.valid(commands=[self.command("", 127, "missing-tool probe")], classification="inconclusive", result_state="unsupported"))
        self.assertFalse(self.valid(commands=[self.command("CONFIRMED\n")], classification="inconclusive", result_state="unsupported"))


if __name__ == "__main__":
    unittest.main()
