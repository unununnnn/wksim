# Full MODEL-13 — MulticopterNOpx4 model contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #147. The mode is defined by observed reference behavior and a pinned interface, never by name inference.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:58` — MulticopterNOpx4; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-13`, `followup_ids=[147]`; parent #1 (Wayfinder, OPEN).
- Owned evidence covers PX4/ArduCopter SITL paths only; nothing in this checkout defines this mode's model interface or accepted control method, and the reference behavior is unobserved.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-13-A | Interface definition | `blocked`: unpinned | Inputs, outputs, units and rate pinned from the reference |
| MODEL-13-B | Applicable control method | `blocked`: undefined | The accepted control method from reference evidence |
| MODEL-13-C | PX4 independence | `partial`: rule fixed here | PX4 SITL evidence never recorded as this mode |
| MODEL-13-D | Reference observation | `blocked`: unobserved | Captured reference behavior before implementation |

## Model contract

A MulticopterNOpx4 run must declare:

```text
model_identity, interface_schema, control_method, rate_hz, units,
reference_evidence, source, source_sha256
```

Until the reference observation exists, the interface stays `interface_unpinned` and the control method `control_method_unknown`; any implementation guessed from the name is `name_inference_rejected`. PX4 SITL results are `px4_substitution_rejected` here.

### Lifecycle

```text
observe the reference mode → pin the interface and control method
→ implement against the pinned schema → audit against the reference capture
```

`accepted` means the interface and control method match the observed reference. It does not mean PX4 compatibility.

### Rejection boundary

Reject on unpinned interfaces, unknown control methods, unobserved references, PX4 substitution and name inference. Keep `interface_unpinned`, `control_method_unknown`, `reference_unobserved`, `px4_substitution_rejected` and `name_inference_rejected` distinct.

## Evidence-backed follow-up slices

1. **Reference observation (owner: validation maintainer):** capture the reference mode's interface and behavior first.
2. **Interface freeze (owner: protocol maintainer):** pin the schema from the capture, then implement.

No current command implements or observes MulticopterNOpx4, so none is claimed here.

## Non-goals and preserved blockers

- No interface or control path is implemented by this contract slice.
- PX4 SITL evidence keeps its separate mode identity; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-13 and for the project.
