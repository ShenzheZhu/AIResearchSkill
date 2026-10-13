#!/usr/bin/env python3
"""Deterministic incremental selection, propagation, retention and dispatch checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from fm_agent_core import state
from result_fixture import verification_result
import config
import durable_executor
import executor
import incremental
import job_planner
import orchestrate
import phase_driver
import scheduler
import semantic_executor
import stage_gate
import locking
import isolation
from test_accepted_bug_evidence import write_accepted_candidate


class IncrementalNativeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.target = Path(self.temporary.name).resolve()
        self.git("init", "-q")
        self.git("config", "user.name", "Unit fixture")
        self.git("config", "user.email", "unit@example.invalid")
        sources = {
            "app.py": "from helper import helper\nfrom stable import stable\nfrom leaf import leaf\ndef app(x):\n    return helper(x) + stable(x) + leaf(x)\n",
            "helper.py": "def helper(x):\n    return x + 1\n",
            "stable.py": "RATE = 1\ndef stable(x):\n    return x * RATE\n",
            "leaf.py": "def leaf(x):\n    return x\n",
        }
        for path, text in sources.items():
            (self.target / path).write_text(text)
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")
        self.baseline = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/fm-agent-skill/baseline", self.baseline)
        settings = dict(config.DEFAULTS)
        fingerprint, inputs = state.fingerprint_for_config(self.target, settings)
        self.settings = settings
        state.atomic_json(state.skill_dir(self.target) / "active.json", {
            "status": "succeeded", "mode": "full", "snapshot_commit": self.baseline,
            "fingerprint": fingerprint, "inputs": inputs,
        })
        state.atomic_json(state.fm_dir(self.target) / "phases.json", {"phases": [{
            "phase": 1, "name": "Fixture", "depends_on_phases": [],
            "modules": [{"name": "app", "source_files": list(sources)}],
        }]})
        executor.extract(self.target, [])
        self.index = incremental.functions(self.target)
        for function_id, item in self.index.items():
            artifact = self.artifact(function_id)
            spec = {"signature": function_id.split("::")[-1] + "(x)", "pre_condition": "x is an integer", "post_condition": "returns the established integer result"}
            info = {"callees": []}
            if function_id == "app.py::app":
                info["callees"] = [dict(name=name, signature=f"{name}(x)", pre_condition="x is an integer", post_condition="returns the established integer result") for name in ("helper", "stable", "leaf")]
            state.atomic_json(Path(f"{artifact}.spec.json"), spec)
            state.atomic_json(Path(f"{artifact}.info.json"), info)
            state.atomic_json(self.result(function_id), verification_result(function_id=function_id, snapshot_commit=self.baseline,
                verdict="MATCH", reasoning={"actual_postcondition": "returns the established integer result",
                    "spec_postcondition": spec["post_condition"], "counterexample": None,
                    "offending_statements": None, "reason": "Deterministic retained-result fixture"}, gaps=None, error=None))
        self.edges = [{"caller_artifact": self.index["app.py::app"]["artifact"], "callee_artifact": self.index[f"{name}.py::{name}"]["artifact"]} for name in ("helper", "stable", "leaf")]
        state.atomic_json(state.control_dir(self.target) / "agent_static_edges.json", {"edges": self.edges})
        executor.graph(self.target)
        state.atomic_json(state.skill_dir(self.target) / "baseline.json", {
            "schema_version": 5, "baseline_commit": self.baseline, "fingerprint": fingerprint,
            "run_fingerprint": fingerprint, "inputs": inputs, "source_manifest": state.source_manifest(self.target), "completed_at": state.now(),
        })

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.target), *args], text=True, capture_output=True, check=True).stdout.strip()

    def artifact(self, function_id):
        return state.fm_dir(self.target) / "extracted_functions" / self.index[function_id]["artifact"]

    def result(self, function_id):
        return state.fm_dir(self.target) / "logic_verification_results" / Path(self.index[function_id]["artifact"]).with_suffix(".json")

    def prepare(self, intent="change helper result"):
        record = state.active_record(self.target)
        record.update(status="running", mode="incremental", snapshot_commit=self.git("rev-parse", "HEAD"), current_phase="update_specs", phases=state.PHASES["incremental"])
        settings = dict(self.settings, incremental_intent=intent)
        record["fingerprint"], record["inputs"] = state.fingerprint_for_config(self.target, settings)
        state.atomic_json(state.skill_dir(self.target) / "active.json", record)
        executor.preserve_specs(self.target)
        executor.extract(self.target, [])
        executor.diff(self.target)
        executor.restore_specs(self.target)
        self.index = incremental.functions(self.target)
        state.atomic_json(state.control_dir(self.target) / "graph_edges.json", {"edges": [edge for edge in self.edges if edge["callee_artifact"] in {item["artifact"] for item in self.index.values()}]})
        executor.select(self.target)
        selected = self.target / "fm_agent/relevant_files.json"
        state.atomic_json(selected, {"selected_function_ids": ["app.py::app"], "excluded_function_ids": sorted(set(self.index) - {"app.py::app"})})
        incremental.merge_selection(self.target, selected, "intent")
        return record

    def plan(self, function_id, spec=None, info=None):
        artifact = self.artifact(function_id)
        path = self.target / "fm_agent/fixture_plan.json"
        pair = {"spec": spec or state.read_json(Path(f"{artifact}.spec.json"), {}), "info": info or state.read_json(Path(f"{artifact}.info.json"), {})}
        state.atomic_json(path, {"sidecar_updates": {self.index[function_id]["artifact"]: pair}})
        return incremental.apply_plan(self.target, path, [self.index[function_id]["artifact"]])

    def test_changed_global_and_deleted_callee_invalidate_while_unrelated_origin_survives(self):
        stable_body = self.artifact("stable.py::stable").read_bytes()
        leaf_artifact = self.index["leaf.py::leaf"]["artifact"]
        untouched = self.result("helper.py::helper").read_bytes()
        (self.target / "stable.py").write_text("RATE = 2\ndef stable(x):\n    return x * RATE\n")
        (self.target / "leaf.py").unlink()
        self.git("add", "-u")
        self.git("commit", "-qm", "global and deletion")
        self.prepare()
        decision = incremental.decision(self.target)
        self.assertEqual(self.artifact("stable.py::stable").read_bytes(), stable_body)
        self.assertIn("stable.py::stable", decision["included"])
        self.assertIn("app.py::app", decision["included"])
        self.assertFalse(self.result("stable.py::stable").exists())
        self.assertFalse((state.fm_dir(self.target) / "logic_verification_results" / Path(leaf_artifact).with_suffix(".json")).exists())
        self.assertEqual(self.result("helper.py::helper").read_bytes(), untouched)
        retained = state.retained_function(self.target, "helper.py::helper")
        self.assertEqual(retained["verification_snapshot_commit"], self.baseline)
        self.assertEqual(retained["verification_bytes"].encode(), untouched)

    def test_relevant_unchanged_pair_is_reviewed_without_reverification(self):
        before = {suffix: Path(f"{self.artifact('app.py::app')}{suffix}").read_bytes() for suffix in (".spec.json", ".info.json")}
        proof = self.result("app.py::app").read_bytes()
        self.prepare()
        result = self.plan("app.py::app")
        self.assertEqual(result["applied"], 0)
        decision = incremental.decision(self.target)
        self.assertIn("app.py::app", decision["reviewed"])
        self.assertNotIn("app.py::app", decision["included"])
        self.assertEqual(self.result("app.py::app").read_bytes(), proof)
        self.assertEqual(before, {suffix: Path(f"{self.artifact('app.py::app')}{suffix}").read_bytes() for suffix in before})
        self.assertIsNotNone(state.retained_function(self.target, "app.py::app"))

    def test_sidecar_changes_propagate_only_actual_expectations_and_direct_dependents(self):
        self.prepare()
        app = self.artifact("app.py::app")
        info = state.read_json(Path(f"{app}.info.json"), {})
        info["callees"][0]["post_condition"] = "returns x plus two"
        self.plan("app.py::app", info=info)
        decision = incremental.decision(self.target)
        self.assertIn("helper.py::helper", decision["pending_review"])
        self.assertNotIn("stable.py::stable", decision["pending_review"])
        helper_spec = state.read_json(Path(f"{self.artifact('helper.py::helper')}.spec.json"), {})
        helper_spec["post_condition"] = "returns x plus two"
        self.plan("helper.py::helper", spec=helper_spec)
        decision = incremental.decision(self.target)
        self.assertEqual(set(decision["included"]), {"app.py::app", "helper.py::helper"})
        self.assertEqual(set(decision["pending_reconcile"]), {"app.py::app"})
        self.assertNotIn("leaf.py::leaf", decision["review"])
        self.assertIsNotNone(state.retained_function(self.target, "stable.py::stable"))
        self.assertFalse(self.result("helper.py::helper").exists())

    def test_same_snapshot_new_precondition_invalidates_and_early_verification_is_refused(self):
        record = self.prepare()
        spec = state.read_json(Path(f"{self.artifact('app.py::app')}.spec.json"), {})
        spec["pre_condition"] = "x must be positive"
        self.plan("app.py::app", spec=spec)
        self.assertFalse(self.result("app.py::app").exists())
        self.assertIsNone(state.retained_function(self.target, "app.py::app"))
        with self.assertRaisesRegex(ValueError, "converge"):
            job_planner._verification(self.target, record, "verify_affected")
        with self.assertRaisesRegex(ValueError, "earliest incomplete"):
            semantic_executor._active(self.target, "verify_affected")

    def test_planner_top_down_frontier_and_fresh_ticket_carry_latest_intent(self):
        record = self.prepare("Newest goal overrides the former helper policy.")
        artifact = self.index["app.py::app"]["artifact"]
        state.atomic_json(state.fm_dir(self.target) / "spec_prompts/phase_01_topdown_layers.json", {
            "phase": 1, "layers": [{"layer": 1, "functions": [{"artifact": artifact}]}],
        })
        state.atomic_json(state.control_dir(self.target) / "incremental_decision.json", dict(incremental.decision(self.target), sidecars_restored=True))
        with patch.object(state, "phase_layers_ready", return_value=(True, "")), patch.object(scheduler, "current_jobs_for_phase", return_value=[{"id": "context-fixture", "type": "domain_context", "status": "succeeded"}]):
            job_planner._update_specs(self.target, record, "update_specs")
        jobs = scheduler.current_jobs_for_phase(self.target, "update_specs")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["type"], "incremental_spec_plan")
        self.assertEqual(jobs[0]["artifacts"], [artifact])
        claimed = durable_executor.claim(self.target, jobs[0]["id"], "codex")
        ticket = state.read_json(self.target / claimed["ticket_path"], {})
        self.assertEqual(ticket["developer_intent"], record["inputs"]["config"]["incremental_intent"])
        self.assertEqual(ticket["host_invocation"]["native_launch_arguments"], {"fork_turns": "none"})
        self.assertEqual(ticket["write_paths"], [f"fm_agent_skill/worker_reports/{jobs[0]['id']}.json"])
        self.assertIn(scheduler._run_id(self.target)[0], jobs[0]["id"])
        self.assertNotIn("verify_affected", {job["phase"] for job in scheduler.current_jobs_for_phase(self.target, "verify_affected")})

    def test_resume_reuses_sealed_baseline_validation_after_diff_replaces_old_proofs(self):
        (self.target / "stable.py").write_text("RATE = 2\ndef stable(x):\n    return x * RATE\n")
        self.git("add", "stable.py")
        self.git("commit", "-qm", "changed global")
        record = state.active_record(self.target)
        record.update(status="running", mode="incremental", snapshot_commit=self.git("rev-parse", "HEAD"))
        settings = dict(self.settings, incremental_intent="update the rate")
        record["fingerprint"], record["inputs"] = state.fingerprint_for_config(self.target, settings)
        state.atomic_json(state.skill_dir(self.target) / "active.json", record)
        self.assertTrue(executor.validate_baseline(self.target)["ok"])
        self.prepare("update the rate")
        self.assertFalse(self.result("stable.py::stable").exists())
        self.assertTrue(stage_gate.baseline_ready(self.target, []))
        record = state.active_record(self.target)
        record.update(status="interrupted", current_phase="update_specs", phase_status={name: {"status": "succeeded"} for name in record["phases"][:6]})
        state.atomic_json(state.skill_dir(self.target) / "active.json", record)
        locking.acquire(self.target)
        resumed = phase_driver._pipeline(self.target, "resume")
        self.assertEqual(resumed["current_phase"], "update_specs")
        receipt = state.read_json(state.control_dir(self.target) / "baseline_validation.json", {})
        receipt["baseline"]["completed_at"] = "changed"
        state.atomic_json(state.control_dir(self.target) / "baseline_validation.json", receipt)
        self.assertFalse(stage_gate.baseline_ready(self.target, []))

    def test_reconciliation_retry_compares_initial_pair_after_partial_sidecar_write(self):
        self.prepare()
        app = self.artifact("app.py::app")
        before = {"spec": state.read_json(Path(f"{app}.spec.json"), {}), "info": state.read_json(Path(f"{app}.info.json"), {})}
        changed = json.loads(json.dumps(before["info"]))
        changed["callees"][0]["post_condition"] = "returns x plus two"
        state.atomic_json(Path(f"{app}.info.json"), changed)
        result = incremental.reconcile(self.target, {"id": "retry-fixture", "input": {"function_id": "app.py::app"}}, before)
        self.assertEqual(result["artifacts"], [self.index["app.py::app"]["artifact"]])
        self.assertIn("helper.py::helper", incremental.decision(self.target)["pending_review"])
        self.assertNotIn("stable.py::stable", incremental.decision(self.target)["pending_review"])

    def test_completed_identical_intent_is_noop_but_new_goal_is_incremental(self):
        args = argparse.Namespace(note="new helper goal", incremental=None, submodules=[], knowledge=[], extra_edge=None,
                                  one_phase=False, codegraph=False, all_bugs=None)
        self.assertEqual(orchestrate.inspect(self.target, args)["mode"], "incremental")
        baseline = state.read_json(state.skill_dir(self.target) / "baseline.json", {})
        baseline["inputs"]["config"]["incremental_intent"] = args.note
        state.atomic_json(state.skill_dir(self.target) / "baseline.json", baseline)
        self.assertEqual(orchestrate.inspect(self.target, args)["mode"], "noop")
        args.note = "a newer goal"
        self.assertEqual(orchestrate.inspect(self.target, args)["mode"], "incremental")

    def test_module_selector_can_inspect_unchanged_source_and_contracts(self):
        record = self.prepare("change a shared business policy")
        job_planner._select_scope(self.target, record, "select_scope")
        job = scheduler.current_jobs_for_phase(self.target, "select_scope")[0]
        allowed = set(semantic_executor._read_paths(self.target, job))
        self.assertIn("app.py", allowed)
        self.assertIn("stable.py", allowed)
        for suffix in ("", ".spec.json", ".info.json"):
            self.assertIn(f"fm_agent/extracted_functions/{self.index['app.py::app']['artifact']}{suffix}", allowed)

    def test_on_demand_uses_original_uncommitted_baseline_and_preserves_run_inputs(self):
        (self.target / "stable.py").write_text("RATE = 2\ndef stable(x):\n    return x * RATE\n")
        initial = isolation.create(self.target)
        origin = initial["snapshot_commit"]
        self.git("update-ref", "refs/fm-agent-skill/baseline", origin)
        isolation.discard(Path(initial["snapshot"]))
        baseline = state.read_json(state.skill_dir(self.target) / "baseline.json", {})
        baseline["baseline_commit"] = origin
        settings = dict(self.settings, incremental_intent="original incrementally analyzed goal")
        baseline["run_fingerprint"], baseline["inputs"] = state.fingerprint_for_config(self.target, settings)
        state.atomic_json(state.skill_dir(self.target) / "baseline.json", baseline)
        (self.target / "README.md").write_text("Later documentation only.\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "later docs")
        source_head = self.git("rev-parse", "HEAD")
        checked = {"ok": True, "function_id": "helper.py::helper", "candidate_id": state.candidate_id("helper.py::helper"),
                   "baseline_commit": origin, "config": self.settings}
        with patch.object(orchestrate, "validate_inspect", return_value=checked):
            dispatched = orchestrate.validate_dispatch(self.target, "helper.py::helper")
        snapshot = Path(dispatched["project"])
        try:
            self.assertEqual(state.current_snapshot_commit(snapshot), origin)
            self.assertEqual(isolation.marker(snapshot)["snapshot_commit"], origin)
            self.assertEqual(state.active_record(snapshot)["inputs"], baseline["inputs"])
            self.assertEqual(state.active_record(snapshot)["fingerprint"], baseline["run_fingerprint"])
            self.assertEqual(self.git("rev-parse", "HEAD"), source_head)
            self.assertEqual((self.target / "stable.py").read_text(), "RATE = 2\ndef stable(x):\n    return x * RATE\n")
        finally:
            isolation.discard(snapshot)

    def test_targeted_completion_never_promotes_a_partial_candidate_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            job = write_accepted_candidate(target)
            record = state.active_record(target)
            record.update(status="running", validation_scope=[job["input"]["candidate_id"]], validation_job_id=job["id"])
            state.atomic_json(state.skill_dir(target) / "active.json", record)
            with patch.object(phase_driver, "_pipeline", side_effect=AssertionError("targeted validation cannot promote a full baseline")):
                action = phase_driver.next_step(target, 1, "codex")
            self.assertEqual(action["action"], "validation_ready_to_publish")
            self.assertEqual(action["argv"][-3:], ["validate-complete", "--project", str(target)])

    def test_resume_rejects_explicit_all_bugs_change_but_inherits_omission(self):
        args = argparse.Namespace(note="", incremental=None, submodules=[], knowledge=[], extra_edge=None, one_phase=False, codegraph=False, all_bugs=True)
        checked = {"ok": True, "config": {"all_bugs": False}}
        marker = {"snapshot": str(self.target)}
        with patch.object(orchestrate, "snapshot_marker", return_value=marker), patch.object(orchestrate, "_active_ref", return_value=self.baseline), patch.object(state, "inspect_resume", return_value=checked):
            result = orchestrate.resume_plan(self.target, args)
            self.assertIn("all-bugs", result["reason"])
            args.all_bugs = None
            self.assertTrue(orchestrate.resume_plan(self.target, args)["ok"])


if __name__ == "__main__": unittest.main()
