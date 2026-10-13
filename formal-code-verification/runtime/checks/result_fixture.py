"""Construct the strict current verification format for deterministic fixtures."""
from fm_agent_core import state


def verification_result(function_id, snapshot_commit, verdict, reasoning=None, gaps=None, error=None):
    return {
        "schema_version": 3, "function_id": function_id, "snapshot_commit": snapshot_commit,
        "verdict": verdict, "reasoning": reasoning, "gaps": gaps, "error": error,
        "reasoning_complete": verdict in {"MATCH", "MISMATCH"}, "loop_evidence": [],
        "candidates": [{"candidate_id": state.candidate_id(function_id), "reasoning": reasoning}] if verdict == "MISMATCH" else [],
    }
