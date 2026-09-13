/*
 * wksim_perf_stream.h -- diagnostic self-thread context-switch stream recorder.
 *
 * Implements `docs/coordination/perf-stream-contract-20260913.md`. This is a new module;
 * the older capability probe (`ds-perf-self-capability-20260913-01`) is untouched.
 *
 * Scope: one calling thread, one software DUMMY event, one bounded ring, one owned
 * reader thread. No runner wiring, no pacing, no scheduling of other threads, no
 * sysctl/affinity/resource-limit change. The collector loop does no allocation,
 * parsing, file I/O or hashing.
 *
 *   int wksim_perf_start(void **handle);
 *   int wksim_perf_stop(void *handle, const char *raw_path, const char *meta_path);
 *
 * start  must run on the thread whose switches are recorded; stop must run on that same
 * thread. start returns 0 on success or -1 with wksim_perf_last_error()/errno set, and
 * leaves no reader, event or mapping behind on failure. stop writes the raw stream and
 * the metadata with exclusive creation (never overwriting existing evidence), joins the
 * reader before releasing storage, cleans every owned resource on every path, and keeps
 * the primary failure when a cleanup step also fails.
 *
 * Ownership refusal: if stop cannot join the collector thread it returns -1 *without*
 * freeing, unmapping or closing anything, because the thread may still be using the ring
 * mapping, the storage area, the event fd and the handle. The caller keeps ownership and
 * the failure is reported as `join_failed` in metadata when the write path is reached.
 * On a start failure, where the handle cannot be handed back, a failed join likewise
 * retains every resource and leaks the handle deliberately (recorded as WKSIM_ERR_JOIN)
 * rather than freeing memory the collector may still touch.
 *
 * Build:
 *   cc -std=c11 -O2 -Wall -Wextra -Werror -pthread -o app app.c wksim_perf_stream.c
 *   (-lrt is not needed on glibc >= 2.17)
 *
 * ---- Contract items that are NOT implementable as written, or are missing -----------
 * These are reported rather than silently changed; each is answered below with the
 * minimal choice this implementation makes, so main can accept or amend it.
 *
 * G1. "Capture owner PID/TID and current boot before enable" has no output field for the
 *     TID/boot ordering. Owner tid is fixed at start and boot_id is read before enable;
 *     both are stored in the handle and written to metadata. No new API is needed.
 *
 * G2. The contract does not say what happens to an incomplete capture's bytes. This
 *     implementation still writes the raw prefix that was safely copied, and marks
 *     collector_complete=false with explicit collector_errors. Writing nothing would
 *     discard the only primary evidence; writing silently would fake success.
 *
 * G3. The contract fixes no ring size, only "128 data pages". This implementation uses
 *     128 * sysconf(_SC_PAGESIZE) bytes, and now *requires* meta.data_offset and
 *     meta.data_size to equal the mapped geometry exactly. There is no zero fallback: a
 *     zero or differing value fails start, because the collector reads only through this
 *     mapping. The observed values are written to metadata for diagnosis.
 *
 * G4. The contract asks for a "10ms" poll but does not define it as an API parameter.
 *     It is a compile-time constant (WKSIM_PERF_POLL_NS, default 10 ms) so the header
 *     signature stays exactly the two contract functions.
 *
 * G5. The contract requires "raw timestamps inside the capture's outer bounds" but the
 *     writer never checks that, because parsing is forbidden in the collector loop and
 *     stop is not an offline auditor. The bounds are emitted; offline acceptance owns
 *     the check. stop does walk the captured bytes to *account* for record types and to
 *     report whether the length is 8-byte aligned and whether trailing bytes are a whole
 *     record, but it never rewrites, truncates or pads a byte.
 *
 * G6. "Storage exhaustion or any collector error makes capture incomplete" leaves the
 *     ring buffer itself unspecified: the perf ring can wrap and lose records even when
 *     128 MiB of storage is free. Two separate bounded checks now exist: the 4096-byte
 *     ring-headroom guard and the storage-room check, each with its own counter. The
 *     contract's own "independent loss / sequence audit" is explicitly left to offline
 *     acceptance. A wrap is therefore detected as pressure, not proven impossible.
 *
 * G7. `reader_policy` is an int in metadata; this implementation writes the raw
 *     SCHED_OTHER value that pthread_getschedparam read back after an explicit-policy
 *     create, and fails start if the readback is not SCHED_OTHER.
 *
 * G8. The contract defines no error channel beyond the two return codes. This module adds
 *     wksim_perf_last_error() (thread-local read-only string) and structured
 *     collector_errors in metadata. Dropping the extra symbol leaves the two contract
 *     functions unchanged.
 *
 * G9. Losslessness is not provable from this side at all: a PERF_RECORD_LOST the kernel
 *     has not yet published is not flushed by PERF_EVENT_IOC_DISABLE, so
 *     collector_complete=true only means "the collector finished with no error of its
 *     own". Metadata therefore carries losslessness_proven=false plus an explicit
 *     reason; flight admission stays blocked until the stop sentinel is defined and
 *     verified.
 * -----------------------------------------------------------------------------------
 */
#ifndef WKSIM_PERF_STREAM_H
#define WKSIM_PERF_STREAM_H

#ifdef __cplusplus
extern "C" {
#endif

/* Start recording switches of the calling thread. On success *handle owns the event,
 * mapping, storage and reader thread; call wksim_perf_stop exactly once.
 * On ordinary failure *handle is NULL. If a failed cleanup cannot join the reader,
 * start returns -1 with a non-NULL retained handle; its owner must retain it and may
 * retry stop. A failed start is never accepted as a capture. */
int wksim_perf_start(void **handle);

/* Stop recording, join the reader, and write raw_path plus meta_path. Both files are
 * created exclusively (O_CREAT|O_EXCL); an existing file fails the call and nothing is
 * overwritten. Returns 0 only when the capture is complete and both files were written.
 *
 * Resource ownership: on every path that can join the reader, all owned resources are
 * released and the handle is consumed. The single exception is a failed pthread_join, in
 * which case the collector may still be running: the call returns -1 and retains the
 * storage, the ring mapping, the event fd and the handle for the caller. Do not free or
 * reuse the handle; its owner may retry stop to join and release it. Wrong-owner
 * or invalid-argument calls also retain ownership. Neither output is accepted
 * unless stop returns 0; the metadata cannot certify its own final close. */
int wksim_perf_stop(void *handle, const char *raw_path, const char *meta_path);

/* Human-readable last failure for the calling thread; never NULL. */
const char *wksim_perf_last_error(void);

#ifdef __cplusplus
}
#endif

#endif /* WKSIM_PERF_STREAM_H */
