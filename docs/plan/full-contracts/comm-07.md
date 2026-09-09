# Full COMM-07 — Mavlink_Vision positioning output contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #134. A camera image with pose metadata is not a vision-position estimate, and the #30 RGB path is not evidence for this mode.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:38` — vision positioning data output.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=COMM-07`, `followup_ids=[134]`; the ticket names #1 and #30 (real RGB camera, CLOSED).
- `Simulator/ue55/rgb.py` and `docs/rgb-capture-component.md`: the calibrated, epoch-bound RGB capture path with applied-pose metadata and strict step/time identity. It produces images with capture context — no vision-position estimate, covariance, or estimator-facing message.
- Missing: the pinned vision positioning message set, frame/covariance/sample-time semantics and the per-stack estimator integration contract.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| COMM-07-A | Vision message set | `blocked`: unpinned | Pinned message(s) with field map from a fixed dialect source |
| COMM-07-B | Coordinate/covariance | `blocked`: undefined | Frame, units and covariance semantics validated |
| COMM-07-C | Sampling time | `blocked`: undefined | Sample time versus authoritative sim time pinned |
| COMM-07-D | Estimator integration | `blocked`: undefined | Per-stack estimator input contract with acceptance/rejection evidence |
| COMM-07-E | Capture path distinction | `partial`: #30 RGB path exists with pose metadata | Image evidence never substitutes for an estimate message |

## Message contract

Every vision positioning output must resolve against:

```text
message_id, message_name, dialect, dialect_sha256, coordinate_frame,
units, covariance, sample_time_ns, sample_timebase, estimator_target,
vehicle_id, epoch, source_identity
```

The sample time is the acquisition/estimation instant under its declared timebase — never the message send time or an inferred wall clock. Covariance is mandatory semantics: an estimate without declared covariance is `covariance_invalid`, not "zero covariance". Estimator acceptance is proven per supported stack; a parsed message is not an integrated estimate.

### Lifecycle

```text
pin message set and dialect → declare frame/units/covariance semantics
→ bind sample timebase → emit estimates with identity
→ estimator admits or rejects per contract → audit both outcomes
```

`accepted` means the message conforms to the pinned contract. It does not mean the estimator fused it or the vehicle's estimate improved.

### Rejection boundary

Reject on unknown messages, frame mismatch, invalid covariance, unknown time semantics, estimator rejection, stale samples and image-as-estimate confusion. Keep `unknown_message`, `frame_mismatch`, `covariance_invalid`, `time_semantics_unknown`, `estimator_rejected`, `stale_sample` and `image_not_estimate` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket emits no estimate and starts no estimator.

1. **Message freeze (owner: protocol maintainer):** pin the vision message set and field map from a fixed dialect source.
2. **Estimator contract (owner: control maintainer):** define per-stack estimator input requirements with acceptance/rejection evidence.
3. **Live slice (owner: UE/validation maintainer):** derive one estimate path from the existing capture seam into the frozen message contract; the RGB image path remains image evidence.

No current command implements or verifies Mavlink_Vision, so none is claimed here.

## Non-goals and preserved blockers

- No vision message, covariance semantics or estimator integration is implemented by this contract slice.
- #30 keeps its closed bounded meaning as image capture; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for COMM-07 and for the project.
