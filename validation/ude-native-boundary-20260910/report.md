# UDE native end-boundary repair — 2026-09-10

The original PX4 run02 strict audit rejected `Native trajectory override`.
One trajectory CDR (attitude-native.jsonl line 38605) had native source stamp
37.78 s, equal to the point stage's last sparse physical cursor. Its DDS source
and receiver timestamps were after stage end; preceding raw recovery request177,
command174 and matching position-only native target proved post-stage recovery.
Three measured receiver-time windows contained zero trajectory messages, but
receiver time alone was not used to permit the exception.

The narrow shared-auditor repair allows only source stamp exactly equal to the
physical end, with post-end DDS source/received timestamps, post-end recorded
recovery ordering, one matching run/epoch/request/command/payload, raw accepted
ACK, matching NED position/yaw and inactive NaN axes, and matching position-only
OffboardControlMode. Any interior source stamp still rejects, including delayed
receipt. Original PID defaults and physical budgets remain unchanged. Accepted
boundary associations appear explicitly under native.recovery_boundaries.

## Existing checks

`test-output.transcript.txt` records the already-executed command and tool output:
24 tests passed, including a real-run-shaped boundary fixture and 13 rejection
mutations; diff-check clean. `real-row-helper.transcript.txt` records the prior
helper-only proof for actual row38605. Both are clearly labelled conversation
transcriptions: neither is represented as an original captured process log.
No additional test, audit or simulation was executed while writing this archive.
The original rejected report is preserved; root owns full re-audits in separate
report files.

Frozen source identities at the time of these checks:

- tools/audit_pid_flight.py: `1ecb06bd520e472cabf5c21bd01216d497a8080cf3f0543e96692b3189717d7b`
- validation/test_ude_runtime.py: `a5959577e21a85e2ca2b0f170e298916fda54651f82dad3e3d24749f0af1bc4f`
- Simulator/wksim_runtime/pid_task.py: `e0fc7a117c4d56582152b657cbf48be48f7242aa0b6bcb75dc0a1180eb802381`

## Clock-source evidence

Actual installed source (read against this run's admitted Control identity):
`/root/wksim-attitude-control-x3_2v4wb/install/prometheus_control/local/lib/python3.10/dist-packages/prometheus_control/native_px4.py`:

- lines162–168: timestamp() takes latest VehicleLocalPosition.timestamp,
  verifies freshness/boot-microsecond range; it is not a fresh send-time sample.
- lines239 and245–248: position-mode OffboardControlMode and TrajectorySetpoint
  reuse that timestamp. Native timestamp equality does not imply simultaneous
  wall-clock publication or exact native acceptance time.
- line208: public State uses position.timestamp_sample or position.timestamp.

Project `Simulator/wksim_core/px4_mavlink.py`, serve loop around lines130–137:
model.step(commands,4) advances four 1ms ticks; trace is emitted every five frames
(after the initial frame), giving the normal 20ms sparse physical cursor.
`pid_task.py` marks stage end after pending native acknowledgement and computes
its cursor independently. At this boundary: end native State37.764 s,
physical cursor37.78 s, subsequent recovery trajectory source37.78 s,
receiver physical cursor37.80 s. No assumption of exact native acceptance tick
is introduced by the repair.

## Prepared, not executed

`check_dual_stack_sources.py` is a standard-library, read-only checker for completed
PX4/AP run directories. It reads result/config/protocol/retained sources, requires
completed owned-child teardown before inspection, checks the frozen UDE protocol
and current/retained run-source bytes, and compares both selected source manifests.
It emits JSON to stdout and starts no processes. It has intentionally NOT been
executed or compiled during the AP run; root must wait for AP completion.

Example after both runs complete (supply the actual AP directory):

```powershell
python -B validation/ude-native-boundary-20260910/check_dual_stack_sources.py --px4-run-dir <completed-PX4-directory> --arducopter-run-dir <completed-AP-directory>
```

This script checks source/protocol consistency, not native/physical flight
acceptance. Separate successful independent audits remain required.
