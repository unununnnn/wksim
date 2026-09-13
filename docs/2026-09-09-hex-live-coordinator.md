# Hex live coordinator and first AP attempt

New Windows entry `tools/run-hex-live.ps1` delegates to
`tools/audit_hex_live.py`. The coordinator binds fresh run/instance/model/port,
checks the UE candidate, waits for UE and bridge startup, launches the existing
isolated flight, preserves raw/ACK/capture evidence and retires owned processes.
The independent visual auditor verifies actual raw correspondence, Actor
budgets, phase continuity/coverage and capture hashes. Rendered-image review is
explicit and separate; automatic numeric success alone cannot return full PASS.

Seventeen finite offline tests passed. Independent review checked actual old
Hex result/audit schemas and the pinned UE module. It caught and fixed a
takeoff-window defect: `task_control_ready→takeoff_reached` covered only 20 ms
in the old run. The source-proven interval is `armed→takeoff_reached`, covering
actual autonomous takeoff without changing any duration/cadence budget. Retained
source and native-evidence hashes are recomputed, not merely trusted as flags.

One actual AP attempt ran as `hex-ap-live-20260909-01`.
Windows evidence is `validation/25-ap-live-20260909-01/`; native evidence is
`/root/wksim-hex-flight-ap-live-20260909-01/hex-ap-live-20260909-01`.
Its exact launch is preserved in `validation/hex-live-launch-20260909/`.

**Rejected before arming:** `RuntimeError: Native parameter unavailable: ARMING_CHECK`.
The coordinator correctly returned 1. No takeoff occurred. The native result
records all children reaped, empty cleanup errors, unchanged sources/candidate;
all owned Windows/Linux process identities and the relay were independently
checked retired. The old result and failures remain unchanged.

The partial display evidence is real but ground-only: 1,929 ACKs match raw ticks
20–41,520 exactly; all fixed Actor limits pass, accepted-step maximum gap is
40 ms, maximum transport bound is 0.0231423 s. Twenty-one captures are fresh and
ACK-correlated. Final captures become stale after source retirement, rather
than being retimestamped LIVE. Parent inspected `frames/frame-0049.png`: visible
Hex model and LIVE HUD at simulation 41.060 s, on the ground. This does not
certify in-flight rotation, phase coverage, or completed #66.

Independent reports and finite probes are retained in
`validation/hex-blocker-review-20260909/`,
`validation/hex-live-implementation-20260909/`,
`validation/hex-live-prerun-review-20260909/`, and
`validation/hex-live-failed-ap-review-20260909/`.
The failed run identified a source-specific AP 4.7 parameter migration; an
explicit AP-only contract revision is required before another attempt. Legacy
PX4 plan/protocol and its cold-reset parent must remain valid.
