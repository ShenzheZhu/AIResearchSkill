"""Independent candidates, complete loop obligations and immutable origin reuse."""
from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from fm_agent_core import loop_evidence, state
import bug_summary
import scheduler
import stage_gate
import terminal_report
from result_fixture import verification_result
from test_accepted_bug_evidence import write_accepted_candidate


class CandidatesLoopsReuseTest(unittest.TestCase):
    def test_each_same_function_candidate_needs_its_own_accepted_outcome(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            first = write_accepted_candidate(target, bug_id="first", status="confirmed")
            second = write_accepted_candidate(target, bug_id="second", status="rejected", candidate_ordinal=2)
            third = write_accepted_candidate(target, bug_id="third", status="inconclusive", candidate_ordinal=3)
            candidates = state.direct_candidates(target)
            self.assertEqual(len(candidates), 3)
            self.assertEqual({item["function_id"] for item in candidates.values()}, {"calc.py::inc"})
            self.assertTrue(state.semantic_job_plan_ready(target, "bug_validation", candidate_ids=set(candidates))[0])
            summary = bug_summary.write_summary(target, "full")
            self.assertEqual([summary[f"total_{status}"] for status in ("confirmed", "rejected", "inconclusive")], [1, 1, 1])
            findings = terminal_report._bug_results(target, "unversioned", set(candidates))
            self.assertEqual({item["candidate_id"] for item in findings}, set(candidates))
            self.assertEqual([job["status"] for job in (first, second, third)], ["succeeded"] * 3)
            path = target / second["bug_result_path"]
            report = state.read_json(path, {})
            report["candidate_id"] = first["input"]["candidate_id"]
            state.atomic_json(path, report)
            with self.assertRaisesRegex(ValueError, "candidate identity"):
                state.accepted_candidate(target, second["input"]["candidate_id"])

    def test_partial_legacy_and_duplicate_reasoning_do_not_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            write_accepted_candidate(target)
            entry = state.source_index(target)["functions"][0]
            artifact = state.fm_dir(target) / "extracted_functions" / entry["artifact"]
            path = state.fm_dir(target) / "logic_verification_results" / Path(entry["artifact"]).with_suffix(".json")
            result = state.read_json(path, {})
            self.assertTrue(state.verification_result_ready(target, artifact, entry["id"], result)[0])
            for changed in ({**result, "schema_version": 2}, {**result, "reasoning_complete": False}):
                self.assertFalse(state.verification_result_ready(target, artifact, entry["id"], changed)[0])
            state.atomic_json(state.skill_dir(target) / "config.json", {"all_bugs": True})
            duplicate = copy.deepcopy(result)
            duplicate["candidates"].append({"candidate_id": state.candidate_id(entry["id"], 2), "reasoning": duplicate["reasoning"]})
            self.assertIn("independent", state.verification_result_ready(target, artifact, entry["id"], duplicate)[1])

    def test_loop_induction_and_nested_abrupt_exits_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            artifact = state.fm_dir(target) / "extracted_functions" / "sum.py"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("def collect(values):\n    total = 0\n    for value in values:\n        while value > 0:\n            if value == 2:\n                return total\n            value -= 1\n            if value == 1:\n                break\n        if value == 0:\n            continue\n        total += value\n    return total\n")
            state.atomic_json(Path(f"{artifact}.spec.json"), {"signature": "collect(values)", "pre_condition": "values contains nonnegative integers", "post_condition": "returns the sum of processed values"})
            state.atomic_json(Path(f"{artifact}.info.json"), {"callees": []})
            parsed = loop_evidence.inventory(artifact)
            self.assertIsNone(parsed["gap"])
            self.assertEqual(len(parsed["loops"]), 2)
            self.assertEqual([len(loop["abrupt_exits"]) for loop in parsed["loops"]], [2, 2])
            result = verification_result("sum.py::collect", "unversioned", "MATCH", reasoning={"actual_postcondition": "returns the sum of processed values", "spec_postcondition": "returns the sum of processed values", "counterexample": None, "offending_statements": None, "reason": "Every reachable exit was considered"})
            self.assertFalse(state.verification_result_ready(target, artifact, result["function_id"], result)[0])
            result["loop_evidence"] = [{"loop_id": loop["loop_id"], "invariant": "total describes the processed prefix", "initialization": "The empty prefix has total zero", "preservation": "Each body step preserves the stated prefix relation", "normal_exit": "Exhaustion establishes the required final relation", "abrupt_exits": [{"exit_id": exit["exit_id"], "argument": "This exact exit preserves the required downstream relation"} for exit in loop["abrupt_exits"]]} for loop in parsed["loops"]]
            self.assertTrue(state.verification_result_ready(target, artifact, result["function_id"], result)[0])
            for key in ("initialization", "preservation", "normal_exit"):
                incomplete = copy.deepcopy(result)
                incomplete["loop_evidence"][0][key] = ""
                self.assertFalse(state.verification_result_ready(target, artifact, result["function_id"], incomplete)[0])
            result["loop_evidence"][0]["abrupt_exits"].pop()
            self.assertFalse(state.verification_result_ready(target, artifact, result["function_id"], result)[0])

    def test_tree_sitter_inventory_and_unavailable_parser_cannot_claim_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "loop.ts"
            path.write_text("export function collect(xs: number[]) { let total = 0; for (const x of xs) { if (x < 0) break; total += x; } return total; }\n")
            parsed = loop_evidence.inventory(path)
            self.assertIsNone(parsed["gap"])
            self.assertEqual(len(parsed["loops"]), 1)
            self.assertEqual(len(parsed["loops"][0]["abrupt_exits"]), 1)
            with patch.object(loop_evidence, "_tree_sitter_language", return_value=None):
                self.assertIn("unavailable", loop_evidence.inventory(path)["gap"])

    def test_comprehension_clauses_and_nested_callable_ownership(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "clauses.py"
            path.write_text("async def collect(xs):\n    if xs:\n        async def inner():\n            async for x in xs:\n                return x\n    values = [x + y for x in xs for y in xs if y > 0]\n    names = {x for x in xs}\n    mapping = {x: x + 1 for x in xs}\n    lazy = (x for x in xs)\n    return values, names, mapping, lazy\n")
            parsed = loop_evidence.inventory(path)
            self.assertIsNone(parsed["gap"])
            self.assertEqual(len(parsed["loops"]), 5)
            self.assertEqual([row["generator_index"] for row in parsed["loops"]], [1, 2, 1, 1, 1])
            self.assertEqual([row["abrupt_exits"] for row in parsed["loops"]], [[]] * 5)
            path.write_text("async def inner(xs):\n    async for x in xs:\n        if x:\n            return x\n    return None\n")
            self.assertEqual(len(loop_evidence.inventory(path)["loops"]), 1)
            path.write_text("async def stream(xs):\n    return [x async for x in xs]\n")
            self.assertTrue(loop_evidence.inventory(path)["loops"][0]["asynchronous"])

    def test_go_labeled_break_is_an_outer_and_inner_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested.go"
            path.write_text("package fixture\nfunc collect(xs []int) int { outer: for _, x := range xs { for x > 0 { if x == 1 { break outer }; return x } }; return 0 }\n")
            parsed = loop_evidence.inventory(path)
            self.assertIsNone(parsed["gap"])
            self.assertEqual(len(parsed["loops"]), 2)
            self.assertEqual([len(loop["abrupt_exits"]) for loop in parsed["loops"]], [2, 2])
            self.assertEqual(parsed["loops"][0]["abrupt_exits"][0]["statement"], "break outer")

    def test_registered_grammars_cover_range_loops_and_detached_methods(self):
        cases = {
            ".cpp": "int sum(int* xs) { int total = 0; for (int x : {1, 2}) { total += x; } return total; }",
            ".java": "public int sum(int[] xs) { int total = 0; for (int x : xs) { total += x; } return total; }",
            ".ts": "async sum(xs: number[]) { let total = 0; for (const x of xs) { total += x; } return total; }",
            ".c": "int sum(int* xs) { int i = 0; do { i++; } while (i < 2); return i; }",
            ".rs": "fn sum(xs: &[i32]) -> i32 { let mut total = 0; for x in xs { total += x; } total }",
        }
        for extension, source in cases.items():
            with self.subTest(extension=extension), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / f"source{extension}"
                path.write_text(source)
                parsed = loop_evidence.inventory(path)
                self.assertIsNone(parsed["gap"])
                self.assertEqual(len(parsed["loops"]), 1)

    def git(self, target, *arguments):
        return subprocess.run(["git", "-C", str(target), *arguments], check=True, text=True, capture_output=True).stdout.strip()

    def test_retained_bytes_need_origin_input_and_accepted_receipt_qualification(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            self.git(target, "init", "-q")
            self.git(target, "config", "user.name", "Fixture")
            self.git(target, "config", "user.email", "fixture@example.invalid")
            (target / "calc.py").write_text("def inc(x):\n    return x + 1\n")
            (target / "other.py").write_text("def untouched():\n    return 1\n")
            self.git(target, "add", "calc.py", "other.py")
            self.git(target, "commit", "-qm", "baseline")
            job = write_accepted_candidate(target)
            origin = self.git(target, "rev-parse", "HEAD")
            state.atomic_json(state.skill_dir(target) / "baseline.json", {"baseline_commit": origin, "fingerprint": "receipt-check", "run_fingerprint": "receipt-check"})
            function = state.source_index(target)["functions"][0]
            artifact = state.fm_dir(target) / "extracted_functions" / function["artifact"]
            row = {"artifact": function["artifact"], "source_path": "calc.py", "source_blob": self.git(target, "rev-parse", f"{origin}:calc.py"), "spec": state.read_json(Path(f"{artifact}.spec.json"), {}), "info": {"callees": []}, "verification_snapshot_commit": origin, "verification_bytes": (state.fm_dir(target) / "logic_verification_results" / Path(function["artifact"]).with_suffix(".json")).read_bytes().decode("utf-8"), "bug_validations": [{"candidate_id": job["input"]["candidate_id"], "job_id": job["id"], "snapshot_commit": origin, "input_fingerprint": "receipt-check", "result_path": job["bug_result_path"]}]}
            before = {path: (target / path).read_bytes() for path in (job["bug_result_path"], f"fm_agent/logic_verification_results/{Path(function['artifact']).with_suffix('.json')}")}
            (target / "other.py").write_text("def untouched():\n    return 2\n")
            self.git(target, "add", "other.py")
            self.git(target, "commit", "-qm", "new unrelated source")
            current = self.git(target, "rev-parse", "HEAD")
            active = state.active_record(target)
            active.update(snapshot_commit=current, fingerprint="new-run")
            state.atomic_json(state.skill_dir(target) / "active.json", active)
            index = state.source_index(target)
            index["snapshot_commit"] = current
            state.atomic_json(state.control_dir(target) / "analysis_index.json", index)
            state.atomic_json(state.control_dir(target) / "job_plans/bug_validation.json", {"schema_version": 1, "phase": "bug_validation", "snapshot_commit": current, "entries": [], "created_jobs": 0, "total_entries": 0})
            self.assertEqual(state.direct_candidates(target), {})
            state.atomic_json(state.control_dir(target) / "retained_evidence.json", {"schema_version": 1, "snapshot_commit": current, "functions": {function["id"]: row}})
            self.assertEqual(state.accepted_candidate(target, job["input"]["candidate_id"])["id"], job["id"])
            self.assertEqual(bug_summary.write_summary(target, "incremental")["total_confirmed"], 1)
            self.assertEqual(scheduler.aggregate(target)["groups"], [])
            self.assertEqual(before, {path: (target / path).read_bytes() for path in before})
            result_path = state.fm_dir(target) / "logic_verification_results" / Path(function["artifact"]).with_suffix(".json")
            result_path.write_text(row["verification_bytes"] + " ")
            self.assertEqual(state.direct_candidates(target), {})
            result_path.write_bytes(row["verification_bytes"].encode())
            changed = dict(row["spec"], pre_condition="x must be positive")
            state.atomic_json(Path(f"{artifact}.spec.json"), changed)
            self.assertEqual(state.direct_candidates(target), {})
            state.atomic_json(Path(f"{artifact}.spec.json"), row["spec"])
            connection = scheduler._connect(target)
            connection.execute("DELETE FROM receipts WHERE job_id=?", (job["id"],))
            connection.close()
            with self.assertRaisesRegex(ValueError, "receipt"):
                state.accepted_candidate(target, job["input"]["candidate_id"])

    def test_mid_line_javascript_arrows_and_iifes_retain_exact_source_slices(self):
        for extracted in ("value => value + 1", "(() => { return 1; })()"):
            with self.subTest(extracted=extracted), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                self.git(target, "init", "-q")
                self.git(target, "config", "user.name", "Fixture")
                self.git(target, "config", "user.email", "fixture@example.invalid")
                (target / "callbacks.js").write_text(f"export const callback = {extracted}; export const other = 7;\n")
                (target / "other.py").write_text("def value(): return 1\n")
                self.git(target, "add", "callbacks.js", "other.py")
                self.git(target, "commit", "-qm", "baseline")
                origin = self.git(target, "rev-parse", "HEAD")
                function = {"id": "callbacks.js::callback", "path": "callbacks.js", "artifact": "callback.js", "line_start": 1, "line_end": 1}
                artifact = state.fm_dir(target) / "extracted_functions/callback.js"
                artifact.parent.mkdir(parents=True)
                artifact.write_text(extracted)
                spec = {"signature": "callback(value)", "pre_condition": "value is an integer", "post_condition": "returns the specified numeric result"}
                state.atomic_json(Path(f"{artifact}.spec.json"), spec)
                state.atomic_json(Path(f"{artifact}.info.json"), {"callees": []})
                verification = verification_result(function["id"], origin, "MATCH", reasoning={"actual_postcondition": spec["post_condition"], "spec_postcondition": spec["post_condition"], "counterexample": None, "offending_statements": None, "reason": "The expression establishes the required result"})
                result_path = state.fm_dir(target) / "logic_verification_results/callback.json"
                state.atomic_json(result_path, verification)
                row = {"artifact": function["artifact"], "source_path": function["path"], "source_blob": self.git(target, "rev-parse", f"{origin}:callbacks.js"), "spec": spec, "info": {"callees": []}, "verification_snapshot_commit": origin, "verification_bytes": result_path.read_bytes().decode(), "bug_validations": []}
                (target / "other.py").write_text("def value(): return 2\n")
                self.git(target, "add", "other.py")
                self.git(target, "commit", "-qm", "unrelated source")
                current = self.git(target, "rev-parse", "HEAD")
                state.atomic_json(state.control_dir(target) / "analysis_index.json", {"schema_version": 2, "snapshot_commit": current, "functions": [function]})
                state.atomic_json(state.control_dir(target) / "retained_evidence.json", {"schema_version": 1, "snapshot_commit": current, "functions": {function["id"]: row}})
                self.assertTrue(state.verification_result_ready(target, artifact, function["id"], verification)[0])
                artifact.write_text("value => value + 2")
                self.assertFalse(state.verification_result_ready(target, artifact, function["id"], verification)[0])


if __name__ == "__main__":
    unittest.main()
