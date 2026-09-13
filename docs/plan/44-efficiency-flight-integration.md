# #105 efficiency flight integration — concrete next slice

2026-09-10. The primary agent owns the following new paths for the continued
user-authorized simulation-toolchain implementation:

- `Simulator/wksim_runtime/efficiency_task.py`, `efficiency-flight-v1.json`
- `tools/efficiency_physics.py`, `run_efficiency_flight.py`, `run-efficiency-flight.sh`
- `tools/audit_efficiency_flight.py` and corresponding validation evidence/tests

Keep original model.cpp/model.py, PID disturbance code, native FC adapters and
all historical pins unchanged. Use the newly built aerodynamic efficiency model
as an explicitly checked experimental replacement, retaining the original model
admission alongside its exact new library/build identities. Normal eta=1 is
already binary64-equivalent to the original for the declared 4000-step bench;
this is not G6 certification.

Freeze the first flight profile to the existing public native position hold:
PX4 OFFBOARD and ArduCopter GUIDED through installed Control WjBuqN, with a public
MOVE to ENU [2,3,3], yaw 0. Use the existing frozen PID physical budgets unchanged:
6 seconds stable hold before requesting origin, position/speed/yaw .3m/.3m/s/.15rad;
eta0=.97 at origin+2000 through origin+3000, all other eta=1, unchanged input16;
error .5m during disturbance, envelope tilt15deg / height1.5..4.5m / distance4m;
recovery by end+8000 with the last1500 native intervals continuously inside
.3m/.3m/s/.15rad. This profile uses native position controllers, not external PID;
its separate admission and physical results must say that explicitly. The units,
vehicle geometry/mass and nominal dynamics match the retained profile; actual
closed-loop compliance still must be measured without relaxing those bounds.

After the real stable hold, Task publishes an exclusive immutable arm request
with its observed current control epoch. The physics owner takes its own current
native tick as origin, binds the identity, and atomically publishes the plan or
baseline origin receipt. Do not let Task guess origin from a delayed trace cursor.
The owner polls for revoke-file presence (including incomplete files), latches
changes/deletion/second requests, and uses EfficiencyEvent before each 1ms step.
A baseline follows the same timeline with no event and eta1 throughout.

Reuse the actual packet-capture wrappers (AP servo packet / PX4 actuator CDR)
without PWM modification. Record original packets, decoded input16, all16 ODE4
rotor/substage rows, native ticks/random state, physical outputs and terminal
restoration. The first three runs per selected stack are baseline, fault and
same-seed fault in a fresh process/epoch/storage. Keep #46 deterministic replay
and Full separate from this protocol repetition.

For clean termination, defer a signal while inside a native interval until its
raw output has been recorded; outside the interval an interrupt can retire the
server. This avoids losing a final native step between ctypes return and Python
recording. Always restore/read back eta1 before graceful model destruction.

Reuse public Task/RC raw-observation helpers only as observation code; do not run
an RC scenario or emit RC frames. The independent auditor must re-decode original
actuator packets, prove input16 unchanged, validate exact event/epoch/timing,
recompute eta force/torque per substage, and enforce physical budgets per1ms.
Do not turn the seven native bench results into flight acceptance. Failed runs
remain failed even if coefficient restoration or subsequent landing succeeds.

Latest execution: the native-position baseline/fault/repeat matrices on both
stacks are implemented and passed; see
[the flight report](../2026-09-10-motor-efficiency-flight-report.md).
The original stable-hold, 1000-interval event and final 1500-interval recovery
budgets were enforced by raw independent audits. This file preserves the design
and ownership record; it is no longer a statement that the runner is missing.
