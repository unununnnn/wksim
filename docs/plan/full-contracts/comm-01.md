# Full COMM-01 — UDP_Full reference protocol contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #128. It does not treat the manual's 168-byte `SOut2Simulator` listing or the owned UDP paths as a complete UDP_Full implementation.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:32` — reference complete UDP output and consumption; the manual lists a 168-byte `SOut2Simulator`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=COMM-01`, `followup_ids=[128]`; parent #1 (Wayfinder, OPEN).
- Owned UDP evidence: `Simulator/wksim_core/ap_json.py` (`Lockstep`, `sensor_message`, `decode_servos`, `serve` on UDP) and `Simulator/wksim_runtime/telemetry.py` (`Observer` datagram decode/forward with system identity). These are owned protocols with their own identities — neither implements the reference 168-byte layout.
- No pinned field map, byte order, rate or target-address specification for `SOut2Simulator` exists in this checkout; no local SDK interop run or packet capture has been compared against it.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| COMM-01-A | Reference layout identity | `blocked`: manual byte count only; no pinned field map | 168-byte field map with offsets, types, units, endianness from a fixed source |
| COMM-01-B | Owned UDP datagram paths | `partial`: AP JSON lockstep and telemetry observer exist with identity | Owned paths keep distinct identity and are never relabelled as UDP_Full |
| COMM-01-C | Rate and target address | `blocked`: reference semantics unpinned | Observed rate and destination behavior bound to the layout |
| COMM-01-D | Full-mode control/feedback | `blocked`: not implemented | Complete-mode control/feedback per the frozen layout |
| COMM-01-E | SDK interop and capture | `blocked`: no comparison run | Local SDK interop plus packet-capture comparison |

## Datagram contract

Every UDP_Full datagram must resolve against a pinned layout manifest:

```text
layout_id, byte_length=168, endianness, field_map (name/offset/type/unit),
rate_hz, source_identity, target_address, direction, version, sequence,
epoch, source_sha256
```

An owned datagram path is not the reference protocol; a manual byte count is not a frozen layout. A datagram that does not match the pinned length/layout is rejected, never partially parsed into valid-looking fields.

### Lifecycle

```text
pin layout manifest → validate field map and endianness → bind
source/target identity and rate → run with per-datagram sequence/identity
→ reject malformed/stale explicitly → stop → reconnect binds current epoch only
```

`accepted` means a datagram conforms to the pinned layout. It does not mean the receiver acted on it or the reference program would interoperate without a capture comparison.

### Rejection boundary

Reject on layout mismatch, wrong length, unknown fields, endianness errors, unmet rate, address mismatch, unsupported mode and stale datagrams. Keep `layout_mismatch`, `wrong_length`, `unknown_field`, `endianness_error`, `rate_unmet`, `address_mismatch`, `unsupported_mode` and `stale_datagram` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket implements no protocol and captures no packet.

1. **Layout freeze (owner: protocol maintainer):** pin the 168-byte field map from a fixed manual/SDK source with hash; the manual listing alone is not a frozen layout.
2. **Owned UDP bridge (owner: runtime maintainer):** implement the bounded reader/writer only after the layout is frozen; reuse the owned UDP/identity patterns from `ap_json.py` and `telemetry.py` without relabelling them.
3. **Capture comparison (owner: validation maintainer):** local SDK interop with packet-capture comparison against the frozen layout, positive and negative datagrams included.

No current command implements or verifies UDP_Full, so no interop run is claimed here.

## Non-goals and preserved blockers

- No protocol code is implemented and no packet capture is performed by this contract slice.
- The owned AP JSON and telemetry paths keep their separate identities; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for COMM-01 and for the project.
