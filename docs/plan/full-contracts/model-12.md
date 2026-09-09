# Full MODEL-12 — MulticopterNoCtrl model contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #146. No-controller mode drives the model directly; FC-driven flight evidence never substitutes.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:57` — MulticopterNoCtrl; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-12`, `followup_ids=[146]`; parent #1 (Wayfinder, OPEN).
- The owned core (`Simulator/wksim_core/model.py`, `model_parameters.py`) hosts multicopter dynamics driven through PX4/ArduCopter SITL — the model base exists, but every owned run goes through a flight controller; no direct-input path, motion condition set or reset definition exists for this mode.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-12-A | Direct model inputs | `blocked`: none | Direct rotor/actuator inputs without an FC |
| MODEL-12-B | Motion definition | `blocked`: none | Motion conditions with expected truth responses |
| MODEL-12-C | Reset definition | `blocked`: none | Reset semantics to a declared state |
| MODEL-12-D | Owned multicopter base | `partial`: FC-driven dynamics exist | Same model base reusable without relabelling modes |

## Model contract

A MulticopterNoCtrl run must declare:

```text
model_identity, vehicle_class=multicopter_noctrl, input_schema,
motion_conditions, reset_semantics, mass_kg, inertia,
source, source_sha256
```

Inputs drive the model's actuators directly; booting a flight controller for this mode is `fc_required_rejected`. Reset returns position, attitude, velocities and rotor state to declared values — not a pause or a re-arm.

### Lifecycle

```text
declare input schema → drive direct actuator inputs
→ run motion conditions against truth → reset per declared semantics
→ record identity and results
```

`accepted` means direct inputs, motion conditions and reset are defined and evidenced. It does not mean numerical agreement with any reference.

### Rejection boundary

Reject on missing model, invalid input, undefined conditions, failed reset and FC requirements. Keep `model_not_found`, `input_invalid`, `condition_undefined`, `reset_failed` and `fc_required_rejected` distinct.

## Evidence-backed follow-up slices

1. **Direct input (owner: model maintainer):** expose a direct actuator input schema on the owned model with tests.
2. **Reset slice (owner: runtime maintainer):** implement and audit the reset semantics.

No current command implements MulticopterNoCtrl, so none is claimed here.

## Non-goals and preserved blockers

- No direct-input path or reset is implemented by this contract slice.
- FC-driven multicopter evidence keeps its separate mode identity; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-12 and for the project.
