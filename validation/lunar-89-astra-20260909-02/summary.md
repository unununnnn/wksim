# #89 / 36-algorithm — fixed upstream UDE

Completed the bounded pure-algorithm slice. Source files: `Simulator/wksim_control/position_ude.py`, `validation/test_position_ude.py`, `tools/check_position_ude_source.py`. No runtime selection, flight, performance or parent acceptance claim. #35 remains OPEN; the user's explicit pure-source assignment and child guide permit this slice before unrelated whole-flight acceptance. #90 owns selection/run integration.

## Source and equations

Prometheus commit `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`, `Modules/uav_control/include/Position_Controller/pos_controller_UDE.h`, working-byte SHA256 `ae0c9a300e435775b836f56667aadf90e4779db0b116218178d747bb50ce6699`. The five original headers are copied with working and LF upstream blob hashes in `identities.json`; every original is byte-equal after CRLF-to-LF normalization to git-show of the pinned commit. Original files were not changed.

Codebase Memory native `index_status --project wksim-prometheus` returned ready (50865 nodes / 165157 edges). `search_graph --project wksim-prometheus --query pos_controller_UDE --limit 6` located init 67–93 and update 95–215. Actual header, dependencies and caller `uav_controller.cpp` UDE branch 419–427 were read. The caller uses update(200.0). Graph was navigation only; no post-edit structural query or completeness claim.

For componentwise clipped position/velocity errors e,v in [-3,3]: u_l=a_ref+Kp*e+Kd*v; u_d=-(Kp*I_old+Kd*e+v)/T; update I by e*dt iff abs(e)<0.5, else clear; clamp u_d by disturbance_limit; acceleration=u_l-u_d. Integral is NOT clamped and moving references do NOT clear it. The clearing cycle still uses old integral. Original vertical force scaling (including negative-Fz horizontal sign reversal), per-axis tilt bounds, current-yaw roll/pitch and current-body-Z force projection are preserved.

Defaults reproduce upstream init: Kp=.5, Kd=2, T=1s, disturbance limit=1, tilt=20 degrees, gravity=9.8; mass must be explicit. Python configuration supports independent axis values; the original ROS parameter loader couples XY. Existing PIDState/PIDReference and NativeThrustConfig data/mapping contract are reused, never PositionPID or its update. Output reports controller=ude and exposes nominal and disturbance acceleration separately.

Explicit differences: positive finite T/mass/dt and nonnegative finite gains/limits required; state/reference require finite values and unit quaternion; zero Fz and intermediate overflow reject before committing state. Invalid calls preserve last valid history. A valid inactive call clears integral/last_output and raises, whereas upstream has no mode gate. Reset requires a reason and clears all persistent algorithm state; caller must reset on selection/takeover/release/restart/clock discontinuity. Pure dt input cannot itself detect a clock jump. Python takes actual simulation dt; the oracle alone supplies float32(1/float32(hz)) matching original float dt. Diagnostic tracking-error windows/logging are omitted and do not feed control. Float toRad rounding explains bounded force/attitude differences. Thrust remains independently calibrated through existing mapping.

## Fixed comparison and real results

Protocol canonical SHA256 `52d106448a01e0e4460a50f12a0a513f5ca822f77cad1b56fa66b4d102fc93b2`, now checked by the tool. Inputs use rational arithmetic and literal quaternions, avoiding platform sin/cos regeneration. Tolerances were declared before the first run: abs=2e-6, rel=2e-7, unchanged. Original init/update functions are directly included and executed; only class private visibility changes in the fixture. ROS NodeHandle/UAVState are shells; real Eigen 3.4.0 and g++ 11.4.0 are used. Reset comparison invokes original init.

Both offline runs passed: 1223 cases x 2 parameter sets = 2446 samples, 16 channels = 39136 compared values. Cases cover hover, signed boundaries, persistent integral/disturbance saturation, clearing/reset history, variable dt/moving reference, negative/low/high vertical force, tilt and current attitude projection. Max force error 5.557479489937123e-7 N, max roll/pitch error 1.2518821201901176e-8 rad; integral/u_l/u_d/Z-force/yaw/collective errors zero. See raw config input/stdout, per-case comparison JSONL, compile/version logs and binary hash. Run 01 preserves initial evidence; run 02 verifies the final tool after adding the explicit protocol identity guard. No tolerances or cases changed.

Commands from project root:

```powershell
python -m unittest validation.test_position_ude -v
wsl -d Ubuntu-22.04 -- python3 tools/check_position_ude_source.py --evidence validation/lunar-89-astra-20260909-01
wsl -d Ubuntu-22.04 -- python3 tools/check_position_ude_source.py --evidence validation/lunar-89-astra-20260909-02
python -m unittest validation.test_position_ude validation.test_position_pid -v
wsl -d Ubuntu-22.04 -- python3 -m unittest validation.test_position_ude validation.test_position_pid -v
```

12 UDE tests passed initially. Final Windows and WSL tests each passed 24 (12 UDE + 12 existing PID), zero skipped. Logs saved here. Negatives cover invalid configuration/state/dt/active type, inactive reset/reject, empty reset reason, zero Fz, overflow, model identity mismatch, and invalid-cycle history preservation. WSL emits its existing localhost proxy warning but tests and oracle exit successfully. The original math_utils.h emits an unused sign_function missing-return warning; this function is not called by UDE. No comparison/test failures occurred. No FC/model/ROS/UE processes were started; temporary offline build directories were removed by the context manager after binary hashing.

Scoped source/test/tool/summary staged whitespace checks pass. Whole-evidence whitespace checking reports original header whitespace, raw oracle output trailing spaces and CRLF logs; raw bytes are intentionally preserved, not reformatted to suppress evidence warnings.

## Model verification

Current thread `01a0856d-8757-7442-b45c-644c51d0d567` latest local rollout turn_context reports `model=gpt-6-astra`, `effort=low`. Older turn_context records are Luna/xhigh and are not represented as the current setting. No subagents were used.

All #89 pure slice completion criteria satisfied. Full/PID-parent/runtime UDE acceptance remains unproven. Other writers' NE files were left outside this commit.
