# Full MODEL-04 — Tri-axis hexarotor (coaxial Y6) contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #137. A planar hexarotor allocation never approximates coaxial rotor interaction.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:49` — tri-axis hexarotor; not covered by the planar hexarotor.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-04`, `followup_ids=[137]`; parent #1 (Wayfinder, OPEN).
- `Simulator/wksim_runtime/hex-flight-v1.json` pins a planar Hex identity (`hex_x`); it has no coaxial rotor pairs, so it cannot evidence this configuration.
- Missing: coaxial geometry, per-rotor rotation signs, the allocation matrix and concrete parameters with source and hash.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-04-A | Coaxial configuration | `blocked`: none | Coaxial rotor pair geometry with stack order |
| MODEL-04-B | Rotation directions | `blocked`: none | Per-rotor signs including coaxial pairs |
| MODEL-04-C | Motor allocation | `blocked`: none | Allocation/mixing matrix for the coaxial layout |
| MODEL-04-D | Concrete parameters | `blocked`: none | Mass, inertia, propulsion parameters with source/hash |
| MODEL-04-E | Non-coverage rule | `partial`: rule fixed here | Planar hex evidence never recorded as Y6 coverage |

## Model contract

A coaxial Y6 model must declare:

```text
model_identity, coaxial_geometry, rotation_signs, allocation_matrix,
mass_kg, inertia, propulsion_parameters, source, source_sha256,
applicable_stacks
```

Coaxial pairs share an axis with explicit upper/lower ordering; their aerodynamic interaction is either modeled from a pinned source or declared unmodeled — never silently inherited from a planar allocation.

### Lifecycle

```text
pin configuration source → define coaxial geometry and signs
→ derive the allocation matrix → implement owned dynamics
→ run defined tests → record identity and results
```

`accepted` means the configuration, signs, allocation and parameters are defined and evidenced. It does not mean numerical agreement with any reference.

### Rejection boundary

Reject on missing model, invalid geometry, rotation-sign mismatch, invalid allocation, missing parameters and planar-hex substitution. Keep `model_not_found`, `geometry_invalid`, `rotation_sign_mismatch`, `allocation_invalid`, `parameters_missing` and `substitution_rejected` distinct.

## Evidence-backed follow-up slices

1. **Configuration (owner: model maintainer):** pin the coaxial source and parameters, then implement the owned model with tests.
2. **Allocation audit (owner: validation maintainer):** validate the coaxial allocation matrix and rotation signs explicitly.

No current command implements the coaxial Y6, so none is claimed here.

## Non-goals and preserved blockers

- No Y6 model or test is implemented by this contract slice.
- The planar Hex identity keeps its separate configuration; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-04 and for the project.
