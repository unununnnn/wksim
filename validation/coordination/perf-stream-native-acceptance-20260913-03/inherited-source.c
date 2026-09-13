/*
 * wksim_perf_stream.c -- see wksim_perf_stream.h for the contract and the items the
 * written contract cannot express (G1..G9).
 *
 * Layout of this file:
 *   1. constants and the internal state (caller owns the memory, so no allocation on
 *      any failure path after the handle is handed out)
 *   2. error bookkeeping: mutually excluded between the two threads; the first failure
 *      wins, owner-thread failures are promoted in front after the join, and no cleanup
 *      failure can replace the primary one
 *   3. the reader thread: explicit SCHED_OTHER through a real pthread_attr_t, verified by
 *      readback, then a ready handshake the owner waits for before enabling
 *   4. the collector loop: bounded poll, verbatim byte-range copy, acquire/release ring
 *      ordering, two independent pressure checks, no allocation, no header parsing, no
 *      file I/O, no hashing
 *   5. start/stop lifecycle: every failure path joins before releasing; a failed join
 *      retains ownership instead of freeing memory the collector may still be using
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include "wksim_perf_stream.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/perf_event.h>
#include <pthread.h>
#include <sched.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

/* ---- 1. constants and state --------------------------------------------- */

#define WKSIM_PERF_SCHEMA "wksim.perf_switch_stream.v1"
#define WKSIM_PERF_STORAGE_BYTES (128u * 1024u * 1024u)   /* contract: 128 MiB */
#define WKSIM_PERF_RING_PAGES 128u
#define WKSIM_PERF_PRESSURE_GUARD 4096u                   /* contract guard */
#define WKSIM_PERF_RECORD_BYTES 32u                       /* reference only: header8+id24;
                                                           * the collector never assumes it */
#define WKSIM_PERF_ERR_SLOTS 12
#define WKSIM_PERF_ERR_TEXT 128

#ifndef WKSIM_PERF_POLL_NS
#define WKSIM_PERF_POLL_NS 10000000L                      /* contract: 10 ms */
#endif

#define MISC_SWITCH_OUT (1u << 13)

/* Explicit collector failure codes. The first one recorded is the primary failure. */
enum {
    WKSIM_ERR_NONE = 0,
    WKSIM_ERR_BAD_ARGUMENT,
    WKSIM_ERR_ALREADY_STARTED,
    WKSIM_ERR_THREAD_CREATE,
    WKSIM_ERR_THREAD_POLICY,
    WKSIM_ERR_STORAGE_MAP,
    WKSIM_ERR_PERF_OPEN,
    WKSIM_ERR_RING_MAP,
    WKSIM_ERR_META_GEOMETRY,
    WKSIM_ERR_BOOT_ID,
    WKSIM_ERR_CLOCK,
    WKSIM_ERR_ENABLE,
    WKSIM_ERR_CAPTURE_INCOMPLETE,
    WKSIM_ERR_PRESSURE,
    WKSIM_ERR_MALFORMED_STREAM,
    WKSIM_ERR_DISABLE,
    WKSIM_ERR_NO_PAIR,
    WKSIM_ERR_OUTPUT_EXISTS,
    WKSIM_ERR_OUTPUT_WRITE,
    WKSIM_ERR_OUTPUT_PARTIAL,
    WKSIM_ERR_JOIN,
    WKSIM_ERR_MUNMAP,
    WKSIM_ERR_CLOSE,
    WKSIM_ERR_COUNT
};

static const char *const wksim_err_name[WKSIM_ERR_COUNT] = {
    "none", "bad_argument", "already_started", "thread_create", "thread_policy",
    "storage_map", "perf_open", "ring_map", "meta_geometry", "boot_id", "clock",
    "enable", "capture_incomplete", "pressure_guard", "malformed_stream", "disable",
    "no_switch_pair", "output_exists", "output_write", "output_partial", "join",
    "munmap", "close"
};

struct wksim_perf_error {
    int code;
    int saved_errno;
    bool from_owner;                 /* owner-thread failures stay primary after reorder */
    char text[WKSIM_PERF_ERR_TEXT];
};

struct wksim_perf_stream {
    pthread_t reader;
    bool reader_running;
    bool reader_joined;

    /* Each synchronisation object is destroyed only when its init succeeded. */
    bool error_lock_ok;
    bool ready_lock_ok;
    bool ready_cond_ok;

    /* Handshake: the owner must not enable before the reader has verified its own
     * scheduling policy and entered the poll loop. Both fields live in the handle (never on
     * a frame that can go out of scope) and are read and written under `ready_lock`. */
    pthread_mutex_t ready_lock;
    pthread_cond_t ready_cond;
    bool reader_ready;
    bool reader_policy_ok;

    int fd;                          /* perf event */
    struct perf_event_mmap_page *meta;
    unsigned char *ring;             /* data area of the mapping */
    uint64_t ring_bytes;
    size_t map_size;

    unsigned char *storage;          /* bounded 128 MiB capture area */
    uint64_t storage_capacity;
    uint64_t captured_bytes;
    uint64_t records_captured;

    /* Kernel-reported ring geometry, kept for the output even when start fails. */
    uint64_t meta_data_offset;
    uint64_t meta_data_size;

    /* Record shape accounting over the captured bytes. The capture is a verbatim copy of
     * every published perf record, so it is NOT required to be a multiple of 32: LOST and
     * unknown records have other sizes. */
    bool raw_len_record_aligned;     /* captured_bytes % 8 == 0 */
    uint32_t max_record_bytes_seen;
    uint64_t unparsed_bytes;         /* trailing bytes that are not a whole record */
    uint64_t switch_records;
    uint64_t switch_cpu_wide_records;
    uint64_t lost_records;
    uint64_t lost_samples_records;
    uint64_t unknown_records;
    uint64_t ring_pressure_events;   /* times the ring headroom guard fired */
    uint64_t storage_pressure_events;
    bool join_failed;                /* reader may still be alive; ownership is retained */

    _Atomic bool stop_requested;
    _Atomic bool drain_done;

    int64_t owner_pid;
    int64_t owner_tid;
    int clock_id;
    char boot_id[64];

    uint64_t start_ns;
    uint64_t enable_before_ns;
    uint64_t enable_after_ns;
    uint64_t disable_before_ns;
    uint64_t disable_after_ns;
    bool enable_attempted;
    bool enable_ok;

    int reader_policy;               /* read back from pthread_getschedparam */
    int reader_priority;

    bool captured_meta_exact;        /* data_offset/data_size cross-check */
    uint64_t switch_out;
    uint64_t switch_in;
    uint64_t pairs;

    /* The owner thread and the reader thread both record failures, so the array and its
     * count are guarded: without this the two threads race on error_count and the slots. */
    pthread_mutex_t error_lock;
    struct wksim_perf_error errors[WKSIM_PERF_ERR_SLOTS];
    int error_count;
};

static _Thread_local char wksim_last_error[WKSIM_PERF_ERR_TEXT];

static void set_last_error(const char *text)
{
    snprintf(wksim_last_error, sizeof wksim_last_error, "%s", text);
}

const char *wksim_perf_last_error(void)
{
    return wksim_last_error[0] ? wksim_last_error : "no error";
}

/* ---- 2. error bookkeeping ----------------------------------------------- */

static bool on_owner_thread(const struct wksim_perf_stream *stream)
{
    return stream->owner_tid == (int64_t)syscall(SYS_gettid);
}

/* Record a failure; only the first code and first non-zero errno survive, so a later
 * cleanup failure can never replace the primary one. `where` names the call site.
 *
 * Called from both threads, so the array and the count are guarded. The guard is held only
 * on failure paths -- the collector loop never records an error on the normal path, so the
 * mutex is off the hot path. */
static void record_error(struct wksim_perf_stream *stream, int code, int saved_errno,
                         const char *where)
{
    if (stream == NULL) {
        return;
    }
    bool from_owner = on_owner_thread(stream);
    /* strerror() returns an unbounded string; cap it before it is used in a
     * fixed-size message so -Wformat-truncation sees an explicit upper bound. */
    char errtext[64];
    if (saved_errno != 0) {
        snprintf(errtext, sizeof errtext, "%.*s", (int)sizeof errtext - 1,
                 strerror(saved_errno));
    } else {
        errtext[0] = '\0';
    }
    pthread_mutex_lock(&stream->error_lock);
    if (stream->error_count < WKSIM_PERF_ERR_SLOTS) {
        struct wksim_perf_error *slot = &stream->errors[stream->error_count];
        slot->code = code;
        slot->saved_errno = saved_errno;
        slot->from_owner = from_owner;
        snprintf(slot->text, sizeof slot->text, "%s", where ? where : "");
        stream->error_count++;
    }
    int count = stream->error_count;
    pthread_mutex_unlock(&stream->error_lock);

    if (count == 1) {
        char message[WKSIM_PERF_ERR_TEXT];
        char reason[WKSIM_PERF_ERR_TEXT];
        if (saved_errno != 0) {
            /* name <= 24, errtext <= 63, fixed wrapper 14: provably < 128 */
            snprintf(reason, sizeof reason, "%s (errno %d: %.*s)",
                     wksim_err_name[code], saved_errno,
                     (int)sizeof errtext - 1, errtext);
        } else {
            snprintf(reason, sizeof reason, "%s", wksim_err_name[code]);
        }
        /* Both halves are precision-capped, so the total can never reach 128. */
        snprintf(message, sizeof message, "%.*s: %.*s",
                 WKSIM_PERF_ERR_TEXT / 2 - 2, where ? where : "failure",
                 WKSIM_PERF_ERR_TEXT / 2 - 2, reason);
        set_last_error(message);
    }
}

/* After the reader has been joined, move owner-thread failures in front: a lifecycle
 * failure such as a failed ENABLE must be the primary error even when the reader recorded
 * a failure first. Order inside each group is preserved. */
static void promote_owner_errors(struct wksim_perf_stream *stream)
{
    struct wksim_perf_error ordered[WKSIM_PERF_ERR_SLOTS];
    int used = 0;
    for (int pass = 0; pass < 2; pass++) {
        for (int index = 0; index < stream->error_count && index < WKSIM_PERF_ERR_SLOTS;
                index++) {
            bool want_owner = (pass == 0);
            if (stream->errors[index].from_owner == want_owner) {
                ordered[used++] = stream->errors[index];
            }
        }
    }
    for (int index = 0; index < used; index++) {
        stream->errors[index] = ordered[index];
    }
    stream->error_count = used;
}

/* Run the reorder on the joined handle and refresh the thread-local message. */
static void settle_errors(struct wksim_perf_stream *stream)
{
    pthread_mutex_lock(&stream->error_lock);
    promote_owner_errors(stream);
    if (stream->error_count > 0) {
        struct wksim_perf_error *primary = &stream->errors[0];
        /* 128 (capped text) + wrapper + capped errno text: provably bounded. */
        char message[WKSIM_PERF_ERR_TEXT + 80];
        if (primary->saved_errno != 0) {
            char errtext[64];
            snprintf(errtext, sizeof errtext, "%.*s", (int)sizeof errtext - 1,
                     strerror(primary->saved_errno));
            snprintf(message, sizeof message, "%.*s (errno %d: %.*s)",
                     WKSIM_PERF_ERR_TEXT, primary->text, primary->saved_errno,
                     (int)sizeof errtext - 1, errtext);
        } else {
            snprintf(message, sizeof message, "%.*s", WKSIM_PERF_ERR_TEXT,
                     primary->text);
        }
        set_last_error(message);
    }
    pthread_mutex_unlock(&stream->error_lock);
}

static int first_errno(struct wksim_perf_stream *stream)
{
    pthread_mutex_lock(&stream->error_lock);
    int saved = stream->error_count > 0 ? stream->errors[0].saved_errno : 0;
    pthread_mutex_unlock(&stream->error_lock);
    return saved;
}

/* Read-only snapshot used by stop, after the reader is joined and no writer remains. */
static int error_count_now(const struct wksim_perf_stream *stream)
{
    return stream->error_count;
}

/* Formatted variant: the only difference is that the call site text can carry the sizes
 * and offsets that make a shape error reproducible. */
__attribute__((format(printf, 4, 5)))
static void record_errorf(struct wksim_perf_stream *stream, int code, int saved_errno,
                          const char *format, ...)
{
    char text[WKSIM_PERF_ERR_TEXT];
    va_list ap;
    va_start(ap, format);
    vsnprintf(text, sizeof text, format, ap);
    va_end(ap);
    record_error(stream, code, saved_errno, text);
}

/* ---- time and small helpers --------------------------------------------- */

static bool monotonic_ns(int clock_id, uint64_t *out)
{
    struct timespec now;
    if (clock_gettime(clock_id, &now) != 0) {
        return false;
    }
    if (now.tv_sec < 0 || now.tv_nsec < 0) {
        return false;
    }
    *out = (uint64_t)now.tv_sec * 1000000000ull + (uint64_t)now.tv_nsec;
    return true;
}

static bool is_positive_power_of_two(uint64_t value)
{
    return value != 0 && (value & (value - 1)) == 0;
}

static bool read_boot_id(char *out, size_t out_size)
{
    int fd = open("/proc/sys/kernel/random/boot_id", O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        return false;
    }
    ssize_t got = read(fd, out, out_size - 1);
    int close_errno = 0;
    if (close(fd) != 0) {
        close_errno = errno;
    }
    if (got <= 0) {
        errno = close_errno;
        return false;
    }
    out[got] = '\0';
    for (ssize_t index = 0; index < got; index++) {
        if (out[index] == '\n' || out[index] == '\r') {
            out[index] = '\0';
            break;
        }
    }
    if (out[0] == '\0') {
        errno = close_errno;
        return false;
    }
    return true;
}

/* Copy `length` bytes out of the forward writable ring honouring wrap. */
static void ring_copy(unsigned char *dst, const unsigned char *data, uint64_t size,
                      uint64_t pos, uint64_t length)
{
    uint64_t first = size - pos;
    if (first > length) {
        first = length;
    }
    memcpy(dst, data + pos, (size_t)first);
    if (length > first) {
        memcpy(dst + first, data, (size_t)(length - first));
    }
}

/* Drain everything the kernel has published and advance data_tail.
 *
 * The collector copies the published byte range [data_tail, data_head) verbatim. It does
 * not read, interpret or realign a single perf_event_header: record framing, LOST and
 * unknown types are the offline reader's business, and parsing here would be exactly the
 * "assume a fixed 32-byte stride" mistake that silently dropped non-switch records. The
 * raw file therefore holds the kernel's bytes unchanged, in order, with no padding.
 *
 * Two independent bounded-resource checks, each with its own failure code:
 *   - ring headroom: pending must stay 4096 bytes clear of the ring capacity
 *   - storage room: the chunk must fit in the fixed 128 MiB area
 * Neither one truncates: on pressure the capture is invalidated and the loop stops. */
static void collect_available(struct wksim_perf_stream *stream, uint64_t ring_bytes,
                              uint64_t mask)
{
    while (true) {
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        uint64_t head = __atomic_load_n(&stream->meta->data_head, __ATOMIC_ACQUIRE);
        /* data_tail is only written by this thread; a relaxed load keeps the access atomic
         * with respect to the kernel's page updates. */
        uint64_t tail = __atomic_load_n(&stream->meta->data_tail, __ATOMIC_RELAXED);
        uint64_t pending = head - tail;
        if (pending > ring_bytes) {
            record_errorf(stream, WKSIM_ERR_MALFORMED_STREAM, 0,
                          "reader: head/tail beyond ring capacity (head=%" PRIu64
                          " tail=%" PRIu64 " ring=%" PRIu64 ")",
                          head, tail, ring_bytes);
            return;
        }
        if (pending == 0) {
            return;
        }
        if (pending + WKSIM_PERF_PRESSURE_GUARD > ring_bytes) {
            /* The producer is too close to wrapping past us for the bytes in flight to be
             * recoverable; the contract guard invalidates the capture. */
            stream->ring_pressure_events++;
            record_errorf(stream, WKSIM_ERR_PRESSURE, 0,
                          "reader: ring headroom guard fired (pending=%" PRIu64
                          " ring=%" PRIu64 " guard=%u)",
                          pending, ring_bytes, (unsigned)WKSIM_PERF_PRESSURE_GUARD);
            return;
        }

        uint64_t pos = tail & mask;
        uint64_t contiguous = ring_bytes - pos;
        uint64_t chunk = contiguous < pending ? contiguous : pending;
        uint64_t room = stream->storage_capacity - stream->captured_bytes;
        if (chunk > room) {
            chunk = room;                       /* bounded area: never grow, never wrap */
        }
        if (chunk == 0) {
            stream->storage_pressure_events++;
            record_errorf(stream, WKSIM_ERR_PRESSURE, 0,
                          "reader: storage exhausted (captured=%" PRIu64
                          " of %" PRIu64 " bytes)",
                          stream->captured_bytes, stream->storage_capacity);
            return;
        }

        ring_copy(stream->storage + stream->captured_bytes, stream->ring, ring_bytes, pos,
                  chunk);
        stream->captured_bytes += chunk;
        tail += chunk;

        /* Publish the consumed prefix only after the bytes are in storage. */
        __atomic_thread_fence(__ATOMIC_RELEASE);
        __atomic_store_n(&stream->meta->data_tail, tail, __ATOMIC_RELEASE);
        /* Loop again to pick up bytes the kernel published while we copied. The loop is
         * bounded by the ring guard: once the producer is within the guard distance the
         * capture is invalidated instead of silently losing the in-flight bytes. */
    }
}

/* ---- 3. the reader thread ----------------------------------------------- */

/* The collector never allocates, parses headers, opens a file or hashes anything: it
 * copies published bytes into the bounded storage area and advances data_tail. */
static void *wksim_perf_reader(void *argument)
{
    struct wksim_perf_stream *stream = argument;
    if (stream == NULL) {
        return NULL;
    }

    /* Explicit scheduling: this thread must not inherit the manager's FIFO priority.
     * start() requests these attributes through pthread_attr_setinheritsched /
     * pthread_attr_setschedpolicy, and this readback proves what the kernel granted.
     * pthread calls return their error code, not errno. */
    struct sched_param param;
    memset(&param, 0, sizeof param);
    param.sched_priority = 0;                       /* SCHED_OTHER requires priority 0 */
    int set_rc = pthread_setschedparam(pthread_self(), SCHED_OTHER, &param);
    int policy = -1;
    int priority = -1;
    int get_rc = pthread_getschedparam(pthread_self(), &policy, &param);
    if (get_rc == 0) {
        priority = param.sched_priority;
    }
    stream->reader_policy = policy;
    stream->reader_priority = priority;
    bool verified = (set_rc == 0 && get_rc == 0 && policy == SCHED_OTHER && priority == 0);
    if (!verified) {
        record_errorf(stream, WKSIM_ERR_THREAD_POLICY, set_rc != 0 ? set_rc : get_rc,
                      "reader: not SCHED_OTHER (set=%d get=%d policy=%d priority=%d)",
                      set_rc, get_rc, policy, priority);
    }

    /* Ready handshake: the owner waits for this before enabling. The decision and the
     * result are published under the lock so the owner never samples a half-written flag
     * and never reads a frame that has gone out of scope. */
    pthread_mutex_lock(&stream->ready_lock);
    stream->reader_policy_ok = verified;
    stream->reader_ready = true;
    pthread_cond_broadcast(&stream->ready_cond);
    pthread_mutex_unlock(&stream->ready_lock);

    if (!verified) {
        return NULL;                                /* start reports this failure */
    }

    const uint64_t ring_bytes = stream->ring_bytes;
    const uint64_t mask = ring_bytes - 1;
    while (!atomic_load_explicit(&stream->stop_requested, memory_order_acquire)) {
        collect_available(stream, ring_bytes, mask);
        struct timespec request = { 0, WKSIM_PERF_POLL_NS };
        while (nanosleep(&request, &request) != 0) {
            if (errno != EINTR) {
                int saved = errno;
                record_error(stream, WKSIM_ERR_CLOCK, saved, "reader: nanosleep");
                break;
            }
            if (atomic_load_explicit(&stream->stop_requested, memory_order_acquire)) {
                break;
            }
        }
    }

    /* Final drain after disable. The owner sets stop_requested only after DISABLE
     * returned, so the producer is stopped here and one more drain takes everything the
     * kernel published. What it cannot take is a record the kernel has not published yet:
     * a pending PERF_RECORD_LOST is not flushable by DISABLE. `drain_done` therefore
     * means "this thread finished its last pass", not "nothing can be missing". */
    collect_available(stream, ring_bytes, mask);
    atomic_store_explicit(&stream->drain_done, true, memory_order_release);
    return NULL;
}

/* ---- start -------------------------------------------------------------- */

static void release_handle(struct wksim_perf_stream *stream)
{
    if (stream == NULL) {
        return;
    }
    if (stream->meta != NULL) {
        munmap(stream->meta, stream->map_size);
        stream->meta = NULL;
        stream->ring = NULL;
    }
    if (stream->fd >= 0) {
        close(stream->fd);
        stream->fd = -1;
    }
    if (stream->storage != NULL) {
        munmap(stream->storage, (size_t)stream->storage_capacity);
        stream->storage = NULL;
    }
}

/* Join the collector with its real return code (pthread calls report through the return
 * value, never through errno). Returns the code, or 0 on success.
 *
 * A failed join is NOT retrofitted into success: if the thread could not be joined it may
 * still be running, so ownership of the storage, the mapping, the event fd and the handle
 * itself stays with the collector and must not be unmapped, closed or freed. */
static int join_reader(struct wksim_perf_stream *stream, bool mark_joined)
{
    if (!stream->reader_running) {
        return 0;
    }
    int rc = pthread_join(stream->reader, NULL);
    /* Every nonzero join result -- including ESRCH -- retains ownership: the caller
     * cannot prove the collector is gone, so nothing is freed and reader_joined is
     * never set. */
    if (rc != 0) {
        stream->join_failed = true;
        return rc;
    }
    stream->reader_running = false;
    if (mark_joined) {
        stream->reader_joined = true;
    }
    return 0;
}

/* Destroy only the synchronisation objects whose init succeeded. Never called while
 * the collector may still run (retained path keeps them). */
static void destroy_locks(struct wksim_perf_stream *stream)
{
    if (stream->ready_cond_ok) {
        pthread_cond_destroy(&stream->ready_cond);
        stream->ready_cond_ok = false;
    }
    if (stream->ready_lock_ok) {
        pthread_mutex_destroy(&stream->ready_lock);
        stream->ready_lock_ok = false;
    }
    if (stream->error_lock_ok) {
        pthread_mutex_destroy(&stream->error_lock);
        stream->error_lock_ok = false;
    }
}

/* Shared start-failure tail: stop the reader, join it, and only then release. A failed
 * join retains every resource AND hands the stream back through *handle (start still
 * returns -1), so the caller can retry wksim_perf_stop once the reader has exited;
 * nothing is hidden. */
static int start_abort(struct wksim_perf_stream *stream, int saved, void **handle)
{
    atomic_store_explicit(&stream->stop_requested, true, memory_order_release);
    int join_rc = join_reader(stream, true);
    if (join_rc != 0) {
        record_error(stream, WKSIM_ERR_JOIN, join_rc,
                     "start: reader join failed, handle retained for caller");
        settle_errors(stream);
        *handle = stream;
        errno = saved;
        return -1;
    }
    settle_errors(stream);
    destroy_locks(stream);
    release_handle(stream);
    free(stream);
    errno = saved;
    return -1;
}

int wksim_perf_start(void **handle)
{
    if (handle == NULL) {
        errno = EINVAL;
        set_last_error("start: handle is NULL");
        return -1;
    }
    *handle = NULL;

    struct wksim_perf_stream *stream = calloc(1, sizeof *stream);
    if (stream == NULL) {
        int saved = errno;
        set_last_error("start: cannot allocate the handle");
        errno = saved;
        return -1;
    }
    /* Synchronisation objects exist before anything can record an error or start a
     * thread. Each successful init is tracked; every release path destroys exactly the
     * objects that were initialised, including partial-init failure. */
    int init_rc = pthread_mutex_init(&stream->error_lock, NULL);
    stream->error_lock_ok = (init_rc == 0);
    if (stream->error_lock_ok) {
        init_rc = pthread_mutex_init(&stream->ready_lock, NULL);
        stream->ready_lock_ok = (init_rc == 0);
    }
    if (stream->ready_lock_ok) {
        init_rc = pthread_cond_init(&stream->ready_cond, NULL);
        stream->ready_cond_ok = (init_rc == 0);
    }
    if (!stream->ready_cond_ok) {
        set_last_error("start: cannot initialise the internal locks");
        destroy_locks(stream);
        free(stream);
        errno = init_rc;
        return -1;
    }

    stream->fd = -1;
    stream->clock_id = CLOCK_MONOTONIC;
    stream->owner_pid = (int64_t)getpid();
    stream->owner_tid = (int64_t)syscall(SYS_gettid);
    stream->reader_policy = -1;
    pthread_attr_t thread_attr;
    memset(&thread_attr, 0, sizeof thread_attr);
    if (stream->owner_tid <= 0) {
        int saved = errno;
        record_error(stream, WKSIM_ERR_BAD_ARGUMENT, saved, "start: gettid");
        destroy_locks(stream);
        release_handle(stream);
        free(stream);
        errno = saved;
        return -1;
    }

    /* Bounded storage, allocated and touched before enable; never grown later. */
    stream->storage_capacity = WKSIM_PERF_STORAGE_BYTES;
    stream->storage = mmap(NULL, (size_t)stream->storage_capacity,
                           PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (stream->storage == MAP_FAILED) {
        int saved = errno;
        stream->storage = NULL;
        destroy_locks(stream);
        release_handle(stream);
        free(stream);
        errno = saved;
        return -1;
    }
    {
        long page = sysconf(_SC_PAGESIZE);
        if (page <= 0 || !is_positive_power_of_two((uint64_t)page)) {
            int saved = errno;
            record_error(stream, WKSIM_ERR_BAD_ARGUMENT, saved,
                         "start: sysconf(_SC_PAGESIZE)");
            release_handle(stream);
            free(stream);
            errno = saved;
            return -1;
        }
        for (uint64_t offset = 0; offset < stream->storage_capacity;
                offset += (uint64_t)page) {
            stream->storage[offset] = 0;            /* pre-fault every page */
        }
        stream->ring_bytes = (uint64_t)page * WKSIM_PERF_RING_PAGES;
    }

    /* Owner identity and boot before enable. */
    if (!read_boot_id(stream->boot_id, sizeof stream->boot_id)) {
        int saved = errno;
        record_error(stream, WKSIM_ERR_BOOT_ID, saved, "start: read boot_id");
        release_handle(stream);
        free(stream);
        errno = saved;
        return -1;
    }
    if (!monotonic_ns(stream->clock_id, &stream->start_ns)) {
        int saved = errno;
        record_error(stream, WKSIM_ERR_CLOCK, saved, "start: clock before enable");
        release_handle(stream);
        free(stream);
        errno = saved;
        return -1;
    }

    struct perf_event_attr attr;
    memset(&attr, 0, sizeof attr);
    attr.type = PERF_TYPE_SOFTWARE;
    attr.size = sizeof attr;
    attr.config = PERF_COUNT_SW_DUMMY;
    attr.sample_period = 1;
    attr.sample_type = PERF_SAMPLE_TID | PERF_SAMPLE_TIME | PERF_SAMPLE_CPU;
    attr.disabled = 1;
    attr.inherit = 0;
    attr.sample_id_all = 1;
    attr.context_switch = 1;
    attr.wakeup_events = 1;
    attr.use_clockid = 1;
    attr.clockid = CLOCK_MONOTONIC;
    attr.exclude_kernel = 1;
    attr.exclude_hv = 0;

    stream->fd = (int)syscall(SYS_perf_event_open, &attr, 0, -1, -1,
                              PERF_FLAG_FD_CLOEXEC);
    if (stream->fd < 0) {
        int saved = errno;
        record_error(stream, WKSIM_ERR_PERF_OPEN, saved, "start: perf_event_open");
        release_handle(stream);
        free(stream);
        errno = saved;
        return -1;
    }

    size_t page = (size_t)sysconf(_SC_PAGESIZE);
    stream->map_size = page + (size_t)stream->ring_bytes;
    void *mapping = mmap(NULL, stream->map_size, PROT_READ | PROT_WRITE, MAP_SHARED,
                         stream->fd, 0);
    if (mapping == MAP_FAILED) {
        int saved = errno;
        record_error(stream, WKSIM_ERR_RING_MAP, saved, "start: ring mmap");
        release_handle(stream);
        free(stream);
        errno = saved;
        return -1;
    }
    stream->meta = (struct perf_event_mmap_page *)mapping;
    stream->ring = (unsigned char *)mapping + page;

    /* Kernel geometry must equal the mapping exactly. There is no zero fallback: a zero
     * data_offset/data_size is a mismatch too, because the collector reads only through
     * the mapping this module created. The observed values are kept for the output so a
     * mismatch is diagnosable after the fact. */
    stream->meta_data_offset = stream->meta->data_offset;
    stream->meta_data_size = stream->meta->data_size;
    if (stream->meta_data_offset == (uint64_t)page
            && stream->meta_data_size == stream->ring_bytes
            && is_positive_power_of_two(stream->meta_data_size)) {
        stream->captured_meta_exact = true;
    } else {
        record_errorf(stream, WKSIM_ERR_META_GEOMETRY, 0,
                      "start: perf ring geometry data_offset=%" PRIu64
                      " data_size=%" PRIu64 " differs from the mapping page=%zu ring=%" PRIu64,
                      stream->meta_data_offset, stream->meta_data_size, page,
                      stream->ring_bytes);
        release_handle(stream);
        free(stream);
        errno = EINVAL;
        return -1;
    }

    /* Reader thread with explicit SCHED_OTHER. The attributes are set on a real
     * pthread_attr_t: pthread_create with NULL attributes would inherit the creating
     * thread's policy, so a manager running at FIFO priority would hand FIFO to the
     * collector and the module would only *claim* SCHED_OTHER. */
    int attr_rc = pthread_attr_init(&thread_attr);
    if (attr_rc == 0) {
        struct sched_param reader_sched;
        memset(&reader_sched, 0, sizeof reader_sched);
        reader_sched.sched_priority = 0;
        attr_rc = pthread_attr_setinheritsched(&thread_attr, PTHREAD_EXPLICIT_SCHED);
        if (attr_rc == 0) {
            attr_rc = pthread_attr_setschedpolicy(&thread_attr, SCHED_OTHER);
        }
        if (attr_rc == 0) {
            attr_rc = pthread_attr_setschedparam(&thread_attr, &reader_sched);
        }
    }
    if (attr_rc != 0) {
        record_error(stream, WKSIM_ERR_THREAD_POLICY, attr_rc,
                     "start: cannot request SCHED_OTHER attributes");
        release_handle(stream);
        free(stream);
        errno = attr_rc;
        return -1;
    }

    int create_rc = pthread_create(&stream->reader, &thread_attr,
                                   wksim_perf_reader, stream);
    pthread_attr_destroy(&thread_attr);
    if (create_rc != 0) {
        record_error(stream, WKSIM_ERR_THREAD_CREATE, create_rc, "start: pthread_create");
        release_handle(stream);
        free(stream);
        errno = create_rc;
        return -1;
    }
    stream->reader_running = true;

    /* Ready handshake: the collector states its verified policy and its intent to run
     * before the owner enables the event, so no record is published before a reader is
     * polling. Reading the flag out of a stack frame that pthread_create's frame could
     * already have left is exactly what this replaces. */
    int lock_rc = pthread_mutex_lock(&stream->ready_lock);
    int wait_rc = lock_rc;
    while (wait_rc == 0 && !stream->reader_ready) {
        wait_rc = pthread_cond_wait(&stream->ready_cond, &stream->ready_lock);
    }
    bool reader_ready = (wait_rc == 0) && stream->reader_ready;
    bool reader_policy_ok = reader_ready && stream->reader_policy_ok;
    if (lock_rc == 0) {
        /* cond_wait may fail with the mutex reacquired; always release what we hold,
         * otherwise a reader mid-publish would block the join below. */
        pthread_mutex_unlock(&stream->ready_lock);
    }
    if (!reader_ready) {
        int saved = wait_rc != 0 ? wait_rc : EAGAIN;
        record_error(stream, WKSIM_ERR_THREAD_CREATE, saved,
                     "start: reader did not report ready");
        return start_abort(stream, saved);
    }

    if (ioctl(stream->fd, PERF_EVENT_IOC_RESET, 0) != 0) {
        int saved = errno;
        record_error(stream, WKSIM_ERR_ENABLE, saved, "start: PERF_EVENT_IOC_RESET");
        return start_abort(stream, saved);
    }
    stream->enable_attempted = true;
    if (!monotonic_ns(stream->clock_id, &stream->enable_before_ns)) {
        int saved = errno;
        record_error(stream, WKSIM_ERR_CLOCK, saved, "start: clock before ENABLE");
        return start_abort(stream, saved);
    }
    if (ioctl(stream->fd, PERF_EVENT_IOC_ENABLE, 0) != 0) {
        int saved = errno;
        record_error(stream, WKSIM_ERR_ENABLE, saved, "start: PERF_EVENT_IOC_ENABLE");
        return start_abort(stream, saved);
    }
    if (!monotonic_ns(stream->clock_id, &stream->enable_after_ns)) {
        int saved = errno;
        record_error(stream, WKSIM_ERR_CLOCK, saved, "start: clock after ENABLE");
        ioctl(stream->fd, PERF_EVENT_IOC_DISABLE, 0);
        return start_abort(stream, saved);
    }
    stream->enable_ok = true;

    if (!reader_policy_ok) {
        /* The collector recorded the detailed reason before signalling ready; this is the
         * start-side summary. DISABLE first, then stop and join, so the thread has already
         * left the poll loop. */
        record_error(stream, WKSIM_ERR_THREAD_POLICY, 0,
                     "start: reader is not SCHED_OTHER");
        ioctl(stream->fd, PERF_EVENT_IOC_DISABLE, 0);
        return start_abort(stream, EPERM);
    }

    *handle = stream;
    set_last_error("no error");
    return 0;
}

/* ---- 5. stop ------------------------------------------------------------ */

static int write_all(int fd, const unsigned char *data, uint64_t length)
{
    uint64_t written = 0;
    while (written < length) {
        ssize_t got = write(fd, data + written, (size_t)(length - written));
        if (got < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (got == 0) {
            errno = EIO;
            return -1;
        }
        written += (uint64_t)got;
    }
    return 0;
}

/* Walk the captured bytes as a perf record stream. Sizes come from the record headers,
 * never from a fixed stride: the capture keeps every record exactly as published,
 * including LOST and unknown types, so its length need not be a multiple of 32 (or of
 * anything else). Only the 8-byte header is decoded, and the payload is not touched.
 *
 * Returns false when the stream cannot be walked (header smaller than the header struct,
 * size not 8-byte aligned, or a record running past the end). */
static bool walk_perf_records(const unsigned char *data, uint64_t length,
                              uint32_t *max_record_size, uint64_t *unparsed_bytes)
{
    uint64_t offset = 0;
    uint32_t largest = 0;
    while (offset < length) {
        if (length - offset < sizeof(struct perf_event_header)) {
            *unparsed_bytes = length - offset;
            break;
        }
        unsigned char header[sizeof(struct perf_event_header)];
        memcpy(header, data + offset, sizeof header);
        uint16_t record_size = 0;
        memcpy(&record_size, header + 6, sizeof record_size);
        if (record_size < sizeof(struct perf_event_header)
                || record_size % sizeof(struct perf_event_header) != 0
                || (uint64_t)record_size > length - offset) {
            return false;
        }
        if ((uint32_t)record_size > largest) {
            largest = (uint32_t)record_size;
        }
        offset += (uint64_t)record_size;
    }
    *max_record_size = largest;
    return true;
}

static void count_perf_records(struct wksim_perf_stream *stream)
{
    uint32_t largest = 0;
    uint64_t unparsed = 0;
    stream->raw_len_record_aligned =
        (stream->captured_bytes % sizeof(struct perf_event_header)) == 0;
    if (!walk_perf_records(stream->storage, stream->captured_bytes, &largest, &unparsed)) {
        record_error(stream, WKSIM_ERR_MALFORMED_STREAM, 0,
                     "stop: captured bytes are not a walkable perf record stream");
        return;
    }
    if (unparsed != 0) {
        /* Not an error by itself: the pressure guard stops mid-stream, so the last bytes
         * can be a partial record. They stay in the raw file and are reported, never
         * dropped or padded. */
        record_errorf(stream, WKSIM_ERR_CAPTURE_INCOMPLETE, 0,
                      "stop: %" PRIu64 " trailing bytes are not a whole perf record",
                      unparsed);
    }
    stream->unparsed_bytes = unparsed;
    stream->max_record_bytes_seen = largest;

    uint64_t switch_records = 0;
    uint64_t cpu_wide = 0;
    uint64_t lost = 0;
    uint64_t lost_samples = 0;
    uint64_t unknown = 0;
    uint64_t out = 0;
    uint64_t in = 0;
    /* Only the walkable prefix holds whole records; the unparsed trailing bytes are
     * reported but never read as a phantom record. */
    uint64_t walkable = stream->captured_bytes - unparsed;
    for (uint64_t offset = 0; offset < walkable;) {
        unsigned char header[sizeof(struct perf_event_header)];
        memcpy(header, stream->storage + offset, sizeof header);
        uint32_t type = 0;
        uint16_t misc = 0;
        uint16_t record_size = 0;
        memcpy(&type, header, sizeof type);
        memcpy(&misc, header + 4, sizeof misc);
        memcpy(&record_size, header + 6, sizeof record_size);
        offset += (uint64_t)record_size;

        if (type == PERF_RECORD_SWITCH) {
            switch_records++;
            if ((misc & MISC_SWITCH_OUT) != 0) {
                out++;
            } else {
                in++;
            }
        } else if (type == PERF_RECORD_SWITCH_CPU_WIDE) {
            cpu_wide++;
        } else if (type == PERF_RECORD_LOST) {
            lost++;
        } else if (type == PERF_RECORD_LOST_SAMPLES) {
            lost_samples++;
        } else {
            unknown++;
        }
    }
    stream->switch_records = switch_records;
    stream->switch_cpu_wide_records = cpu_wide;
    stream->lost_records = lost;
    stream->lost_samples_records = lost_samples;
    stream->unknown_records = unknown;
    stream->switch_out = out;
    stream->switch_in = in;
    stream->pairs = out < in ? out : in;
    stream->records_captured = switch_records + cpu_wide + lost + lost_samples + unknown;
}

static char *json_escape(const char *text, char *buffer, size_t buffer_size)
{
    size_t out = 0;
    for (size_t index = 0; text[index] != '\0' && out + 2 < buffer_size; index++) {
        char ch = text[index];
        if (ch == '"' || ch == '\\') {
            buffer[out++] = '\\';
            buffer[out++] = ch;
        } else if ((unsigned char)ch < 0x20) {
            buffer[out++] = ' ';
        } else {
            buffer[out++] = ch;
        }
    }
    buffer[out] = '\0';
    return buffer;
}

int wksim_perf_stop(void *handle, const char *raw_path, const char *meta_path)
{
    struct wksim_perf_stream *stream = handle;
    if (stream == NULL || raw_path == NULL || meta_path == NULL) {
        errno = EINVAL;
        set_last_error("stop: NULL handle or path");
        return -1;
    }
    if (stream->owner_tid != (int64_t)syscall(SYS_gettid)) {
        errno = EPERM;
        set_last_error("stop: must run on the owning thread");
        return -1;
    }

    bool disable_ok = false;
    bool munmap_ok = true;
    bool close_ok = true;

    /* Disable before the final drain, so the reader's last pass is exact. */
    if (stream->enable_attempted) {
        if (!monotonic_ns(stream->clock_id, &stream->disable_before_ns)) {
            int saved = errno;
            record_error(stream, WKSIM_ERR_CLOCK, saved, "stop: clock before DISABLE");
        }
        if (ioctl(stream->fd, PERF_EVENT_IOC_DISABLE, 0) == 0) {
            disable_ok = true;
        } else {
            int saved = errno;
            record_error(stream, WKSIM_ERR_DISABLE, saved, "stop: PERF_EVENT_IOC_DISABLE");
        }
        if (!monotonic_ns(stream->clock_id, &stream->disable_after_ns)) {
            int saved = errno;
            record_error(stream, WKSIM_ERR_CLOCK, saved, "stop: clock after DISABLE");
        }
    }

    atomic_store_explicit(&stream->stop_requested, true, memory_order_release);

    int join_rc = join_reader(stream, true);
    if (join_rc != 0) {
        /* The collector could not be joined, so it may still be touching the ring mapping,
         * the storage area, the event fd and this handle. Refusing here is the only safe
         * answer: do not unmap, do not close, do not free, and do not claim the reader
         * stopped. The handle stays owned by the caller and the failure is explicit. */
        record_error(stream, WKSIM_ERR_JOIN, join_rc,
                     "stop: pthread_join failed, reader ownership retained");
        errno = join_rc;
        return -1;
    }
    /* No writer remains: reorder the owner's failures to the front and refresh the
     * thread-local message so the primary error is the lifecycle one. */
    settle_errors(stream);
    int error_count = error_count_now(stream);

    /* Walk the captured bytes as a perf record stream (sizes from the headers, never a
     * fixed stride) so LOST and unknown records survive and are counted. */
    count_perf_records(stream);
    error_count = error_count_now(stream);

    /* Primary failure: any explicit collector error, an incomplete capture, or no pair.
     * These are decided before any I/O so writing cannot mask them. */
    if (error_count == 0 && (!stream->enable_ok || !disable_ok)) {
        record_error(stream, WKSIM_ERR_CAPTURE_INCOMPLETE, 0,
                     "stop: enable/disable did not complete");
    }
    if (error_count == 0 && stream->pairs == 0) {
        record_error(stream, WKSIM_ERR_NO_PAIR, 0,
                     "stop: no complete switch in/out pair was captured");
    }

    /* Exclusive creation first for both files, so a pre-existing path invalidates the
     * whole write before any byte is written. */
    int raw_fd = -1;
    int meta_fd = -1;
    raw_fd = open(raw_path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
    if (raw_fd < 0) {
        int saved = errno;
        record_error(stream, saved == EEXIST ? WKSIM_ERR_OUTPUT_EXISTS
                                             : WKSIM_ERR_OUTPUT_WRITE,
                     saved, "stop: create raw");
    } else {
        meta_fd = open(meta_path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
        if (meta_fd < 0) {
            int saved = errno;
            record_error(stream, saved == EEXIST ? WKSIM_ERR_OUTPUT_EXISTS
                                                 : WKSIM_ERR_OUTPUT_WRITE,
                         saved, "stop: create meta");
        }
    }

    bool raw_written = false;
    bool meta_written = false;
    /* Declared at the top of the write section: no declaration after a statement. */
    char escaped_boot[128];
    char meta[8192];
    int written = 0;
    if (raw_fd >= 0 && meta_fd >= 0) {
        if (stream->captured_bytes > 0
                && write_all(raw_fd, stream->storage, stream->captured_bytes) != 0) {
            int saved = errno;
            record_error(stream, WKSIM_ERR_OUTPUT_WRITE, saved, "stop: write raw");
            raw_written = false;
        } else {
            raw_written = true;
        }

        json_escape(stream->boot_id, escaped_boot, sizeof escaped_boot);
        written = snprintf(
            meta, sizeof meta,
            "{\n"
            "  \"schema\": \"%s\",\n"
            "  \"classification\": \"diagnostic_only\",\n"
            "  \"full_acceptance\": false,\n"
            "  \"owner_pid\": %" PRId64 ",\n"
            "  \"owner_tid\": %" PRId64 ",\n"
            "  \"boot_id\": \"%s\",\n"
            "  \"clock_id\": \"CLOCK_MONOTONIC\",\n"
            "  \"enable_before_ns\": %" PRIu64 ",\n"
            "  \"enable_after_ns\": %" PRIu64 ",\n"
            "  \"disable_before_ns\": %" PRIu64 ",\n"
            "  \"disable_after_ns\": %" PRIu64 ",\n"
            "  \"ring_bytes\": %" PRIu64 ",\n"
            "  \"data_offset\": %" PRIu64 ",\n"
            "  \"data_size\": %" PRIu64 ",\n"
            "  \"meta_geometry_exact\": %s,\n"
            "  \"storage_capacity_bytes\": %" PRIu64 ",\n"
            "  \"captured_bytes\": %" PRIu64 ",\n"
            "  \"raw_len_record_aligned\": %s,\n"
            "  \"max_record_bytes\": %" PRIu32 ",\n"
            "  \"unparsed_trailing_bytes\": %" PRIu64 ",\n"
            "  \"reader_policy\": %d,\n"
            "  \"reader_policy_name\": \"%s\",\n"
            "  \"captured_records\": %" PRIu64 ",\n"
            "  \"switch_records\": %" PRIu64 ",\n"
            "  \"switch_cpu_wide_records\": %" PRIu64 ",\n"
            "  \"lost_records\": %" PRIu64 ",\n"
            "  \"lost_samples_records\": %" PRIu64 ",\n"
            "  \"unknown_records\": %" PRIu64 ",\n"
            "  \"switch_out\": %" PRIu64 ",\n"
            "  \"switch_in\": %" PRIu64 ",\n"
            "  \"complete_pairs\": %" PRIu64 ",\n"
            "  \"ring_pressure_events\": %" PRIu64 ",\n"
            "  \"storage_pressure_events\": %" PRIu64 ",\n"
            "  \"losslessness_proven\": false,\n"
            "  \"losslessness_reason\": \"a pending PERF_RECORD_LOST is not flushable by "
            "PERF_EVENT_IOC_DISABLE, so collector_complete does not prove a lossless "
            "capture; flight admission stays blocked pending the stop sentinel\",\n"
            "  \"config\": {\"pid_argument\": 0, \"cpu_argument\": -1, \"inherit\": 0, "
            "\"exclude_kernel\": 1, \"context_switch\": 1, \"sample_id_all\": 1, "
            "\"sample_type\": [\"PERF_SAMPLE_TID\", \"PERF_SAMPLE_TIME\", "
            "\"PERF_SAMPLE_CPU\"]},\n"
            "  \"collector_complete\": %s,\n"
            "  \"collector_errors\": [",
            WKSIM_PERF_SCHEMA, stream->owner_pid, stream->owner_tid, escaped_boot,
            stream->enable_before_ns, stream->enable_after_ns,
            stream->disable_before_ns, stream->disable_after_ns, stream->ring_bytes,
            stream->meta_data_offset, stream->meta_data_size,
            stream->captured_meta_exact ? "true" : "false",
            stream->storage_capacity, stream->captured_bytes,
            stream->raw_len_record_aligned ? "true" : "false",
            stream->max_record_bytes_seen, stream->unparsed_bytes,
            stream->reader_policy,
            stream->reader_policy == SCHED_OTHER ? "SCHED_OTHER" : "not_sched_other",
            stream->records_captured, stream->switch_records,
            stream->switch_cpu_wide_records, stream->lost_records,
            stream->lost_samples_records, stream->unknown_records,
            stream->switch_out, stream->switch_in, stream->pairs,
            stream->ring_pressure_events, stream->storage_pressure_events,
            error_count == 0 ? "true" : "false");
        if (written < 0 || (size_t)written >= sizeof meta) {
            record_error(stream, WKSIM_ERR_OUTPUT_WRITE, 0, "stop: build metadata");
        } else {
            size_t used = (size_t)written;
            for (int index = 0; index < error_count; index++) {
                char escaped[WKSIM_PERF_ERR_TEXT * 2];
                json_escape(stream->errors[index].text, escaped, sizeof escaped);
                int part = snprintf(meta + used, sizeof meta - used,
                                    "%s{\"code\": \"%s\", \"saved_errno\": %d, "
                                    "\"from_owner\": %s, \"where\": \"%s\"}",
                                    index == 0 ? "" : ", ",
                                    wksim_err_name[stream->errors[index].code],
                                    stream->errors[index].saved_errno,
                                    stream->errors[index].from_owner ? "true" : "false",
                                    escaped);
                if (part < 0 || (size_t)part >= sizeof meta - used) {
                    record_error(stream, WKSIM_ERR_OUTPUT_WRITE, 0,
                                 "stop: metadata buffer exhausted");
                    break;
                }
                used += (size_t)part;
            }
            int tail = snprintf(meta + used, sizeof meta - used,
                                "],\n  \"lifecycle\": {\"disable_ok\": %s, "
                                "\"reader_joined\": %s, \"join_failed\": %s, "
                                "\"munmap_ok\": %s, \"close_ok\": %s},\n"
                                "  \"enable_attempted\": %s\n}\n",
                                disable_ok ? "true" : "false",
                                stream->reader_joined ? "true" : "false",
                                stream->join_failed ? "true" : "false",
                                munmap_ok ? "true" : "false", close_ok ? "true" : "false",
                                stream->enable_attempted ? "true" : "false");
            if (tail < 0 || (size_t)tail >= sizeof meta - used) {
                record_error(stream, WKSIM_ERR_OUTPUT_WRITE, 0,
                             "stop: metadata tail buffer exhausted");
            } else {
                used += (size_t)tail;
                if (write_all(meta_fd, (const unsigned char *)meta, used) != 0) {
                    int saved = errno;
                    record_error(stream, WKSIM_ERR_OUTPUT_WRITE, saved,
                                 "stop: write meta");
                } else {
                    meta_written = true;
                }
            }
        }
    }

    if (raw_fd >= 0 && close(raw_fd) != 0) {
        int saved = errno;
        close_ok = false;
        record_error(stream, WKSIM_ERR_CLOSE, saved, "stop: close raw");
    }
    if (meta_fd >= 0 && close(meta_fd) != 0) {
        int saved = errno;
        close_ok = false;
        record_error(stream, WKSIM_ERR_CLOSE, saved, "stop: close meta");
    }
    if ((raw_fd >= 0 || meta_fd >= 0) && !(raw_written && meta_written)) {
        record_error(stream, WKSIM_ERR_OUTPUT_PARTIAL, 0,
                     "stop: one output file is missing or partial");
    }

    /* Cleanup: unmap the ring, close the event, release storage. Every step is checked
     * and none of them can replace the primary failure. */
    if (stream->meta != NULL) {
        if (munmap(stream->meta, stream->map_size) != 0) {
            int saved = errno;
            munmap_ok = false;
            record_error(stream, WKSIM_ERR_MUNMAP, saved, "stop: munmap ring");
        }
        stream->meta = NULL;
        stream->ring = NULL;
    }
    if (stream->fd >= 0) {
        if (close(stream->fd) != 0) {
            int saved = errno;
            close_ok = false;
            record_error(stream, WKSIM_ERR_CLOSE, saved, "stop: close perf fd");
        }
        stream->fd = -1;
    }
    if (stream->storage != NULL) {
        if (munmap(stream->storage, (size_t)stream->storage_capacity) != 0) {
            int saved = errno;
            record_error(stream, WKSIM_ERR_MUNMAP, saved, "stop: munmap storage");
        }
        stream->storage = NULL;
    }

    /* Success requires every lifecycle step and a complete, error-free capture with
     * both output files written. Nothing below can change the primary error. */
    bool complete = (error_count_now(stream) == 0) && disable_ok && stream->reader_joined
                    && munmap_ok && close_ok && raw_written && meta_written;
    int primary_errno = first_errno(stream);
    if (!complete && primary_errno == 0) {
        /* The primary failure is a semantic one (pressure, no pair, ownership refused)
         * rather than a syscall failure; report a code instead of a bare errno 0. */
        if (error_count_now(stream) == 0) {
            record_error(stream, WKSIM_ERR_OUTPUT_PARTIAL, 0,
                         "stop: lifecycle step failed after the capture");
        }
        primary_errno = EIO;
    }
    if (complete) {
        set_last_error("no error");
    }
    errno = complete ? 0 : primary_errno;
    free(stream);
    return complete ? 0 : -1;
}
