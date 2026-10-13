#!/usr/bin/env python3
# Modified by AIResearchSkill: verify genuinely accepted evidence survives cleanup, publication, and cumulative summaries.
"""Regression checks for cumulative on-demand Bug Validation artifacts."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import orchestrate  # noqa: E402
import isolation  # noqa: E402
import reset_full_artifacts  # noqa: E402
import scheduler  # noqa: E402
from fm_agent_core import state  # noqa: E402
from test_accepted_bug_evidence import write_accepted_candidate


def bug_id(function_id: str) -> str:
    return hashlib.sha256(function_id.encode()).hexdigest()[:16]


class ValidationPersistenceTest(unittest.TestCase):
    def write_candidate(self, target: Path, function_id: str, marker: str) -> None:
        digest = bug_id(function_id)
        root = target / "fm_agent" / "bug_validation"
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{digest}.result.json").write_text(
            json.dumps({"function_id": function_id, "marker": marker}), encoding="utf-8"
        )
        probe = target / "fm_agent_skill" / "probes" / digest / "attempt_001"
        probe.mkdir(parents=True, exist_ok=True)
        (probe / "reproduction_result.json").write_text(marker, encoding="utf-8")

    def test_merging_one_candidate_preserves_another_candidates_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            snapshot = Path(temporary) / "snapshot"
            first, second = "src/a.c::first", "src/b.c::second"
            self.write_candidate(source, first, "old-first")
            self.write_candidate(source, second, "old-second")
            self.write_candidate(snapshot, first, "new-first")
            result = orchestrate.merge_validation_candidate(source, snapshot, first)
            self.assertEqual(result["marker"], "new-first")
            for function_id, marker in ((first, "new-first"), (second, "old-second")):
                digest = bug_id(function_id)
                self.assertEqual(
                    json.loads((source / "fm_agent" / "bug_validation" / f"{digest}.result.json").read_text(encoding="utf-8"))["marker"],
                    marker,
                )
                self.assertEqual(
                    (source / "fm_agent_skill" / "probes" / digest / "attempt_001" / "reproduction_result.json").read_text(encoding="utf-8"),
                    marker,
                )

    def test_partial_summary_accumulates_only_current_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            first, second, stale = "src/a.c::first", "src/b.c::second", "src/old.c::stale"
            root = target / "fm_agent" / "bug_validation"
            root.mkdir(parents=True)
            target = target.resolve()
            write_accepted_candidate(target, first, bug_id(first))
            write_accepted_candidate(target, second, bug_id(second), "rejected")
            (root / f"{bug_id(stale)}.result.json").write_text(json.dumps({
                "function_id": stale, "snapshot_commit": "old-baseline", "confirmation_status": "confirmed",
                "attempts": [{"ordinal": 1}],
            }), encoding="utf-8")
            with patch.object(orchestrate.state, "direct_mismatch_ids", return_value={first, second}), \
                 patch.object(orchestrate.state, "baseline_commit", return_value="unversioned"):
                summary = orchestrate.write_partial_validation_summary(target)
            self.assertEqual(summary["dynamic_validation"], "partial")
            self.assertEqual(summary["validated_function_ids"], [first, second])
            self.assertEqual(summary["total_confirmed"], 1)
            self.assertEqual(summary["total_rejected"], 1)
            self.assertEqual(summary["total_static_findings"], 0)

    def test_success_cleanup_and_sync_preserve_confirmed_evidence_until_new_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = (Path(temporary) / "source").resolve()
            snapshot = (Path(temporary) / "snapshot").resolve()
            source.mkdir()
            snapshot.mkdir()
            function_id = "src/a.c::first"
            digest = bug_id(function_id)
            evidence = f"fm_agent_skill/probes/{digest}/attempt_001/reproduction_result.json"
            state.atomic_json(isolation.marker_path(snapshot), {
                "source_project": str(source), "snapshot_commit": "unversioned",
            })
            state.atomic_json(state.skill_dir(snapshot) / "active.json", {
                "snapshot_commit": "unversioned", "fingerprint": "test", "current_phase": "bug_validation",
                "phases": ["bug_validation"], "phase_status": {"bug_validation": {"status": "running"}},
            })
            job = write_accepted_candidate(snapshot, function_id, digest)
            self.assertEqual(job["status"], "succeeded")
            state.atomic_json(state.skill_dir(snapshot) / "worker_reports" / "transient.json", {})
            state.atomic_json(scheduler.checkpoint.root(source) / "official_result.json", {
                "official_result_available": True,
            })

            reset_full_artifacts.clear_transient(snapshot)
            self.assertFalse((state.skill_dir(snapshot) / "worker_reports").exists())
            self.assertTrue(scheduler._path(snapshot, job["id"]).is_file())
            with patch.object(isolation, "_run"), patch.object(isolation, "_remove"):
                self.assertTrue(isolation.sync(snapshot)["synced"])
            self.assertEqual((source / evidence).read_bytes(), (snapshot / evidence).read_bytes())
            self.assertEqual(scheduler.jobs_for_phase(source, "bug_validation")[0]["status"], "succeeded")
            connection = scheduler._connect(source)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM receipts WHERE job_id=?", (job["id"],)).fetchone()[0], 1)
            finally:
                connection.close()
            self.assertEqual(scheduler.accepted_job(source, job["id"], snapshot_commit="unversioned", input_fingerprint="test")["status"], "succeeded")

            reset_full_artifacts.reset(source)
            self.assertFalse((source / evidence).exists())
            self.assertEqual(scheduler.jobs_for_phase(source, "bug_validation"), [])


if __name__ == "__main__":
    unittest.main()
