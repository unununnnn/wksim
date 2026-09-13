# #94 NE runtime integration and flight contract — v1

2026-09-10. #93 and #35 are complete. This document records the bounded NE
runtime integration implemented in the same external XYZ_ATT task seam as
PID/UDE, plus the fresh stack flight runs and independent audits. The frozen
configuration is `Simulator/wksim_runtime/ne-flight-v1.json`, SHA256
`3b09761ad60976aa971f43e81edc0de9bb4ede7065a10b5d512c57c22a478e18`.

## Exact integration scope requiring assignment

The installed Control node already consumes public XYZ_ATT. The selected
external task binds NE explicitly while preserving PID/UDE defaults. The
bounded runtime change covers four existing files plus one independent auditor:

1. `Simulator/wksim_runtime/pid_task.py`: explicit PID/UDE/NE dispatch with typed NEConfig and PositionNE; per-controller immutable protocol hash; NE trace/output/reset identity; bind initial position at stage takeover. PID and UDE behavior remains unchanged.
2. `tools/run_pid_flight.py`: seal selected configuration, NE algorithm and all imported dependencies; pass the selected protocol to task/physics; emit actual controller identity in admission/result/source copies. Preserve pre/post identity and cleanup gates.
3. `tools/pid_physics.py`: selected protocol/event binding, exact source packets,
held inputs, every 1ms tick and latched revocation are retained.
4. `tools/audit_pid_flight.py` plus `tools/audit_ne_flight.py`: independently
recompute NE filters, both integrals, discarded LLF contribution,
nominal/disturbance terms, force, attitude and native output from raw evidence.
The NE oracle never imports the online NE update.

Tests are `validation/test_ne_runtime.py` plus the existing PID/UDE suites. The
shell wrapper and installed Control package remain unchanged; no installed
Control modification is needed for the existing public attitude outlet.

## Proposed frozen run requirements

Reuse the PID physical budgets byte-for-value: quad-X library `cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`, mass 1.515 kg, physics step .001 s; timing maximum native dt .2 s and ACK .2 simulated s / 2 wall s, whole-run watchdog 360 wall s. These are the frozen NE admission limits used by the runs; no control-rate achievement is implied.

NE parameters are kp=(.5,.5,.5), kd=(2,2,2), disturbance_limit=(1,1,1),
t_ude=1, t_ne=1 and per-axis tilt=8 degrees. Source semantics come from #93,
upstream `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`, NE header hash
`759e3296ea32eb34050ed8764c75e4bd88f6ba8cdb52da82c5e10b745f45fe7f`.

Each stack/run must independently measure 3 s native ATTITUDE_TARGET median collective and pass the existing 2 s level validation before measurement. No previous/default hover. Validate model hash/mass and stack binding. AP positive collective and PX4 FRD negative Z mapping remain distinct. Calibration samples, model, source/config hashes, run ID, native generation, control epoch and installed paths must be recorded together.

Point: ENU (2,3,3), yaw 0, settle 6 s, measure 4 s, position .3 m, speed .3 m/s, yaw .15 rad. Circle: center (1.4,3,3), radius .6 m, period 12 s, settle 12 s, measure 12 s, position .35 m, yaw .15 rad; use analytic position/velocity/acceleration. Disturbance: actual four actuator inputs times .97 for exactly 1000 ticks, declared 2000 ticks ahead and loaded at least 1000 ticks ahead; 6 s settling, .5 m maximum error, return within 8 s with final 1.5 s dwell at .3 m/.3 m/s/.15 rad. Envelope: height 1.5–4.5 m, distance from point <=4 m, each tilt axis <=15 degrees. Freeze candidate bytes and independent audit pins before any run; do not adjust after seeing results.

Only new consumed native State timestamps advance NE. Duplicate timestamps produce no update; first fresh sample binds initial position and time without an output. Reject nonfinite/nonpositive time, backwards time or dt above budget without clamping or synthetic catch-up. Fresh armed state, COMMAND_CONTROL and unchanged epoch/generation are mandatory. PX4 must continuously prove attitude/rates/allocation enabled with position/velocity/altitude flags disabled; AP must prove GUIDED, required parameter readback and actual attitude outlet.

On selection, stage entry/release, loss, invalid time or epoch change, clear both integrals and all nine filters. Rebinding initial position is a full reset. A failed run cannot silently continue under a new epoch. Measured settling and measurement windows allow XYZ_ATT only. Native position preparation/recovery/land remain separately marked and cannot contribute NE success.

## Commands and acceptance gap

The implementation and independent audit commands are:

```powershell
python -B -m unittest validation.test_position_ne validation.test_pid_flight -q
python -B -m unittest validation.test_ne_runtime validation.test_ude_runtime validation.test_pid_flight_audit -q
bash tools/run-pid-flight.sh --stack px4 --run-id ne-px4-acceptance-20260910-01 --config Simulator/wksim_runtime/ne-flight-v1.json --preflight
bash tools/run-pid-flight.sh --stack arducopter --run-id ne-arducopter-acceptance-20260910-01 --config Simulator/wksim_runtime/ne-flight-v1.json --preflight
```

The same isolated runner accepts the exact frozen NE configuration. Each flight
uses a fresh `/root/wksim-pid-flight-*` directory and a separate audit output;
retained command records and reports are under
`validation/ne-runtime-acceptance-20260910/`.

Independent acceptance covers raw source/config identities, same-run calibration,
every NE update/reset and initial-position binding, public request/command IDs,
native targets, every 1ms physics input/output, fixed windows and owned cleanup.
PID-mislabel, changed memory, stale/duplicate/backwards time, wrong model/stack,
substituted hover, native position during measurement, missed tick and altered
disturbance bindings remain rejection cases. Native sampling limitations remain
explicit; no exact unseen acceptance time is claimed. #95/#96 are complete for
this NE physical slice; R1, RateUnmet and Full remain unchanged.

## Recorded flight results

PX4 run `ne-px4-acceptance-20260910-01` completed and landed with owned-child
cleanup intact. Its first audit invocation was rejected by a missing auditor
argument; that report remains preserved. The corrected independent audit is
`validation/ne-runtime-acceptance-20260910/px4-boundary2-strict-audit-report.json`,
SHA256 `5cd6eff3b8bdf817035e6d31b2f9579346be61c32e5c31102f369c6f090e4e48`.
It checked 93,400 physical ticks, 850 native associations and NE recomputation
counts point 167 / circle 399 / disturbance 284. Maximum position errors were
0.104605 m, 0.142220 m and 0.119038 m for point, circle and disturbance.

ArduCopter run `ne-arducopter-acceptance-20260910-01` also completed and landed
with 659 native associations, 510 motor comparisons and 126,336 physical ticks.
Its strict audit is `validation/ne-runtime-acceptance-20260910/arducopter-strict-audit-report.json`,
SHA256 `c12fc18c3f95cc8bc62b371d0bf20833d662a3531a9feba7ca0ce1f9f76be688`.
NE recomputation counts were point 132 / circle 307 / disturbance 220; maximum
position errors were 0.163224 m, 0.158618 m and 0.160244 m. Both reports bind
the same frozen protocol/model/source manifest and retain exact input hashes.
