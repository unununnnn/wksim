# Scheduler bootstrap startup timeout, 2026-09-12

## Scope

This note retains the first real scheduler probe after commit `04aced1`. The probe was diagnostic only and was not acceptance eligible.

The command was:

```text
wsl -d Ubuntu-22.04 --cd /mnt/c/Users/PC/Documents/odid编译/wksim -- python3 -B tools/profile_joint_scheduler.py --output /root/wksim-scheduler-probe-20260912-bootstrap-01
```

The retained machine-readable summary is
`validation/33-scheduler-bootstrap-startup-timeout-20260912/summary.json`.
The raw evidence remains outside the repository at
`/root/wksim-scheduler-probe-20260912-bootstrap-01`.

## Observed result

The profile exited with `status=diagnostic_partial` and
`TimeoutError: Native target startup`. Its outer preflight completed with
return code 0. The manager then created epoch
`273040932b044f07a1f105bcd41600c9`, but that epoch created only the owned
`runtime --prepared --preflight` child. No model, ArduPilot, PX4, DDS agent,
or planner child was started.

The inner preflight log is empty and the child was still running when the
fixed 180 second native-startup deadline expired. The stop request then
terminated that child with return code -15. The manager's final return code
0 records controlled shutdown; it is not a successful run.

The run remained at tick 0. It produced no first physical step, trace capture,
capture token, gate token, or tracefs instance. Therefore this attempt says
nothing about the new capture bootstrap after native startup and cannot be
used as rate, flight, or G0-G6 acceptance evidence.

Cleanup did complete: the manager process group and epoch process group were
retired, no manager members remained, the source hashes were unchanged, and
the report contains no cleanup error.

## Root cause boundary

`profile_joint_scheduler.py` first performs a complete preflight. The manager
then performs a second complete preflight before it launches native targets.
That second check includes the AP and PX4 source snapshots (24,593 and 42,012
files respectively), package and manifest identities, the model artifact,
overlay state, and flight proof.

The manager ran as `SCHED_FIFO` priority 50 with `reset_on_fork=false`. The
inner child was assigned nice -5, but its actual scheduling policy was not
recorded. It can therefore inherit the manager's real-time policy. This is a
concrete code risk, although the retained evidence cannot prove that policy
inheritance alone caused the slow preflight.

The evidence supports fixing and recording the inner preflight scheduler
before changing any deadline. Merely extending 180 seconds would hide the
repeated work or real-time inheritance risk. Reusing the outer preflight is
also deferred: it would require a single-use admission bound to the same
configuration, profile, package, manifest, source, model, overlay, and flight
proof identities.

## Next candidate

The next candidate must place the inner preflight child in `SCHED_OTHER`
before the expensive identity walk, record its actual policy and elapsed
phase time, and fail closed if that isolation cannot be established. The
180 second startup deadline remains unchanged. The 1 ms physical step,
native input and clock barriers, no-catch-up rule, and strict cumulative
lateness greater than 100 ms failure gate also remain unchanged.

A new real probe is allowed only after the scheduler isolation change passes
offline tests and independent review. It must use a new absent output
directory; this failed candidate must not be rerun unchanged.
