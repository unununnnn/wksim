# Full OPS-10 — Control, mission and algorithm contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #161. It does not promote the verified velocity/yaw, attitude, PID/UDE/NE, RC seam, single-planner or ArUco paths into the full public Prometheus algorithm set.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:78`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-10`, `followup_ids=[161]`; parents #35 (Prometheus PID controller selection and closed loop, OPEN) and #32 (dual-stack velocity/yaw, CLOSED); the ticket also names #1, #36, #37, #38, #39 and #40.
- `ros2/src/prometheus_control/prometheus_control/command.py`: `CommandProcessor` with the INIT / RC_POS_CONTROL / COMMAND_CONTROL / LAND_CONTROL mode machine, `Acceptance`/`Desired` types and rejection of invalid kind/shape/non-finite values without mutation.
- Commit `a81515c` and `docs/plan/38-rc-integration.md`: the #99 bounded shared seam — `Simulator/wksim_control/rc_input.py` `RCInput` feeds a validated `Desired` via `set_rc_desired()`; RC output only in RC_POS_CONTROL, disarm clears and returns to INIT. The document states the installed Control node is unchanged and this is not RC product acceptance.
- `Simulator/wksim_control/position_pid.py`, `position_ude.py`, `position_ne.py` with `Simulator/wksim_runtime/pid-flight-v1.json`, `ude-flight-v1.json`, `ne-flight-v1.json`: owned PID/UDE/NE controller modules and frozen flight configurations.
- `Simulator/wksim_runtime/velocity_evidence.py`: velocity-window verification backing the closed #32 slice; `attitude_task.py`/`attitude-entry-v1.json` back the #34 attitude exit.
- `Simulator/wksim_runtime/mission_plan.py`, `mission_actions.py`, `mission_task.py`, `mission_evidence.py`: owned mission plan/action/evidence modules.
- Upstream `Modules/` (motion_planning, ego_planner_swarm, FAST_LIO, tutorial demos) remains migration source material; no per-item fixed source/version/hash mapping to accepted wksim experiments exists, and no multi-vehicle formation capability is owned.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-10-A | RC modes | `partial`: #99 seam validates RC_POS_CONTROL handoff only | Other public RC modes with explicit setup/activation, stream revocation and native handoff |
| OPS-10-B | Controller paths | `partial`: PID/UDE/NE modules and flight configs exist; #35 selection open | Controller selection closed with source comparison, preflight and per-stack acceptance |
| OPS-10-C | Mission layer | `partial`: owned plan/action/evidence modules exist on bounded missions | Mission lifecycle with acceptance/completion distinction audited on both stacks |
| OPS-10-D | Planning/perception demos | `partial`: single planner and the ArUco path are the explicit first slices | Per-demo fixed source/version/hash mapping and single-experiment acceptance |
| OPS-10-E | Multi-vehicle mission/formation | `blocked`: no owned formation capability | Joint-scene multi-vehicle mission/formation with authority time and per-vehicle identity |
| OPS-10-F | Public experiment mapping | `blocked`: no fixed per-item mapping of the public experiment set | Frozen mapping list with per-item acceptance owners |

## Command and mission contract

Every control/mission command must carry:

```text
command_id, source (rc | command | mission), mode, vehicle_id, run_id, epoch,
step, sim_time_ns, reference_kind, reference_value, precondition_state,
acceptance, completion_window, error_budget, source_identity
```

Per the context language: **command acceptance** means the mission/control layer validated and stored the command — not FC acknowledgement and not action completion. **Action completion** means actual feedback satisfies the objective within the window and error budget. **Task takeover** requires mode, state and attitude alignment before control targets stream. A verified single-experiment path (velocity/yaw, attitude, one planner, ArUco) is not the public algorithm set.

### Lifecycle

```text
declare mode/preconditions → validate command identity and reference
→ acceptance recorded with epoch/step → execute under takeover conditions
→ evaluate completion in the declared window/budget → end/land/reset
→ reconnect binds current epoch only
```

`accepted` does not imply the vehicle moved, the FC acknowledged, or the mission completed. Completion is evaluated only over the declared window and error budget; a `completion_timeout` is a distinct result, not a silent retry.

### Rejection boundary

Reject on unsupported mode, invalid command shape or non-finite values, state mismatch, missing alignment, missing takeover conditions, rejected mission, unmapped algorithm and unsupported formation. Keep `unsupported_mode`, `invalid_command`, `nonfinite_value`, `state_mismatch`, `not_aligned`, `takeover_required`, `mission_rejected`, `algorithm_unmapped`, `formation_unsupported` and `completion_timeout` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket changes no controller, mission or algorithm code.

1. **RC modes (owner: control maintainer):** extend the #99 seam to the explicit public RC mode list with setup/activation and revocation semantics; requires a native handoff design before node changes.
2. **Controller selection (owner: control maintainer):** close #35 with a frozen comparison budget over the owned PID/UDE/NE modules and their flight configs.
3. **Public experiment mapping (owner: validation maintainer):** freeze the public experiment list with per-item source/version/hash and acceptance owners before any new demo ticket; do not infer coverage from upstream directory names.
4. **Formation slice (owner: mission maintainer):** no owned formation source exists; requires a joint-scene authority decision and per-vehicle identity before implementation.

No current command implements RC modes beyond the seam, controller selection, the demo mapping or formation. Upstream `Modules/` content is source material, not ported capability.

## Non-goals and preserved blockers

- No controller, mission, RC-node or algorithm code is modified by this contract slice.
- #32 and #34 evidence keeps its bounded meaning; #35, #36, #37, #38, #39 and #40 keep their original scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for OPS-10 and for the project.
