#!/usr/bin/env python3
"""Guard the original FM-Agent specification requirements retained by the Skill."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "references" / "specification-rules.md"
WORKER = ROOT / "agents" / "fm-spec-batch-worker.md"


class SpecificationRuleAlignmentTest(unittest.TestCase):
    def test_reference_retains_original_fm_agent_requirements(self) -> None:
        text = " ".join(REFERENCE.read_text(encoding="utf-8").split())
        for required in (
            "ownership transfer and allocation/deallocation obligations",
            "shape, encoding, and schema",
            "Every claim must be verifiable and falsifiable",
            "alternative implementation satisfying the same contract",
            "deleting one branch or one helper call",
        ):
            self.assertIn(required, text)

    def test_spec_worker_applies_the_same_requirements(self) -> None:
        text = " ".join(WORKER.read_text(encoding="utf-8").split())
        for required in (
            "ownership transfer and allocation/deallocation obligations",
            "shape, encoding, and schema",
            "Every claim must be verifiable and falsifiable",
            "alternative implementation satisfying the same contract",
            "deleting one branch or one helper call",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
