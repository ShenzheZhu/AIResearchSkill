#!/usr/bin/env python3
# Added by AIResearchSkill: verify fresh Bug Validator Workers receive complete bounded pass tickets.
"""Bug Validator passes need no Coordinator-authored evidence permissions."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from result_fixture import verification_result

from fm_agent_core import state
import bug_validation_executor
import scheduler


class BugWorkerTicketTest(unittest.TestCase):
    def prepare(self, target: Path) -> dict:
        state.atomic_json(state.skill_dir(target) / "active.json", {
            "snapshot_commit": "unversioned", "fingerprint": "ticket-check", "mode": "full",
            "phases": ["bug_validation"], "current_phase": "bug_validation",
        })
        (target / "calc.py").write_text("def inc(value):\n    return value + 1\n", encoding="utf-8")
        (target / "caller.py").write_text("from calc import inc\ndef call(value):\n    return inc(value)\n", encoding="utf-8")
        (target / "Makefile").write_text("all:\n\tpython3 -m py_compile calc.py\n", encoding="utf-8")
        test = target / "tests/test_calc.py"
        test.parent.mkdir()
        test.write_text("raise AssertionError('unpermitted test oracle')\n", encoding="utf-8")
        entries = [
            {"id": "calc.py::inc", "path": "calc.py", "artifact": "calc-inc-1.py", "language": "python"},
            {"id": "caller.py::call", "path": "caller.py", "artifact": "caller-call-1.py", "language": "python"},
        ]
        state.atomic_json(state.control_dir(target) / "analysis_index.json", {
            "schema_version": 2, "snapshot_commit": "unversioned", "functions": entries,
        })
        for entry in entries:
            artifact = state.fm_dir(target) / "extracted_functions" / entry["artifact"]
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text((target / entry["path"]).read_text(), encoding="utf-8")
            state.atomic_json(Path(f"{artifact}.spec.json"), {"signature": entry["id"], "pre_condition": "value is an integer", "post_condition": "returns value + 2"})
            state.atomic_json(Path(f"{artifact}.info.json"), {"callees": []})
        state.atomic_json(state.control_dir(target) / "graph_edges.json", {
            "edges": [{"caller_artifact": "caller-call-1.py", "callee_artifact": "calc-inc-1.py"}],
        })
        state.atomic_json(state.fm_dir(target) / "logic_verification_results/calc-inc-1.json", verification_result(function_id="calc.py::inc", snapshot_commit="unversioned", verdict="MISMATCH", reasoning={"actual_postcondition": "returns value + 1", "spec_postcondition": "returns value + 2",
                          "counterexample": "value=0 returns 1 instead of 2", "offending_statements": "return value + 1", "reason": "The return differs from the required value"}))
        job = scheduler.create(target, {
            "id": "bug-validation-candidate", "type": "bug_validate", "phase": "bug_validation",
            "depends_on": [], "artifacts": [], "required_outputs": ["fm_agent/bug_validation/candidate.result.json"],
            "input": {"candidate_id": state.candidate_id("calc.py::inc"), "bug_id": "candidate", "function_id": "calc.py::inc", "mode": "full"},
        })
        return scheduler.transition(target, job["id"], "start", None, None, "execution")

    def execution(self, target: Path) -> Path:
        root = bug_validation_executor.attempt_dir(target, "candidate", 1)
        entry = {"ecosystem": "host-project-toolchain", "kind": "module", "target": "calc.py", "symbol": "inc"}
        state.atomic_json(root / "reproduction.json", {"function_id": "calc.py::inc", "candidate_id": state.candidate_id("calc.py::inc"),
            "schema_version": 3, "bug_id": "candidate", "attempt": 1, "snapshot_commit": "unversioned",
            "language": "python", "public_entrypoint": entry, "probe_file": "probe.py", "timeout_seconds": 30,
            "expected_marker": "CONFIRMED", "not_confirmed_marker": "NOT CONFIRMED",
        })
        (root / "probe.py").write_text('print("CONFIRMED")\n', encoding="utf-8")
        state.atomic_json(root / "reproduction_result.json", {"function_id": "calc.py::inc", "candidate_id": state.candidate_id("calc.py::inc"),
            "schema_version": 2, "execution_mode": "agent-executed", "bug_id": "candidate", "attempt": 1,
            "snapshot_commit": "unversioned", "language": "python", "public_entrypoint": entry,
            "state": "completed", "classification": "confirmed", "reason": "The recorded probe contradicted the contract",
            "commands": [{"command": "python3 probe.py", "cwd": root.relative_to(target).as_posix(), "returncode": 0,
                          "stdout": "CONFIRMED\n", "stderr": ""}],
        })
        return root

    def test_each_pass_persists_complete_fresh_worker_ticket(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job = self.prepare(target)
            preparation = bug_validation_executor.worker_request(target, job, "preparation", "codex")
            self.assertEqual(preparation["required_outputs"], [
                "fm_agent_skill/probes/candidate/attempt_001/reproduction.json", "fm_agent_skill/probes/candidate/attempt_001/probe.py",
            ])
            self.assertIn("calc.py", preparation["read_paths"])
            self.assertIn("caller.py", preparation["read_paths"])
            self.assertIn("fm_agent/logic_verification_results/calc-inc-1.json", preparation["read_paths"])
            self.assertIn("Makefile", preparation["read_paths"])
            root = self.execution(target)
            execution = bug_validation_executor.worker_request(target, job, "execution", "codex")
            self.assertEqual(execution["public_entrypoint"]["target"], "calc.py")
            self.assertIn(root.relative_to(target).as_posix() + "/workspace/", execution["write_paths"])
            self.assertNotIn("fm_agent/logic_verification_results/calc-inc-1.json", execution["read_paths"])
            finalization = bug_validation_executor.worker_request(target, job, "finalization", "codex")
            self.assertEqual(finalization["required_outputs"], job["required_outputs"])
            self.assertEqual(finalization["write_paths"], ["fm_agent/bug_validation/candidate.result.json", "fm_agent/bug_validation/candidate.md"])
            self.assertIn((root / "reproduction_result.json").relative_to(target).as_posix(), finalization["read_paths"])
            self.assertNotIn("calc.py", finalization["read_paths"])
            for ticket in (preparation, execution, finalization):
                persisted = state.read_json(target / ticket["ticket_path"], {})
                self.assertEqual(persisted, {key: value for key, value in ticket.items() if key != "ticket_path"})
                self.assertEqual(ticket["project"], str(target))
                self.assertEqual(ticket["function_id"], "calc.py::inc")
                self.assertEqual(ticket["language"], "python")
                self.assertEqual(ticket["job_manifest"], "fm_agent_skill/jobs/bug-validation-candidate.json")
                self.assertIn(ticket["job_manifest"], ticket["read_paths"])
                self.assertEqual(ticket["host_invocation"]["native_launch_arguments"], {"fork_turns": "none"})
                self.assertTrue(Path(ticket["worker_definition"]).is_file())
                self.assertNotIn("tests/test_calc.py", ticket["read_paths"])
                self.assertFalse(any("<language" in path for path in ticket["required_outputs"]))
                self.assertFalse(any(path.startswith("fm_agent_skill/control/") for path in ticket["write_paths"]))

    def test_missing_preparation_or_execution_evidence_cannot_issue_an_incomplete_ticket(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job = self.prepare(target)
            state.control_dir(target).joinpath("analysis_index.json").unlink()
            with self.assertRaisesRegex(ValueError, "source-index entry"):
                bug_validation_executor.worker_request(target, job, "preparation", "codex")
            root = self.execution(target)
            (root / "reproduction_result.json").unlink()
            with self.assertRaisesRegex(ValueError, "recorded execution result"):
                bug_validation_executor.worker_request(target, job, "finalization", "codex")

    def test_preparation_can_discover_public_exports_from_neutral_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job = self.prepare(target)
            source_parent = target / "selected"
            source_parent.mkdir()
            (source_parent / "calc.py").write_text((target / "calc.py").read_text(), encoding="utf-8")
            (target / "README.md").write_text("The public package is native/public_calc; use PYTHONPATH=native.\n", encoding="utf-8")
            (source_parent / "README.md").write_text("This selection preserves the public module implementation.\n", encoding="utf-8")
            initializer = target / "native/public_calc/__init__.py"
            initializer.parent.mkdir(parents=True)
            initializer.write_text("from .calc import inc\n", encoding="utf-8")
            (target / "native/pyproject.toml").write_text('[project]\nname = "public-calc"\n', encoding="utf-8")
            answers = target / "docs/answers.md"
            answers.parent.mkdir()
            answers.write_text("Unpermitted answer document\n", encoding="utf-8")
            (target / "tests/__init__.py").write_text("# test metadata\n", encoding="utf-8")
            index_path = state.control_dir(target) / "analysis_index.json"
            index = state.read_json(index_path, {})
            index["functions"][0]["path"] = "selected/calc.py"
            state.atomic_json(index_path, index)
            ticket = bug_validation_executor.worker_request(target, job, "preparation", "codex")
            for path in ("README.md", "selected/README.md", "native/public_calc/__init__.py", "native/pyproject.toml"):
                self.assertIn(path, ticket["read_paths"])
            self.assertNotIn("docs/answers.md", ticket["read_paths"])
            self.assertNotIn("tests/__init__.py", ticket["read_paths"])


if __name__ == "__main__":
    unittest.main()
