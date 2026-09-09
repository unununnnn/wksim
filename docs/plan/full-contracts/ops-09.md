# Full OPS-09 — Fault contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #160. It does not promote one GNSS interruption seam or one planned motor-efficiency experiment into the public fault scope.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:77`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-09`, `followup_ids=[160]`; parents #44 (reproducible single-motor efficiency fault, OPEN with children #105–#108) and #45 (GNSS interruption and state-validity recovery, OPEN).
- `Simulator/wksim_core/gnss_event.py` with `docs/2026-09-09-gnss-event-report.md`: `GnssEventPlan` bound to run/epoch/vehicle over authoritative 1 ms tick intervals, `GnssSample` preserving source identity, sequence, source tick and all 13 HIL_GPS integer fields, `GnssEventController.decide` returning immutable `GnssDecision` records, explicit `signal_loss`/`invalid_fix`/`stale_source`/`duplicate_or_old_source` results and `reset(new_epoch)`. The report states there is no generic fault framework, wall-clock scheduling or background replay.
- `validation/test_gnss_event.py`, `validation/test_gnss_px4_injection.py` and the `wksim-ap-gnss-109-*` evidence directories cover offline decisions and native-injection candidates for the GNSS event only.
- `Simulator/wksim_runtime/scene_clock.py`: joint fault/suspend semantics with `recoverable` boundaries and explicit recovery; this is input-loss handling, not a fault-injection matrix.
- `Simulator/wksim_runtime/pid_task.py` / `pid-flight-v1.json`: a bounded **effective actuator command multiplier** disturbance used for PID/UDE/NE controller evaluation. It is not a motor stuck/shutdown model and not an environment disturbance.
- No wind/gust/environment disturbance model and no per-sensor bias/freeze model exist in the owned core; no public per-link communication anomaly scope is defined.

## Atomic scope

| ID | Fault capability | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-09-A | Motor stuck/shutdown/efficiency | `partial`: #44 approved one bounded single-motor efficiency experiment; children pending | Fault time, duration, target motor and magnitude in run config and record; truth and FC feedback reflect the change; state clears after reset |
| OPS-09-B | Sensor bias/freeze/loss | `partial`: GNSS signal-loss seam exists with strict time/identity rules; no IMU/baro/mag bias/freeze | Per-sensor bias/freeze/loss events on the sample envelope with distinct results |
| OPS-09-C | Environment disturbance | `blocked`: no owned wind/gust source; the PID disturbance is an actuator multiplier | Owned disturbance source, budget and measured vehicle response |
| OPS-09-D | Communication anomaly | `partial`: joint barrier/fault semantics cover input loss and suspension | Public per-link delay/loss/corruption scope with distinct, replayable results |
| OPS-09-E | Fault plan and injection identity | `partial`: GNSS plan proves epoch/run/vehicle-bound, tick-interval, non-retroactive injection for one type | Same plan contract across fault types; no generic framework is claimed |
| OPS-09-F | Recovery and reset | `partial`: GNSS `reset(new_epoch)` and `SceneClock.recoverable` exist; motor reset pending #108 | Per-event explicit recovery and reset clearing fault state, audited per type |

## Fault event contract

Every injected fault must be a recorded plan containing:

```text
fault_id, fault_type, target_identity (motor index / sensor_id / link_id),
run_id, epoch, vehicle_id, start_tick, end_tick (authoritative 1 ms ticks,
start inclusive, end exclusive), magnitude, injection_point,
decision_tick, result, reason, reset_semantics, source_identity
```

A plan is bound to one run/epoch/vehicle and cannot overwrite, duplicate or retroactively modify processed ticks. A fault **decision record** is not a physical effect: acceptance requires truth and flight-controller feedback reflecting the target change. An actuator-command multiplier used for controller evaluation is not a motor fault and not an environment disturbance.

### Lifecycle

```text
declare plan with explicit target/interval/magnitude → bind run/epoch/vehicle
→ inject at the authoritative boundary → observe truth + FC feedback
→ end or reset per event semantics → explicit recovery; no silent reuse of faulted state
```

`accepted` means the plan is valid and admitted. It does not mean the physical response matched an expectation, the controller recovered, or the vehicle stayed safe. Old epochs stay rejected; a new epoch re-declares plans explicitly.

### Rejection boundary

Reject on unknown fault type or target, foreign epoch, stale or duplicate plan, retroactive tick, invalid magnitude, missing recovery and rejected reset. Keep `fault_not_found`, `foreign_epoch`, `stale_plan`, `duplicate_plan`, `retroactive_tick`, `invalid_target`, `magnitude_out_of_range`, `recovery_required`, `reset_rejected` and `unsupported_fault` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket injects no fault and starts no process.

1. **Motor fault slice (owner: model maintainer):** execute the approved #44 path via #105–#108: one real single-motor efficiency event with config/record identity, truth and FC feedback evidence, same-seed rerun and reset check. Uses the existing fixed-model task entries; requires the approved safety/lost-link and numerical budget.
2. **Sensor fault model (owner: model maintainer):** add bias/freeze/loss for base sensors on the OPS-08 sample envelope. Blocked by the per-sensor calibration/noise/latency budget.
3. **Environment disturbance slice (owner: physics maintainer):** no owned wind/gust source exists; requires an explicit source and budget decision before any implementation ticket.
4. **Communication anomaly audit (owner: runtime maintainer):** define the public per-link anomaly scope and bind it to the existing `SceneClock`/joint barrier lifecycle with distinct results; do not relabel input-loss suspension as a comm fault matrix.

No current command implements the public fault scope. The GNSS seam and SceneClock semantics remain evidence for their bounded slices only.

## Non-goals and preserved blockers

- No motor, sensor-bias, disturbance or communication fault is implemented by this contract slice.
- #44 and #45 remain open with their original acceptance criteria and dependencies; #105–#108 are unaffected.
- The PID/UDE/NE actuator-multiplier disturbance remains a controller-evaluation input, not a fault model.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for OPS-09 and for the project.
