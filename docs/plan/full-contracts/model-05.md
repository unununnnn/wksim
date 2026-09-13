# Full MODEL-05 — Quad-axis octorotor (X8) contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #138. Eight rotors on four axes is a distinct configuration, not a quadrotor with doubled motors.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:50` — quad-axis octorotor; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-05`, `followup_ids=[138]`; parent #1 (Wayfinder, OPEN).
- `Simulator/wksim_core/model_parameters.py` fixes a Quad X record (`motor_count=4`); no X8 configuration, propulsion parameters or mixing matrix exists in the owned core.
- Missing: the X8 configuration, propulsion model and mixing validation.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-05-A | Configuration | `blocked`: none | Independent X8 geometry with eight rotors on four axes |
| MODEL-05-B | Propulsion | `blocked`: none | Propulsion model and parameters with source/hash |
| MODEL-05-C | Mixing validation | `blocked`: none | Allocation validation for the X8 layout |
| MODEL-05-D | Non-coverage rule | `partial`: rule fixed here | Quad/octorotor evidence never recorded as X8 coverage |

## Model contract

An X8 model must declare:

```text
model_identity, configuration, rotor_geometry, propulsion_parameters,
allocation_matrix, mass_kg, inertia, source, source_sha256,
applicable_stacks
```

The mixing matrix is validated for the X8 layout explicitly; a scaled quadrotor matrix is `substitution_rejected`. Applicable flight stacks are declared per configuration.

### Lifecycle

```text
pin configuration source → define geometry and propulsion
→ derive and validate the allocation matrix → implement owned dynamics
→ run defined tests → record identity and results
```

`accepted` means the configuration, propulsion and mixing are defined and evidenced. It does not mean numerical agreement with any reference.

### Rejection boundary

Reject on missing model, invalid configuration or propulsion, unvalidated mixing and substitution. Keep `model_not_found`, `configuration_invalid`, `propulsion_invalid`, `mixing_unvalidated` and `substitution_rejected` distinct.

## Evidence-backed follow-up slices

1. **Configuration (owner: model maintainer):** pin the X8 source and parameters, then implement the owned model.
2. **Mixing audit (owner: validation maintainer):** validate the X8 allocation explicitly after the freeze.

No current command implements the X8, so none is claimed here.

## Non-goals and preserved blockers

- No X8 model or test is implemented by this contract slice.
- Quad X evidence keeps its separate identity; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-05 and for the project.
