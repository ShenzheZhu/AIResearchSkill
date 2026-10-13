#!/usr/bin/env python3
"""Executable contract checks for Claude/Codex Worker dispatch."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fm_agent_core import worker_contracts  # noqa: E402
from fm_agent_core import coordinator_contract  # noqa: E402
import scheduler  # noqa: E402


class HostAdapterContractTest(unittest.TestCase):
    def test_every_registered_worker_has_one_immutable_definition(self) -> None:
        for worker in sorted(set(worker_contracts.JOB_WORKERS.values())):
            self.assertTrue(worker_contracts.definition_path(worker).is_file(), worker)

    def test_every_scheduler_type_has_a_host_contract(self) -> None:
        self.assertEqual(set(worker_contracts.JOB_WORKERS), scheduler.JOB_TYPES)

    def test_codex_uses_a_generic_subagent(self) -> None:
        contract = worker_contracts.invocation("fm-agent-skill:fm-spec-batch-worker", "codex")
        self.assertEqual(contract["kind"], "generic_subagent")
        self.assertEqual(contract["native_launch_tool"], "collaboration.spawn_agent")
        self.assertEqual(contract["launch_mode"], "parallel_when_available")
        self.assertIn("worker_definition", contract)
        self.assertIn("collaboration.spawn_agent", contract["developer_instruction"])

    def test_auto_detects_the_codex_plugin_bundle_without_environment_variables(self) -> None:
        self.assertEqual(worker_contracts.resolve_host("auto"), "codex")

    def test_claude_uses_its_registered_worker(self) -> None:
        contract = worker_contracts.invocation("fm-agent-skill:fm-spec-batch-worker", "claude")
        self.assertEqual(contract["kind"], "registered_worker")
        self.assertEqual(contract["name"], "fm-agent-skill:fm-spec-batch-worker")

    def test_coordinator_is_the_host_parent_not_a_worker(self) -> None:
        contract = coordinator_contract.invocation("codex")
        self.assertEqual(contract["kind"], "native_parent_agent")
        self.assertEqual(contract["worker_launch"], "generic_subagent")
        self.assertEqual(contract["native_launch_tool"], "collaboration.spawn_agent")
        self.assertEqual(contract["launch_mode"], "parallel_returned_tickets")
        self.assertFalse(contract["terminal_allowed"])


if __name__ == "__main__":
    unittest.main()
