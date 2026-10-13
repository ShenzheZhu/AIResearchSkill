#!/usr/bin/env python3
# Modified by AIResearchSkill: isolate canonical receipt acceptance from subsequent Worker dispatch.
"""Regression checks for canonical Bug Validation finalization receipts."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import bug_validation_executor  # noqa: E402


class BugValidationReceiptTest(unittest.TestCase):
    def test_finalization_derives_classification_from_report_not_host_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            output = "fm_agent/bug_validation/candidate.result.json"
            report_path = target / output
            report_path.parent.mkdir(parents=True)
            report_path.write_text(json.dumps({
                "confirmation_status": "confirmed",
                "attempts": [{"ordinal": 1, "classification": "confirmed"}],
            }), encoding="utf-8")
            job = {
                "id": "bug-validation-candidate",
                "phase": "bug_validation",
                "type": "bug_validate",
                "status": "running",
                "attempts": 1,
                "required_outputs": [output],
                "bug_result_path": output,
                "input": {"bug_id": "candidate", "mode": "full"},
            }
            captured: dict[str, object] = {}

            def transition(_target, _job_id, action, receipt, *_unused):
                captured["action"] = action
                captured["receipt"] = receipt
                return {**job, "status": "succeeded"}

            with patch.object(bug_validation_executor, "load_job", return_value=job), \
                 patch.object(bug_validation_executor, "finalization_matches_current_attempt", return_value=True), \
                 patch.object(bug_validation_executor.scheduler, "transition", side_effect=transition), \
                 patch.object(bug_validation_executor, "next_action", return_value={"action": "terminal", "status": "succeeded"}), \
                 patch.object(bug_validation_executor, "all_phase_jobs_succeeded", return_value=False):
                bug_validation_executor.submit_finalization(target, job["id"], {
                    "job_id": job["id"], "status": "completed", "outputs": [output],
                })

            self.assertEqual(captured["action"], "complete")
            self.assertEqual(captured["receipt"], {
                "job_id": job["id"],
                "status": "completed",
                "outputs": [output],
                "classification": "confirmed",
            })

    def test_finalization_rejects_report_without_current_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            output = "fm_agent/bug_validation/candidate.result.json"
            report_path = target / output
            report_path.parent.mkdir(parents=True)
            report_path.write_text(json.dumps({"attempts": [{"ordinal": 1}]}), encoding="utf-8")
            job = {"id": "bug-validation-candidate", "required_outputs": [output], "bug_result_path": output}
            with self.assertRaisesRegex(ValueError, "valid current attempt classification"):
                bug_validation_executor.canonical_finalization_receipt(target, job)


if __name__ == "__main__":
    unittest.main()
