#!/usr/bin/env python3
# Modified by AIResearchSkill: cover declared production directories through inventory, extraction, and phases.
"""Accepted scopes and test exclusions stay consistent through extraction."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import executor
import orchestrate
import stage_gate
from fm_agent_core import state


class ScopeAndTestSourcesTest(unittest.TestCase):
    def inspect(self, target: Path, scopes: list[str]) -> dict:
        args = argparse.Namespace(submodules=scopes, knowledge=[], extra_edge=None, codegraph=False, one_phase=False)
        with patch.object(state, "preflight", return_value={"ok": True}), patch.object(state, "inspect_baseline", return_value={"valid": False}):
            return orchestrate.inspect(target, args)

    def test_accepted_scope_spellings_reach_inventory_extraction_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.object(state, "current_snapshot_commit", return_value="unversioned"):
            target = Path(temporary).resolve()
            (target / "src").mkdir()
            (target / "src/api.py").write_text("def api():\n    return 1\n")
            (target / "other.py").write_text("def other():\n    return 2\n")
            variants = [
                (["src"], ["src"]), (["./src"], ["src"]), (["src/"], ["src"]),
                (["src/../src"], ["src"]), ([str(target / "src")], ["src"]),
                (["src", "./src", str(target / "src")], ["src"]),
                (["."], []), (["./"], []), ([str(target)], []), (["src", "."], []),
            ]
            for supplied, expected_scope in variants:
                with self.subTest(scope=supplied):
                    inspected = self.inspect(target, supplied)
                    self.assertTrue(inspected["ok"], inspected)
                    scope = inspected["config"]["submodules"]
                    self.assertEqual(scope, expected_scope)
                    expected_paths = ["src/api.py"] if scope else ["other.py", "src/api.py"]
                    self.assertEqual([item["path"] for item in state.source_manifest(target, scope)["files"]], expected_paths)
                    extracted = executor.extract(target, scope)
                    self.assertGreater(extracted["function_count"], 0)
                    manifest = state.read_json(state.fm_dir(target) / "extraction_manifest.json", {})
                    self.assertEqual(sorted(item["source_path"] for item in manifest["functions"]), expected_paths)
                    self.assertEqual(sorted(item["path"] for item in extracted["index"]["functions"]), expected_paths)
                    self.assertEqual(sorted(item["path"] for item in state.scoped_functions(target, scope)), expected_paths)

    def test_root_scope_does_not_hide_invalid_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            (target / "api.py").write_text("def api():\n    return 1\n")
            for invalid in ("missing", "api.py", str(target.parent)):
                with self.subTest(scope=invalid):
                    result = self.inspect(target, [".", invalid])
                    self.assertFalse(result["ok"])
                    self.assertEqual(result["issues"], [f"invalid --submodule: {invalid}"])

    def test_declared_dist_only_project_reaches_preflight_extraction_and_phases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.object(state, "current_snapshot_commit", return_value="unversioned"):
            target = Path(temporary).resolve()
            paths = ["dist/api.py", "dist/test_api.py", "dist/tests/api.py", "build/generated.py", "out/generated.py", "dist/build/generated.py", "dist/fm_agent/generated.py"]
            for path in paths:
                source = target / path
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("def api():\n    return 1\n")
            with patch.object(state, "git", return_value="revision"):
                self.assertFalse(state.preflight(target)["ok"])
                self.assertEqual(state.preflight(target, ["dist"])["source_file_count"], 1)
                args = argparse.Namespace(submodules=[str(target / "dist")], knowledge=[], extra_edge=None, codegraph=False, one_phase=False)
                with patch.object(state, "inspect_baseline", return_value={"valid": False}):
                    inspected = orchestrate.inspect(target, args)
            self.assertTrue(inspected["ok"], inspected)
            scopes = inspected["config"]["submodules"]
            self.assertEqual(scopes, ["dist"])
            state.atomic_json(state.skill_dir(target) / "active.json", {"inputs": {"submodules": scopes}})
            with patch.object(state, "git", return_value="revision"), patch.object(state, "snapshot_sources_clean", return_value=True):
                gate = stage_gate.validate(target, "full", "preflight", state.active_record(target)["inputs"]["submodules"])
            self.assertTrue(gate["ok"], gate)
            for arguments in ([], ["--submodule", str(target / "dist")]):
                output = io.StringIO()
                with patch.object(sys, "argv", ["preflight.py", "--project", str(target), *arguments]), patch.object(state, "git", return_value=""), redirect_stdout(output):
                    with self.assertRaises(SystemExit) as exited:
                        runpy.run_path(str(ROOT / "scripts/preflight.py"))
                self.assertEqual(exited.exception.code, 0, output.getvalue())
                self.assertEqual(json.loads(output.getvalue())["source_file_count"], 1)
            self.assertEqual([item["path"] for item in state.source_manifest(target, scopes)["files"]], ["dist/api.py"])
            extracted = executor.extract(target, scopes)
            self.assertEqual(extracted["function_count"], 1)
            self.assertEqual(extracted["index"]["functions"][0]["path"], "dist/api.py")
            manifest = state.read_json(state.fm_dir(target) / "extraction_manifest.json", {})
            self.assertEqual(manifest["functions"][0]["source_path"], "dist/api.py")
            state.atomic_json(state.skill_dir(target) / "config.json", {"submodules": ["build"]})
            state.atomic_json(state.fm_dir(target) / "phases.json", {"phases": [{"phase": 1, "name": "API", "modules": [{"source_files": paths}], "depends_on_phases": []}]})
            executor.normalize_phases(target)
            phases = state.read_json(state.fm_dir(target) / "phases.json", {})
            self.assertEqual(phases["file_extensions"], ["py"])
            self.assertEqual(phases["phases"][0]["modules"][0]["source_files"], ["dist/api.py"])
            executor.graph(target)
            self.assertTrue(state.phase_layers_ready(target)[0])

    def test_declared_js_ts_paths_override_only_selected_default_skips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            production = ["dist/app.js", "build/client.ts", "out/entry.mjs", "src/dist/native.ts"]
            excluded = ["dist/app.test.js", "build/client.spec.ts", "out/tests/entry.mjs", "src/dist/__tests__/native.ts", "target/generated.js", "src/build/generated.ts", "fm_agent/generated.ts", "fm_agent_skill/generated.ts", "fm_agent_plugin/generated.js", ".codegraph/generated.js", ".git/generated.ts"]
            for path in production + excluded:
                source = target / path
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("function api() { return 1; }\n")
            self.assertEqual(state.source_files(target), [])
            scopes = ["dist", "build", "out", "src/dist", "src", "dist"]
            self.assertEqual(sorted(path.relative_to(target).as_posix() for path in state.source_files(target, scopes)), sorted(production))
            self.assertEqual([item["path"] for item in state.source_manifest(target, scopes)["files"]], sorted(production))
            for scope in (".git", "fm_agent", "fm_agent_skill", "fm_agent_plugin", ".codegraph"):
                self.assertEqual(state.source_files(target, [scope]), [])

    def test_vendor_dependency_skip_can_be_explicitly_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            for relative in ("dist/checkout.js", "dist/vendor/library.js", "vendor/api.py"):
                source = target / relative
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("def api(): return 1\n" if source.suffix == ".py" else "export function api() { return 1; }\n")
            self.assertEqual(state.source_files(target), [])
            self.assertEqual([path.relative_to(target).as_posix() for path in state.source_files(target, ["dist"])], ["dist/checkout.js"])
            scopes = ["dist", "dist/vendor", "vendor"]
            expected = ["dist/checkout.js", "dist/vendor/library.js", "vendor/api.py"]
            self.assertEqual(sorted(path.relative_to(target).as_posix() for path in state.source_files(target, scopes)), expected)
            self.assertEqual([item["path"] for item in state.source_manifest(target, scopes)["files"]], expected)

    def test_dispatch_reuses_normalized_config_after_snapshot_relocation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source, snapshot = root / "source", root / "snapshot"
            for target in (source, snapshot):
                (target / "src").mkdir(parents=True)
                (target / "src/api.py").write_text("def api():\n    return 1\n")
                state.atomic_json(state.skill_dir(target) / "config.json", {"submodules": ["src"]})
            for supplied, expected_scope in ((str(source / "src"), ["src"]), (".", [])):
                with (
                    self.subTest(scope=supplied),
                    patch.object(sys, "argv", ["orchestrate.py", "dispatch", "--project", str(source), "--submodule", supplied]),
                    patch.object(state, "preflight", return_value={"ok": True}),
                    patch.object(state, "inspect_baseline", return_value={"valid": False}),
                    patch.object(orchestrate, "_active_ref", return_value=None),
                    patch.object(orchestrate, "create_snapshot", return_value={"snapshot": str(snapshot)}),
                    patch.object(orchestrate, "discard_snapshot"),
                    patch.object(orchestrate, "acquire", return_value={}),
                    patch.object(orchestrate, "call_pipeline", return_value={}) as prepare,
                    patch.object(orchestrate, "publish_run_index"),
                ):
                    output = io.StringIO()
                    with redirect_stdout(output):
                        orchestrate.main()
                    dispatched = json.loads(output.getvalue())
                    self.assertTrue(dispatched["ok"], dispatched)
                    self.assertEqual(dispatched["config"]["submodules"], expected_scope)
                    self.assertEqual(prepare.call_args.args[3]["submodules"], expected_scope)

    def test_js_and_ts_tests_are_excluded_without_dropping_production_names(self) -> None:
        tests = [f"src/api.{kind}.{extension}" for kind in ("test", "spec") for extension in ("js", "jsx", "mjs", "cjs", "ts", "tsx", "mts", "cts")]
        tests += ["src/__tests__/api.ts", "src/tests/api.js", "src/test_api.ts"]
        production = ["src/api.ts", "src/testimonials.tsx", "src/api.specification.ts", "src/api.test-helper.js", "src/specification.js"]
        for path in tests:
            self.assertTrue(state.is_test_source_path(path), path)
        for path in production:
            self.assertFalse(state.is_test_source_path(path), path)
        with tempfile.TemporaryDirectory() as temporary, patch.object(state, "current_snapshot_commit", return_value="unversioned"):
            target = Path(temporary).resolve()
            paths = tests + production
            for path in paths:
                source = target / path
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("function api() { return 1; }\n")
            export = target / "codegraph.json"
            state.atomic_json(export, {"nodes": [{"path": path, "name": "api", "line_start": 1, "line_end": 1} for path in paths]})
            expected = sorted(production)
            self.assertEqual(sorted(path.relative_to(target).as_posix() for path in state.source_files(target)), expected)
            self.assertEqual([item["path"] for item in state.source_manifest(target, ["src"])["files"]], expected)
            extracted = executor.extract(target, ["src"], export)
            self.assertEqual(sorted(item["path"] for item in extracted["index"]["functions"]), expected)
            state.atomic_json(state.fm_dir(target) / "phases.json", {"phases": [{"phase": 1, "name": "API", "modules": [{"source_files": paths}], "depends_on_phases": []}]})
            executor.normalize_phases(target)
            phase = state.read_json(state.fm_dir(target) / "phases.json", {})["phases"][0]
            self.assertEqual(phase["modules"][0]["source_files"], expected)
            self.assertTrue(state.phases_schema_ready(target)[0])


if __name__ == "__main__":
    unittest.main()
