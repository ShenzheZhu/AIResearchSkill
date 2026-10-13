#!/usr/bin/env python3
# Added by AIResearchSkill: verify Bug Validator authority against real durable acceptance receipts.
"""Accepted Bug Validation evidence cannot fall back to unaccepted files."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from result_fixture import verification_result

from fm_agent_core import state
import bug_summary
import bug_validation_executor
import scheduler


def write_accepted_candidate(target: Path, function_id="calc.py::inc", bug_id="candidate", status="confirmed", *, prior_unsupported=False, candidate_ordinal=1) -> dict:
    identity = state.candidate_id(function_id, candidate_ordinal)
    snapshot = state.current_snapshot_commit(target)
    if not state.active_record(target):
        state.atomic_json(state.skill_dir(target) / "active.json", {
            "snapshot_commit": snapshot, "fingerprint": "receipt-check",
            "mode": "full", "phases": ["bug_validation"], "current_phase": "bug_validation",
        })
    source_path, symbol = function_id.split("::", 1)
    index_path = state.control_dir(target) / "analysis_index.json"
    index = state.read_json(index_path, {"functions": []})
    item = next((entry for entry in index["functions"] if entry.get("id") == function_id), None)
    if item is None:
        item = {"id": function_id, "artifact": f"{bug_id}{Path(source_path).suffix}"}
        index["functions"].append(item)
    language = "python" if Path(source_path).suffix == ".py" else "c"
    source = target / source_path
    source.parent.mkdir(parents=True, exist_ok=True)
    code = f"def {symbol}(x):\n    return x + 1\n" if language == "python" else f"int {symbol}(int x) {{ return x + 1; }}\n"
    if not source.exists():
        source.write_text(code, encoding="utf-8")
    elif code not in source.read_text(encoding="utf-8"):
        source.write_text(source.read_text(encoding="utf-8") + code, encoding="utf-8")
    source_text = source.read_text(encoding="utf-8")
    line_start = source_text[:source_text.index(code)].count("\n") + 1
    item.update(path=source_path, language=language, line_start=line_start, line_end=line_start + len(code.splitlines()) - 1)
    index.update(schema_version=2, snapshot_commit=snapshot)
    state.atomic_json(index_path, index)
    artifact = state.fm_dir(target) / "extracted_functions" / item["artifact"]
    if not artifact.exists():
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(code, encoding="utf-8")
    spec_path = Path(f"{artifact}.spec.json")
    if not spec_path.exists():
        state.atomic_json(spec_path, {
            "signature": f"{symbol}(x)", "pre_condition": "x is an integer",
            "post_condition": "returns x + 1" if status == "rejected" else "returns x + 2",
        })
    state.atomic_json(Path(f"{artifact}.info.json"), {"callees": []})
    verification_path = state.fm_dir(target) / "logic_verification_results" / Path(item["artifact"]).with_suffix(".json")
    if not verification_path.exists():
        state.atomic_json(verification_path, verification_result(function_id=function_id, snapshot_commit=snapshot, verdict="MISMATCH", gaps=None, error=None, reasoning={"actual_postcondition": "returns x + 1", "spec_postcondition": state.read_json(spec_path, {})["post_condition"],
                          "counterexample": "x=1 returns a different value than the reasoned candidate", "offending_statements": "return x + 1",
                          "reason": "The reasoned return contract requires dynamic validation"}))
    if candidate_ordinal > 1:
        verification = state.read_json(verification_path, {})
        reason = dict(verification["reasoning"], counterexample=f"x={candidate_ordinal} exercises a separate candidate hypothesis")
        verification["candidates"].append({"candidate_id": identity, "reasoning": reason})
        state.atomic_json(verification_path, verification)
        active = state.active_record(target)
        active.setdefault("inputs", {}).setdefault("config", {})["all_bugs"] = True
        state.atomic_json(state.skill_dir(target) / "active.json", active)
    output = f"fm_agent/bug_validation/{bug_id}.result.json"
    job = scheduler.create(target, {
        "id": f"bug-validation-{bug_id}", "phase": "bug_validation", "type": "bug_validate",
        "depends_on": [], "required_outputs": [output], "artifacts": [], "negative_retries": 1 if prior_unsupported else 0,
        "input": {"candidate_id": identity, "bug_id": bug_id, "function_id": function_id, "mode": "full"},
    })
    entrypoint = {"ecosystem": "host-project-toolchain", "kind": "module", "target": "calc.py", "symbol": "inc"}
    attempts = []
    for ordinal in range(1, 3 if prior_unsupported else 2):
        job = scheduler.transition(target, job["id"], "start", None, None, "execution")
        root = bug_validation_executor.attempt_dir(target, bug_id, ordinal)
        state.atomic_json(root / "reproduction.json", {"function_id": function_id, "candidate_id": identity,
            "schema_version": 3, "bug_id": bug_id, "attempt": ordinal, "snapshot_commit": snapshot,
            "language": "python", "public_entrypoint": entrypoint, "probe_file": "probe.py",
            "expected_marker": "CONFIRMED", "not_confirmed_marker": "NOT CONFIRMED", "timeout_seconds": 30,
        })
        classification = ("inconclusive" if ordinal == 1 else "not_reproduced") if prior_unsupported else "not_reproduced" if status == "rejected" else status
        marker = {"confirmed": "CONFIRMED", "not_reproduced": "NOT CONFIRMED", "inconclusive": "no outcome marker"}[classification]
        unsupported = prior_unsupported and ordinal == 1
        (root / "probe.py").write_text(f"print({marker!r})\n", encoding="utf-8")
        evidence = (root / "reproduction_result.json").relative_to(target).as_posix()
        state.atomic_json(target / evidence, {"function_id": function_id, "candidate_id": identity,
            "schema_version": 2, "execution_mode": "agent-executed", "bug_id": bug_id, "attempt": ordinal,
            "snapshot_commit": snapshot, "language": "python", "public_entrypoint": entrypoint,
            "state": "unsupported" if unsupported else "completed", "classification": classification,
            "reason": "Required persistence service unavailable" if unsupported else "Recorded public-entry probe outcome",
            "commands": [] if unsupported else [{"command": "python3 probe.py", "cwd": root.relative_to(target).as_posix(),
                          "returncode": 0, "stdout": marker + "\n", "stderr": ""}],
        })
        attempts.append({"ordinal": ordinal, "classification": classification, "dynamic_evidence": {"reproduction_result": evidence}})
        state.atomic_json(target / output, {"candidate_id": identity,
            "schema_version": 2, "bug_id": bug_id, "function_id": function_id, "snapshot_commit": snapshot,
            "confirmation_status": status, "attempts": attempts,
        })
        accepted = scheduler.transition(target, job["id"], "complete", bug_validation_executor.canonical_finalization_receipt(target, job), None, "execution")
        if prior_unsupported and ordinal == 1:
            scheduler.transition(target, job["id"], "retry", None, None, "execution")
    plan_path = state.control_dir(target) / "job_plans" / "bug_validation.json"
    entries = state.read_json(plan_path, {}).get("entries", [])
    entries.append({"candidate_id": identity, "function_id": function_id, "job_id": job["id"]})
    state.atomic_json(plan_path, {
        "schema_version": 1, "phase": "bug_validation", "snapshot_commit": snapshot,
        "entries": entries, "created_jobs": len(entries), "total_entries": len(entries),
    })
    return accepted


class AcceptedBugEvidenceTest(unittest.TestCase):
    def accepted(self, target: Path, job: dict, **identity) -> dict:
        return scheduler.accepted_job(target, job["id"], snapshot_commit=identity.get("snapshot_commit", "unversioned"),
                                      input_fingerprint=identity.get("input_fingerprint", "receipt-check"))

    def test_durable_receipt_survives_json_cleanup_and_different_live_head(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job = write_accepted_candidate(target)
            scheduler._path(target, job["id"]).unlink()
            with patch.object(state, "current_snapshot_commit", return_value="different-live-head"):
                self.assertEqual(self.accepted(target, job)["status"], "succeeded")

    def test_empty_or_unreadable_ledger_never_accepts_a_saved_job_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job = write_accepted_candidate(target)
            scheduler.clear_run(target)
            with self.assertRaisesRegex(ValueError, "unavailable"):
                self.accepted(target, job)
            with patch.object(scheduler.sqlite3, "connect", side_effect=sqlite3.OperationalError("unreadable ledger")), \
                 self.assertRaisesRegex(ValueError, "unreadable ledger"):
                self.accepted(target, job)
            scheduler.checkpoint.db_path(target).unlink()
            with self.assertRaisesRegex(ValueError, "database is missing"):
                self.accepted(target, job)
            self.assertFalse(scheduler.checkpoint.db_path(target).exists())

    def test_changed_output_or_missing_malformed_or_foreign_receipt_is_unavailable(self) -> None:
        mutations = {
            "output": lambda target, job, connection: (target / job["bug_result_path"]).write_text(
                (target / job["bug_result_path"]).read_text() + "\n", encoding="utf-8"),
            "missing": lambda target, job, connection: connection.execute("DELETE FROM receipts WHERE job_id=?", (job["id"],)),
            "malformed": lambda target, job, connection: connection.execute("UPDATE receipts SET payload_json='{}' WHERE job_id=?", (job["id"],)),
            "foreign": lambda target, job, connection: connection.execute("UPDATE runs SET input_fingerprint='other-inputs'"),
            "attempt": lambda target, job, connection: connection.execute("UPDATE attempts SET status='running' WHERE job_id=?", (job["id"],)),
            "input": lambda target, job, connection: connection.execute("UPDATE receipts SET input_hash='different-input' WHERE job_id=?", (job["id"],)),
            "artifact": lambda target, job, connection: connection.execute("DELETE FROM artifacts WHERE job_id=?", (job["id"],)),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                job = write_accepted_candidate(target)
                connection = scheduler._connect(target)
                mutate(target, job, connection)
                connection.close()
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    self.accepted(target, job)

    def test_changed_recorded_command_outcome_cannot_remain_confirmed(self) -> None:
        for output, returncode in (("", 0), ("NOT CONFIRMED\n", 0), ("CONFIRMED\n", 1)):
            with self.subTest(output=output, returncode=returncode), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                job = write_accepted_candidate(target)
                evidence_path = bug_validation_executor.attempt_dir(target, "candidate", 1) / "reproduction_result.json"
                evidence = state.read_json(evidence_path, {})
                evidence["commands"][0].update({"stdout": output, "returncode": returncode})
                state.atomic_json(evidence_path, evidence)
                with self.assertRaisesRegex(ValueError, "command evidence"):
                    self.accepted(target, job)

    def test_adapter_execution_uses_the_same_output_classifier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job = write_accepted_candidate(target)
            root = bug_validation_executor.attempt_dir(target, "candidate", 1)
            contract = state.read_json(root / "reproduction.json", {})
            contract["public_entrypoint"]["ecosystem"] = "python-packaging"
            state.atomic_json(root / "reproduction.json", contract)
            result = state.read_json(root / "reproduction_result.json", {})
            result.pop("execution_mode")
            result.pop("commands")
            result.update({"public_entrypoint": contract["public_entrypoint"], "command": ["python3", "probe.py"],
                           "returncode": 0, "stdout": "CONFIRMED\n", "stderr": ""})
            state.atomic_json(root / "reproduction_result.json", result)
            self.assertTrue(bug_validation_executor.execution_result_valid(target, job))
            for stdout, returncode in (("", 0), ("NOT CONFIRMED\n", 0), ("CONFIRMED\n", 1),
                                       ("build succeeded\nCONFIRMED\n", 0), ("CONFIRMED verifier success\n", 0),
                                       ("CONFIRMED\nCONFIRMED\n", 0)):
                result.update({"stdout": stdout, "returncode": returncode})
                state.atomic_json(root / "reproduction_result.json", result)
                self.assertFalse(bug_validation_executor.execution_result_valid(target, job))

    def test_summary_and_completion_require_real_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.object(state, "direct_mismatch_ids", return_value={"calc.py::inc"}):
            target = Path(temporary).resolve()
            job = write_accepted_candidate(target)
            self.assertTrue(bug_validation_executor.all_phase_jobs_succeeded(target, "bug_validation"))
            self.assertEqual(bug_summary.write_summary(target, "full")["total_confirmed"], 1)
            connection = scheduler._connect(target)
            connection.execute("DELETE FROM receipts WHERE job_id=?", (job["id"],))
            connection.close()
            with self.assertRaisesRegex(ValueError, "unavailable"):
                bug_summary.write_summary(target, "full")
            with self.assertRaisesRegex(ValueError, "unavailable"):
                bug_validation_executor.all_phase_jobs_succeeded(target, "bug_validation")
            scheduler.clear_run(target)
            with self.assertRaisesRegex(ValueError, "no originating run"):
                bug_summary.write_summary(target, "full")


if __name__ == "__main__":
    unittest.main()
