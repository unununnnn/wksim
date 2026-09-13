# Full MODEL-07 (compound wing) — Compound-wing model contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #141, the compound-wing half of ledger row MODEL-07. Compound-wing coverage requires both actuator sets and the transition regime; neither multicopter nor fixed-wing evidence alone covers it.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:52` — fixed-wing and compound wing; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-07`, `followup_ids=[140, 141]`; parent #1 (Wayfinder, OPEN).
- Owned evidence covers multicopters only; no compound-wing model source, combined actuator mapping or transition condition exists in this checkout.
- Gap per the ticket: model source, control stack/actuators and flight conditions are missing, and a plain multicopter stack must not be forced into the role.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-07-VW-A | Model source | `blocked`: none | Pinned source with aerodynamic and propulsion parameters |
| MODEL-07-VW-B | Lift+rotor actuation | `blocked`: none | Both actuator sets mapped with units and limits |
| MODEL-07-VW-C | Transition conditions | `blocked`: none | Hover/transition/cruise conditions with expected responses |
| MODEL-07-VW-D | No forced ArduCopter | `partial`: rule fixed here | Audits rejecting plain-multicopter substitution |

## Model contract

A compound-wing model must declare:

```text
model_identity, vehicle_class=compound_wing, aerodynamic_parameters,
rotor_set, surface_set, control_stack, transition_conditions,
source, source_sha256
```

The transition regime (hover→cruise and back) is part of the model contract with declared conditions and expected responses. The control stack must support both actuator sets; a plain multicopter stack is `stack_incompatible`.

### Lifecycle

```text
pin model source → map both actuator sets → declare control stack
→ run hover/transition/cruise conditions → record identity and results
```

`accepted` means source, actuators, stack and transition conditions are defined and evidenced. It does not mean numerical agreement with any reference.

### Rejection boundary

Reject on missing model, unpinned source, unmapped actuators, incompatible stacks, undefined transition and substitution. Keep `model_not_found`, `source_unpinned`, `actuator_unmapped`, `stack_incompatible`, `transition_undefined` and `substitution_rejected` distinct.

## Evidence-backed follow-up slices

1. **Model source (owner: model maintainer):** select and pin the compound-wing model source with license.
2. **Transition slice (owner: physics maintainer):** define and audit the transition conditions after the actuator mapping freeze.

No current command implements the compound wing, so none is claimed here.

## Non-goals and preserved blockers

- No compound-wing model or condition is implemented by this contract slice.
- The fixed-wing is handled under #140 on the same row; multicopter evidence keeps its scope; #1 keeps its state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-07 (compound wing) and for the project.
