# Independent perf stream recorder: native baseline

The main coordinator completed a bounded Linux native baseline for the
self-thread recorder. This is an independent diagnostic module, with no model,
controller, firmware or UE dependency. It is not a MIXED flight or new
architecture acceptance result.

The final recorder SHA256 is
`c0fa0530cd4d8e207c69451b379fa988510391016326aa98433e599c4d178af3`.
The [native receipt](../validation/coordination/perf-stream-native-acceptance-20260913-05/receipt.json)
retains compiler argv, exact source snapshots, binary hashes, results and
same-boot process-group cleanup. All builds used `-Wall -Wextra -Werror`.

The actual compiled checks covered:

- A failed pthread_create: explicit SCHED_OTHER attributes, original EAGAIN,
  null handle and unchanged self FD/thread counts.
- Failed join, including ESRCH: no fabricated joined state, and a failed start
  returns retained ownership to its caller.
- Four collector cases: verbatim unframed bytes, wrapping with monotonic tail,
  ring pressure before copying, and bounded storage exhaustion.
- Bad policy readback: rejection before enable, with no FD/thread leak.
- Injected munmap failure: resources really released by the test wrapper, API
  reports failure, metadata records the failed cleanup, handle is cleared and
  the independent consumer rejects the evidence.

The [normal demo](../validation/coordination/perf-stream-native-acceptance-20260913-05/demo-receipt.json)
ran four 150ms sleeps in one owned process. The reader's actual policy was
SCHED_OTHER. It retained 256 raw bytes: eight records and four complete pairs.
The independent Python consumer decoded these bytes successfully. Both demo
and consumer exited; their process groups were empty on the same boot.
Raw SHA256: `a7ea953c6ac3abba154046bb5ca713bdf61aed0ac637f01146e334143e27d1f2`.

Integration fixes include explicit reader scheduling, synchronized readiness,
checked join outcomes, caller-visible retained handles, bounded error text,
and capture-resource cleanup before metadata serializes its outcome. The C
API now takes `wksim_perf_stop(void **handle, ...)`: null after return means
consumed; non-null means ownership remains with the caller. Stop's return code
must be zero before either output can be sealed as successful; metadata cannot
certify its own final output-file close.

Compiler failures are preserved separately. Native acceptance directory 02
captured an in-progress edit and is not a delivered-source failure claim.
Directory 03 records the remaining bounded-string diagnostic; 04 passed with
the prior stop signature; 05 is the final explicit-handle interface above.

`stream_completeness_proven` and `losslessness_proven` remain false. A final
pending kernel loss can be invisible until another event is emitted. The stop
sentinel, stress coverage and whole-run overhead measurement remain required
before flight wiring. The original pacing and physical acceptance gates have
not changed. The frozen historical checkout is not promoted to new-architecture
acceptance by any result in this document.
