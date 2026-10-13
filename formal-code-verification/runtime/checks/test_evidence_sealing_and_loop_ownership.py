"""Immutable dynamic attempts and execution ownership of parsed loops."""
from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from fm_agent_core import loop_evidence, state
import bug_summary
import bug_validation_executor as validator
import scheduler
from test_accepted_bug_evidence import write_accepted_candidate


class EvidenceSealingAndLoopOwnershipTest(unittest.TestCase):
    def test_accepted_probe_contract_and_execution_bytes_are_sealed(self):
        for case in ("probe", "contract", "command", "reason", "new_build_record"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                job = write_accepted_candidate(target)
                root = validator.attempt_dir(target, "candidate", 1)
                if case == "probe":
                    (root / "probe.py").write_text("print('NOT CONFIRMED')\n")
                elif case == "contract":
                    data = state.read_json(root / "reproduction.json", {})
                    data["timeout_seconds"] = 31
                    state.atomic_json(root / "reproduction.json", data)
                elif case == "new_build_record":
                    state.atomic_json(root / "build_result.json", {"state": "completed", "ok": True})
                else:
                    data = state.read_json(root / "reproduction_result.json", {})
                    if case == "command":
                        data["commands"][0]["command"] = "python3 another_unrecorded_probe.py"
                    else:
                        data["reason"] = "changed after acceptance"
                    state.atomic_json(root / "reproduction_result.json", data)
                with self.assertRaisesRegex(ValueError, "evidence bytes|output bytes"):
                    scheduler.accepted_job(target, job["id"], snapshot_commit="unversioned", input_fingerprint="receipt-check")
                with self.assertRaises(ValueError):
                    bug_summary.write_summary(target, "full")

    def prepare(self, target):
        state.atomic_json(state.skill_dir(target) / "active.json", {"snapshot_commit": "unversioned", "fingerprint": "seal-check", "phases": ["bug_validation"], "current_phase": "bug_validation"})
        (target / "calc.py").write_text("def inc(x): return x + 1\n")
        return scheduler.create(target, {"id": "candidate", "phase": "bug_validation", "type": "bug_validate", "required_outputs": ["fm_agent/bug_validation/candidate.result.json"], "artifacts": [], "negative_retries": 1, "input": {"bug_id": "candidate", "function_id": "calc.py::inc", "candidate_id": state.candidate_id("calc.py::inc"), "mode": "full"}})

    def attempt(self, target, job, number, value=1, unsupported=False):
        job = scheduler.transition(target, job["id"], "start", None, None, "execution")
        root = validator.attempt_dir(target, "candidate", number)
        entry = {"ecosystem": "host-project-toolchain", "kind": "module", "target": "calc.py", "symbol": "inc"}
        identity = {"bug_id": "candidate", "candidate_id": state.candidate_id("calc.py::inc"), "function_id": "calc.py::inc", "attempt": number, "snapshot_commit": "unversioned"}
        state.atomic_json(root / "reproduction.json", {"schema_version": 3, **identity, "language": "python", "public_entrypoint": entry, "probe_file": "probe.py", "expected_marker": "CONFIRMED", "not_confirmed_marker": "NOT CONFIRMED", "timeout_seconds": 30})
        probe = root / "probe.py"
        # The contract is x+2 at x=0 and x+1 otherwise; different legal probes
        # therefore give a genuine negative followed by a concrete violation.
        probe.write_text("import sys\nsys.path.insert(0,sys.argv[1])\nimport calc\n" + f"x={value}\nexpected=x+2 if x==0 else x+1\nprint('CONFIRMED' if calc.inc(x)!=expected else 'NOT CONFIRMED')\n")
        commands = []
        classification = "inconclusive"
        if not unsupported:
            result = subprocess.run([sys.executable, "-B", str(probe), str(target)], cwd=root, text=True, capture_output=True, check=True)
            classification = "confirmed" if result.stdout.startswith("CONFIRMED\n") else "not_reproduced"
            commands = [{"command": f"{sys.executable} -B {probe} {target}", "cwd": root.relative_to(target).as_posix(), "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}]
        path = root / "reproduction_result.json"
        state.atomic_json(path, {"schema_version": 2, **identity, "execution_mode": "agent-executed", "language": "python", "public_entrypoint": entry, "commands": commands, "state": "unsupported" if unsupported else "completed", "classification": classification, "reason": "Recorded execution outcome"})
        return job, {"ordinal": number, "classification": classification, "dynamic_evidence": {"reproduction_result": path.relative_to(target).as_posix()}}

    def report(self, target, job, attempts, status):
        state.atomic_json(target / job["bug_result_path"], {"schema_version": 2, "bug_id": "candidate", "candidate_id": job["input"]["candidate_id"], "function_id": job["input"]["function_id"], "snapshot_commit": "unversioned", "confirmation_status": status, "attempts": attempts})

    def test_genuine_negative_then_negative_or_confirmation_preserves_history(self):
        for second_value in (1, 0):
            with self.subTest(second_value=second_value), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                job = self.prepare(target)
                job, first = self.attempt(target, job, 1)
                root = validator.attempt_dir(target, "candidate", 1)
                state.atomic_json(root / "build_profile.json", {"adapter": "python"})
                state.atomic_json(root / "build_result.json", {"state": "completed", "ok": True})
                self.report(target, job, [first], "inconclusive")
                job = scheduler.transition(target, job["id"], "complete", validator.canonical_finalization_receipt(target, job), None, "execution")
                self.assertEqual(job["status"], "retryable")
                connection = scheduler._connect(target)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM receipts WHERE job_id=?", (job["id"],)).fetchone()[0], 1)
                connection.close()
                scheduler.transition(target, job["id"], "retry", None, None, "execution")
                job, second = self.attempt(target, job, 2, value=second_value)
                self.report(target, job, [first, second], "confirmed" if second_value == 0 else "rejected")
                job = scheduler.transition(target, job["id"], "complete", validator.canonical_finalization_receipt(target, job), None, "execution")
                self.assertEqual(job["status"], "succeeded")
                self.assertEqual(scheduler.accepted_job(target, job["id"], snapshot_commit="unversioned", input_fingerprint="seal-check")["validated_attempts"], [first, second])
                state.atomic_json(root / "build_result.json", {"state": "completed", "ok": False})
                with self.assertRaisesRegex(ValueError, "evidence bytes"):
                    scheduler.accepted_job(target, job["id"], snapshot_commit="unversioned", input_fingerprint="seal-check")

    def test_duplicate_dropped_or_rewritten_partial_outcomes_cannot_be_rejected(self):
        for case in ("duplicate", "drop", "rewrite_record"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                job = self.prepare(target)
                job, first = self.attempt(target, job, 1, unsupported=True)
                self.report(target, job, [first], "inconclusive")
                job = scheduler.transition(target, job["id"], "complete", validator.canonical_finalization_receipt(target, job), None, "execution")
                scheduler.transition(target, job["id"], "retry", None, None, "execution")
                job, second = self.attempt(target, job, 2)
                history = [second, copy.deepcopy(second)] if case == "duplicate" else [second] if case == "drop" else [first, second]
                self.report(target, job, history, "inconclusive" if case == "rewrite_record" else "rejected")
                if case == "rewrite_record":
                    path = validator.attempt_dir(target, "candidate", 1) / "reproduction_result.json"
                    data = state.read_json(path, {})
                    data["reason"] = "rewritten prior outcome"
                    state.atomic_json(path, data)
                receipt = validator.canonical_finalization_receipt(target, job)
                self.assertIsNotNone(scheduler._validate(target, job, receipt))
                self.assertNotEqual(scheduler.transition(target, job["id"], "complete", receipt, None, "execution")["status"], "succeeded")

    def test_another_job_cannot_reuse_an_immutable_probe_namespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job = write_accepted_candidate(target)
            with self.assertRaisesRegex(ValueError, "namespace"):
                scheduler.create(target, {"id": "another-job", "phase": "bug_validation", "type": "bug_validate", "required_outputs": ["fm_agent/bug_validation/another.result.json"], "artifacts": [], "input": {**job["input"], "candidate_id": state.candidate_id("calc.py::inc", 2)}})
            self.assertEqual(scheduler.accepted_job(target, job["id"], snapshot_commit="unversioned", input_fingerprint="receipt-check")["status"], "succeeded")

    def test_nested_python_definition_expressions_belong_to_the_owner(self):
        sources = (
            "def outer(xs):\n    def inner(default=[x for x in xs]):\n        return default\n    return inner()\n",
            "def outer(xs):\n    @decorate([x for x in xs])\n    def inner(value):\n        return value\n    return inner\n",
            "def outer(xs):\n    def inner(value: [x for x in xs]):\n        return value\n    return inner\n",
            "def outer(xs):\n    inner = lambda default=[x for x in xs]: default\n    return inner()\n",
        )
        for source in sources:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "source.PY"
                path.write_text(source)
                self.assertEqual(len(loop_evidence.inventory(path)["loops"]), 1)
                self.assertFalse(loop_evidence.ready(path, [])[0])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.py"
            path.write_text("def outer(default=[x for x in xs]):\n    return default\n")
            self.assertEqual(loop_evidence.inventory(path)["loops"], [])

    def test_nested_generator_and_closure_bodies_are_separate(self):
        sources = {
            ".js": "function* outer(xs) { function* inner() { for (const x of xs) { yield x; } } return inner; }",
            ".go": "package p\nfunc outer(xs []int) func() int { return func() int { for _, x := range xs { return x }; return 0 } }",
            ".rs": "fn outer(xs: Vec<i32>) -> impl Fn() -> i32 { move || { for x in &xs { return *x; } 0 } }",
        }
        for extension, source in sources.items():
            with self.subTest(extension=extension), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / f"source{extension}"
                path.write_text(source)
                self.assertEqual(loop_evidence.inventory(path), {"loops": [], "gap": None})

    def test_switch_break_and_labeled_block_targets_do_not_exit_outer_loop(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.js"
            path.write_text("function outer(xs) { for (const x of xs) { switch(x) { case 1: break; case 2: continue; } } }")
            parsed = loop_evidence.inventory(path)
            self.assertIsNone(parsed["gap"])
            self.assertEqual([item["statement"] for item in parsed["loops"][0]["abrupt_exits"]], ["continue;"])
            path.write_text("function outer(xs) { for (const x of xs) { block: { for (;;) { break block; } } } }")
            parsed = loop_evidence.inventory(path)
            self.assertEqual([len(loop["abrupt_exits"]) for loop in parsed["loops"]], [0, 1])
            path = Path(temporary) / "source.c"
            path.write_text("int outer() { for (;;) { goto done; } done: return 0; }")
            self.assertIn("goto", loop_evidence.inventory(path)["gap"])


if __name__ == "__main__":
    unittest.main()
