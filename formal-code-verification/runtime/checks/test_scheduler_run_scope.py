#!/usr/bin/env python3
"""Regression checks that prior scheduler rows cannot block a current run."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fm_agent_core import state  # noqa: E402
import scheduler  # noqa: E402
import stage_gate  # noqa: E402
import phase_driver  # noqa: E402


class SchedulerRunScopeTest(unittest.TestCase):
    def test_system_prompt_safety_guidance_does_not_self_trigger_oracle_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            prompt_root = target / "fm_agent" / "spec_prompts"
            domain = prompt_root / "domain_context"
            knowledge = domain / "user_knowledge"
            knowledge.mkdir(parents=True)
            state.atomic_json(target / "fm_agent_skill" / "active.json", {
                "snapshot_commit": "unversioned", "inputs": {"knowledge": []},
            })
            state.atomic_json(target / "fm_agent" / "phases.json", {"phases": [{"phase": 1}]})
            (prompt_root / "system_prompt.md").write_text(
                "Do not copy BUG: labels into behavioral contracts.\n", encoding="utf-8"
            )
            state.atomic_json(knowledge / "manifest.json", {
                "schema_version": 1, "snapshot_commit": "unversioned", "entries": [],
            })
            for name in ("engine_overview.txt", "phase_01_types.txt"):
                (domain / name).write_text(
                    state.OBSERVATIONAL_CONTEXT_MARKER + "\nobserved API topology\n", encoding="utf-8"
                )
            self.assertEqual(state.specification_context_ready(target), (True, ""))

    def test_old_failed_job_is_excluded_from_current_phase_receipt_and_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            skill = target / "fm_agent_skill"
            skill.mkdir()
            state.atomic_json(skill / "active.json", {
                "snapshot_commit": "new-snapshot", "fingerprint": "new-inputs",
                "phases": ["project_understanding"], "current_phase": "project_understanding",
            })
            connection = scheduler._connect(target)
            connection.execute(
                "INSERT INTO jobs(job_id,run_id,phase,type,status,attempt,max_attempts,remaining_dependencies,input_hash,payload_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                ("old-plan", "old-run", "project_understanding", "phase_plan", "failed", 1, 1, 0, "old", json.dumps({"id": "old-plan", "status": "failed"}), state.now(), state.now()),
            )
            connection.commit(); connection.close()

            receipt = scheduler.phase_receipt(target, "project_understanding")
            self.assertTrue(receipt["gate_ready"])
            self.assertTrue(scheduler.aggregate(target)["converged"])

    def test_invalid_accepted_phase_plan_is_requeued_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            skill = target / "fm_agent_skill"; skill.mkdir()
            plan_dir = target / "fm_agent"; plan_dir.mkdir()
            (plan_dir / "phases.json").write_text(json.dumps({"phases": [{"modules": ["bad.cpp"]}]}), encoding="utf-8")
            state.atomic_json(skill / "active.json", {
                "snapshot_commit": "snapshot", "fingerprint": "inputs",
                "phases": ["project_understanding"], "current_phase": "project_understanding",
            })
            job = {
                "schema_version": 2, "id": "phase-plan", "phase": "project_understanding",
                "type": "phase_plan", "status": "succeeded", "depends_on": [],
                "required_outputs": ["fm_agent/phases.json"], "artifacts": [], "attempts": 1,
                "max_attempts": 1, "created_at": state.now(), "updated_at": state.now(),
            }
            scheduler._persist(target, job, insert=True)
            restarted = scheduler.restart_invalid_phase_plan(target, "project_understanding")
            self.assertEqual(restarted["requeued"], ["phase-plan"])
            self.assertEqual(scheduler._load(target, "phase-plan")["status"], "queued")
            self.assertFalse((plan_dir / "phases.json").exists())

    def test_automatic_bug_validation_requires_a_plan_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            skill = target / "fm_agent_skill"; skill.mkdir()
            state.atomic_json(skill / "active.json", {
                "snapshot_commit": "snapshot", "fingerprint": "inputs",
                "phases": ["bug_validation"], "current_phase": "bug_validation",
            })
            self.assertEqual(stage_gate.bug_validation_current(target, "full"), (False, "Bug Validation plan is missing"))

    def test_empty_automatic_plan_completes_when_no_candidates_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            control = target / "fm_agent_skill" / "control" / "job_plans"
            control.mkdir(parents=True)
            state.atomic_json(target / "fm_agent_skill" / "active.json", {
                "snapshot_commit": "unversioned", "fingerprint": "inputs",
                "phases": ["bug_validation"], "current_phase": "bug_validation",
            })
            state.atomic_json(control / "bug_validation.json", {
                "schema_version": 1, "phase": "bug_validation", "snapshot_commit": "unversioned",
                "entries": [], "created_jobs": 0, "total_entries": 0,
            })
            self.assertEqual(stage_gate.bug_validation_current(target, "full"), (True, ""))

    def test_bug_validation_phase_uses_the_deterministic_candidate_planner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            action = phase_driver._deterministic_action(target, {"inputs": {}}, "bug_validation")
            self.assertEqual(action["kind"], "plan_bug_validation")
            self.assertIn("job_planner.py", action["argv"][0][1])
            self.assertEqual(action["argv"][0][-1], "bug_validation")


if __name__ == "__main__":
    unittest.main()
