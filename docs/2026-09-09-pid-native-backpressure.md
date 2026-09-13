# PX4 PID native backpressure acceptance (#86)

Starting HEAD `cd32561`, branch `codex/independent-rgb-integration`.
The earlier failed flight and audits remain unchanged.

## Cause and fix

The old run issued 2,551 PID requests but retained only 1,831 native attitude
targets. Raw decoding shows request 10 (State 28.004 s) was overwritten by
request 11 before the next native publication. The target at 28.020 s matches
request 11, not 10. Public command acceptance stores a target; it does not wait
for the separate, rate-limited native output timer.

`PIDTask` now holds one request until its public ACK, matching native outlet,
and two distinct matching FC ATTITUDE_TARGET telemetry timestamps have been
observed. The next consumed State must cover those timestamps. Duplicate
telemetry timestamps cannot release it. The existing 0.2 simulated-second /
2 wall-second deadline remains a hard failure boundary, including after ACK.
This is transport backpressure, not native acceptance certification; the
independent raw audit still checks each request against CDR and native logs.

No controller equations, physical budgets, configuration hash, installed
Control/FC/model resources, or auditor windows were changed. Test fixtures
reproduced premature release before the fix. Sourced WSL regression: 46 passed,
zero skipped, including actual generated ROS float32 State through the outlet.

## Single new flight and strict audit

Evidence directory: `validation/pid-native-association-20260909/`.
Diagnostic `inspect_native.py` reads the old run only. `run_candidate.py` runs
one fresh PX4 candidate; `finish_candidate.py` audits without editing originals.
Exact argv/timestamps/return codes are retained beside stdout/stderr.

```bash
bash tools/run-pid-flight.sh --stack px4 --run-id pid-px4-native-backpressure-20260909-01 --config Simulator/wksim_runtime/pid-flight-v1.json --output-root /root/wksim-pid-flight-pid-px4-native-backpressure-20260909-01
```

Preflight and flight exited 0. Run result is `observed`, safe_landing=true,
children_reaped=true, cleanup_errors=[], source_unchanged=true,
candidate_unchanged=true and stop_kind=`landed_stop`. All four owned PIDs were
checked absent after termination. The sealed WSL run is
`/root/wksim-pid-flight-pid-px4-native-backpressure-20260909-01/pid-px4-native-backpressure-20260909-01`.

**Strict audit exited 0: `recorded_evidence_pass`.**

- 95,360 continuous physics ticks; exact 1,000-tick disturbance.
- 850 independently recomputed PID updates: point 166, circle 400, disturbance 284.
- Every request has distinct native CDR and execution-log association under
  unchanged windows; 512 native motor comparisons; ULog has no dropouts.
- Fixed point/circle/disturbance physical metrics and final recovery dwell pass.
- All source/config/raw input hashes are retained in `audit.json` and
  `source-sha256.json`. Frozen protocol SHA remains
  `25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`.

This satisfies #86's PX4-only frozen physical/native flight acceptance.
It does not close #35: AP #87 and configuration/result review #88 still remain.
Full, R1, RateUnmet and hardware/resource boundaries are unchanged. Sampled
native logs do not prove exact first acceptance tick or per-packet publisher GID.

The existing pyulog 1.2.2 private directory is reused. Large raw streams/result
copies remain in WSL/local evidence; their hashes and strict audit are in Git.
Known source files were read directly; no stale graph was used for new call
structure. No parent/sibling sources or sealed installations were modified.
