# Full MODEL-03 — Tricopter model contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #136. Rotor-count similarity never substitutes for a separate tricopter configuration.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:48` — tricopter; not covered by the quadrotor or hexarotor tickets.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-03`, `followup_ids=[136]`; parent #1 (Wayfinder, OPEN).
- `Simulator/wksim_core/model_parameters.py` fixes a Quad X component record and `Simulator/wksim_runtime/hex-flight-v1.json` fixes a Hex identity — neither defines a tricopter's geometry, tail servo or tests.
- Missing: the tricopter configuration, motor/servo actuation mapping, owned dynamics model and test definition.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-03-A | Configuration definition | `blocked`: none | Three-rotor-plus-tail-servo geometry, mass, inertia |
| MODEL-03-B | Drive/servo mapping | `blocked`: none | Motor and servo mapping with units, signs, limits |
| MODEL-03-C | Model and test definition | `blocked`: none | Owned dynamics model with expected-response tests |
| MODEL-03-D | Non-coverage rule | `partial`: rule fixed here | Quad/hex evidence never recorded as tricopter coverage |

## Model contract

A tricopter model must declare:

```text
model_identity, configuration, rotor_geometry, servo_mapping,
mass_kg, inertia, source, source_sha256, applicable_stacks,
test_definition
```

The tail servo is part of the actuation contract: yaw authority through the servo is modeled and tested, not approximated by a quad/hex mixing matrix. Applicable flight stacks are declared per configuration; absence of a stack mapping is `stack_unsupported`.

### Lifecycle

```text
pin configuration source → define geometry/inertia → map motors and servo
→ implement owned dynamics → run defined tests → record identity and results
```

`accepted` means the configuration, mapping and tests are defined and evidenced. It does not mean numerical agreement with any reference.

### Rejection boundary

Reject on missing model, invalid configuration, unmapped servo, invalid inertia, unsupported stacks and quad/hex substitution. Keep `model_not_found`, `configuration_invalid`, `servo_unmapped`, `inertia_invalid`, `stack_unsupported` and `substitution_rejected` distinct.

## Evidence-backed follow-up slices

1. **Configuration (owner: model maintainer):** pin the tricopter source and parameters, then implement the owned model with tests.
2. **Servo slice (owner: physics maintainer):** validate the tail-servo yaw path explicitly after the mapping freeze.

No current command implements the tricopter, so none is claimed here.

## Non-goals and preserved blockers

- No tricopter model or test is implemented by this contract slice.
- Quad X and Hex evidence keeps its separate identity; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-03 and for the project.
