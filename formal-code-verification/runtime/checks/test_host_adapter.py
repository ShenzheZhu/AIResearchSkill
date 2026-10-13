#!/usr/bin/env python3
# Modified by AIResearchSkill: check fresh-context arguments on actual dispatch tickets.
"""Executable contract checks for Claude/Codex Worker dispatch."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fm_agent_core import worker_contracts  # noqa: E402
from fm_agent_core import coordinator_contract  # noqa: E402
import scheduler  # noqa: E402
import semantic_executor  # noqa: E402
from fm_agent_core import state  # noqa: E402


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
        self.assertEqual(contract["native_launch_arguments"], {"fork_turns": "none"})
        self.assertEqual(contract["fallback"], "blocked_requires_fresh_context")
        self.assertEqual(contract["launch_mode"], "parallel_when_available")
        self.assertIn("worker_definition", contract)
        self.assertIn("collaboration.spawn_agent", contract["developer_instruction"])

    def test_codex_dispatch_ticket_supplies_fresh_native_launch_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            job = {
                "id": "spec-calculation", "type": "spec_batch", "phase": "specification",
                "attempts": 1, "artifacts": ["calc.py"],
                "required_outputs": ["fm_agent/extracted_functions/calc.py.spec.json", "fm_agent/extracted_functions/calc.py.info.json"],
            }
            state.atomic_json(target / "fm_agent_skill/jobs/spec-calculation.json", job)
            artifact = target / "fm_agent/extracted_functions/calc.py"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("def inc(value): return value + 1\n", encoding="utf-8")
            ticket = semantic_executor._ticket(target, job, "codex")
            persisted = state.read_json(target / ticket["ticket_path"], {})
            invocation = persisted["host_invocation"]
            calls = []

            def spawn_agent(*, task_name, message, fork_turns):
                calls.append({"task_name": task_name, "message": message, "fork_turns": fork_turns})

            spawn_agent(
                task_name=ticket["job_id"],
                message=f"Read ticket {target / ticket['ticket_path']} and immutable definition {invocation['worker_definition']}; use only ticket-permitted evidence.",
                **invocation["native_launch_arguments"],
            )
            self.assertEqual(calls[0]["fork_turns"], "none")
            self.assertEqual(invocation["fallback"], "blocked_requires_fresh_context")
            self.assertEqual(persisted["read_paths"], [
                "fm_agent/extracted_functions/calc.py", "fm_agent_skill/jobs/spec-calculation.json",
            ])

    def test_auto_detects_the_codex_plugin_bundle_without_environment_variables(self) -> None:
        self.assertEqual(worker_contracts.resolve_host("auto"), "codex")

    def test_claude_uses_its_registered_worker(self) -> None:
        contract = worker_contracts.invocation("fm-agent-skill:fm-spec-batch-worker", "claude")
        self.assertEqual(contract["kind"], "registered_worker")
        self.assertEqual(contract["name"], "fm-agent-skill:fm-spec-batch-worker")

    def test_continuation_is_candidate_bound_and_fresh_launch_remains_available(self) -> None:
        identity = {"project": "/isolated/counters", "job_id": "bug-count", "attempt": 1,
                    "candidate_id": "counter.py::total::bug-001", "input_hash": "current-input"}
        action = worker_contracts.invocation("fm-agent-skill:fm-bug-validate-worker", "codex",
                                           candidate_continuation=identity)
        self.assertEqual(action["candidate_continuation"], identity)
        self.assertEqual(action["native_followup_tool"], "collaboration.followup_task")
        self.assertEqual(action["native_launch_arguments"], {"fork_turns": "none"})
        with self.assertRaises(ValueError):
            worker_contracts.invocation("fm-agent-skill:fm-verify-function-worker", "codex",
                                        candidate_continuation=identity)

    def test_coordinator_is_the_host_parent_not_a_worker(self) -> None:
        contract = coordinator_contract.invocation("codex")
        self.assertEqual(contract["kind"], "native_parent_agent")
        self.assertEqual(contract["worker_launch"], "generic_subagent")
        self.assertEqual(contract["native_launch_tool"], "collaboration.spawn_agent")
        self.assertEqual(contract["launch_mode"], "parallel_returned_tickets")
        self.assertEqual(contract["native_launch_arguments"], {"fork_turns": "none"})
        self.assertEqual(contract["fallback"], "blocked_requires_fresh_context")
        self.assertFalse(contract["terminal_allowed"])


if __name__ == "__main__":
    unittest.main()
