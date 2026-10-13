"""Exhausted Workers stop event waits after independent work drains."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from fm_agent_core import state
import durable_executor
import phase_driver
import scheduler


class FailedDagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.target = Path(self.temporary.name).resolve()
        self.snapshot = patch.object(state, "current_snapshot_commit", return_value="saved-snapshot")
        self.snapshot.start()
        self.addCleanup(self.snapshot.stop)
        state.atomic_json(state.skill_dir(self.target) / "active.json", {
            "status": "running", "mode": "full", "snapshot_commit": "saved-snapshot",
            "fingerprint": "failed-dag", "phases": ["specification", "verification"],
            "current_phase": "specification", "phase_status": {"specification": {"status": "running"}},
            "inputs": {"config": {}, "submodules": []},
        })
        state.atomic_json(state.skill_dir(self.target) / "config.json", {"retries": 1})

    def exhausted_spec(self, dependent=True) -> None:
        scheduler.create(self.target, {
            "id": "spec-api", "phase": "specification", "type": "spec_batch",
            "depends_on": [], "artifacts": ["api.py"],
            "required_outputs": ["fm_agent/extracted_functions/api.py.spec.json", "fm_agent/extracted_functions/api.py.info.json"],
        })
        if dependent:
            scheduler.create(self.target, {
                "id": "verify-api", "phase": "verification", "type": "verify_function",
                "depends_on": ["spec-api"], "artifacts": ["api.py"],
                "required_outputs": ["fm_agent/logic_verification_results/api.json"],
            })
        scheduler.transition(self.target, "spec-api", "start", None, None, "execution")
        failed = scheduler.transition(self.target, "spec-api", "fail", None, "Worker retry budget exhausted", "execution")
        self.assertEqual(failed["status"], "failed")

    def test_failed_dependency_without_live_worker_does_not_wait(self) -> None:
        self.exhausted_spec()
        action = durable_executor.next_actions(self.target, 3, host="codex")
        self.assertEqual(action["action"], "phase_failed")
        self.assertFalse(action["scheduler"]["converged"])
        self.assertFalse(action["coordinator"]["continuation_required"])
        self.assertEqual(phase_driver.next_step(self.target, 3, "codex")["action"], "phase_failed")
        self.assertFalse(scheduler._running(self.target))

    def test_terminal_failure_without_dependents_does_not_converge(self) -> None:
        self.exhausted_spec(dependent=False)
        self.assertEqual(durable_executor.next_actions(self.target, 3)["action"], "phase_failed")

    def test_independent_jobs_finish_before_reporting_terminal_failure(self) -> None:
        self.exhausted_spec()
        scheduler.create(self.target, {
            "id": "independent", "phase": "specification", "type": "phase_refine",
            "depends_on": [], "artifacts": [], "required_outputs": [],
        })
        self.assertEqual(phase_driver.next_step(self.target, 3, "codex")["action"], "dispatch_workers")
        scheduler.transition(self.target, "independent", "start", None, None, "execution")
        self.assertEqual(phase_driver.next_step(self.target, 3, "codex")["action"], "wait_for_completion_event")
        scheduler.transition(self.target, "independent", "complete", {
            "job_id": "independent", "status": "completed", "outputs": [],
        }, None, "execution")
        self.assertEqual(phase_driver.next_step(self.target, 3, "codex")["action"], "phase_failed")

    def test_capacity_blocked_work_without_failed_job_still_waits(self) -> None:
        state.atomic_json(state.skill_dir(self.target) / "config.json", {"max_active_subagents": 1})
        for job_id in ("first", "second"):
            scheduler.create(self.target, {
                "id": job_id, "phase": "specification", "type": "phase_refine",
                "depends_on": [], "artifacts": [], "required_outputs": [],
            })
        scheduler.transition(self.target, "first", "start", None, None, "execution")
        self.assertEqual(phase_driver.next_step(self.target, 3, "codex")["action"], "wait_for_completion_event")


if __name__ == "__main__":
    unittest.main()
