#!/usr/bin/env python3
# Added by AIResearchSkill: retain genuine candidate receipts across on-demand validation.
"""Repeated on-demand validation keeps other candidates' accepted authority."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from result_fixture import verification_result

from fm_agent_core import state
import bug_validation_executor
import isolation
import orchestrate
import scheduler


class OnDemandValidationReceiptsTest(unittest.TestCase):
    def test_dispatch_and_complete_preserve_previous_candidate_and_allow_targeted_revalidation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(state, "current_snapshot_commit", return_value="unversioned"), \
             patch.object(state, "baseline_commit", return_value="unversioned"):
            base = Path(temporary).resolve()
            source = base / "source"
            source.mkdir()
            (source / "calc.py").write_text("def inc(x): return x + 1\ndef dec(x): return x - 1\n", encoding="utf-8")
            entries = []
            for line, symbol, operator in ((1, "inc", "+"), (2, "dec", "-")):
                artifact_name = f"calc-{symbol}-{line}.py"
                entries.append({"id": f"calc.py::{symbol}", "path": "calc.py", "artifact": artifact_name,
                                "language": "python", "line_start": line, "line_end": line})
                artifact = state.fm_dir(source) / "extracted_functions" / artifact_name
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_text(f"def {symbol}(x): return x {operator} 1\n", encoding="utf-8")
                state.atomic_json(Path(f"{artifact}.spec.json"), {
                    "signature": f"{symbol}(x)", "pre_condition": "x is an integer", "post_condition": f"returns x {operator} 2",
                })
                state.atomic_json(Path(f"{artifact}.info.json"), {"callees": []})
                actual, expected = (2, 3) if symbol == "inc" else (0, -1)
                state.atomic_json(state.fm_dir(source) / "logic_verification_results" / Path(artifact_name).with_suffix(".json"), verification_result(function_id=f"calc.py::{symbol}", snapshot_commit="unversioned", verdict="MISMATCH", gaps=None, error=None, reasoning={"actual_postcondition": f"returns x {operator} 1", "spec_postcondition": f"returns x {operator} 2",
                                  "counterexample": f"x=1 returns {actual} instead of {expected}",
                                  "offending_statements": f"return x {operator} 1", "reason": "The return value differs from the contract"}))
            state.atomic_json(state.control_dir(source) / "analysis_index.json", {
                "schema_version": 2, "snapshot_commit": "unversioned", "functions": entries,
            })
            state.atomic_json(state.control_dir(source) / "graph_edges.json", {"edges": []})
            state.atomic_json(state.skill_dir(source) / "active.json", {
                "snapshot_commit": "unversioned", "fingerprint": "receipt-check", "status": "succeeded",
                "mode": "full", "phases": ["bug_validation"], "current_phase": "bug_validation",
            })
            state.atomic_json(state.skill_dir(source) / "baseline.json", {"baseline_commit": "unversioned", "fingerprint": "receipt-check", "run_fingerprint": "receipt-check"})
            snapshot_number = 0

            def create_snapshot(_source):
                nonlocal snapshot_number
                snapshot_number += 1
                snapshot = base / f"snapshot-{snapshot_number}"
                shutil.copytree(source, snapshot, ignore=shutil.ignore_patterns("checkpoint"))
                marker = {"source_project": str(source), "snapshot": str(snapshot), "snapshot_commit": "unversioned"}
                state.atomic_json(isolation.marker_path(source), marker)
                state.atomic_json(isolation.marker_path(snapshot), marker)
                return {"snapshot": str(snapshot)}

            def discard_snapshot(snapshot):
                isolation.marker_path(source).unlink()
                shutil.rmtree(snapshot)

            def inspection(_target, requested):
                candidate = requested if "::bug-" in requested else state.candidate_id(requested)
                function = state.direct_candidates(source)[candidate]["function_id"]
                return {"ok": True, "baseline_commit": "unversioned", "config": {}, "candidate_id": candidate, "function_id": function}

            with patch.object(orchestrate, "validate_inspect", side_effect=inspection), \
                 patch.object(orchestrate, "create_snapshot", side_effect=create_snapshot), \
                 patch.object(orchestrate, "discard_snapshot", side_effect=discard_snapshot):
                for function_id, expected_count in (("calc.py::inc", 1), ("calc.py::dec", 2), ("calc.py::inc", 2)):
                    with self.subTest(function_id=function_id, run=snapshot_number + 1):
                        dispatched = orchestrate.validate_dispatch(source, function_id)
                        snapshot = Path(dispatched["project"])
                        job_id = dispatched["job_id"]
                        bug_id = dispatched["bug_id"]
                        candidate_id = dispatched["candidate_id"]
                        self.assertEqual(bug_validation_executor.start(snapshot, job_id)["pass"], "preparation")
                        job = scheduler._load(snapshot, job_id)
                        root = bug_validation_executor.attempt_dir(snapshot, bug_id, 1)
                        symbol = function_id.split("::")[-1]
                        entrypoint = {"ecosystem": "host-project-toolchain", "kind": "module", "target": "calc.py", "symbol": symbol}
                        state.atomic_json(root / "reproduction.json", {"function_id": function_id, "candidate_id": candidate_id,
                            "schema_version": 3, "bug_id": bug_id, "attempt": 1, "snapshot_commit": "unversioned",
                            "language": "python", "public_entrypoint": entrypoint, "probe_file": "probe.py",
                            "expected_marker": "CONFIRMED", "not_confirmed_marker": "NOT CONFIRMED", "timeout_seconds": 30,
                        })
                        expected = 3 if symbol == "inc" else -1
                        probe = root / "probe.py"
                        probe.write_text(
                            "import sys\nsys.path.insert(0, sys.argv[1])\nimport calc\n"
                            f"actual = calc.{symbol}(1)\nprint('CONFIRMED' if actual != {expected} else 'NOT CONFIRMED')\n",
                            encoding="utf-8",
                        )
                        executed = subprocess.run([sys.executable, "-B", str(probe), str(snapshot)], cwd=root, text=True, capture_output=True, check=True)
                        state.atomic_json(root / "reproduction_result.json", {"function_id": function_id, "candidate_id": candidate_id,
                            "schema_version": 2, "execution_mode": "agent-executed", "bug_id": bug_id,
                            "attempt": 1, "snapshot_commit": "unversioned", "language": "python", "public_entrypoint": entrypoint,
                            "state": "completed", "classification": "confirmed", "reason": "Public module returns a value different from the contract",
                            "commands": [{"command": f"{sys.executable} -B {probe} {snapshot}", "cwd": root.relative_to(snapshot).as_posix(),
                                          "returncode": executed.returncode, "stdout": executed.stdout, "stderr": executed.stderr}],
                        })
                        self.assertEqual(bug_validation_executor.submit_agent_execution(snapshot, job_id)["pass"], "finalization")
                        state.atomic_json(snapshot / job["bug_result_path"], {"candidate_id": candidate_id, "schema_version": 2, "bug_id": bug_id,
                            "function_id": function_id, "snapshot_commit": "unversioned", "confirmation_status": "confirmed",
                            "attempts": [{"ordinal": 1, "classification": "confirmed", "dynamic_evidence": {
                                "reproduction_result": (root / "reproduction_result.json").relative_to(snapshot).as_posix(),
                            }}],
                        })
                        self.assertEqual(bug_validation_executor.submit_finalization(snapshot, job_id)["status"], "succeeded")
                        completed = orchestrate.validate_complete(source)
                        self.assertTrue(completed["ok"])
                        self.assertEqual(completed["summary"]["total_confirmed"], expected_count)
                        plan = state.read_json(state.control_dir(source) / "job_plans/bug_validation.json", {})
                        for retained in completed["summary"]["validated_candidate_ids"]:
                            entry = next(value for value in plan["entries"] if value["candidate_id"] == retained)
                            origin = scheduler.accepted_origin(source, entry["job_id"])
                            self.assertEqual(scheduler.accepted_job(source, entry["job_id"], **origin)["status"], "succeeded")



if __name__ == "__main__":
    unittest.main()
