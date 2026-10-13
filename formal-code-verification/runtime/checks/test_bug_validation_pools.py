#!/usr/bin/env python3
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
        target = Path(temporary)
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
                "artifacts": [], "input": {"bug_id": f"bug-{index}", "function_id": f"f-{index}", "mode": "full"},
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
