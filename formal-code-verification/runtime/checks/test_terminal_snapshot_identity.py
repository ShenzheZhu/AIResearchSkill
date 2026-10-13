#!/usr/bin/env python3
"""Published reports use the sealed snapshot rather than the live source HEAD."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from fm_agent_core import state
import checkpoint
import terminal_report


class TerminalSnapshotIdentityTest(unittest.TestCase):
    def test_saved_result_survives_different_live_head_and_other_snapshots_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            artifact = state.fm_dir(target) / "extracted_functions/calc-inc-1.py"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("def inc(x):\n    return x + 1\n", encoding="utf-8")
            state.atomic_json(Path(f"{artifact}.spec.json"), {
                "signature": "inc(x)", "pre_condition": "x is an integer", "post_condition": "returns x + 2",
            })
            state.atomic_json(Path(f"{artifact}.info.json"), {"callees": []})
            state.atomic_json(state.control_dir(target) / "analysis_index.json", {
                "functions": [{"id": "calc.py::inc", "artifact": artifact.name}],
            })
            result = {
                "schema_version": 2, "function_id": "calc.py::inc", "snapshot_commit": "saved-snapshot",
                "verdict": "MISMATCH", "gaps": None, "error": None,
                "reasoning": {"actual_postcondition": "returns x + 1", "spec_postcondition": "returns x + 2",
                              "counterexample": "x=0 returns 1 instead of 2", "offending_statements": "return x + 1",
                              "reason": "The return value is one below the contract"},
            }
            result_path = state.fm_dir(target) / "logic_verification_results/calc-inc-1.json"
            state.atomic_json(result_path, result)
            state.atomic_json(checkpoint.root(target) / "official_result.json", {"official_result_available": True})
            with patch.object(state, "current_snapshot_commit", return_value="new-live-head"), \
                 patch.object(checkpoint, "validate", return_value={"snapshot_commit": "saved-snapshot", "checkpoint_id": "sealed"}):
                report = terminal_report.build(target)
                self.assertTrue(report["official_result_available"])
                self.assertEqual(report["counts"]["verification_results"], 1)
                self.assertEqual(report["counts"]["candidates"], 1)
                self.assertEqual(report["findings"]["candidates"], ["calc.py::inc"])

                result["snapshot_commit"] = "new-live-head"
                state.atomic_json(result_path, result)
                self.assertEqual(terminal_report.build(target)["counts"]["verification_results"], 0)


if __name__ == "__main__":
    unittest.main()
