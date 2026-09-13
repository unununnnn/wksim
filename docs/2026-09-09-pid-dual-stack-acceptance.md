# #35 dual-stack PID acceptance

Final validation uses identical current PID/runtime/physics/config source hashes
on PX4 and ArduCopter. `validation/pid-final-review-20260909/verify_pair.py`
asserts those hashes, independent full-audit schemas/statuses, retained result
hashes, actual PID selection, and safe completed teardown. Its retained verdict
is `pair-acceptance.json`, status `passed`.

| Stack | Run | Physical ticks | Independently recomputed/native-associated updates |
| --- | --- | ---: | ---: |
| PX4 | `pid-px4-final-source-20260909-02` | 92,888 | 851 |
| ArduCopter | `pid-ap-shaped-feedback-20260909-02` | 126,163 | 656 |

Both strict audits returned `recorded_evidence_pass`, with exact 1,000-tick
declared disturbances, frozen point/circle/recovery metrics, actual native
attitude/thrust targets, source-derived motor/physics matching, and safe landing.
All owned flight children were reaped. These are distinct independent runs,
not a joint scene or a real-time-rate acceptance.

The AP strict report is
`validation/35-pid-arducopter/ap-shaped-feedback-20260909/strict-audit-report.json`;
PX4 is `validation/pid-final-px4-20260909/strict-audit-report.json`.
Their command metadata is separately named `strict-audit-command.json`.
The first collection scripts mistakenly reused `audit.json` for command metadata
after the auditor had written that filename. Those originals are preserved;
they are NOT the retained acceptance reports. `audit_retained.py` regenerated
the full reports from unchanged sealed raw evidence using distinct paths.

## AP feedback correction and adversarial review

The first AP backpressure run is retained as failed in
`validation/35-pid-arducopter/native-backpressure-20260909/`. It reached the first
PID command and hit the unchanged 0.2 simulated-second observation deadline.
Failure landing was observed, but its result remained `safe_landing=false` and
`unsuccessful_isolated_teardown`; it is never counted as an accepted run.

Independent source review of the admitted AP candidate established that
`ATTITUDE_TARGET` reports the shaped attitude-controller target and input
collective. `ModeGuided::set_angle` separately logs the raw requested quaternion
in GUIA. Requiring exact MAV quaternion equality was therefore an invalid
cross-stack assumption. AP online pacing now requires exact raw CDR quaternion
and thrust plus two distinct matching FC collective observations. PX4 retains
exact telemetry quaternion matching. The unchanged offline auditor still
requires AP's raw GUIA quaternion association for every PID command.

The same review reproduced release on delayed same-value CDR older than the
request State. The runtime now rejects that source timestamp. Independent
old/new probes confirm both fixes, duplicate/future timestamp rejection and
both original deadlines. Report/probes: `validation/pid-review-20260909/`.

Sourced WSL regression: 47 tests passed, zero skipped. The independent AP reviewer
also rechecked 14 raw-input hashes, 28 retained source hashes, 9 installed Control
hashes, binary/model/log identities, and all 656 online observations. Reused
Linux PIDs were distinguished by process starttime; no unrelated process was
terminated. All prior failed runs remain unchanged.

## Acceptance boundary

Configuration/result review against each original #35 criterion is in
`docs/plan/35-product-selector-contract.md`. The existing explicit `--config`
path selects real `PositionPID`; measured windows use public XYZ_ATT with no
native position helper. Fixed upstream attribution, initialization, reset,
mass and thrust conventions remain in the original controller-port report.

Both final runs bind `pid_task.py` SHA256
`ffbddccff7a1135bb6342c6883d8a7c22b2922fc16b0d2652e4d80a8fc073d62` and unchanged
protocol `25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`.
The independent auditor is unchanged by the AP pacing fix. Its limitations
remain: sampled native logs, no exact first acceptance tick or per-packet
publisher GID, and source/hash-bound mass rather than runtime getter.

This closes the bounded PID acceptance, not Full, R1/G6, RateUnmet, all-model,
hardware, GUI coverage, or joint-scene acceptance. No frozen numerical budget,
sealed installation, original ROS1 source, parent or sibling project changed.
