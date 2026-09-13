# Diagnostic self-thread switch stream: candidate contract

Purpose: retain raw context-switch boundaries for a future MIXED diagnostic.
This is an implementation candidate, not an approved flight configuration.
No pacing, scheduling of existing threads, acceptance threshold or production
runner change is authorized by this contract.

## Ownership and lifecycle

- C API `int wksim_perf_start(void **handle)` opens software DUMMY for the
  calling thread only: pid=0, cpu=-1, group_fd=-1, CLOEXEC, inherit=0,
  context_switch=1, sample_id_all=1, TID|TIME|CPU, CLOCK_MONOTONIC,
  exclude_kernel=1. Capture owner PID/TID and current boot before enable.
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
- `int wksim_perf_stop(void *handle, const char *raw_path, const char *meta_path)`
  must run on the original owner thread. Disable before final drain; join the
  reader before using its storage or unmapping. Clean all owned resources on
  every path. Do not throw away the primary failure when cleanup also fails.
- Stop writes raw bytes and metadata only after capture ended, using exclusive
  file creation and checked writes. Never overwrite existing evidence. A start
  failure must leave no active reader/event/mapping and return an error.

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
  `sample_type=[TID,TIME,CPU]`.
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

## Completeness blocker

A final kernel ring loss can remain pending without a LOST record until another
successful output. Disable does not itself flush that count. The pressure guard
and a well-paired decoded prefix therefore do not prove a loss-free capture.
Current decoder output must state `stream_completeness_proven=false`.

A proposed stop check, still requiring review and native falsification tests,
drains first, obtains free ring space, then brackets an owner-thread nanosleep
while the event remains enabled. The decoder would require an actual out/in
pair in those clock bounds, not assume that sched_yield or sleep guarantees it.
Only observation windows ending before this final check could be certified.
Any missing check, LOST record or inconsistent drain/lifecycle would reject
the evidence. Until this is implemented and verified, flight wiring is blocked.
