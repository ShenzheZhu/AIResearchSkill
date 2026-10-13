#!/usr/bin/env python3
"""Regression checks for source-worktree isolation at snapshot creation."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import isolation  # noqa: E402
from fm_agent_core import state  # noqa: E402


class SnapshotIsolationTest(unittest.TestCase):
    def test_snapshot_does_not_write_gitignore(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / ".gitignore").write_text("*.log\n", encoding="utf-8")
            (target / "main.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(target)], check=True)
            subprocess.run(["git", "-C", str(target), "add", "."], check=True)
            subprocess.run([
                "git", "-C", str(target), "-c", "user.name=Test", "-c",
                "user.email=test@example.invalid", "commit", "-qm", "initial",
            ], check=True)
            before = (target / ".gitignore").read_bytes()
            created = isolation.create(target)
            self.assertEqual((target / ".gitignore").read_bytes(), before)
            # A later source edit belongs to the user's live worktree, not to
            # the detached analysis snapshot.
            (target / "main.cpp").write_text("int main() { return 1; }\n", encoding="utf-8")
            self.assertEqual(
                (Path(created["snapshot"]) / "main.cpp").read_text(encoding="utf-8"),
                "int main() { return 0; }\n",
            )
            isolation.discard(Path(created["snapshot"]))

    def test_sync_promotes_baseline_provenance_to_source_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / "main.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(target)], check=True)
            subprocess.run(["git", "-C", str(target), "add", "."], check=True)
            subprocess.run([
                "git", "-C", str(target), "-c", "user.name=Test", "-c",
                "user.email=test@example.invalid", "commit", "-qm", "initial",
            ], check=True)
            created = isolation.create(target)
            snapshot = Path(created["snapshot"])
            baseline = {"schema_version": 4, "baseline_commit": created["snapshot_commit"], "fingerprint": "test", "inputs": {}, "completed_at": "2026-01-01T00:00:00+00:00"}
            (snapshot / "fm_agent_skill").mkdir(exist_ok=True)
            (snapshot / "fm_agent_skill" / "baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
            probe = snapshot / "fm_agent_skill" / "probes" / "candidate" / "attempt_001"
            probe.mkdir(parents=True)
            (probe / "reproduction_result.json").write_text('{"classification":"confirmed"}\n', encoding="utf-8")
            stale_probe = target / "fm_agent_skill" / "probes" / "stale"
            stale_probe.mkdir(parents=True)
            (stale_probe / "old.txt").write_text("old\n", encoding="utf-8")
            self.assertTrue(isolation.sync(snapshot)["synced"])
            self.assertEqual(json.loads((target / "fm_agent_skill" / "baseline.json").read_text(encoding="utf-8")), baseline)
            self.assertEqual(
                (target / "fm_agent_skill" / "probes" / "candidate" / "attempt_001" / "reproduction_result.json").read_text(encoding="utf-8"),
                '{"classification":"confirmed"}\n',
            )
            self.assertFalse((target / "fm_agent_skill" / "probes" / "stale").exists())

    def test_source_manifest_accepts_dirty_baseline_content_and_detects_later_edits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            source = target / "main.cpp"
            source.write_text("int main() { return 0; }\n", encoding="utf-8")
            manifest = state.source_manifest(target)
            self.assertTrue(state.source_manifest_diff(target, manifest)["compatible"])
            source.write_text("int main() { return 1; }\n", encoding="utf-8")
            diff = state.source_manifest_diff(target, manifest)
            self.assertFalse(diff["compatible"])
            self.assertEqual(diff["changed"], ["main.cpp"])


if __name__ == "__main__":
    unittest.main()
