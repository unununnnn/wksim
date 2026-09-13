# First-step scheduler gate startup failure

## Identity and scope

The diagnostic command was:

```bash
python3 -B tools/profile_joint_scheduler.py \
  --output /root/wksim-scheduler-probe-20260912-gated-01
```

It ran once from commit `ce5d23dd1c7df71899fbe9a2ce0e52d510fa5777`
as run `scheduler-c6bc7af31dba`, epoch
`586209af37b94e278bc60547d68aa6e5`. The full 132-file,
24,449,840-byte evidence tree remains at
`/root/wksim-scheduler-probe-20260912-gated-01`. The repository retains the
bounded audit summary in
`validation/33-scheduler-gated-startup-20260912/summary.json`.

This was a ground diagnostic. It did not complete a trace window or a flight
task and is not rate, scheduler-cause, flight, or acceptance evidence.

## Failure established by the run

The supervisor reached `JointPhysics.advance()` at physical tick zero and
published a valid `capture-gate-ready.v1` record. It did not advance the
physical clock. Fifteen seconds later it failed closed because no
`capture-active` token had been published.

The AP and PX4 model workers and native FC processes had started. `children.json`
contains their owned PID/start-tick identities, all three diagnostic process
names were published, `wire.jsonl` contains AP actuator and PX4 connected
events, and both FC logs show that they were waiting for sensor traffic.
There are no sensor or physical-step wire events; every recorded wire tick is
zero.

The outer profile nevertheless waited for its 180-second native-target
deadline and reported `TimeoutError: Native target startup`. That label is not
the underlying failure. The profile required all six selected FC thread names
before starting the collector, while the supervisor required the collector's
active token before releasing tick zero. The collector also performed the FC
thread inventory and kernel-TID mapping before publishing its active token.
The AP `DDS` and related FC threads observed in earlier running captures become
available only after simulation traffic begins, so the two sides waited on
each other.

No `capture-launch.json`, `capture/`, or gate-release record exists, and
`collector.log` is empty because the collector was never spawned. This run
therefore cannot classify native waits, scheduler delay, storage, release
paths, or model cost.

## Cleanup and next boundary

The manager returned one after the fail-closed supervisor fault. The manager
group and epoch groups were retired, no scheduler or collector process remains,
the seven pinned sources were unchanged, and no global tracing controls were
touched because no private trace instance was created.

The next code revision must bootstrap a private, bounded scheduler capture and
publish a truthful create-only active proof before releasing tick zero. It must
then bind the late-appearing FC threads to unique owned kernel TIDs inside the
same retained window before installing the final exact filters. Startup
readiness snapshots and supervisor faults must be retained so a missing or
ambiguous thread fails immediately with its real reason. No further real probe
is allowed until that sequence is covered by offline tests and independent
review.

The fixed 1 ms physical step, native input and clock barriers, no-catch-up
behavior, and strict cumulative lateness threshold above 100 ms remain
unchanged.
