# Self-thread perf capability on WSL2

The main coordinator verified a short self-thread context-switch probe on
Linux 6.6.87.2-microsoft-standard-WSL2. It ran as root, with software DUMMY,
`pid=0`, `cpu=-1`, `inherit=0`, `exclude_kernel=1`, and CLOCK_MONOTONIC.
No flight, global scheduler change, other-PID tracing or installation occurred.

The [execution receipt](../validation/coordination/perf-c-acceptance-20260913-03/receipt.json)
records compilation with `-Wall -Wextra -Werror`, 32 successful author checks,
13 successful independent cases and a timeout formatter regression that now
reports failure. Only after these passed did the launcher execute the probe.
Both WSL prechecks were empty and matched the execution boot within 60 seconds.

The [actual probe result](../validation/coordination/perf-c-acceptance-20260913-03/probe-result.json)
contains eight records: four switch-outs and four switch-ins, consuming all
256 pending bytes. It reports no loss, foreign identities, malformed records,
pairing errors or timestamp reversals. Elapsed time was 600,490,334 ns.
All owned compiler/test/probe processes exited and their process groups were
empty on the same boot. No keeper was used.

The executed probe source SHA256 is
`02669b424c04a10aa9db2b68406b52f92ce90ced90be78e0c2d2209acf73077f`.
Executed source snapshots and hashes are retained with the receipt. Private
binaries were placed under `/root/wksim-perf-c-tests-k769545e` so a WSL boot
change does not remove them as happened with the previous `/tmp` build.

The earlier [compiled formatter counterexample](../validation/coordination/perf-c-acceptance-20260913-02/receipt.json)
is preserved: a one-second timeout with a failed status incorrectly printed
`self_thread_switch_capable`. The final verdict now checks parser status,
the overall failure flag, cleanup, timing and elapsed time. Integration also
keeps geometry observations separate from saved syscall errno values.

This proves a short capability test in this execution environment. It does
not prove access for an unprivileged process, affordable overhead during a
whole flight, a loss-free full-flight recorder or the cause of MIXED lateness.
The raw ring bytes were not retained by this capability program; its actual
result, executed implementation, independent tests and source hashes are
retained. A future recorder must preserve raw records and explicitly reject
overflow before its output is used to attribute release gaps.

MIXED, G6 and Full remain incomplete under their original acceptance gates.
