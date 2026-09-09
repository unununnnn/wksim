# Full MODEL-06 — Octorotor model contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #139. Rotor-count adjacency never substitutes for the octorotor's own configuration and stack validation.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:51` — octorotor; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-06`, `followup_ids=[139]`; parent #1 (Wayfinder, OPEN).
- Owned multicopter evidence covers Quad X (`model_parameters.py`) and a planar Hex (`hex-flight-v1.json`) only; no planar octorotor configuration exists.
- Missing: the octorotor configuration and per-stack applicability validation.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-06-A | Configuration | `blocked`: none | Independent geometry, mass and inertia |
| MODEL-06-B | Applicable FC validation | `blocked`: none | Per-stack support validated |
| MODEL-06-C | Non-coverage rule | `partial`: rule fixed here | Quad/Hex/X8 evidence never recorded as octorotor coverage |

## Model contract

An octorotor model must declare:

```text
model_identity, configuration, rotor_geometry, allocation_matrix,
mass_kg, inertia, source, source_sha256, applicable_stacks
```

Each applicable flight stack is validated against the configuration; an unlisted stack is `stack_unsupported`, and adjacent multicopter evidence is `substitution_rejected` here.

### Lifecycle

```text
pin configuration source → define geometry/inertia/allocation
→ validate applicable stacks → implement owned dynamics
→ run defined tests → record identity and results
```

`accepted` means the configuration and stack mapping are defined and evidenced. It does not mean numerical agreement with any reference.

### Rejection boundary

Reject on missing model, invalid configuration, unsupported stacks and substitution. Keep `model_not_found`, `configuration_invalid`, `stack_unsupported` and `substitution_rejected` distinct.

## Evidence-backed follow-up slices

1. **Configuration (owner: model maintainer):** pin the octorotor source and parameters, then implement the owned model.
2. **Stack audit (owner: validation maintainer):** validate per-stack applicability after the freeze.

No current command implements the octorotor, so none is claimed here.

## Non-goals and preserved blockers

- No octorotor model or test is implemented by this contract slice.
- Quad X, Hex and X8 evidence keeps separate identities; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-06 and for the project.
