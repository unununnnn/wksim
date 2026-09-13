# Diagnostic self-thread switch stream: candidate contract

Purpose: retain raw context-switch boundaries for a future MIXED diagnostic.
This is an implementation candidate, not an approved flight configuration.
No pacing, scheduling of existing threads, acceptance threshold or production
runner change is authorized by this contract.

## Ownership and lifecycle

- C API `int wksim_perf_start(void **handle)` opens software DUMMY for the
  calling thread only: pid=0, cpu=-1, group_fd=-1, CLOEXEC, inherit=0,
  context_switch=1, sample_id_all=1, TID|TIME|CPU, CLOCK_MONOTONIC,
  exclude_kernel=1, read_format=16 (PERF_FORMAT_LOST). Create a fresh event fd
  for each capture; RESET does not reset its loss counter. Do not use SET_OUTPUT.
  Capture owner PID/TID and current boot before enable.
- One owned native reader thread uses explicit SCHED_OTHER and verifies its
  actual policy. It must not inherit the manager's FIFO priority. Do not change
  the main thread, other threads, affinities, sysctls or resource limits.
- Allocate/touch a bounded 128 MiB storage area and map 128 data pages before
  enable. No allocation, parsing, file I/O or Python callback in the collector
  loop. Poll at a bounded 10ms interval; handle EINTR and atomic stop state.
- Use a normal forward writable perf ring, never overwrite/backward mode.
  Acquire published data_head, validate monotonic head/tail and capacity,
  copy wrapped bytes before publishing data_tail with appropriate ordering.
  Pressure within 4096 bytes of ring capacity invalidates capture; this is a
  conservative guard, not a proof that silent loss is impossible. Preserve
  raw records and require an independent loss/sequence audit as well.
- Storage exhaustion or any collector error makes capture incomplete. No
  silent truncation, growth, overwrite, skipped records or success fallback.
- `int wksim_perf_stop(void **handle, const char *raw_path, const char *meta_path)`
  must run on the original owner thread. Disable before final drain; join the
  reader before using its storage or unmapping. Clean all owned resources on
  every path. Do not throw away the primary failure when cleanup also fails.
  Caller passes &handle: clear it only after release; retain it on a failed join
  or rejected call so ownership is observable even when the function returns -1.
  Start can likewise return an error with a non-NULL retained handle if its
  cleanup cannot join. Neither output is accepted unless stop returns zero;
  metadata cannot certify its own final output-file close.
- Stop writes raw bytes and metadata only after capture ended, using exclusive
  file creation and checked writes. Never overwrite existing evidence. A start
  failure returns an error. If cleanup cannot join, retain the non-NULL handle
  and its resources as described above; never free storage still in use.

## Evidence format

`raw_path` holds the exact concatenation of published perf records, without
normalization or filtering. Target is little-endian x86_64. Metadata is JSON:

- `schema`: `wksim.perf_switch_stream.v1`; `classification`: `diagnostic_only`;
  `full_acceptance`: false.
- `owner_pid`, `owner_tid`, `boot_id`, `clock_id`: `CLOCK_MONOTONIC`.
- `enable_before_ns`, `enable_after_ns`, `disable_before_ns`,
  `disable_after_ns`: actual clock bounds of the corresponding ioctl calls.
- `ring_bytes`, `storage_capacity_bytes`, `captured_bytes`, `reader_policy`.
  `reader_policy` is the actual Linux integer policy and must be plain integer
  zero (SCHED_OTHER), not a policy name, bool or float. Captured bytes cannot
  exceed storage capacity. Metadata/windows JSON reject duplicate keys.
- `config`: `pid_argument=0`, `cpu_argument=-1`, `inherit=0`,
  `exclude_kernel=1`, `context_switch=1`, `sample_id_all=1`,
  `sample_type=[TID,TIME,CPU]`, `read_format=16`.
- `kernel_lost_read_ok`, `kernel_lost_read_bytes`, `kernel_lost_read_errno`,
  `kernel_lost_count`: read the same event fd after successful DISABLE and before
  close. Require exactly 16 bytes (value, lost), with at most eight EINTR attempts.
  Failure/short read leaves count null; nonzero loss invalidates the capture.
- `collector_complete`: boolean; `collector_errors`: list of explicit failures
  including saved errno where applicable; `lifecycle` booleans `disable_ok`,
  `reader_joined`, `munmap_ok`, `close_ok`.

Do not compute hashes in the capture loop. The main launcher seals source,
metadata and raw file hashes after stop and binds the boot/owner to the run.
Synthetic fixtures must be labeled synthetic; no fabricated flight evidence.

## Independent offline acceptance

Validate metadata types/required fields, exact byte length, same owner and
clock, enable/disable ordering, complete lifecycle and zero collector errors.
Decode header8 + TID/TIME/CPU24 = exact32-byte SWITCH records; reject LOST,
LOST_SAMPLES, CPU_WIDE, unknown/truncated/malformed records, nonpositive or
foreign identities, nonincreasing timestamps, illegal preempt-on-in and any
unpaired sequence. Raw timestamps must lie inside the capture's outer bounds.
Require at least one complete pair. Preserve out/in timestamps and CPU values.

An optional separately pinned windows JSON lists `id`, `start_ns`, `end_ns`.
Compute intersections with observed switch-out/in spans using integer ns;
reject malformed or out-of-capture windows. This is a boundary observation,
not proof of which task ran, why scheduling occurred or exact CPU execution
time. Future joins to rate/parent diagnostics must bind original run identity
and monotonic clock explicitly. Do not fabricate absent historic switch data.

The main coordinator alone compiles and runs native verification after fresh
checks of both WSL distributions. No flight wiring until code, independent
tests, lifecycle failure paths and measured overhead have been reviewed.

## Configured-event completeness

A final kernel ring loss can remain pending without a LOST record until another
successful output. Disable does not itself flush that count. The pressure guard
and a well-paired decoded prefix therefore do not prove a loss-free capture.
The selected implementation instead reads PERF_FORMAT_LOST after DISABLE.
Its output-failure counter includes pending loss before a LOST record is
published. This was checked against actual kernel 6.6.87.2-microsoft-standard-WSL2
and source tag linux-msft-wsl-6.6.87.2. New fd, mmap before ENABLE, inherit=0,
and no output redirection are required. A kernel change requires revalidation.

The independent consumer requires all counter fields to have exact valid types,
read_format=16, successful read16/errno0 and uint64 count zero, in addition to
all collector, lifecycle, geometry, owner, raw and pairing checks above.
Only then is stream_completeness_proven=true, covering windows within
[enable_after_ns, disable_before_ns]. This is the configured event's capture,
not causal scheduling attribution or physical acceptance.

Every completeness-dependent invocation must use --require-kernel-counter.
Counterless historical input remains inspection-only with completeness false.
The earlier stop sentinel is superseded; no sleep/checkpoint is needed by the
selected implementation. See [kernel-counter verification](../2026-09-13-perf-kernel-loss-counter.md)
for native zero-loss, pending-loss, short-read and EINTR evidence plus review.
Whole-run overhead and actual rate-window integration remain required before
flight wiring is accepted.
