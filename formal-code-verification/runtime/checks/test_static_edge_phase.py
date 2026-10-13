#!/usr/bin/env python3
"""Static graphs require a semantic edge Worker before their phase can pass."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fm_agent_core import state
import executor
import phase_driver
import scheduler


class StaticEdgePhaseTest(unittest.TestCase):
    def test_extraction_keeps_requested_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            (target / "selected").mkdir()
            (target / "selected/calc.py").write_text("def selected():\n    return 1\n")
            (target / "unrelated.py").write_text("def unrelated():\n    return 2\n")
            action = phase_driver._deterministic_action(target, {"inputs": {"submodules": ["selected"]}}, "extraction")
            phase_driver._run_action(action)
            functions = state.read_json(state.fm_dir(target) / "extraction_manifest.json", {})["functions"]
            self.assertEqual([item["source_path"] for item in functions], ["selected/calc.py"])

    def prepare(self, target: Path, phase: str) -> dict:
        (target / "calc.py").write_text("def inc(x):\n    return x + 1\n\ndef twice(x):\n    return inc(inc(x))\n", encoding="utf-8")
        record = {
            "mode": "full" if phase == "call_graph" else "incremental",
            "status": "running", "snapshot_commit": "unversioned", "fingerprint": "inputs",
            "phases": [phase], "current_phase": phase,
            "phase_status": {phase: {"status": "running"}},
            "inputs": {"config": {"call_graph_backend": "agent-static"}, "submodules": []},
        }
        state.atomic_json(state.skill_dir(target) / "active.json", record)
        state.atomic_json(state.fm_dir(target) / "phases.json", {"phases": [{
            "phase": 1, "name": "Calculator", "modules": [{"name": "calc", "source_files": ["calc.py"]}], "depends_on_phases": [],
        }]})
        executor.extract(target, [])
        # This old empty graph met the artifact gate without analyzing calls.
        executor.graph(target)
        return record

    def complete_worker(self, target: Path, edges: list[dict]) -> None:
        jobs = scheduler.current_jobs_for_phase(target, state.active_record(target)["current_phase"])
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        scheduler.transition(target, job["id"], "start", None, None, "execution")
        state.atomic_json(target / job["required_outputs"][0], {"edges": edges})
        accepted = scheduler.transition(target, job["id"], "complete", {
            "job_id": job["id"], "status": "succeeded", "outputs": job["required_outputs"], "counts": {"edges": len(edges)},
        }, None, "execution")
        self.assertEqual(accepted["status"], "succeeded")

    def test_worker_then_promotion_preserves_call_relation_in_both_graph_phases(self) -> None:
        for phase in ("call_graph", "rebuild_graph"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary).resolve()
                record = self.prepare(target, phase)
                with patch.object(state, "snapshot_sources_clean", return_value=True), patch.object(phase_driver, "_pipeline", return_value=record) as pipeline:
                    action = phase_driver.next_step(target, 1, "codex")
                    self.assertEqual(action["action"], "dispatch_workers")
                    self.assertEqual(action["dispatches"][0]["type"], "resolve_agent_static_edges")
                    pipeline.assert_not_called()
                    job = scheduler.current_jobs_for_phase(target, phase)[0]
                    self.assertEqual(job["input"]["source_paths"], ["calc.py"])
                    functions = state.read_json(state.fm_dir(target) / "extraction_manifest.json", {})["functions"]
                    artifacts = {item["name"]: item["artifact"] for item in functions}
                    self.complete_worker(target, [{"caller_artifact": artifacts["twice"], "callee_artifact": artifacts["inc"], "evidence": "twice calls inc"}])
                    action = phase_driver.next_step(target, 1, "codex")
                    self.assertEqual(action["action"], "run_deterministic")
                    self.assertEqual(action["argv"][0][2], "record-agent-edges")
                    pipeline.assert_not_called()
                    phase_driver._run_action(action)
                    graph = state.read_json(state.control_dir(target) / "graph_edges.json", {})
                    self.assertEqual(graph["edges"][0]["caller_artifact"], artifacts["twice"])
                    layers = state.read_json(state.fm_dir(target) / "spec_prompts" / "phase_01_topdown_layers.json", {})["layers"]
                    self.assertEqual(layers[0]["functions"][0]["artifact"], artifacts["twice"])
                    self.assertEqual(layers[1]["functions"][0]["artifact"], artifacts["inc"])
                    self.assertEqual(phase_driver.next_step(target, 1, "codex")["action"], "phase_completed")

    def test_empty_candidate_is_allowed_only_after_worker_and_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            record = self.prepare(target, "call_graph")
            self.assertEqual(phase_driver.next_step(target, 1, "codex")["action"], "dispatch_workers")
            self.complete_worker(target, [])
            action = phase_driver.next_step(target, 1, "codex")
            self.assertEqual(action["action"], "run_deterministic")
            phase_driver._run_action(action)
            with patch.object(state, "snapshot_sources_clean", return_value=True), patch.object(phase_driver, "_pipeline", return_value=record):
                self.assertEqual(phase_driver.next_step(target, 1, "codex")["action"], "phase_completed")

    def test_invalid_candidate_retries_then_repair_passes_graph_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            record = self.prepare(target, "call_graph")
            phase_driver.next_step(target, 1, "codex")
            job = scheduler.current_jobs_for_phase(target, "call_graph")[0]
            scheduler.transition(target, job["id"], "start", None, None, "execution")
            state.atomic_json(target / job["required_outputs"][0], {"edges": [{
                "caller_artifact": "missing.py", "callee_artifact": "other.py",
            }]})
            rejected = scheduler.transition(target, job["id"], "complete", {
                "job_id": job["id"], "status": "succeeded", "outputs": job["required_outputs"],
            }, None, "execution")
            self.assertEqual(rejected["status"], "retryable")
            self.assertEqual(rejected["failure_class"], "output")
            self.assertIn("current extracted artifacts", rejected["message"])
            scheduler.transition(target, job["id"], "retry", None, None, "output")
            self.assertEqual(phase_driver.next_step(target, 1, "codex")["action"], "dispatch_workers")
            functions = state.read_json(state.fm_dir(target) / "extraction_manifest.json", {})["functions"]
            artifacts = {item["name"]: item["artifact"] for item in functions}
            self.complete_worker(target, [{
                "caller_artifact": artifacts["twice"], "callee_artifact": artifacts["inc"],
            }])
            action = phase_driver.next_step(target, 1, "codex")
            self.assertEqual(action["action"], "run_deterministic")
            phase_driver._run_action(action)
            with patch.object(state, "snapshot_sources_clean", return_value=True), patch.object(phase_driver, "_pipeline", return_value=record):
                self.assertEqual(phase_driver.next_step(target, 1, "codex")["action"], "phase_completed")

    def test_codegraph_action_does_not_require_agent_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            state.atomic_json(state.control_dir(target) / "codegraph_export.json", {"nodes": [], "edges": []})
            action = phase_driver._deterministic_action(target, {"inputs": {"config": {"call_graph_backend": "codegraph"}}}, "call_graph")
            self.assertEqual(action["argv"][2], "graph")
            self.assertIn("--codegraph-export", action["argv"])


if __name__ == "__main__":
    unittest.main()
