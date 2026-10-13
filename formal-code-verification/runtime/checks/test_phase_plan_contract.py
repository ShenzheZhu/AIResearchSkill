#!/usr/bin/env python3
# Modified by AIResearchSkill: resolve macOS temporary-directory aliases in fixtures.
"""Regression checks for phase-plan compatibility and scheduler admission."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import executor  # noqa: E402
import checkpoint  # noqa: E402
import scheduler  # noqa: E402


class PhasePlanContractTest(unittest.TestCase):
    def test_legacy_source_list_and_depends_on_are_normalized_before_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            (project / "student.h").write_text("class Student {};\n", encoding="utf-8")
            (project / "student.cpp").write_text("#include \"student.h\"\n", encoding="utf-8")
            plan_dir = project / "fm_agent"
            plan_dir.mkdir()
            (plan_dir / "phases.json").write_text(json.dumps({"phases": [
                {"id": "interface", "name": "Interface", "modules": ["student.h"], "depends_on": []},
                {"id": "implementation", "name": "Implementation", "modules": ["student.cpp"], "depends_on": ["interface"]},
            ]}), encoding="utf-8")

            executor.normalize_phases(project)
            normalized = json.loads((plan_dir / "phases.json").read_text(encoding="utf-8"))
            self.assertEqual(normalized["phases"][0]["modules"][0]["source_files"], ["student.h"])
            self.assertEqual(normalized["phases"][1]["depends_on_phases"], [1])

            job = {"type": "phase_plan", "required_outputs": ["fm_agent/phases.json"]}
            self.assertIsNone(scheduler._validate(project, job))

    def test_checkpoint_phase_names_follow_the_active_mode_order(self) -> None:
        full = ["preflight", "project_understanding", "phase_cleanup", "extraction", "call_graph", "specification", "verification", "bug_validation", "finalize"]
        incremental = ["validate_baseline", "refresh_plan", "preserve_specs", "diff", "rebuild_graph", "select_scope", "update_specs", "verify_affected", "bug_validation", "finalize"]
        self.assertEqual(checkpoint._phase_info("bug_validation", full), (8, "08-bug-validation.json"))
        self.assertEqual(checkpoint._phase_info("finalize", full), (9, "09-finalize.json"))
        self.assertEqual(checkpoint._phase_info("update_specs", incremental), (7, "07-update-specs.json"))
        self.assertEqual(checkpoint._phase_info("bug_validation", incremental), (9, "09-bug-validation.json"))
        self.assertEqual(checkpoint._phase_info("finalize", incremental), (10, "10-finalize.json"))


if __name__ == "__main__":
    unittest.main()
