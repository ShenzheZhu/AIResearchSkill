#!/usr/bin/env python3
"""Regression checks for bounded Bug Validation job capacity."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import scheduler
import durable_executor
from config import DEFAULTS
from fm_agent_core import state


class BugValidationCapacityTest(unittest.TestCase):
    def _target(self, temporary: str) -> Path:
        target = Path(temporary).resolve()
        state.atomic_json(state.skill_dir(target) / "active.json", {
            "snapshot_commit": "unversioned", "fingerprint": "capacity-test",
            "phases": ["bug_validation"], "current_phase": "bug_validation",
        })
        state.atomic_json(state.skill_dir(target) / "config.json", {
            "max_active_subagents": 6, "bug_validation_concurrency": 4,
        })
        for index in range(7):
            scheduler.create(target, {
                "id": f"bug-{index}", "phase": "bug_validation", "type": "bug_validate",
                "depends_on": [], "required_outputs": [f"fm_agent/bug_validation/{index}.result.json"],
                "artifacts": [], "input": {"candidate_id": state.candidate_id(f"f-{index}"),
                    "bug_id": f"bug-{index}", "function_id": f"f-{index}", "mode": "full"},
            })
        return target

    def test_running_validation_obeys_primary_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._target(temporary)
            for index in range(4):
                scheduler.transition(target, f"bug-{index}", "start", None, None, "execution")
            capacity = scheduler._capacity(target)
            self.assertEqual(capacity["active"], 4)
            self.assertEqual(capacity["by_type"]["bug_validate"], 4)
            self.assertEqual(scheduler.admissible(target)["jobs"], [])
            self.assertEqual(durable_executor.next_actions(target, 4)["dispatches"], [])
            with self.assertRaisesRegex(ValueError, "bug_validate capacity reached"):
                scheduler.transition(target, "bug-4", "start", None, None, "execution")
            scheduler.transition(target, "bug-0", "fail", None, "Worker interrupted", "execution")
            self.assertEqual(scheduler._capacity(target)["active"], 3)
            listed = durable_executor.next_actions(target, 4)
            self.assertEqual([item["job_id"] for item in listed["dispatches"]], ["bug-0"])
            self.assertEqual(listed["dispatches"][0]["action"], "claim_worker")
            self.assertEqual(scheduler._load(target, "bug-0")["status"], "queued")

    def test_global_capacity_and_live_leases_survive_dispatch_listing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._target(temporary)
            state.atomic_json(state.skill_dir(target) / "config.json", {
                "max_active_subagents": 3, "bug_validation_concurrency": 4,
            })
            scheduler.create(target, {"id": "other", "phase": "bug_validation", "type": "phase_refine",
                "depends_on": [], "required_outputs": [], "artifacts": []})
            for job_id in ("bug-0", "bug-1", "other"):
                scheduler.transition(target, job_id, "start", None, None, "execution")
            connection = scheduler._connect(target)
            leases = [dict(row) for row in connection.execute("SELECT * FROM leases ORDER BY job_id")]
            connection.close()
            listed = durable_executor.next_actions(target, 7)
            self.assertEqual(listed["action"], "wait_for_completion_event")
            self.assertEqual(listed["backpressure"]["active"], 3)
            self.assertEqual(listed["dispatches"], [])
            with self.assertRaisesRegex(ValueError, "global subagent capacity reached"):
                scheduler.transition(target, "bug-2", "start", None, None, "execution")
            connection = scheduler._connect(target)
            self.assertEqual([dict(row) for row in connection.execute("SELECT * FROM leases ORDER BY job_id")], leases)
            connection.close()
            self.assertNotIn("bug_validation_finalize_concurrency", DEFAULTS)
            self.assertNotIn("bug_validation_finalize_concurrency", scheduler.DEFAULT_CAPS)


if __name__ == "__main__":
    unittest.main()
