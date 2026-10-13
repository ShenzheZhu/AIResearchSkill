# Host-native Coordinator

Modified by AIResearchSkill: isolate native Workers and allow validated same-attempt Bug continuation.

The current Claude Code or Codex **parent Agent** is the only FM-Agent
Coordinator. It is not a Worker and must stay active until the durable DAG
converges or the host forcibly ends the turn.

## Lifecycle

1. Call `phase_driver.py next` and act only on its returned action. It is the
   sole owner of phase start/completion and deterministic phase ordering.
2. When `action: dispatch_workers`, invoke every returned Worker ticket through the
   host's native subagent mechanism: Claude uses `registered_worker`; Codex
   uses the ticket's `native_launch_tool`, normally
   `collaboration.spawn_agent`, with one unique task name per job and
   `native_launch_arguments` (`fork_turns="none"`). Spec and Verify always
   start independently. A Bug execution ticket with `candidate_continuation`
   may use `native_followup_tool` (`collaboration.followup_task`) on its exact
   preparation Worker only after preparation validation. Require the same
   project, job, candidate, attempt and input hash, and no unrelated messages,
   tests or answer keys in that context. If that context or tool is unavailable,
   use the ticket's fresh launch path. Pass only the complete
   ticket, immutable definition and its permitted evidence. Launch returned
   tickets up to the host's available slots. The absence of a named Worker
   registry does **not** mean Codex has no subagent capability. If no fresh
   native context is available, preserve the ticket and report
   `blocked_requires_fresh_context`; the parent may already contain tests or
   answers and must not perform semantic Worker work itself.
3. Submit every Worker receipt immediately, repair/retry when directed, and
   call `phase_driver.py next` again to fill free slots.
4. When `action: wait_for_completion_event`, wait only for an already-running
   Worker and call `next` immediately after its receipt. Do not send a terminal
   user response.
5. Only `dag_converged` permits the current phase's receipt and gate. It does
   not itself permit `pipeline.py complete`; every pipeline phase must pass.

Workers never coordinate, invoke other Workers, change phase state, or write
`fm_agent_skill/` control state. If the host ends the parent Agent turn, the
Coordinator leaves the snapshot and durable DAG intact; the next Skill
invocation reclaims them.
