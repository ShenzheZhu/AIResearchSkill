"""Mixed retry results must pass the same phase gate as their accepted receipt."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from fm_agent_core import state
import bug_summary
import scheduler
import stage_gate
from test_accepted_bug_evidence import write_accepted_candidate


class MixedValidationGateTest(unittest.TestCase):
    def gate(self, target):
        # The unversioned fixture has no source snapshot whose cleanliness can be checked.
        with patch.object(state, "snapshot_sources_clean", return_value=True):
            return stage_gate.validate(target, "full", "bug_validation", [])

    def test_retained_unavailable_attempt_then_final_negative_passes_as_inconclusive(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job = write_accepted_candidate(target, status="inconclusive", prior_unsupported=True)
            accepted = scheduler.accepted_job(
                target, job["id"], snapshot_commit="unversioned", input_fingerprint="receipt-check",
            )
            self.assertEqual(accepted["status"], "succeeded")
            summary = bug_summary.write_summary(target, "full")
            self.assertEqual(summary["total_inconclusive"], 1)
            self.assertEqual(state.bug_validation_ready(target, {"calc.py::inc"}), (True, ""))
            self.assertTrue(self.gate(target)["ok"])

    def test_final_status_still_requires_matching_dynamic_attempts(self):
        for recorded, claimed, prior_unsupported in (
            ("rejected", "inconclusive", False),
            ("inconclusive", "confirmed", False),
            ("inconclusive", "rejected", False),
            ("inconclusive", "rejected", True),
        ):
            with self.subTest(recorded=recorded, claimed=claimed, prior_unsupported=prior_unsupported), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                job = write_accepted_candidate(target, status=recorded, prior_unsupported=prior_unsupported)
                summary = bug_summary.write_summary(target, "full")
                self.assertTrue(self.gate(target)["ok"])
                path = target / job["bug_result_path"]
                report = state.read_json(path, {})
                report["confirmation_status"] = claimed
                state.atomic_json(path, report)
                summary[f"total_{recorded}"] = 0
                summary[f"total_{claimed}"] = 1
                state.atomic_json(state.fm_dir(target) / "bug_validation/summary.json", summary)
                self.assertFalse(state.bug_validation_ready(target, {"calc.py::inc"})[0])
                self.assertFalse(self.gate(target)["ok"])


if __name__ == "__main__":
    unittest.main()
