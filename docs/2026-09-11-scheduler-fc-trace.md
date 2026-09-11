# Five-owner FC scheduler trace at `75eff14`

## Scope and identity

The diagnostic command was:

```bash
python3 -B tools/profile_joint_scheduler.py \
  --output /root/wksim-scheduler-probe-75eff14-01
```

It ran from commit `75eff14893d33d3dcd4f78084aade8bdb60db33f` as run
`scheduler-5fcc2ecfd454`, epoch
`d3ea3e617ea841d09d5280c42d9deede`. The full 147 MiB source directory remains at
`/root/wksim-scheduler-probe-75eff14-01`; the repository retains the bounded audit
summary in `validation/33-scheduler-fc-trace-75eff14/summary.json`.

This was a ground diagnostic. `acceptance_eligible` is false, so it cannot count as a
rate or flight pass.

## What the trace established

The private tracefs instance mapped all intended owners and threads:

- AP worker, PX4 worker, and the joint supervisor;
- AP `arducopter`, `log_io`, and `DDS` threads;
- PX4 `sim_send`, `logger`, and `wq:lp_default` threads.

The 10.000323148 second capture completed without dropped trace events. The private
instance was removed, the global trace controls were unchanged, the manager exited
zero, the epoch process groups retired, and the checked sources remained unchanged.
The retained raw trace is 45,136,380 bytes with SHA-256
`13ba41545629621aeafe141c7d36bce8d7728bad54ded6270a505159124982c5`.

Within the capture window, none of the recorded native-input waits exceeded 2 ms.
Twenty AP-only samples had a 158.340 microsecond median and a 410.492 microsecond
maximum. Twenty combined AP-then-PX4 samples had a 268.0315 microsecond median and a
617.686 microsecond maximum. The separate native analyzers saw maxima of 454.474
microseconds for ArduCopter and 377.987 microseconds for PX4.

The AP `log_io` thread completed 105 writes. Their median was 10 microseconds, p99 was
46 microseconds, and maximum was 68 microseconds; no write exceeded 1 ms, and no
`fsync` or `fdatasync` was observed. No write or sync call was captured for the mapped
PX4 `logger` thread. The captured window therefore does not support a storage-stall
change.

## Rate result and remaining gap

The 1x segment covered 3,934 four-tick groups from tick 40 through 15,776. Group
duration had a 3.061358 ms median, 3.993087 ms p99, and 14.624236 ms maximum. The
ending phase was 87.154593 ms late, below the strict 100 ms latch, but this diagnostic
duration does not satisfy the formal rate dwell.

The largest phase jumps were early:

| Tick | Phase increase | Prior-group excess | Release residual |
| ---: | ---: | ---: | ---: |
| 5504 | 10.692813 ms | 10.624236 ms | 0.068577 ms |
| 1928 | 9.129197 ms | 9.088804 ms | 0.040393 ms |
| 2000 | 5.830800 ms | 5.093132 ms | 0.737668 ms |
| 1936 | 4.552243 ms | 4.490909 ms | 0.061334 ms |
| 4272 | 3.543936 ms | 3.085567 ms | 0.458369 ms |

At tick 5504, the 14.624236 ms group included 10.435053 ms in native inputs but only
1.217805 ms of supervisor thread CPU. That interval, along with the other largest
early spikes, fell before the FC comm-to-kernel-TID mapping finished and tracing was
enabled. The captured trace therefore cannot assign those stalls to the FC threads.

The next diagnostic change must start the private FC trace before these early events,
using a fail-closed direct namespace-TID mapping or an equivalent verified mechanism.
Until such a trace reproduces a slow interval, no scheduler, storage, model, barrier,
or release-path implementation change is justified. The fixed 1 ms physical step,
native barriers, no-catch-up behavior, and strict cumulative lateness threshold remain
unchanged.
