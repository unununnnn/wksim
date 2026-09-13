# Full MODEL-07 (fixed-wing) — Fixed-wing model contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #140, the fixed-wing half of ledger row MODEL-07. A multicopter stack is never a fixed-wing controller.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:52` — fixed-wing and compound wing; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-07`, `followup_ids=[140, 141]`; parent #1 (Wayfinder, OPEN).
- Owned evidence covers multicopters only (Quad X, Hex); no fixed-wing model source, aerodynamic parameters or actuator set exists in this checkout.
- Gap per the ticket: model source, control stack/actuators and flight conditions are missing; ArduCopter must not be forced to control a fixed-wing.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-07-FW-A | Model source | `blocked`: none | Pinned source with airfoil/aerodynamic parameters |
| MODEL-07-FW-B | Control stack/actuators | `blocked`: none | Declared fixed-wing-capable stack and actuator set |
| MODEL-07-FW-C | Flight conditions | `blocked`: none | Airspeed/stall/coordinated-turn conditions with expected responses |
| MODEL-07-FW-D | No forced ArduCopter | `partial`: rule fixed here | Audits rejecting multicopter-stack substitution |

## Model contract

A fixed-wing model must declare:

```text
model_identity, vehicle_class=fixed_wing, aerodynamic_parameters,
actuator_set (aileron/elevator/rudder/throttle), control_stack,
flight_conditions, source, source_sha256
```

Lift, drag and stall semantics belong to the fixed-wing model with pinned parameters. The control stack must be fixed-wing-capable; wiring ArduCopter to a fixed-wing is `stack_incompatible`/`substitution_rejected`, never a shortcut to coverage.

### Lifecycle

```text
pin model source → define aerodynamics and actuators → declare control stack
→ run defined flight conditions → record identity and results
```

`accepted` means source, actuators, stack and conditions are defined and evidenced. It does not mean numerical agreement with any reference.

### Rejection boundary

Reject on missing model, unpinned source, unmapped actuators, incompatible stacks, undefined conditions and substitution. Keep `model_not_found`, `source_unpinned`, `actuator_unmapped`, `stack_incompatible`, `condition_undefined` and `substitution_rejected` distinct.

## Evidence-backed follow-up slices

1. **Model source (owner: model maintainer):** select and pin the fixed-wing model source with license.
2. **Stack and conditions (owner: control maintainer):** declare the control stack/actuators and the flight-condition set, then audit.

No current command implements the fixed-wing, so none is claimed here.

## Non-goals and preserved blockers

- No fixed-wing model or condition is implemented by this contract slice.
- The compound wing is handled under #141 on the same row; multicopter evidence keeps its scope; #1 keeps its state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-07 (fixed-wing) and for the project.
