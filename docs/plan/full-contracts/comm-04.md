# Full COMM-04 — Mavlink_Simple interaction contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #131. It does not deliver Mavlink_Simple by reusing the Full path under a new label, and the velocity/yaw slice #32 is not evidence for this mode.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:35` — the simplified MAVLink interaction; the row requires the exact reduction versus Full and its frequencies.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=COMM-04`, `followup_ids=[131]`; parent #1 (Wayfinder, OPEN).
- `Simulator/wksim_runtime/telemetry.py` and `telemetry-dialects.json`: the owned telemetry seam and pinned dialects are the substrate a simple mode would build on; neither defines the simple reduction.
- Missing: the exact message reduction versus Full with rationale, the reduced frequencies, and a reference capture showing which messages the simple mode actually emits.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| COMM-04-A | Reduction mapping | `blocked`: no pinned reduction | Per-message reduction versus Full with rationale |
| COMM-04-B | Frequency and sampling | `blocked`: unpinned | Reduced frequencies and reference sampling per message |
| COMM-04-C | Distinct implementation | `partial`: the no-relabel rule is fixed; no implementation exists | An implementation defined by the frozen reduction |
| COMM-04-D | Reference capture | `blocked`: no observation | Capture of the reference simple mode's actual message set |

## Message contract

Every admitted Mavlink_Simple message must resolve against:

```text
message_id, message_name, dialect, dialect_sha256, frequency_hz,
reduced_from_full, reduction_rationale, system_id, epoch, source_identity
```

The simple mode is defined by its pinned reduction and frequencies. Any implementation that forwards the Full message set under a simple-mode label is rejected (`full_relabel_rejected`). Messages absent from the reduction stay absent — consumers must not infer them.

### Lifecycle

```text
freeze reduction from the COMM-03 set → pin frequencies → capture reference
→ implement the distinct simple path → audit emitted vs pinned messages
```

`accepted` means the emitted set matches the pinned reduction and frequencies. It does not mean the Full interaction works in this mode.

### Rejection boundary

Reject on unknown messages, undefined reductions, unmet frequencies, dialect mismatch, Full-relabel implementations and stale messages. Keep `unknown_message`, `reduction_undefined`, `frequency_unmet`, `dialect_mismatch`, `full_relabel_rejected` and `stale_message` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket freezes no reduction and starts no session.

1. **Reduction freeze (owner: protocol maintainer):** derive the simple message set from the frozen COMM-03 set with per-message rationale.
2. **Reference capture (owner: validation maintainer):** capture the reference simple mode's actual messages and frequencies before finalizing the reduction.
3. **Simple implementation (owner: runtime maintainer):** implement the distinct simple path only after the reduction and frequencies are frozen.

No current command implements or verifies Mavlink_Simple, so none is claimed here.

## Non-goals and preserved blockers

- No MAVLink code is implemented and no capture is performed by this contract slice.
- #32 keeps its closed bounded meaning and is not evidence here; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for COMM-04 and for the project.
