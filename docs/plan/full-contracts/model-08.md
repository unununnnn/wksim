# Full MODEL-08 — CarAckerman model contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #142. A ground vehicle's acceptance requires terrain/contact feedback; aerial multicopter evidence never substitutes.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:53` — CarAckerman; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-08`, `followup_ids=[142]`; parent #1 (Wayfinder, OPEN).
- The owned core contains multicopter dynamics only (`Simulator/wksim_core/model_parameters.py`, fixed Quad X); no Ackermann steering/drive interface, wheel geometry or ground condition exists.
- Terrain/contact feedback is a contract under OPS-07 (`docs/plan/full-contracts/ops-07.md`), not an implementation — a ground vehicle depends on it.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-08-A | Steering/drive interface | `blocked`: none | Ackermann steering and drive interfaces with units, limits, rates |
| MODEL-08-B | Trajectory conditions | `blocked`: none | Defined trajectory conditions with expected responses |
| MODEL-08-C | Terrain conditions | `blocked`: none | Terrain interaction conditions tied to OPS-07 |
| MODEL-08-D | Ground contact dependency | `partial`: rule recorded | Contact/terrain feedback prerequisite explicit |

## Model contract

A CarAckerman model must declare:

```text
model_identity, vehicle_class=car_ackerman, steering_interface,
drive_interface, wheel_geometry, mass_kg, inertia,
terrain_requirements, source, source_sha256
```

Steering angle and drive commands carry units, limits and rate semantics. Ground contact comes from the OPS-07 environment contract; running a ground vehicle against a missing terrain query is `terrain_unavailable`, not free-flight.

### Lifecycle

```text
pin model source → map steering/drive interfaces → declare terrain
requirements → run trajectory and terrain conditions → record identity
```

`accepted` means the interfaces and conditions are defined and evidenced. It does not mean numerical agreement with any reference vehicle.

### Rejection boundary

Reject on missing model, unmapped interfaces, undefined trajectories, unavailable terrain and aerial substitution. Keep `model_not_found`, `interface_unmapped`, `trajectory_undefined`, `terrain_unavailable` and `substitution_rejected` distinct.

## Evidence-backed follow-up slices

1. **Model source (owner: model maintainer):** select and pin the Ackermann model source; requires the OPS-07 static query seam for contact.
2. **Conditions (owner: physics maintainer):** define and audit the trajectory/terrain conditions after the source freeze.

No current command implements CarAckerman, so none is claimed here.

## Non-goals and preserved blockers

- No vehicle model or condition is implemented by this contract slice.
- OPS-07 keeps its environment dependency; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-08 and for the project.
