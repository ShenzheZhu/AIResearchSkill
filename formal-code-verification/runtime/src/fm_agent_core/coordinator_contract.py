# Modified by AIResearchSkill: keep semantic work in fresh native Worker contexts.
"""Host-native Coordinator contract shared by Codex and Claude runs."""
from __future__ import annotations

from .worker_contracts import resolve_host


def invocation(host: str = "auto") -> dict:
    """Describe the parent Agent that owns one complete durable run.

    This is deliberately not a Worker contract.  The current host Agent is
    the sole Coordinator because only it can invoke native subagents and keep
    consuming their receipts.  A Python helper may manage the durable DAG but
    can never replace that host capability.
    """
    resolved = resolve_host(host)
    worker_launch = (
        "registered_worker" if resolved == "claude"
        else "generic_subagent" if resolved == "codex"
        else "host_selected"
    )
    contract = {
        "role": "fm_agent_coordinator",
        "host": resolved,
        "kind": "native_parent_agent",
        "worker_launch": worker_launch,
        "terminal_allowed": False,
        "developer_instruction": (
            "Act as the sole FM-Agent Coordinator in the current host Agent. "
            "Launch only the returned Worker tickets through the host-native "
            "subagent mechanism, submit every receipt, then request the next "
            "Coordinator action immediately. Do not return a terminal analysis "
            "message while the scheduler has queued, running, or retryable jobs. "
            "If the host has no fresh subagent capability, stop with "
            "blocked_requires_fresh_context; never execute semantic Worker work "
            "in the parent conversation. Workers cannot coordinate, spawn workers, "
            "or advance phases."
        ),
    }
    if resolved == "codex":
        contract.update({
            "native_launch_tool": "collaboration.spawn_agent",
            "native_launch_fallback_tool": "spawn_agent",
            "native_launch_arguments": {"fork_turns": "none"},
            "fallback": "blocked_requires_fresh_context",
            "launch_mode": "parallel_returned_tickets",
            "developer_instruction": (
                "Act as the sole FM-Agent Coordinator in the current Codex Agent. For every "
                "returned ticket, first call collaboration.spawn_agent when it is in the current "
                "tool list (or spawn_agent when exposed without a namespace), using a unique "
                "task_name derived from job_id and native_launch_arguments (fork_turns='none'). "
                "Do not inherit the parent conversation. The message may contain only the returned "
                "ticket, immutable worker definition, and evidence permitted by the ticket. "
                "Launch all returned tickets up to the supplied limit in parallel. "
                "Do not conclude native subagents are unavailable merely because this plugin has "
                "no named-agent registry. Submit every receipt, then request the next Coordinator "
                "action immediately. Do not return a terminal analysis message while the scheduler "
                "has queued, running, or retryable jobs. When neither native launch tool is "
                "present, stop with blocked_requires_fresh_context. Never execute semantic Worker "
                "work in the parent conversation, which may already contain tests or answer keys. "
                "Workers cannot coordinate, spawn "
                "workers, or advance phases."
            ),
        })
    return contract
