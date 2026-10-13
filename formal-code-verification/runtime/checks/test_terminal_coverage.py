#!/usr/bin/env python3
# Added by AIResearchSkill: keep reasoning gaps, dynamic outcomes, and business execution coverage distinct.
"""Terminal authority never promotes reasoning or missing receipts into executed coverage."""
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
import scheduler
import terminal_report
from test_accepted_bug_evidence import write_accepted_candidate


class TerminalCoverageTest(unittest.TestCase):
    def prepared(self, target: Path) -> list[dict]:
        write_accepted_candidate(target)
        state.atomic_json(checkpoint.root(target) / "official_result.json", {"official_result_available": True})
        return [{"function_id": "calc.py::inc", "verdict": "MISMATCH"}]

    def build(self, target: Path, verification: list[dict]) -> dict:
        verification = [{**value, "candidates": [{"candidate_id": state.candidate_id(value["function_id"])}]} if value.get("verdict") == "MISMATCH" else value for value in verification]
        with patch.object(checkpoint, "validate", return_value={"snapshot_commit": "unversioned", "checkpoint_id": "sealed"}), \
             patch.object(terminal_report, "_verification_results", return_value=verification):
            return terminal_report.build(target)

    def row(self, *, status="failed", evidence=None, row_id="public-result", function_id="calc.py::inc", requirement="returns x + 2") -> dict:
        return {
            "id": row_id, "flow": "Public calc entry", "function_id": function_id, "candidate_id": state.candidate_id(function_id), "requirement": requirement,
            "status": status, "limitation": "One recorded probe covers this input only",
            "evidence": evidence if evidence is not None else [{
                "level": "actual-code", "path": "fm_agent_skill/probes/candidate/attempt_001/reproduction_result.json",
            }],
        }

    def coverage(self, target: Path, rows: list[dict], snapshot="unversioned") -> None:
        state.atomic_json(state.control_dir(target) / "business_coverage.json", {
            "schema_version": 1, "snapshot_commit": snapshot, "rows": rows,
        })

    def test_reasoning_gaps_and_dynamic_inconclusive_are_counted_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            verification = self.prepared(target)
            write_accepted_candidate(target, "calc.py::dynamic_gap", "dynamic-gap", "inconclusive")
            verification += [{"function_id": "calc.py::dynamic_gap", "verdict": "MISMATCH"}]
            verification += [
                {"function_id": "calc.py::match", "verdict": "MATCH"},
                {"function_id": "calc.py::unknown_contract", "verdict": "INCONCLUSIVE", "gaps": {"reason": "No independent contract"}},
                {"function_id": "calc.py::unknown_intent", "verdict": "INCONCLUSIVE", "gaps": {"reason": "Owner intent unresolved"}},
                {"function_id": "calc.py::callee", "verdict": "DEPENDENCY_RISK", "reasoning": {"reason": "Callee obligation is unresolved"}},
                {"function_id": "calc.py::worker", "verdict": "ERROR", "error": {"message": "Reasoning Worker failed"}},
            ]
            self.coverage(target, [self.row()])
            report = self.build(target, verification)
            self.assertTrue(report["official_result_available"])
            self.assertEqual(report["reasoning"]["counts"], {
                "MATCH": 1, "MISMATCH": 2, "INCONCLUSIVE": 2, "DEPENDENCY_RISK": 1, "ERROR": 1,
            })
            self.assertEqual(len(report["reasoning"]["gaps"]), 4)
            self.assertEqual(report["counts"]["confirmed"], 1)
            self.assertEqual(report["counts"]["dynamic_inconclusive"], 1)
            self.assertNotIn("inconclusive", report["counts"])
            self.assertEqual(report["business_coverage"]["counts"], {"passed": 0, "failed": 1, "unknown": 0})
            self.assertEqual(report["audit_status"], "completed_with_gaps")

    def test_dynamic_inconclusive_alone_keeps_audit_gaps_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            verification = self.prepared(target)
            write_accepted_candidate(target, "calc.py::dynamic_gap", "dynamic-gap", "inconclusive")
            verification.append({"function_id": "calc.py::dynamic_gap", "verdict": "MISMATCH"})
            self.coverage(target, [self.row()])
            report = self.build(target, verification)
            self.assertEqual(report["reasoning"]["gaps"], [])
            self.assertEqual(report["business_coverage"]["counts"]["unknown"], 0)
            self.assertEqual(report["audit_status"], "completed_with_gaps")
            self.assertEqual(report["findings"]["inconclusive"][0]["attempts"], [{
                "ordinal": 1, "classification": "inconclusive", "state": "completed",
                "reason": "Recorded public-entry probe outcome",
            }])

    def test_prior_unavailable_execution_remains_visible_after_a_negative_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            write_accepted_candidate(target, status="inconclusive", prior_unsupported=True)
            state.atomic_json(checkpoint.root(target) / "official_result.json", {"official_result_available": True})
            self.coverage(target, [self.row(status="unknown", evidence=[])])
            report = self.build(target, [{"function_id": "calc.py::inc", "verdict": "MISMATCH"}])
            finding = report["findings"]["inconclusive"][0]
            self.assertEqual(finding["attempt_count"], 2)
            self.assertEqual(finding["attempts"], [
                {"ordinal": 1, "classification": "inconclusive", "state": "unsupported", "reason": "Required persistence service unavailable"},
                {"ordinal": 2, "classification": "not_reproduced", "state": "completed", "reason": "Recorded public-entry probe outcome"},
            ])
            self.assertEqual(report["audit_status"], "completed_with_gaps")

    def test_missing_and_invalid_coverage_cannot_complete_the_audit(self) -> None:
        for case in ("missing", "empty", "foreign_snapshot", "passed_reasoning", "failed_reasoning", "missing_evidence", "duplicate"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                verification = self.prepared(target)
                reasoning_path = state.fm_dir(target) / "logic_verification_results/reasoning.json"
                state.atomic_json(reasoning_path, {"verdict": "MATCH"})
                reasoning = [{"level": "reasoning", "path": reasoning_path.relative_to(target).as_posix()}]
                if case == "empty":
                    self.coverage(target, [])
                elif case == "foreign_snapshot":
                    self.coverage(target, [self.row()], "other-snapshot")
                elif case in {"passed_reasoning", "failed_reasoning"}:
                    self.coverage(target, [self.row(status=case.split("_")[0], evidence=reasoning)])
                elif case == "missing_evidence":
                    self.coverage(target, [self.row(evidence=[{"level": "actual-code", "path": "missing.json"}])])
                elif case == "duplicate":
                    self.coverage(target, [self.row(), self.row()])
                report = self.build(target, verification)
                self.assertEqual(report["audit_status"], "incomplete")
                self.assertEqual(report["business_coverage"]["status"], "missing" if case == "missing" else "invalid")
                if case.endswith("reasoning"):
                    self.assertIn("not reasoning alone", report["business_coverage"]["reason"])

    def test_explicit_unknown_coverage_remains_visible_with_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            verification = self.prepared(target)
            row = self.row(status="unknown", evidence=[])
            del row["function_id"]
            self.coverage(target, [row])
            report = self.build(target, verification)
            self.assertEqual(report["business_coverage"]["status"], "available")
            self.assertEqual(report["business_coverage"]["counts"]["unknown"], 1)
            self.assertEqual(report["audit_status"], "completed_with_gaps")

    def test_execution_level_cannot_hide_unsupported_or_contradictory_outcomes(self) -> None:
        for level in ("actual-code", "integration", "machine-verifier"):
            for status in ("passed", "failed"):
                with self.subTest(level=level, status=status), tempfile.TemporaryDirectory() as temporary:
                    target = Path(temporary).resolve()
                    path = "fm_agent_skill/probes/dynamic-gap/attempt_001/reproduction_result.json"
                    write_accepted_candidate(target, "calc.py::gap", "dynamic-gap", "inconclusive")
                    result = state.read_json(target / path, {})
                    result.update(state="unsupported", classification="inconclusive", commands=[])
                    state.atomic_json(target / path, result)
                    self.coverage(target, [self.row(status=status, function_id="calc.py::gap", evidence=[{"level": level, "path": path}])])
                    coverage = terminal_report._business_coverage(target, "unversioned")
                    self.assertEqual(coverage["status"], "invalid")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            self.prepared(target)
            self.coverage(target, [self.row(status="passed")])
            self.assertEqual(terminal_report._business_coverage(target, "unversioned")["status"], "invalid")
            write_accepted_candidate(target, "calc.py::negative", "negative", "rejected")
            self.coverage(target, [self.row(status="passed", function_id="calc.py::negative", requirement="returns x + 1", evidence=[{"level": "actual-code", "path": "fm_agent_skill/probes/negative/attempt_001/reproduction_result.json"}])])
            self.assertEqual(terminal_report._business_coverage(target, "unversioned")["counts"]["passed"], 1)

    def test_native_coverage_is_bound_to_assigned_requirement_and_accepted_job(self) -> None:
        for case in ("no_function", "other_function", "other_requirement", "other_bug", "no_receipt", "foreign_index", "foreign_plan", "integration", "machine-verifier"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                self.prepared(target)
                write_accepted_candidate(target, "calc.py::negative", "negative", "rejected")
                row = self.row(status="passed", function_id="calc.py::negative", requirement="returns x + 1", evidence=[{
                    "level": "actual-code", "path": "fm_agent_skill/probes/negative/attempt_001/reproduction_result.json",
                }])
                if case == "no_function":
                    del row["function_id"]
                elif case == "other_function":
                    row["function_id"] = "calc.py::inc"
                elif case == "other_requirement":
                    row["requirement"] = "Successful reservations survive restart"
                elif case == "other_bug":
                    row["function_id"] = "calc.py::inc"
                    row["requirement"] = "returns x + 2"
                elif case == "no_receipt":
                    connection = scheduler._connect(target)
                    connection.execute("DELETE FROM receipts WHERE job_id='bug-validation-negative'")
                    connection.close()
                elif case in {"foreign_index", "foreign_plan"}:
                    path = state.control_dir(target) / ("analysis_index.json" if case == "foreign_index" else "job_plans/bug_validation.json")
                    data = state.read_json(path, {})
                    data["snapshot_commit"] = "another-snapshot"
                    state.atomic_json(path, data)
                else:
                    row["evidence"][0]["level"] = case
                self.coverage(target, [row])
                self.assertEqual(terminal_report._business_coverage(target, "unversioned")["status"], "invalid")
                row["status"] = "unknown"
                self.coverage(target, [row])
                coverage = terminal_report._business_coverage(target, "unversioned")
                self.assertEqual(coverage["counts"]["unknown"], 1)
                self.assertEqual(coverage["rows"], [row])

    def test_empty_or_failed_scheduler_has_no_official_findings(self) -> None:
        for case in ("empty", "error"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                verification = self.prepared(target)
                self.coverage(target, [self.row()])
                if case == "empty":
                    scheduler.clear_run(target)
                    report = self.build(target, verification)
                else:
                    with patch.object(scheduler, "aggregate_readonly", side_effect=RuntimeError("scheduler unavailable")):
                        report = self.build(target, verification)
                self.assertFalse(report["official_result_available"])
                self.assertEqual(report["status"], "unavailable")
                self.assertEqual(report["audit_status"], "incomplete")
                self.assertNotIn("findings", report)

    def test_missing_empty_and_pending_scheduler_cannot_complete_a_zero_candidate_run(self) -> None:
        for case in ("missing", "empty", "pending"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                state.atomic_json(checkpoint.root(target) / "official_result.json", {"official_result_available": True})
                if case == "empty":
                    scheduler.clear_run(target)
                elif case == "pending":
                    scheduler.create(target, {"id": "plan", "phase": "project_understanding", "type": "phase_plan", "required_outputs": []})
                report = self.build(target, [])
                self.assertFalse(report["official_result_available"])
                self.assertEqual(report["status"], "unavailable")
                self.assertNotIn("findings", report)
                self.assertIsNone(report["counts"]["confirmed"])
                if case == "missing":
                    self.assertFalse(checkpoint.db_path(target).exists())

    def test_valid_accepted_receipt_and_execution_coverage_remain_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            verification = self.prepared(target)
            self.coverage(target, [self.row()])
            report = self.build(target, verification)
            self.assertTrue(report["official_result_available"])
            self.assertEqual(report["audit_status"], "completed")
            self.assertEqual(report["counts"]["confirmed"], 1)
            self.assertEqual(report["findings"]["confirmed"][0]["function_id"], "calc.py::inc")


if __name__ == "__main__":
    unittest.main()
