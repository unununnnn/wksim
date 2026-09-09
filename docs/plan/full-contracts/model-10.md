# Full MODEL-10 — CarNoCtrl model contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #144. No-controller acceptance exercises the model directly; FC-based evidence is a different mode.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:55` — CarNoCtrl; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-10`, `followup_ids=[144]`; parent #1 (Wayfinder, OPEN).
- The owned core contains multicopter dynamics driven through flight-controller SITL; no direct-input ground vehicle model or observation path exists.
- Ground contact depends on the OPS-07 environment contract, which is defined but not implemented.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-10-A | Direct input interface | `blocked`: none | Direct inputs with units, limits, identity — no FC |
| MODEL-10-B | Model observation | `blocked`: none | Truth observation outputs under direct inputs |
| MODEL-10-C | FC independence | `partial`: rule fixed here | Acceptance never starts or requires a flight controller |
| MODEL-10-D | Terrain dependency | `blocked`: OPS-07 unimplemented | Ground contact through the environment contract |

## Model contract

A CarNoCtrl model must declare:

```text
model_identity, vehicle_class=car_noctrl, input_schema,
observation_schema, mass_kg, inertia, terrain_requirements,
source, source_sha256
```

Inputs drive the model directly; any requirement to boot a flight controller for this mode is `fc_required_rejected`. Observations are truth outputs with identity and units — not FC telemetry.

### Lifecycle

```text
pin model source → declare input and observation schemas
→ drive direct inputs → observe truth outputs → record identity
```

`accepted` means direct inputs produce observed truth per the schemas without any FC. It does not mean numerical agreement with any reference vehicle.

### Rejection boundary

Reject on missing model, invalid input, missing observation, FC requirements and unavailable terrain. Keep `model_not_found`, `input_invalid`, `observation_missing`, `fc_required_rejected` and `terrain_unavailable` distinct.

## Evidence-backed follow-up slices

1. **Model source (owner: model maintainer):** select and pin the model source; requires the OPS-07 static query seam.
2. **Observation slice (owner: physics maintainer):** implement the direct-input model with truth observation and tests.

No current command implements CarNoCtrl, so none is claimed here.

## Non-goals and preserved blockers

- No vehicle model or observation path is implemented by this contract slice.
- OPS-07 keeps its environment dependency; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-10 and for the project.
