# Host-native Coordinator

The current Claude Code or Codex **parent Agent** is the only FM-Agent
Coordinator. It is not a Worker and must stay active until the durable DAG
converges or the host forcibly ends the turn.

## Lifecycle

1. Call `phase_driver.py next` and act only on its returned action. It is the
   sole owner of phase start/completion and deterministic phase ordering.
2. When `action: dispatch_workers`, invoke every returned Worker ticket through the
   host's native subagent mechanism: Claude uses `registered_worker`; Codex
   uses the ticket's `native_launch_tool`, normally
   `collaboration.spawn_agent`, with one unique task name per job and the
   immutable definition in the ticket. Launch all returned Codex tickets in
   parallel. The absence of a named Worker registry does **not** mean Codex
   has no subagent capability. Only if neither `collaboration.spawn_agent`
   nor unnamespaced `spawn_agent` is exposed may the parent perform the
   serial fallback. In that case, do **not** stop the analysis: the
   current parent Agent performs exactly one ticket as a serial Worker fallback,
   following the same immutable definition, assigned paths, and receipt
   contract. It then returns to the Coordinator loop. This fallback preserves
   correctness and availability but has concurrency one.
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
