# Modified by AIResearchSkill: require isolated native Worker contexts.
"""Host-neutral semantic Worker contracts.

Claude can select plugin Workers by name. Codex plugins cannot bundle custom
agent registrations, so Codex must start a native generic subagent and give it
the immutable Worker definition named in the dispatch ticket. Keeping that
choice in deterministic data makes the two execution paths auditable and
testable.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

JOB_WORKERS = {
    "domain_context": "fm-agent-skill:fm-domain-context-worker",
    "spec_batch": "fm-agent-skill:fm-spec-batch-worker",
    "verify_function": "fm-agent-skill:fm-verify-function-worker",
    "verify_batch": "fm-agent-skill:fm-verify-function-worker",
    "bug_validate": "fm-agent-skill:fm-bug-validate-worker",
    "phase_plan": "fm-agent-skill:fm-phase-plan-worker",
    "phase_refine": "fm-agent-skill:fm-phase-refine-worker",
    "resolve_agent_static_edges": "fm-agent-skill:fm-agent-static-edge-worker",
    "select_relevant_modules": "fm-agent-skill:fm-select-relevant-modules-worker",
    "select_relevant_files": "fm-agent-skill:fm-select-relevant-files-worker",
    "incremental_spec_plan": "fm-agent-skill:fm-incremental-spec-plan-worker",
    "reconcile_caller_info": "fm-agent-skill:fm-reconcile-caller-info-worker",
}


def resolve_host(value: str = "auto") -> str:
    """Return the explicit host contract; unknown environments stay portable."""
    if value not in {"auto", "claude", "codex", "portable"}:
        raise ValueError(f"unsupported host: {value}")
    if value != "auto":
        return value
    configured = os.environ.get("FM_AGENT_HOST", "").lower()
    if configured in {"claude", "codex"}:
        return configured
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return "claude"
    if os.environ.get("PLUGIN_ROOT"):
        return "codex"
    if os.environ.get("CODEX_HOME"):
        return "codex"
    # Codex does not guarantee that CODEX_HOME/PLUGIN_ROOT are inherited by
    # subprocesses launched from a Skill.  The installed bundle itself is a
    # stronger signal: only the Codex distribution contains this manifest.
    # Check Claude first because the development tree intentionally ships both
    # manifests for cross-client compatibility.
    if (ROOT / ".codex-plugin" / "plugin.json").is_file():
        return "codex"
    return "portable"


def definition_path(worker: str) -> Path:
    name = worker.split(":", 1)[-1]
    path = ROOT / "agents" / f"{name}.md"
    if not path.is_file():
        raise ValueError(f"registered worker definition is missing: {worker}")
    return path


def for_job_type(job_type: str) -> str:
    try:
        return JOB_WORKERS[job_type]
    except KeyError as exc:
        raise ValueError(f"job type has no registered Worker contract: {job_type}") from exc


def invocation(worker: str, host: str = "auto") -> dict:
    """Build the exact host action without embedding semantic instructions."""
    resolved = resolve_host(host)
    definition = definition_path(worker)
    common = {
        "worker": worker,
        "worker_definition": str(definition),
        "worker_definition_sha256": hashlib.sha256(definition.read_bytes()).hexdigest(),
    }
    if resolved == "claude":
        return {**common, "host": resolved, "kind": "registered_worker", "name": worker}
    if resolved == "codex":
        return {
            **common,
            "host": resolved,
            "kind": "generic_subagent",
            # This is deliberately the real host tool name exposed to the
            # Coordinator, not a vague capability label.  A Skill subprocess
            # cannot invoke host tools itself; the current Codex Agent can.
            "native_launch_tool": "collaboration.spawn_agent",
            "native_launch_fallback_tool": "spawn_agent",
            "native_launch_arguments": {"fork_turns": "none"},
            "launch_mode": "parallel_when_available",
            "fallback": "blocked_requires_fresh_context",
            "developer_instruction": (
                "The Coordinator must first use collaboration.spawn_agent when that native tool is "
                "available (or spawn_agent when exposed without a namespace). Start one generic "
                "subagent for this returned ticket with native_launch_arguments (fork_turns='none'); "
                "do not inherit the parent conversation. Do not treat the lack of a named Worker "
                "registry as missing subagent capability. Give it only the ticket path, this immutable "
                "worker_definition, and evidence permitted by that ticket, then require it to read "
                "both contracts completely and execute them exactly. "
                "Do not paraphrase either contract, inspect unassigned paths, or create a Workflow script. "
                "If neither native launch tool exists, stop with blocked_requires_fresh_context. "
                "The parent must never perform semantic Worker work: its conversation may contain "
                "tests, answer keys, issue labels, or previous conclusions that are not permitted evidence."
            ),
        }
    return {
        **common,
        "host": resolved,
        "kind": "host_selected",
        "fallback": "blocked_requires_fresh_context",
        "developer_instruction": (
            "If this host cannot select the Worker by name, launch a generic subagent. If the host "
            "does not expose a fresh subagent context, stop with blocked_requires_fresh_context. "
            "Do not perform semantic Worker work in the parent conversation. Pass only the dispatch "
            "ticket, immutable worker_definition, and evidence permitted by that ticket."
        ),
    }
