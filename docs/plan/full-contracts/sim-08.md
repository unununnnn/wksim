# Full SIM-08 — APM_SITL_NET mode contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #126. Verified fixed-ArduCopter evidence covers only that vehicle and configuration.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:20` — connecting ArduPilot software-in-the-loop over the network.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=SIM-08`, `followup_ids=[126]`; the ticket names #1, #12 (CLOSED) and #48.
- `tools/validate_sitl_physics.py --stack arducopter` with recorded results and `Simulator/wksim_core/ap_json.py` (the owned AP JSON lockstep feed): fixed-ArduCopter owned-physics product mission verified.
- Gap per the ticket: the APM_SITL_NET reference network operation and stop/reconnect mapping are not itemized; other ArduPilot vehicles cannot substitute.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| SIM-08-A | Owned AP physics | `partial`: recorded validation exists | Sustained thresholds/hashes per configuration |
| SIM-08-B | Native mission | `partial`: verified bounded slice | Evidence preserved as bounded |
| SIM-08-C | NET operation mapping | `blocked`: not itemized | Reference NET operation items verified individually |
| SIM-08-D | Stop/reconnect mapping | `blocked`: unmapped | Reference-aligned stop/reconnect semantics |
| SIM-08-E | Vehicle scope rule | `partial`: rule fixed here | Only the verified ArduCopter configuration evidences this mode |

## Mode contract

Every APM_SITL_NET run must declare:

```text
mode_id, transport, firmware_identity (commit + SHA256),
vehicle_identity, interface_map, stop_semantics, reconnect_semantics,
epoch, source_identity
```

ArduCopter evidence covers only the verified vehicle/configuration; other ArduPilot vehicles and original-program modes are not implied. Each reference operation item — selection, interface set, stop, reconnect — is verified individually.

### Lifecycle

```text
declare mode, firmware and vehicle identity → bind network interface map
→ run under the authoritative clock → stop with recorded semantics
→ reconnect only into a current epoch with fresh identity
```

`accepted` means the declared mode items are individually verified. It does not mean other AP vehicles, other firmware or the original program's NET behavior are covered.

### Rejection boundary

Reject on unsupported mode, firmware mismatch, unverified vehicles, unmapped interfaces, failed stop or reconnect and foreign epochs. Keep `mode_unsupported`, `firmware_mismatch`, `vehicle_unverified`, `interface_unmapped`, `stop_failed`, `reconnect_failed` and `foreign_epoch` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket starts no SITL session.

1. **Mode itemization (owner: protocol maintainer):** freeze the reference NET operation list and verify each item.
2. **Stop/reconnect slice (owner: runtime maintainer):** implement and audit stop/reconnect semantics on the owned path after itemization.

No current command itemizes the reference mode mapping, so none is claimed here.

## Non-goals and preserved blockers

- No mode mapping or lifecycle code is implemented by this contract slice; no SITL session is started.
- #12 and #48 keep their bounded meaning; other ArduPilot vehicles are explicitly out of scope.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for SIM-08 and for the project.
