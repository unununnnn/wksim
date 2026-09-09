# Full SIM-02 — PX4_SITL mode contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #122. Verified owned-path PX4 SITL evidence is not the reference mode's operation mapping.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:14` — standard PX4 software-in-the-loop over TCP.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=SIM-02`, `followup_ids=[122]`; the ticket names #1, #12 (dual-stack capability, CLOSED) and #48 (bounded product evidence).
- `tools/validate_sitl_physics.py --stack px4` with the recorded `validation/px4-physics-*` results: owned physics driving the fixed PX4 build with thresholds, versions and hashes on record.
- `Simulator/wksim_core/px4_mavlink.py` and `tools/sitl_dds.py`: the owned PX4 MAVLink feed and the native DDS validation entry behind the verified standalone DDS product mission.
- Gap per the ticket: frozen PX4_SITL TCP mode selection, interfaces and stop/reconnect mapping are not itemized against the reference.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| SIM-02-A | Owned PX4 physics | `partial`: recorded physics validation exists | Sustained thresholds/hashes per run configuration |
| SIM-02-B | Native DDS mission | `partial`: verified bounded slice | Product mission evidence preserved as bounded |
| SIM-02-C | TCP mode selection | `blocked`: not itemized | Frozen mode/interface mapping verified per item |
| SIM-02-D | Stop/reconnect mapping | `blocked`: unmapped | Reference-aligned stop/reconnect semantics |
| SIM-02-E | Product entry | `partial`: owned entry exists | Formal product entry for this reference mode |

## Mode contract

Every PX4_SITL run must declare:

```text
mode_id, transport=TCP, firmware_identity (commit + SHA256),
model_identity, interface_map, stop_semantics, reconnect_semantics,
epoch, source_identity
```

Owned-path success is not the reference mode's operation mapping. Each mode item — selection, interface set, stop, reconnect — is verified individually; an aggregate pass is not itemized evidence.

### Lifecycle

```text
declare mode and firmware identity → bind TCP interface map
→ run under the authoritative clock → stop with recorded semantics
→ reconnect only into a current epoch with fresh identity
```

`accepted` means the declared mode items are individually verified. It does not mean other PX4 modes (RFly, SIH) or other firmware builds are covered.

### Rejection boundary

Reject on unsupported mode, firmware mismatch, unmapped interfaces, failed stop or reconnect and foreign epochs. Keep `mode_unsupported`, `firmware_mismatch`, `interface_unmapped`, `stop_failed`, `reconnect_failed` and `foreign_epoch` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket starts no SITL session.

1. **Mode itemization (owner: protocol maintainer):** freeze the reference PX4_SITL TCP operation list and verify each item against it.
2. **Stop/reconnect slice (owner: runtime maintainer):** implement and audit stop/reconnect semantics on the owned path after itemization.

No current command itemizes the reference mode mapping, so none is claimed here.

## Non-goals and preserved blockers

- No mode mapping or lifecycle code is implemented by this contract slice; no SITL session is started.
- #12 and #48 keep their bounded meaning; PX4_SITL_RFLY and SIH modes are explicitly out of scope.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for SIM-02 and for the project.
