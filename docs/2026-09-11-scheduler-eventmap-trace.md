# Event-driven FC scheduler trace

## Scope and identity

The ground diagnostic used the event-driven exact-comm mapping added by `8923cff`:

```bash
python3 -B tools/profile_joint_scheduler.py \
  --output /root/wksim-scheduler-probe-eventmap-01
```

The retained run is `scheduler-4598ca8a747b`, epoch
`e91fd8e50550468bbbe6b29f06bffe64`. The full 85,038,066-byte evidence tree remains
at `/root/wksim-scheduler-probe-eventmap-01`; the bounded analysis is retained in
`validation/33-scheduler-fc-trace-eventmap-01/summary.json`.

This was a 10-second ground diagnostic with the legacy `joint_quad_dds_v1` profile.
It is not a flight or rate acceptance result, and the summary therefore records
`acceptance_eligible=false`.

## Mapping and capture integrity

The private `sched_switch` mapping resolved all nine required roles: AP worker, PX4
worker, supervisor, AP `arducopter`/`log_io`/`DDS`, and PX4
`sim_send`/`logger`/`wq:lp_default`. Exact comm ownership was checked against global
`/proc` task inventories before and after mapping. Local namespace IDs and kernel
trace IDs differ, confirming that the trace uses the mapped IDs rather than the WSL
namespace IDs. The mapping trace contains 27,919 bytes with SHA-256
`66d38782994c84c36e8adedfddcbb38d863c8f4fe5514895ce564df9140c31ce`.

The main capture lasted 10.000255023 seconds and produced 31,023,302 bytes with
SHA-256 `484c4f2f31f56612c6fcf55f21a077104c4ca74551a1996eb6aa4fd008366a7b`.
It contains 118,538 scheduler switches, 56,115 wakeups, and 23,665 matched write
entry/exit pairs. Every per-CPU overrun, commit-overrun, and dropped-event counter
remained zero. The private trace instance was removed, the original global controls
were restored unchanged, all epoch process groups retired, and the manager,
preflight, and collector returned zero.

Eight switch-in events lacked a preceding switch-out at the capture boundary, and
nine off-CPU intervals remained open at the end. No write, sync, or syscall interval
was left open. Boundary half-events are excluded rather than reconstructed.

## Rate result

The captured run failed the unchanged strict cumulative-lateness rule at tick 8204:

- rejection: `rate_unmet` at 100,044,370 ns;
- segment: 2,041 four-tick groups, tick 40 through 8204, over 8.263232983 seconds;
- group duration: 3.234184 ms median, 4.517957 ms p99, 13.261794 ms maximum;
- groups exceeding the 4 ms period: 117;
- positive phase increments: 98.872729 ms in total;
- preceding-group excess associated with those increments: 55.840930 ms.

Replaying the recorded boundaries through the unchanged `JointRate` logic reproduces
the recorded RED failure. This establishes cumulative rate loss in this diagnostic;
it does not by itself identify the underlying workload or scheduler cause.

The largest group ended at tick 1928. Its 13.261794 ms duration included a
9.652471 ms native-input stage, but it occurred before the main trace window and
cannot be assigned to a traced FC thread. Inside the main window, the longest
recorded combined AP-then-PX4 input wait was 6.573279 ms at tick 5504. Supervisor
thread CPU was 0.717249 ms; the scheduler trace overlapped 5.878 ms off CPU, including
5.829 ms before wake and 0.049 ms runnable. That timing is co-occurrence: it does not
separate the AP and PX4 waits or prove that any mapped FC thread, Windows scheduling,
or physical storage caused the delay.

Of 54 recorded native waits, 28 lay fully inside the capture window and 26 crossed a
capture boundary and were excluded from scheduler attribution. The inside-window
samples were:

| Native path | Samples | Median | Maximum | Over 2 ms |
| --- | ---: | ---: | ---: | ---: |
| AP input only | 11 | 0.190259 ms | 0.427015 ms | 0 |
| AP then PX4 inputs; not separated | 17 | 0.353212 ms | 6.573279 ms | 1 |

## Write evidence

The model worker writes did not show a millisecond-scale storage tail:

| Path | Complete writes | Median | P99 | Maximum | Over 1 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| AP trace file | 5,901 | 6 us | 65 us | 393 us | 0 |
| AP RPC stdout | 5,901 | 3 us | 16 us | 96 us | 0 |
| PX4 trace file | 5,901 | 6 us | 66 us | 293 us | 0 |
| PX4 RPC stdout | 5,901 | 2 us | 16 us | 97 us | 0 |

The AP `log_io` thread completed 61 writes: 12 us median, 75 us p99, and 87 us
maximum, with no failure, short write, write over 1 ms, `fsync`, or `fdatasync`.
No write or sync call was captured for the mapped PX4 `logger` thread. This window
does not support a storage-stall change.

The next diagnostic must reproduce a slow in-window native wait with narrower AP/PX4
request boundaries, then correlate the responsible FC and host intervals. The fixed
1 ms physical step, native barriers, no-catch-up behavior, and strict `>100 ms`
cumulative-lateness threshold remain unchanged.
