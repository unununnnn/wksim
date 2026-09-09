# #90 UDE runtime candidate contract — BLOCKED

2026-09-09. This is a frozen design candidate, not runtime integration completion.
At inspection, #89 was delivered at 1050001 and #35 remained OPEN. #90 explicitly
depends on both, and owns only this document and `ude-flight-v1.json`, plus new
ticket evidence. The user explicitly requires preserving those file boundaries.
No existing runtime source was changed. #90 must remain OPEN / needs-triage.

## Frozen input and identities

Candidate: `Simulator/wksim_runtime/ude-flight-v1.json`, raw SHA256
`4bca3479d61f73d2ab8253191bdc41938904a43877f6b688c0c55e32567c4590`.
UDE implementation: `Simulator/wksim_control/position_ude.py`, SHA256
`811f7bab2ae022563035005a76b5475665f15e9f49380ee201a7a64e61c0787b`.
Upstream commit `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`; original UDE
header working-byte SHA256 `ae0c9a300e435775b836f56667aadf90e4779db0b116218178d747bb50ce6699`.
#89 raw comparison and identity evidence remain in
`validation/lunar-89-astra-20260909-02/`; its report records 2446 original C++
samples at abs=2e-6, rel=2e-7. This task did not rerun that oracle.

The candidate explicitly uses UDE Kp=.5, Kd=2, T=1s, disturbance limit=1 on
each axis, with 8-degree per-axis tilt to retain the PID candidate setting.
This differs from upstream's default 20 degrees; it is not post-flight tuning.
Model library SHA256 is
`cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`, quad-X,
mass 1.515kg, identity `sha256:` followed by that hash. This is parameter/source
binding, not a runtime mass getter. No physical budget was changed.

Every model, calibration, timing, point, circle, disturbance and envelope field
is equal to the frozen PID protocol SHA256
`25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`.
The offline check asserts that equality and records current source hashes.

## Four exact runtime files requiring assigned ownership

These edits are proposed, NOT applied. The current two-file write scope cannot
meet the ticket's requirement for an actually computing, runnable candidate.

1. `Simulator/wksim_control/position_pid.py:select_controller`: explicit typed
   pid/PIDConfig and ude/UDEConfig dispatch; instantiate PositionUDE for UDE.
   Empty/default/native/unknown or mismatched config rejects. No exception
   handler may substitute PID. Every selection creates reset observer state.
2. `Simulator/wksim_runtime/pid_task.py`: admit separately pinned protocols;
   construct the selected config/algorithm in PIDLoop; propagate actual output
   controller and implementation into trace, resolved config and task report;
   bind event/protocol identity to the selected immutable bytes. Reuse public
   XYZ_ATT, authority checks, lifecycle and preparation without another task
   control interface. Current load_config, PIDLoop, PIDTask and event_for are
   PID-specific, including hard-coded report labels and protocol hashes.
3. `tools/run_pid_flight.py`: select the admitted algorithm/protocol, include UDE
   source/config in pre/post source seals and run-source copies, bind actual
   controller in admission/results, and route selected protocol to task and
   physics. Keep the existing isolated shell wrapper, resources and watchdog.
4. `tools/pid_physics.py`: bind start record and event checks to selected protocol
   identity, preserving full actuator packets and every original/applied input,
   1ms tick, immutable event, terminal row and latched revocation semantics.

Required tests need explicit ownership too (existing test files or a separately
assigned test file). Independent audit adaptation is additional verification
work, not hidden inside the four runtime edits: `tools/audit_pid_flight.py`
currently proves PID and cannot certify UDE by renaming the result.

## Lifecycle, timing and dual-stack requirements

Each stack/run independently measures 3s native ATTITUDE_TARGET collective median
and validates 2s level attitude (height change <=.3m, vertical speed <=.2m/s).
Reject missing/stale samples, wrong stack/model/mass or prior-run calibration.
Record actual samples and resulting hover; no default hover value is admitted.
NativeThrustConfig maps projected force using m*9.8/hover and clamps [.1,1].
AP receives positive collective; PX4 FRD thrust_body is [0,0,-u].

Keep fresh armed state, unchanged control_epoch/native_generation and
COMMAND_CONTROL. PX4 requires OFFBOARD with fresh attitude/rates/allocation true
and position/velocity/altitude disabled. AP requires GUIDED, actual GUID_OPTIONS
bit3 readback and native entry target observation. One stack proves no other.

Reset integral, last_output and timestamp baseline on selection, takeover,
release, restart, authority loss or clock discontinuity. Duplicate native State
stamp skips; first sample establishes baseline; nonpositive/nonfinite stamp or
dt outside (0,.2] fails and clears state. Do not clamp dt or fabricate 200Hz.
Reference time remains physical cursor elapsed, separately recorded from native
State dt. At most one public request pending, ack deadlines .2 simulated/2 wall
seconds. A generation change fails the run; it cannot resume with a silent reset.

UDE uses old integral in its observer, then updates/clears it according to the
original abs(error)<.5 rule; moving reference does not clear history. Trace must
contain nominal/disturbance acceleration, integral, force, body projection,
normalized output, source state/reference/dt, reset reasons, request/command IDs,
run/epoch/native generation, model and selected source/config/calibration hashes.
Measured stages publish XYZ_ATT only. Native position is permitted only in
labelled preparation/recovery/landing outside UDE measurements.

## Frozen windows and failure acceptance

Point [2,3,3], yaw0: 6s settling +4s measurement, error<=.3m, speed<=.3m/s,
yaw<=.15rad. Circle center [1.4,3,3], radius .6m, period12s, yaw0: 12s settling
+12s measurement, error<=.35m, yaw<=.15rad; analytic position/velocity/acceleration
all feed the UDE algorithm. Disturbance: settle6s then multiply channels0..3 by
.97 for exactly1000 ticks, start=origin+2000, loaded at least1000 ticks ahead.
Other12 inputs unchanged. Maximum error .5m; recover within8s after event end,
final fixed1.5s continuously error<=.3m, speed<=.3m/s, yaw<=.15rad.
Envelope: distance<=4m, height1.5..4.5m, each tilt axis<=15deg. Model step1ms.
Keep PID recovery budgets and 360s wall watchdog from the source contract.
Any failure preserves raw data, revokes disturbance and uses bounded existing
LAND/owned-child cleanup. No retry, retuning, native-position substitution or
successful-flight claim follows a failed measured window.

## Command status and independent audit plan

Runnable now, offline only, from repository root:

```powershell
python -B validation/lunar-90-astra-20260909-01/check.py
```

It computes a real UDE update, exercises reset and both synthetic thrust mappings,
checks unchanged budgets, and proves the existing loader rejects this candidate.
Synthetic hover=.5 in this check is not a run calibration.

Following commands specify the proposed reuse interface, NOT currently runnable
UDE commands. Do not launch #91/#92 until #35 and implementation, tests, source
seals, stack-specific preflight and independent UDE audit prerequisites pass.
Each command is a separate single run with unused ID and directory:

```bash
bash tools/run-pid-flight.sh --stack px4 --run-id ude-px4-90-01 --config Simulator/wksim_runtime/ude-flight-v1.json --output-root /root/wksim-pid-flight-ude-px4-90-01
bash tools/run-pid-flight.sh --stack arducopter --run-id ude-ap-90-01 --config Simulator/wksim_runtime/ude-flight-v1.json --output-root /root/wksim-pid-flight-ude-ap-90-01
```

Today both fail protocol admission before flight. After implementation, first
check each with `--preflight` and a distinct fresh ID; preserve raw output and
actual installed FC/control/model/overlay identities. Actual flight must seal
all loaded code and before/after hashes and report cleanup/terminal status.

Independent audit must reconstruct UDE from original equations and recorded
source state/reference/dt, not invoke the online loop or accept its metrics.
Check observer state/reset history and force/mapping with the frozen #89
abs/rel tolerance; separately trace public IDs/CDR to real AP/PX4 native attitude
and actuator consumption. Recompute physical budgets over complete 1ms windows.
Reject deleted/duplicate tick, missing terminal, wrong run/model/calibration,
retagged PID output, stale authority, position help during measurement, changed
event/input, wrong clock reference, retained observer after reset and a single
over-budget sample. Audit output must distinguish algorithm/native/physics
findings. observed/online_ok is not independent PASS. No UDE auditor CLI is
claimed to exist yet.

## Current evidence and next action

`validation/lunar-90-astra-20260909-01/check.log`: 38 tests passed, zero skips,
plus offline candidate assertions; loader rejects with
`PID trial configuration differs from the pre-run frozen protocol`.
No FC/model/ROS/UE process started. Existing runtime files unchanged.
Runtime integration, source-sealed launch and UDE independent audit remain
unproven. Resolve #35 and assign the four runtime files plus verification
ownership before implementation. Configuration-only delivery does not close #90.
