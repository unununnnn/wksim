# UDE frozen numeric literals -> ROS float message boundary

Root reported the first real PX4 run failed before UDE updates with a generated
ROS position_ref float setter assertion. Original failed flight/audit remains in
ude-runtime-acceptance-20260909 and its immutable /root run directory.

Actual chain: PIDTask.execute takes integer JSON point [2,3,3], yaw0 ->
PIDTask.command -> AttitudeTask.command -> UAVCommand position_ref/yaw_ref setter.
The stage neutral/level commands also carry integer yaw into att_ref. PID frozen
JSON uses floats, so earlier PID message coverage did not reveal this case.

Fix is restricted to PIDTask.command: convert position/attitude finite real
components and position-mode yaw to Python float using existing _finite validation.
The measured-stage helper prohibition remains first. Booleans, strings, NaN and
infinity reject; ROS-generated vector length/range checks remain. Caller config
is not mutated and PID/UDE frozen bytes, hashes, algorithm and physical/timing
budgets remain unchanged.

Actual ROS regression creates UAVCommand through real PIDTask.command and inherited
AttitudeTask.command, serializes/deserializes with the admitted generated codecs,
and verifies both frozen config variants, integer yaw/default yaw/attitude yaw,
and invalid scalar rejection. No ROS node or simulation is created.

Commands (repo root):

```powershell
python -B validation/ude-runtime-float-message-20260909/check.py red-02
python -B validation/ude-runtime-float-message-20260909/check.py green
```

red-02: actual regression before fix failed with the exact position_ref symptom,
plus yaw_ref/att_ref/default-yaw failures. green: 48 targeted UDE runtime + PID
runtime + independent PID audit tests passed, zero skips. Exact WSL argv,
stdout/stderr and return codes are retained in corresponding files.

The first red capture skipped because its harness export lost the sourced
PYTHONPATH in WSL command argument handling; it is retained as an invalid repro,
not a pass. red-02 fixes only harness dependency injection using sys.path before
unittest, as the existing audit runner does. Both use the same real admitted ROS
overlays. WSL's localhost proxy warning is retained in stderr.

source-sha256.json binds final code/test/frozen inputs. This change does not turn
the first failed flight into success; a new run ID and new preflight are required.
