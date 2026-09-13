# Kernel event-loss counter replaces the stop sentinel

The selected recorder uses `PERF_FORMAT_LOST` (`read_format=16`) on a fresh
self-thread software DUMMY event. After DISABLE and before closing the event,
it requires a complete 16-byte value/lost read. Nonzero loss, failed/short reads
or exhausted EINTR retries invalidate capture. Unknown counts are `null`, not
zero. No extra stop sleep or checkpoint polling is required.

This mechanism was checked against the actual WSL kernel source tag
`linux-msft-wsl-6.6.87.2`, commit `427645e3db3a8896714f22a3d3fe0c3f7b317ad4`.
The [independent review](coordination/omp-perf-lost-counter-review-20260913.md)
records the output-failure increments and post-disable read path. RESET does
not clear this counter, so a new event fd remains mandatory. Mmap must precede
ENABLE; no inheritance or output redirection is used.

The [minimal native probe](../validation/coordination/perf-lost-counter-20260913-01/receipt.json)
recorded zero loss normally. In its overflow case it never drained the ring:
after DISABLE, the queue contained 127 SWITCH records and no LOST record, while
the fd reported 385 lost events. This demonstrates direct visibility of pending
loss without inducing another event to publish a LOST record.

The integrated recorder passed its existing native fault cases and normal raw
decoding. A controlled reader stall produced a second pending-loss case:
16,383 raw SWITCH records, no published LOST record and kernel count 26,471.
The recorder returned failure and the independent consumer rejected it.
This proves counter visibility independently of pairing checks; it does not
claim that every earlier validator would accept these particular odd prefixes.

Three additional native read-fault cases verified recovery after three EINTRs,
failure after eight EINTRs, and rejection of an eight-byte short read. Both
failure cases retained `kernel_lost_count=null`, released the handle and were
rejected by the consumer. See the
[read-fault receipt](../validation/coordination/perf-counter-integration-20260913-01/read-fault-receipt.json).

Complete configured-event capture requires zero kernel loss **and** successful
collector/lifecycle/geometry/identity/raw-structure validation. Consumers that
depend on this must pass `--require-kernel-counter`. Counterless historical
captures remain inspection-only. The previous sentinel implementation, raw
results and source snapshots are preserved as superseded diagnostic work.

The [integration review](coordination/omp-perf-counter-integration-review-20260913.md)
is conditional on the tested kernel and event configuration. Kernel changes
require revalidation. Whole-run overhead and actual rate-window integration
remain pending. None of this is flight, architecture, MIXED, G6 or Full acceptance.

The tested header's G9 sentinel comment and consumer's introductory docstring
are historical wording; the contract above and executed counter checks define
the current behavior. Tested source bytes remain frozen for reproducibility.
The integration review's claim that the earlier mechanism would completely
miss its particular overflow prefix is too broad: that prefix is unpaired,
so earlier full validation could also reject it. The counter independently
detects unpublished loss; it does not establish an earlier validator false PASS.
