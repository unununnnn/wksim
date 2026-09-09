# #94 NE runtime integration review — blocked

2026-09-09. This is a source-grounded integration contract, not a runnable NE release. #93 is complete; #35 remains OPEN. #94 currently allows only this document, a new `Simulator/wksim_runtime/ne-flight-v1.json`, and new ticket evidence. Its requirement that the candidate actually computes NE cannot be met by those two deliverables alone. No candidate JSON is published as runnable.

## Exact integration scope requiring assignment

The PID report's selector is in the external Python task, not the installed ROS Control node. The installed node consumes public XYZ_ATT. `position_pid.select_controller` rejects NE, and `pid_task.load_config` pins the exact PID bytes before selecting anything. Four runtime edits are required and currently outside this ticket's allowed paths:

1. `Simulator/wksim_runtime/pid_task.py`: explicit PID/NE dispatch with typed NEConfig and PositionNE; per-controller immutable protocol hash; NE trace/output/reset identity; initialize NE from the first fresh stage state after authority confirmation. Keep PID protocol behavior intact. Unknown/missing selections reject. Do not pass NE through PIDConfig or relabel PID output.
2. `tools/run_pid_flight.py`: seal selected configuration, NE algorithm and all imported dependencies; pass the selected protocol to task/physics; emit actual controller identity in admission/result/source copies. Preserve pre/post identity and cleanup gates.
3. `tools/pid_physics.py`: validate the selected frozen protocol/event binding, while retaining exact source packets, held inputs, every 1ms tick and latched revocation. Its current import and loader bind PID only.
4. `tools/audit_pid_flight.py`: independently recompute NE filters, both integrals, discarded LLF contribution, nominal/disturbance terms, force, attitude and native output from raw evidence. Current PID equations and protocol pin cannot audit NE. Never import the online NE update as the oracle.

Tests for these changes also require explicit ownership of the corresponding test files. The existing shell wrapper can retain its name and isolation behavior; no installed Control modification is needed for its existing public attitude outlet. This document does not authorize edits outside #94's allowlist.

## Proposed frozen run requirements

Reuse the PID physical budgets byte-for-value: quad-X library `cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`, mass 1.515 kg, physics step .001 s; timing maximum native dt .2 s and ACK .2 simulated s / 2 wall s, whole-run watchdog 360 wall s. These remain proposed NE admission limits until implemented and tested; no control-rate achievement is implied.

NE parameter proposal: kp=(.5,.5,.5), kd=(2,2,2), disturbance_limit=(1,1,1), t_ude_s=1, t_ne_s=1, per-axis tilt=8 degrees. Source semantics come from #93, upstream `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`, NE header hash `759e3296ea32eb34050ed8764c75e4bd88f6ba8cdb52da82c5e10b745f45fe7f`. These parameters are not tuned or flight validated.

Each stack/run must independently measure 3 s native ATTITUDE_TARGET median collective and pass the existing 2 s level validation before measurement. No previous/default hover. Validate model hash/mass and stack binding. AP positive collective and PX4 FRD negative Z mapping remain distinct. Calibration samples, model, source/config hashes, run ID, native generation, control epoch and installed paths must be recorded together.

Point: ENU (2,3,3), yaw 0, settle 6 s, measure 4 s, position .3 m, speed .3 m/s, yaw .15 rad. Circle: center (1.4,3,3), radius .6 m, period 12 s, settle 12 s, measure 12 s, position .35 m, yaw .15 rad; use analytic position/velocity/acceleration. Disturbance: actual four actuator inputs times .97 for exactly 1000 ticks, declared 2000 ticks ahead and loaded at least 1000 ticks ahead; 6 s settling, .5 m maximum error, return within 8 s with final 1.5 s dwell at .3 m/.3 m/s/.15 rad. Envelope: height 1.5–4.5 m, distance from point <=4 m, each tilt axis <=15 degrees. Freeze candidate bytes and independent audit pins before any run; do not adjust after seeing results.

Only new consumed native State timestamps advance NE. Duplicate timestamps produce no update; first fresh sample binds initial position and time without an output. Reject nonfinite/nonpositive time, backwards time or dt above budget without clamping or synthetic catch-up. Fresh armed state, COMMAND_CONTROL and unchanged epoch/generation are mandatory. PX4 must continuously prove attitude/rates/allocation enabled with position/velocity/altitude flags disabled; AP must prove GUIDED, required parameter readback and actual attitude outlet.

On selection, stage entry/release, loss, invalid time or epoch change, clear both integrals and all nine filters. Rebinding initial position is a full reset. A failed run cannot silently continue under a new epoch. Measured settling and measurement windows allow XYZ_ATT only. Native position preparation/recovery/land remain separately marked and cannot contribute NE success.

## Commands and acceptance gap

The only currently executable checks for this review are:

```powershell
python -B -m unittest validation.test_position_ne validation.test_pid_flight -q
python -B validation/lunar-94-astra-20260909-01/check_boundaries.py
```

There are no valid NE stack-specific flight commands today: the existing `run-pid-flight.sh --stack px4` and `--stack arducopter` paths both load the PID-only protocol. Supplying an NE JSON cannot satisfy them. After the four integrations and tests, publish separate one-run argv with new IDs and fresh `/root/wksim-pid-flight-*` directories, explicit config, per-stack preflight, and separate new audit outputs. Do not execute guessed commands or claim the proposed interface exists.

Independent acceptance must cover raw source/config identities, same-run calibration, every NE update/reset and initial-position binding, public request/command IDs through raw CDR/MAVLink native targets, and every 1ms physics input/output across fixed windows. Required rejection cases: PID mislabelled NE, changed filter/integral, stale/duplicate/backwards time, retained reset memory, wrong model/stack/run, substituted hover, native position during measurement, missed tick, altered disturbance/event binding and missing terminal/cleanup. Preserve native sampling limitations rather than claiming exact unseen acceptance times. `observed` and `online_ok` remain provisional. #95/#96 cannot be released from this review; R1, RateUnmet and Full remain unchanged.
