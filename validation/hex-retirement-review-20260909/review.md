# Independent Hex retirement-order review

Reviewed failure: `/root/wksim-hex-flight-px4-live-reset-20260909-01/hex-px4-live-reset-20260909-01`, with strict report `validation/25-px4-reset-live-20260909-01/flight-audit.json`. No native process, flight or source modification was performed by this reviewer.

## Cause confirmed

`run_hex_flight.py` creates children in physics, Agent, FC, Control order. Shared `runtime.stop_children()` iterates that list in reverse, synchronously sending SIGTERM, waiting, sending SIGKILL to remaining group members, and reaping each group. Thus the actual shutdown order is Control, FC, Agent, physics.

Actual retained `physics.log` first raises `ConnectionResetError: [Errno 104] Connection reset by peer` at `px4_mavlink.py`'s blocking `connection.recv(8192)`. Only subsequently does its owned SIGTERM raise InterruptedError during the apport exception hook. The raw terminal therefore records the peer-reset failure, not the normal owner-retirement error. The strict auditor correctly rejects `terminal_failure`. It must continue to reject that record even though the public flight reached `normal_stop_ready`, landed, and the cold-reset/parent-audit/tick-zero checks pass.

The result records observed/safe_landing, no cleanup errors, children reaped and parent unchanged; physics return code is 1, Agent -15, FC 0 and Control 0. Coordinator completion alone is therefore insufficient, as intended: its later strict audit prevents a false overall pass.

## Proposal assessment

**Approve Hex-specific physics-first retirement**, followed by the existing reverse order of the remaining Control, FC and Agent children. Physics must finish its TERM/wait/kill/reap sequence before the FC is signaled, allowing the existing expected owner-retirement handler to write and flush its raw terminal while the peer remains present. Preserve the original owned child list/result identities; reorder a local list passed to shared cleanup or use a local wrapper. Do not change shared cleanup or the peer-reset audit rule.

The existing per-child waits are bounded at 5 seconds after TERM and 5 seconds after KILL. If PX4 waits on halted lockstep during shutdown it remains subject to the same bounded group retirement, not an unbounded wait. Forced termination or missing final native log data is not automatically acceptable: existing strict raw/native/retirement checks remain mandatory. On partial startup, the wrapper must handle no physics child or an already exited physics child using the existing ProcessLookupError handling.

Residual existing limitation: a SIGTERM can arrive during one of the four observed 1 ms substeps or a JSON write rather than the socket receive wait. Physics-first fixes the demonstrated peer-close race but is not an atomic group-boundary shutdown protocol. Any resulting partial group/tail must still fail the strict audit. A future repeated partial-group failure would justify a safe-boundary stop flag/handshake; this review does not claim it is solved by ordering alone.

## Finite checks

A recording-only probe called the actual shared `stop_children()` with mocked signals/processes. Original input `[physics, agent, fc, control]` yields TERM order `[control, fc, agent, physics]` and modeled peer-reset. Reordered input `[agent, fc, control, physics]` yields `[physics, control, fc, agent]` and modeled normal owner retirement. No OS signal or actual process/socket was created.

The parent's new `validation.test_hex_retirement` was independently run in WSL against the pre-fix runner: two tests, empty startup passes, expected ordering regression fails with the recorded ConnectionResetError sequence. This is the expected red baseline, not a completed fix verification. An initial Windows probe could not mock absent `os.killpg`; it stopped before any action and was rerun in WSL.

Recommendation before retry: complete the narrow runner reorder, rerun the finite test, and require a new full cold-reset flight/strict audit; preserve this rejected run and its terminal unchanged.

## Final patch verification

The parent added a Hex-local wrapper that passes `[nonphysics children] + [physics children]` to the unchanged shared reverse-order cleanup. Direct source review confirms original child ordering/result identities are not mutated, and remaining Control/FC/Agent order is preserved. The same independent WSL command `python3 -B -m unittest validation.test_hex_retirement -v` now passes both tests, including reaping physics before FC gets TERM and empty partial startup. No decoder, physical budget, auditor terminal rule, or generic cleanup function was changed by this fix. **GO for a separately bounded new run using this retirement correction**, with full strict audit still required; the existing failed cold-reset run remains rejected.

Reviewed runner SHA256: `7b57b1d892208ae8b47d50d9c2651f50a6abe2dba7e9bf5db78bc846e3b35a33`; retirement test SHA256: `89df1cb572cc5ebc90a80a1919c5f7d792ae7467d1b2950f86e24fdf5c96d718`.

## Combined AP47v2 / retirement final pre-run review

The parent additionally requested review of the AP47v2 stream-parameter correction before scheduling new PX4 cold-reset and AP attempts. All nine source/test hashes in `validation/hex-ap-stream-params-20260909/applied-source-hashes.json` match the current files. Direct native-source inspection confirms `ArduCopter/Parameters.cpp:590` registers `MAV`, `GCS.cpp:80` registers channel index 0 as subgroup `1`, and `GCS_MAVLink_Parameters.cpp:156/166/185` registers `_POSITION`, `_EXTRA1`, `_EXTRA3`, each documented in Hz. The resulting correct names are MAV1_POSITION/MAV1_EXTRA1/MAV1_EXTRA3, with intended values 10/10/5. ARMING_SKIPCHK remains 0. The retained census reports all 33 expected names present and the 30 unchanged values already correct; future actual ground DDS readback remains mandatory.

New AP47v2 protocol SHA256 is `ce4f0aeb3c2de250aaf10c224f3fa43c326fcfcf8140c3746770879558f9df37`, with plan identity `5c07a2d5c1e4b13580ae8b3ba43ce686324ec340adf2c12e9b4ffaabbba8486a`. Independent comparisons confirm all physical/time budget fields match the unchanged legacy/PX4 and AP47v1 JSON, excluding only version schema and plan identity. Default/PX4 complete plans remain equal. The old AP47v1 file remains intact, and PX4 still selects its original protocol. Exact paired compatibility permits only the specifically reviewed old/current recipe pairs; no indefinite future decoder exception was introduced.

Independent sourced WSL command:

```text
bash validation/lunar-65-astra-20260909-01/run-audit.sh -m unittest validation.test_hex_flight validation.test_hex_ap47 validation.test_hex_flight_audit.PureGuards validation.test_hex_retirement -q
```

**29 tests passed in 0.455 s, no skips.** The source-registration read initially used the deliberately restricted experiment-path helper on a source directory and was rejected before access; direct explicit UNC source paths were then used successfully. No original source or evidence was modified.

The implementer's current strict recent-PX4 report was inspected: identity and cold-reset link/recursive original-parent audit pass; its only error remains the actual physics terminal ConnectionResetError. The review endorses no retrospective promotion. **Combined pre-run recommendation: GO for one bounded fresh PX4 cold-reset attempt, then the separately scheduled AP47v2 attempt**, retaining existing strict physics, retirement, live display and rendered-image review requirements. No new actual flight acceptance is claimed by these offline checks.
