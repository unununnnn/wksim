# Full MODEL-14 — CopterSILVelCtrl workflow contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #148. SIL velocity control closes the loop around the model without a flight controller; real-FC velocity evidence is a different ticket.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:59` — CopterSILVelCtrl; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-14`, `followup_ids=[148]`; parent #1 (Wayfinder, OPEN).
- `Simulator/wksim_control/position_pid.py`, `position_ude.py`, `position_ne.py`: owned controller modules with frozen flight configs (`pid/ude/ne-flight-v1.json`) — candidates for the SIL loop, currently exercised through FC-driven flights.
- #32 (closed) verified dual-stack velocity/yaw through real flight controllers — a different ticket that never covers this pure-model workflow.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-14-A | SIL velocity workflow | `blocked`: none | Reference→controller→model→truth loop without an FC |
| MODEL-14-B | FC velocity distinction | `partial`: rule fixed here | #32 evidence never recorded as this workflow |
| MODEL-14-C | Controller reuse | `partial`: owned modules exist | Reuse with identity and budgets preserved |
| MODEL-14-D | Workflow acceptance | `blocked`: undefined | Conditions and pass criteria frozen, then met |

## Workflow contract

A CopterSILVelCtrl run must declare:

```text
workflow_id, model_identity, controller_identity,
reference_input_schema, truth_feedback_schema, conditions,
pass_criteria, epoch, source_identity
```

The loop closes against model truth, not FC telemetry. Pass criteria are frozen before the run; meeting them is evidence for this workflow only and says nothing about any real-FC velocity behavior.

### Lifecycle

```text
declare workflow, conditions and pass criteria → bind controller and model
→ run reference inputs → evaluate truth against criteria
→ record identity and results
```

`accepted` means the loop ran under the frozen criteria and passed. It does not mean any FC-in-the-loop behavior.

### Rejection boundary

Reject on missing model, unbound controller, undefined conditions, unmet criteria and FC substitution. Keep `model_not_found`, `controller_unbound`, `condition_undefined`, `criteria_unmet` and `fc_substitution_rejected` distinct.

## Evidence-backed follow-up slices

1. **SIL loop (owner: control maintainer):** wire an owned controller to the owned model without an FC, after freezing conditions and criteria.
2. **Acceptance audit (owner: validation maintainer):** run and record the frozen conditions.

No current command implements CopterSILVelCtrl, so none is claimed here.

## Non-goals and preserved blockers

- No SIL loop is implemented by this contract slice.
- #32 and the controller flight configs keep their bounded meaning; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-14 and for the project.
