#!/usr/bin/env python3
# Modified by AIResearchSkill: resolve macOS aliases and supply approved execution evidence before finalization.
"""Regression checks for separate Bug Validation execution/finalize pools."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import scheduler  # noqa: E402
import durable_executor  # noqa: E402
from fm_agent_core import state  # noqa: E402


class BugValidationPoolsTest(unittest.TestCase):
    def _target(self, temporary: str) -> Path:
        target = Path(temporary).resolve()
        state.atomic_json(target / "fm_agent_skill" / "active.json", {
            "snapshot_commit": "unversioned", "fingerprint": "pool-test",
            "phases": ["bug_validation"], "current_phase": "bug_validation",
        })
        state.atomic_json(target / "fm_agent_skill" / "config.json", {
            "max_active_subagents": 6,
            "bug_validation_concurrency": 4,
            "bug_validation_finalize_concurrency": 2,
        })
        for index in range(7):
            scheduler.create(target, {
                "id": f"bug-{index}", "phase": "bug_validation", "type": "bug_validate",
                "depends_on": [], "required_outputs": [f"fm_agent/bug_validation/{index}.result.json"],
                "artifacts": [], "input": {"candidate_id": state.candidate_id(f"f-{index}"), "bug_id": f"bug-{index}", "function_id": f"f-{index}", "mode": "full"},
            })
        return target

    def test_ready_to_finalize_releases_primary_slot_and_finalize_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._target(temporary)
            for index in range(4):
                scheduler.transition(target, f"bug-{index}", "start", None, None, "execution")
            for index in range(2):
                scheduler.mark_bug_validation_ready_to_finalize(target, f"bug-{index}")
                scheduler.claim_bug_validation_finalization(target, f"bug-{index}")

            capacity = scheduler._capacity(target)
            self.assertEqual(capacity["by_type"]["bug_validate"], 2)
            self.assertEqual(capacity["bug_validation_finalizing"], 2)
            self.assertEqual(capacity["active"], 4)
            self.assertEqual([job["id"] for job in scheduler.admissible(target)["jobs"]], ["bug-4", "bug-5"])

            scheduler.mark_bug_validation_ready_to_finalize(target, "bug-2")
            with self.assertRaisesRegex(ValueError, "finalization capacity reached"):
                scheduler.claim_bug_validation_finalization(target, "bug-2")
            self.assertEqual(scheduler._load(target, "bug-2")["bug_validation_stage"], "ready_to_finalize")

    def test_next_reoffers_ready_finalize_without_leasing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._target(temporary)
            scheduler.transition(target, "bug-0", "start", None, None, "execution")
            root = target / "fm_agent_skill/probes/bug-0/attempt_001"
            entry = {"ecosystem": "host-project-toolchain", "kind": "module", "target": "calc.py", "symbol": "value"}
            (target / "calc.py").write_text("def value(): return 1\n", encoding="utf-8")
            state.atomic_json(root / "reproduction.json", {"function_id": "f-0", "candidate_id": state.candidate_id("f-0"),
                "schema_version": 3, "bug_id": "bug-0", "attempt": 1, "snapshot_commit": "unversioned",
                "language": "python", "public_entrypoint": entry, "probe_file": "probe.py", "timeout_seconds": 30,
                "expected_marker": "CONFIRMED", "not_confirmed_marker": "NOT CONFIRMED",
            })
            (root / "probe.py").write_text('print("CONFIRMED")\n', encoding="utf-8")
            state.atomic_json(root / "reproduction_result.json", {"function_id": "f-0", "candidate_id": state.candidate_id("f-0"),
                "schema_version": 2, "execution_mode": "agent-executed", "bug_id": "bug-0", "attempt": 1,
                "snapshot_commit": "unversioned", "language": "python", "public_entrypoint": entry,
                "state": "completed", "classification": "confirmed", "reason": "Recorded probe reproduced the mismatch",
                "commands": [{"command": "python3 probe.py", "cwd": root.relative_to(target).as_posix(), "returncode": 0,
                              "stdout": "CONFIRMED\n", "stderr": ""}],
            })
            scheduler.mark_bug_validation_ready_to_finalize(target, "bug-0")

            listed = durable_executor.next_actions(target, limit=4)
            self.assertEqual(listed["dispatches"][0]["action"], "claim_finalization")
            self.assertEqual(listed["dispatches"][0]["job_id"], "bug-0")
            self.assertEqual(scheduler._load(target, "bug-0")["bug_validation_stage"], "ready_to_finalize")

            claimed = durable_executor.claim(target, "bug-0")
            self.assertEqual(claimed["pass"], "finalization")
            self.assertEqual(scheduler._load(target, "bug-0")["bug_validation_stage"], "finalization")


if __name__ == "__main__":
    unittest.main()
