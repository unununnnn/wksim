# Full MODEL-09 — CarR1Diff model contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #143. Differential drive is defined by its wheel mapping and reset conditions; steering-geometry evidence never substitutes.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:54` — CarR1Diff; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-09`, `followup_ids=[143]`; parent #1 (Wayfinder, OPEN).
- The owned core contains multicopter dynamics only; no differential wheel mapping, ground motion condition or reset semantics exists.
- Terrain/contact feedback is a contract under OPS-07, not an implementation — a ground vehicle depends on it.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-09-A | Differential mapping | `blocked`: none | Left/right wheel drive mapping with units, signs, limits |
| MODEL-09-B | Motion conditions | `blocked`: none | Straight/turn/pivot conditions with expected responses |
| MODEL-09-C | Reset conditions | `blocked`: none | Declared reset semantics to a known state |
| MODEL-09-D | Non-coverage rule | `partial`: rule fixed here | Ackermann/aerial evidence never recorded as differential coverage |

## Model contract

A CarR1Diff model must declare:

```text
model_identity, vehicle_class=car_r1_diff, wheel_mapping,
wheel_geometry, mass_kg, inertia, reset_semantics,
terrain_requirements, source, source_sha256
```

Wheel commands carry units, signs and limits; pivot-in-place behavior is an explicit test condition, not an emergent assumption. Reset returns the vehicle to a declared state — position, heading, velocities — with identity recorded. Ground contact comes from the OPS-07 contract; missing terrain is `terrain_unavailable`.

### Lifecycle

```text
pin model source → map wheel drive → define motion and reset conditions
→ run conditions against terrain → record identity and results
```

`accepted` means the mapping and conditions are defined and evidenced. It does not mean numerical agreement with any reference vehicle.

### Rejection boundary

Reject on missing model, invalid wheel mapping, undefined conditions, failed reset, unavailable terrain and substitution. Keep `model_not_found`, `wheel_mapping_invalid`, `condition_undefined`, `reset_failed`, `terrain_unavailable` and `substitution_rejected` distinct.

## Evidence-backed follow-up slices

1. **Model source (owner: model maintainer):** select and pin the differential-drive source; requires the OPS-07 static query seam.
2. **Conditions (owner: physics maintainer):** define and audit motion/reset conditions after the mapping freeze.

No current command implements CarR1Diff, so none is claimed here.

## Non-goals and preserved blockers

- No vehicle model or condition is implemented by this contract slice.
- OPS-07 keeps its environment dependency; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-09 and for the project.
