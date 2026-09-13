# Full COMM-06 — Mavlink_NoGPS reference behavior contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #133. The GNSS interruption slice is an event seam and does not automatically equal this mode's configuration contract.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:37` — reference interface behavior in the no-GPS scenario.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=COMM-06`, `followup_ids=[133]`; parent #45 (GNSS interruption and state-validity recovery, OPEN).
- `Simulator/wksim_core/gnss_event.py` with `docs/2026-09-09-gnss-event-report.md`: the epoch/run/vehicle-bound GNSS signal-loss event seam with strict source-time and identity rules. It models an interruption event inside a GPS-capable configuration — it neither declares a no-GPS mode nor defines positioning without GPS.
- Missing: the mode's assumed sensor set, positioning/estimation conditions and validity, the legal control modes without GPS, and observed reference behavior.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| COMM-06-A | Mode sensor set | `blocked`: unpinned | Declared sensor set with GPS absent |
| COMM-06-B | Positioning conditions | `blocked`: undefined | Positioning source and validity conditions without GPS |
| COMM-06-C | Control conditions | `blocked`: undefined | Legal control modes/commands without GPS, per path |
| COMM-06-D | Fault/mode distinction | `partial`: GNSS event seam exists | Mode declared as configuration; the fault seam stays an event |
| COMM-06-E | Reference behavior | `blocked`: unobserved | Captured reference interface behavior in the mode |

## Mode contract

A Mavlink_NoGPS configuration must declare:

```text
mode_id, sensor_set, positioning_source, validity_conditions,
permitted_control_modes, epoch, run_id, vehicle_id, source_identity
```

A GNSS interruption event inside a GPS-capable configuration is not the no-GPS mode. Mode legality is declared per control path; a control mode that requires GPS positioning is denied explicitly, not failed mid-flight. If GPS data appears in a declared no-GPS session, that is `gps_present` — a contract violation, not a bonus.

### Lifecycle

```text
declare mode and sensor set → validate positioning source and validity
→ admit only permitted control modes → run with explicit validity reporting
→ stop → reset re-declares the mode under a new epoch
```

`accepted` means the configuration is consistent and admitted. It does not mean the estimate converged, a control mode is safe, or the reference program would behave identically.

### Rejection boundary

Reject on GPS presence in the mode, unavailable positioning, denied control modes, unknown validity, foreign epochs and unsupported configurations. Keep `gps_present`, `positioning_unavailable`, `control_mode_denied`, `validity_unknown`, `foreign_epoch` and `unsupported_configuration` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket declares no mode and starts no run.

1. **Mode freeze (owner: protocol maintainer):** pin the sensor set, positioning conditions and validity from reference observation.
2. **Control matrix (owner: control maintainer):** declare per-path control legality without GPS and audit against it.
3. **Live slice (owner: runtime maintainer):** run one no-GPS session reusing the GNSS seam's identity/time rules without relabelling the fault event as the mode.

No current command implements or observes Mavlink_NoGPS, so none is claimed here.

## Non-goals and preserved blockers

- No mode, sensor model or control change is implemented by this contract slice.
- #45 keeps its open scope; its seam remains a bounded fault event.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for COMM-06 and for the project.
