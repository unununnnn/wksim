# Full OPS-11 — Logging and reproduction contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #162. It does not promote the existing JSONL offline replay into a complete recording system, bag integration or deterministic re-simulation.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:79`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-11`, `followup_ids=[162]`; parent #16 (offline review of existing task records, CLOSED).
- `Simulator/wksim_runtime/replay.py` with `docs/wksim-offline-replay.md`: stdlib-only, read-only offline replay of stopped experiment directories. Exports preserve per-row raw JSON text, per-line hashes and line numbers, source time/timebase, per-stream receive times, command/ACK/event kinds and state validity. Time filters require an explicit clock; cross-timebase identity without a recorded mapping stays `unknown`. Non-finite tokens are preserved as `nonfinite`, not converted to zero coordinates. Missing files, malformed rows, unterminated last lines, explicit sequence gaps and source-time regressions are diagnosed; changed input hashes reject active evidence. Single-file cap is 64 MiB with explicit rejection.
- `docs/2026-09-08-replay-integrity-report.md`: result files and JSONL share one parser; duplicate keys are rejected; per-line `run_id`/`epoch` outrank result metadata with `identity_mismatch`/`partial` reporting. `validation/test_wksim_replay.py` and `validation/offline-replay-20260905/result.json` (AP 20,144 and PX4 21,537 raw records byte-identical) back the slice.
- The replay document states explicitly: this slice is CLI/JSON record review, not deterministic re-simulation, product log writing, live state distribution or the GUI. FC native logs are retained in recorded run directories but are not bound into a record manifest. No bag recording exists.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-11-A | Offline replay | `partial`: #16 closed slice with raw rows, hashes and diagnostics | Read-only replay preserved as the review floor |
| OPS-11-B | Source/receive time | `partial`: source time per explicit timebase plus receive times; unknown cross-timebase identity stays unknown | Per-record time identity across all producers |
| OPS-11-C | Bag and FC-native logs | `blocked`: no bag recording; FC logs retained but unbound | Bag capture plus FC-native logs bound to run identity in one manifest |
| OPS-11-D | Complete event stream | `partial`: bounded task event records exist | Whole-system event stream with ordering, identity and gap diagnostics |
| OPS-11-E | Replay/re-simulation | `blocked`: replay is not re-simulation | Deterministic re-simulation from records under a confirmed numerical budget |
| OPS-11-F | Capacity and missing segments | `partial`: 64 MiB cap with explicit rejection and gap diagnostics | Capacity/rotation/retention and missing-segment policy for the record system |

## Record contract

Every retained record must carry:

```text
run_id, epoch, vehicle_id, stream_id, sequence, source_time, source_timebase,
receive_time_ns, record_kind, raw_sha256, validity, schema, source_identity
```

Source time and receive time are both mandatory and never merged; a record without an explicit timebase is not reorderable against other timebases. Replayed acceptance or ACK text is never rewritten into action completion, and replaying a record is not re-simulating the run. Raw payloads and hashes are immutable evidence; exports are written only outside the input directory.

### Lifecycle

```text
declare record schema → capture per-stream with sequence and both times
→ seal run directory (hashes) → replay read-only with diagnostics
→ export derived views without rewriting raw evidence
→ capacity/rotation per policy; missing segments reported, not filled
```

`accepted` means the record is well-formed and identity-consistent. It does not mean the run was correct, complete, or reproducible. An `active_evidence` hash change rejects the input rather than reading a moving target.

### Rejection boundary

Reject on malformed records, invalid results, unconverted non-finite payloads, duplicate keys, identity mismatches, sequence gaps, time regressions, capacity overflow, active/changing evidence, unknown timebases and missing segments. Keep `malformed_record`, `invalid_result`, `nonfinite_value`, `duplicate_key`, `identity_mismatch`, `sequence_gap`, `time_regression`, `capacity_exceeded`, `active_evidence`, `unknown_timebase` and `missing_segment` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket writes no recorder and replays no run.

1. **Record writer (owner: runtime maintainer):** product record writing with the capacity/rotation/retention policy; the replay tool remains the read-only floor.
2. **FC log binding (owner: validation maintainer):** bind FC-native logs and bag capture to run identity in the record manifest; requires the log location/identity schema.
3. **Re-simulation slice (owner: physics maintainer):** deterministic re-simulation from sealed records; blocked by the #23/G6 numerical budget confirmation. Replay evidence cannot be replayed as re-simulation proof.
4. **Event stream contract (owner: runtime maintainer):** whole-system event stream schema with ordering and gap diagnostics before claiming complete event coverage.

No current command implements bag recording, FC-log binding, the complete event stream or re-simulation, so no new recording or replay run is claimed here.

## Non-goals and preserved blockers

- No recorder, bag integration, event stream or re-simulation is implemented by this contract slice.
- #16 remains a closed bounded slice; its evidence is not relabelled as a complete recording system or cross-platform determinism.
- #23/G6 numerical prerequisites, #9 plugin/ABI and #56 device/license conditions remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for OPS-11 and for the project.
