# Stop-check validation for a bounded observation window

Historical implementation, superseded by the [kernel loss counter](2026-09-13-perf-kernel-loss-counter.md).
The following describes the preserved sentinel source and its original tests,
not the selected recorder or current completeness rule.

The historical independent perf recorder drains through its reader before bracketing
an owner-thread nanosleep while the event remains enabled. It then disables,
drains, joins and writes the captured bytes. This adds work only at stop; no
pacing loop, model, controller, firmware or UE interface was changed.

The consumer verifies the actual out/in pair inside the reported clock bounds.
It also requires a completed check, ordered timestamps, sufficient reported
headroom and an exact cutoff. Any LOST record is rejected before this check.
Requested windows cannot end after `sentinel_before_ns`. Global
`stream_completeness_proven` remains false; the final tail is not certified.
Legacy captures with no check retain their previous inspection-only behavior.

The [native results](../validation/coordination/perf-stop-sentinel-20260913-01/main-verdict.json)
include the existing fault cases, 84 consumer checks and 14 new synthetic
stop-check cases. A normal capture retained 640 bytes / 20 records. The
independent consumer found the actual check pair, accepted the earlier window,
and rejected a one-nanosecond extension beyond its cutoff.

The [controlled kernel-loss test](../validation/coordination/perf-stop-sentinel-20260913-01/loss-receipt.json)
paused only its owned reader after copying 88,544 bytes and before publishing
the consumed tail. The owner performed 20,000 short sleeps, causing real kernel
buffer loss. After resuming, the retained raw stream contained a 48-byte LOST
record reporting 26,376 dropped events. The ring pressure counter was zero and
`collector_complete` was true; the independent consumer nevertheless rejected
the stream with `record_lost_present`. Thus a clean collector flag or alternating
out/in records alone is insufficient. The pause and 100ms poll are test-only,
not a production performance configuration.

All owned compiler, test and consumer processes exited, with same-boot cleanup
checks. The test retains raw records, metadata, source hashes and commands.
It exercises published LOST after an induced loss; it does not establish a
global no-loss property across disable or after the cutoff.

The implementation depends on the fixed self-thread/single-DUMMY-event producer
and Linux perf's lost-record publication semantics. Its [historical review](coordination/omp-stop-sentinel-review-20260913.md)
is retained; the exact current-kernel counter review supersedes that mechanism.
Whole-run overhead and integration with actual rate windows remain pending;
this is not flight, architecture, MIXED, G6 or Full acceptance.
