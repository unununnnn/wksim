# Full COMM-02 — UDP_Simple reference protocol contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #129. It does not treat the manual's 112-byte `SOut2SimulatorSimpleTime` listing as an implementation, nor UDP_Simple as UDP_Full with a mode label.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:33` — reference simplified UDP output with time; the manual lists a 112-byte `SOut2SimulatorSimpleTime`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=COMM-02`, `followup_ids=[129]`; parent #1 (Wayfinder, OPEN).
- Owned rejection-pattern evidence: `Simulator/wksim_core/ap_json.py` (lockstep packet decode with strict servo/sensor handling) and `Simulator/wksim_runtime/telemetry.py` (`decode_datagram` with system identity) prove owned malformed-input handling — for owned protocols, not for this reference layout.
- No pinned 112-byte field map, time-field semantics, dropped-quantity mapping versus UDP_Full, or SDK interop capture exists in this checkout.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| COMM-02-A | Reference layout identity | `blocked`: manual byte count only | Pinned 112-byte field map with offsets, types, units, endianness |
| COMM-02-B | Time semantics | `blocked`: the simple layout's time field is unpinned | Time epoch/unit/monotonicity pinned and distinguished from authoritative sim time |
| COMM-02-C | Dropped quantities | `blocked`: no mapping vs UDP_Full | Explicit list of dropped quantities and consumer impact |
| COMM-02-D | Malformed rejection | `partial`: owned readers prove the pattern on owned protocols | Rejection of illegal simple-layout datagrams |
| COMM-02-E | SDK interop | `blocked`: no comparison run | Original-SDK interop with positive and negative captures |

## Datagram contract

Every UDP_Simple datagram must resolve against a pinned layout manifest:

```text
layout_id, byte_length=112, endianness, field_map (name/offset/type/unit),
time_field, time_unit, time_epoch, dropped_vs_full, rate_hz,
source_identity, target_address, version, source_sha256
```

The simple layout is a distinct protocol. Its embedded time field is data carried in the datagram; it must never be consumed as authoritative simulation time. Dropped quantities stay explicitly unknown to consumers — never reconstructed by guessing.

### Lifecycle

```text
pin layout and time semantics → map dropped quantities vs UDP_Full
→ bind identity/rate → run with strict length/layout rejection
→ stop → reconnect binds current epoch only
```

`accepted` means a datagram conforms to the pinned simple layout. It does not mean the time field is authoritative or that missing quantities are recoverable.

### Rejection boundary

Reject on layout mismatch, wrong length, unknown fields, endianness errors, unknown time semantics, unmapped dropped quantities, unmet rate and stale datagrams. Keep `layout_mismatch`, `wrong_length`, `unknown_field`, `endianness_error`, `time_semantics_unknown`, `unmapped_dropped_quantity`, `rate_unmet` and `stale_datagram` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket implements no protocol and captures no packet.

1. **Layout freeze (owner: protocol maintainer):** pin the 112-byte field map and time field from a fixed manual/SDK source with hash.
2. **Dropped-quantity mapping (owner: protocol maintainer):** derive the exact dropped set from the frozen UDP_Full layout (COMM-01); do not infer it from names.
3. **Interop capture (owner: validation maintainer):** original-SDK interop with positive and negative datagrams captured and hash-recorded.

No current command implements or verifies UDP_Simple, so no interop run is claimed here.

## Non-goals and preserved blockers

- No protocol code is implemented and no packet capture is performed by this contract slice.
- UDP_Simple is not delivered by relabelling UDP_Full; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for COMM-02 and for the project.
