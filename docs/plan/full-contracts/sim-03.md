# Full SIM-03 — PX4_SITL_RFLY mode contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #123. A standard PX4 pass is never recorded as this mode passing.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:15` — Rfly-custom PX4 software-in-the-loop over UDP.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=SIM-03`, `followup_ids=[123]`; parent #1 (Wayfinder, OPEN).
- `docs/project-isolation.md` pins the standard PX4 source (`d6f12ad1…`) and firmware SHA256; `Simulator/wksim_core/px4_mavlink.py` is the owned standard-PX4 feed. No RFly-custom firmware is pinned anywhere in this checkout.
- Missing: the local custom firmware identity, its UDP protocol differences versus standard PX4 SITL, and its license/use conditions.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| SIM-03-A | Custom firmware identity | `blocked`: nothing pinned | Source, commit and SHA256 of the RFly-custom build |
| SIM-03-B | Protocol differences | `blocked`: unknown | Per-field UDP protocol delta versus standard PX4 SITL |
| SIM-03-C | Use conditions | `blocked`: undetermined | License/permission and configuration conditions |
| SIM-03-D | Non-substitution rule | `partial`: rule fixed here | Audits rejecting standard-PX4 substitution |

## Mode contract

Every PX4_SITL_RFLY run must declare:

```text
mode_id, transport=UDP, custom_firmware_identity (source/commit/SHA256),
protocol_delta (per field versus standard), use_conditions,
model_identity, epoch, source_identity
```

Only the pinned RFly-custom firmware on its pinned protocol can evidence this mode. Standard PX4 results — however complete — are `standard_substitution_rejected` when presented as this mode.

### Lifecycle

```text
pin custom firmware → pin protocol delta → record use conditions
→ run with firmware identity in every record → audit against substitution
```

`accepted` means the run used the pinned custom firmware and protocol. It does not mean standard PX4 behavior matched or that use conditions permit distribution.

### Rejection boundary

Reject on unpinned firmware, unknown protocol delta, unmet use conditions, standard substitution and foreign epochs. Keep `firmware_unpinned`, `protocol_delta_unknown`, `conditions_unmet`, `standard_substitution_rejected` and `foreign_epoch` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket pins no firmware and starts no session.

1. **Firmware pin (owner: build maintainer):** locate, pin and license-check the local RFly-custom firmware.
2. **Protocol delta (owner: protocol maintainer):** pin the per-field UDP protocol delta from observation of the pinned firmware.

No current command implements or verifies PX4_SITL_RFLY, so none is claimed here.

## Non-goals and preserved blockers

- No firmware is fetched, pinned or run by this contract slice.
- Standard PX4 evidence keeps its own mode identity; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for SIM-03 and for the project.
