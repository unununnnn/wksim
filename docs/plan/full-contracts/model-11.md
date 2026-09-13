# Full MODEL-11 — Trailer model contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #145. A trailer is defined by its joint to a host vehicle and scene coupling; standalone vehicle evidence never substitutes.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:56` — Trailer; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-11`, `followup_ids=[145]`; parent #1 (Wayfinder, OPEN).
- The owned core contains multicopter dynamics only; no hitch/joint articulation, host-vehicle coupling or scene-coupled ground condition exists.
- Scene coupling depends on the OPS-07 environment contract (defined, not implemented).

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-11-A | Towing/joint model | `blocked`: none | Hitch articulation with angle limits and coupling forces |
| MODEL-11-B | Scene-coupled conditions | `blocked`: none | Slope/obstacle/turn conditions with expected responses |
| MODEL-11-C | Host vehicle dependency | `blocked`: undeclared | Declared host identity; no standalone trailer runs |
| MODEL-11-D | Non-coverage rule | `partial`: rule fixed here | Single-vehicle evidence never recorded as towing coverage |

## Model contract

A trailer model must declare:

```text
model_identity, vehicle_class=trailer, host_vehicle, hitch_joint,
articulation_limits, mass_kg, inertia, scene_requirements,
source, source_sha256
```

The hitch joint carries angle limits and coupling forces with units. A trailer run without a declared host is `host_missing`. Scene coupling (slope, obstacles) uses the OPS-07 environment contract; missing scene support is `scene_unavailable`.

### Lifecycle

```text
pin model source → declare host vehicle and hitch joint
→ define articulation limits → run scene-coupled conditions
→ record identity and results for host and trailer
```

`accepted` means the joint and coupling conditions are defined and evidenced. It does not mean numerical agreement with any reference.

### Rejection boundary

Reject on missing model, missing host, invalid joint, exceeded articulation, unavailable scene and substitution. Keep `model_not_found`, `host_missing`, `joint_invalid`, `articulation_exceeded`, `scene_unavailable` and `substitution_rejected` distinct.

## Evidence-backed follow-up slices

1. **Model source (owner: model maintainer):** pin the trailer source and its host vehicle model; requires OPS-07 scene coupling.
2. **Coupling audit (owner: validation maintainer):** audit articulation and coupling forces after the joint freeze.

No current command implements the trailer, so none is claimed here.

## Non-goals and preserved blockers

- No trailer model or condition is implemented by this contract slice.
- OPS-07 keeps its environment dependency; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-11 and for the project.
