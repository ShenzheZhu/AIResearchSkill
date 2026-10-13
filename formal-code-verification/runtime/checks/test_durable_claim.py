#!/usr/bin/env python3
"""Regression checks for claim-before-launch durable dispatch."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import durable_executor  # noqa: E402
import scheduler  # noqa: E402
from fm_agent_core import state  # noqa: E402
from config import DEFAULTS  # noqa: E402


class DurableClaimTest(unittest.TestCase):
    def test_next_lists_without_leasing_and_claim_leases_one_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            state.atomic_json(target / "fm_agent_skill" / "active.json", {
                "snapshot_commit": "unversioned", "fingerprint": "test",
                "phases": ["specification"], "current_phase": "specification",
            })
            scheduler.create(target, {
                "id": "context", "phase": "specification", "type": "domain_context",
                "depends_on": [], "required_outputs": [], "artifacts": [],
            })
            listed = durable_executor.next_actions(target, limit=4)
            self.assertEqual(listed["action"], "dispatch")
            self.assertEqual(listed["dispatches"], [{
                "action": "claim_worker", "job_id": "context",
                "type": "domain_context", "phase": "specification",
            }])
            self.assertEqual(scheduler._load(target, "context")["status"], "queued")

            claimed = durable_executor.claim(target, "context")
            self.assertEqual(claimed["action"], "host_worker")
            self.assertEqual(claimed["job_id"], "context")
            self.assertEqual(scheduler._load(target, "context")["status"], "running")

    def test_default_worker_batch_size_is_three(self) -> None:
        self.assertEqual(DEFAULTS["worker_max_functions"], 3)


if __name__ == "__main__":
    unittest.main()
