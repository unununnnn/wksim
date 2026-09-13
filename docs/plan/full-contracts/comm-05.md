# Full COMM-05 — Mavlink_NoSend passive mode contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #132. Receive-only is proven by capture, not by configuration intent.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:36` — receive only, never actively send.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=COMM-05`, `followup_ids=[132]`; parent #1 (Wayfinder, OPEN).
- `Simulator/wksim_runtime/telemetry.py`: the `Observer` owns bounded forward/reverse datagram paths with checked destinations — receive-side seams with identity.
- `Simulator/wksim_runtime/gcs_relay.py`: the owned WSL↔Windows stdio relay with private path checks — a bounded transport, not a passive-mode proof.
- Missing: pinned side-effect semantics of passive reception, an explicit response policy (are heartbeats/ACKs permitted?), reference evidence for both, and a packet capture proving zero outbound datagrams.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| COMM-05-A | Passive receive semantics | `blocked`: unpinned | Pinned side effects: state visibility only, no commands, no authority |
| COMM-05-B | Response policy | `blocked`: undefined | Explicit permitted/forbidden response list with reference evidence |
| COMM-05-C | Send-constraint proof | `blocked`: no capture | Capture proving zero outbound datagrams for the mode duration |
| COMM-05-D | Owned receive path | `partial`: observer/relay seams exist | Receive paths stay bounded and are not relabelled as NoSend proof |

## Mode contract

A Mavlink_NoSend session must declare:

```text
mode_id, receive_filter, permitted_responses, outbound_budget=0,
capture_proof, system_id, epoch, source_identity
```

An unproven NoSend mode is indistinguishable from Full: only a capture demonstrating zero outbound datagrams (or exactly the permitted responses) proves the constraint. Passive reception must not create commands, authority or side effects on the vehicle.

### Lifecycle

```text
declare mode with outbound budget zero → freeze response policy
→ run passive reception → capture the whole session
→ audit: any outbound datagram is a violation → stop; reconnect re-binds identity
```

`accepted` means no outbound violation was captured. It does not mean received state was complete, current or acted upon.

### Rejection boundary

Reject on outbound violations, non-permitted responses, missing capture proof, identity mismatch and stale messages. Keep `outbound_violation`, `response_not_permitted`, `capture_missing`, `identity_mismatch` and `stale_message` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket implements no mode and captures no packet.

1. **Policy freeze (owner: protocol maintainer):** pin passive side effects and the response policy from reference evidence.
2. **Capture proof (owner: validation maintainer):** run the bounded path under capture and demonstrate the outbound constraint.
3. **NoSend implementation (owner: runtime maintainer):** implement the mode on the owned telemetry seam after the policy is frozen.

No current command implements or proves Mavlink_NoSend, so none is claimed here.

## Non-goals and preserved blockers

- No protocol mode is implemented and no capture is performed by this contract slice.
- The owned observer/relay seams keep their bounded meaning; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for COMM-05 and for the project.
