# Early-capture scheduler diagnostic failure

## Identity and scope

The diagnostic command was:

```bash
python3 -B tools/profile_joint_scheduler.py \
  --output /root/wksim-scheduler-probe-20260912-early-01
```

It ran from commit `0e38b576931b8513786cee6e82ff27c9d8f2b118` as run
`scheduler-b2fdbe6bbb69`, epoch
`4ae610f093ae4ea786e39f44ab083aa4`. The full source directory remains at
`/root/wksim-scheduler-probe-20260912-early-01`; the repository retains the
bounded audit summary in
`validation/33-scheduler-early-capture-20260912/summary.json`.

This was a ground diagnostic. It did not launch a flight task and is not rate,
flight, scheduler-cause, or acceptance evidence.

## Failure established by the run

The profile exited one with `status=diagnostic_partial` and
`RuntimeError: Capture became active at or after timed tick 40`. The first
status snapshot used to begin capture already reported tick 1836. The private
tracefs token was published at monotonic `304192624808 ns`, after the tick 2319
step at `304191884903 ns` and 23,995 ns before the first recorded tick 2320
sensor event. The rate anchor for tick 40 was `301851906204 ns`; capture became
active about 2.341 seconds after that anchor.

The collector therefore recorded only 8.860488 ms before the profile stopped
the run. Its metadata is `complete=false`, `status=diagnostic_partial`, and
`signals=[15]`. The 33,334-byte trace is loss-free within that short window,
but it excludes the earlier slow intervals this diagnostic was intended to
classify. It cannot support a native-wait, scheduler, storage, release-path, or
model-cause conclusion.

The final completed rate segment covered 595 four-tick groups, measured
0.9737153650145289x, and ended 65.521748 ms late without latching the strict
100 ms limit. The product stopped at tick 2420 with
`flight_completed=false`. These values describe an interrupted diagnostic and
do not satisfy the formal rate dwell.

## Cleanup and retained boundary

The manager exited zero. The collector exited one after the early-capture guard
failed and was terminated for cleanup. The manager group and epoch groups are
empty, the private tracefs instance was removed, global tracing controls were
unchanged, and the seven checked sources remained unchanged. The capture
token, collector identity, private instance inode, run, epoch, and all intended
owner mappings were internally consistent.

The next diagnostic must hold the supervisor before its first physical step,
publish a run/epoch/tick-zero readiness proof, activate the private tracefs
instance and exact FC thread mappings, then release the supervisor only after a
validated capture-active token is durably bound into a release proof. The gate
must remain diagnostic-only and bounded. The fixed 1 ms physical step, native
input and clock barriers, no-catch-up behavior, and strict cumulative lateness
limit remain unchanged.
