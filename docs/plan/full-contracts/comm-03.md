# Full COMM-03 — Mavlink_Full interaction contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #130. It does not generalize the verified QGC handoff or parameter-transaction slices into the complete QGC/SDK MAVLink interaction.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:34` — the complete MAVLink interaction QGC and the SDK require.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=COMM-03`, `followup_ids=[130]`; the ticket names #1, #42 (real QGC dual-stack handoff, verified) and #43 (two parameter transactions and reboot, verified).
- `Simulator/wksim_runtime/telemetry.py`: `Observer` with checked destinations, datagram decode by system identity, bounded forward/reverse paths and report — the #42 QGC slice seam.
- `Simulator/wksim_runtime/parameter_protocol.py` and `parameter_storage.py`: parameter context/validation with explicit semantics (`PARAM_VALUE` has no request ID and is not `COMMAND_ACK`) — the #43 transaction seam.
- `Simulator/wksim_runtime/telemetry-dialects.json`: dialects pinned with `build_manifest_sha256` and builder identity.
- Not frozen: the Full SDK message set, per-message fields, control-authority transitions and per-message frequencies.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| COMM-03-A | Message set freeze | `blocked`: slices verified, set undefined | Pinned Full message set with fields and frequencies |
| COMM-03-B | Identity and control authority | `partial`: #42 handoff verified | System/component identity plus explicit authority grant/loss transitions |
| COMM-03-C | Parameter transactions | `partial`: #43 proves two transactions and reboot | Full parameter protocol coverage with rejection semantics |
| COMM-03-D | State mapping | `partial`: bounded streams mapped | Complete model/FC↔message state mapping |
| COMM-03-E | Dialect identity | `partial`: dialects pinned by build manifest hash | Every admitted message resolved to a pinned dialect |
| COMM-03-F | Frequency budget | `blocked`: frequencies unpinned | Per-message budgets with explicit breach results |

## Message contract

Every admitted Mavlink_Full message must resolve against:

```text
message_id, message_name, dialect, dialect_sha256, field_map,
system_id, component_id, direction, frequency_hz, control_authority,
epoch, source_identity
```

A verified QGC handoff or parameter slice is not the Full SDK message set; a parsed message is not granted control authority. Authority changes are explicit transitions recorded with identity and epoch.

### Lifecycle

```text
pin dialect and message set → bind system/component identity
→ admit messages per field map and frequency → authority transitions explicit
→ stop → reconnect re-announces identity under the current epoch only
```

`accepted` means a message conforms to dialect, identity and frequency. It does not mean a command was executed, a parameter persisted across reboot, or authority was granted.

### Rejection boundary

Reject on unknown messages, dialect mismatch, field mismatch, identity mismatch, denied control authority, rejected parameters, unmet frequency and stale messages. Keep `unknown_message`, `dialect_mismatch`, `field_mismatch`, `identity_mismatch`, `control_authority_denied`, `parameter_rejected`, `frequency_unmet` and `stale_message` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket freezes no message set and starts no QGC session.

1. **Message set freeze (owner: protocol maintainer):** pin the Full message set from a fixed SDK/QGC source with field lists and frequencies.
2. **Authority contract (owner: runtime maintainer):** define and implement the control-authority state machine on the existing telemetry seam.
3. **Parameter coverage (owner: runtime maintainer):** extend `parameter_protocol.py`/`parameter_storage.py` to the frozen transaction list with reboot persistence evidence.
4. **Frequency audit (owner: performance maintainer):** per-message frequency budgets with explicit breach results.

No current command implements the Full set, authority transitions or frequency budgets, so none is claimed here.

## Non-goals and preserved blockers

- No MAVLink message set, authority machine or frequency budget is implemented by this contract slice.
- #42 and #43 keep their verified bounded meaning; #32's velocity/yaw closure is not evidence for this mode.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for COMM-03 and for the project.
