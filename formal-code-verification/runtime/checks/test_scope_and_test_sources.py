#!/usr/bin/env python3
"""Accepted scopes and test exclusions stay consistent through extraction."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import executor
import orchestrate
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
