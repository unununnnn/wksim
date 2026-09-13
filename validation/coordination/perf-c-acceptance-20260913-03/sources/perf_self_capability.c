/*
 * perf_self_capability.c -- self-thread context-switch capability probe, v2.
 *
 * v1 is preserved byte-for-byte as perf_self_capability.c.v1-erroneous. v2 answers the
 * main review:
 *
 *   - sequence: open -> mmap -> RESET -> ENABLE -> bounded sleeps -> DISABLE (checked)
 *     -> ONE stable read of data_head/data_tail -> parse -> drain if new records
 *     arrived. v1 parsed before disabling and could then re-parse a moving ring.
 *   - only PERF_RECORD_SWITCH contributes to success. PERF_RECORD_SWITCH_CPU_WIDE,
 *     unknown types, and switch records for another pid or tid are reported and fail.
 *     Both pid and tid must equal this thread's.
 *   - PERF_RECORD_LOST layout: { u64 id; u64 lost; } after the header, so `lost` is the
 *     SECOND u64. PERF_RECORD_LOST_SAMPLES carries a single { u64 lost; }.
 *   - leftover/truncated bytes, the record cap, a head that moved, and unbalanced
 *     in/out pairing all fail. A positive in/out count alone is not success.
 *   - page size comes from sysconf and must be a positive power of two; data_offset and
 *     data_size from perf_event_mmap_page are validated against the mapped region.
 *   - every clock_gettime and nanosleep return is checked; EINTR loops still stop at an
 *     absolute deadline so the total stay under one second.
 *   - _GNU_SOURCE is defined only when the build did not already define it.
 *   - no E2BIG compatibility retry: this is a fixed kernel 6.6 target, and an error is
 *     reported as-is.
 *
 * exclude_kernel: the man page documents it as a way to avoid counting kernel activity.
 * Whether it is usable here, and what it costs, is decided by the self-test on the
 * target host, not assumed. Build with -DPERF_PROBE_EXCLUDE_KERNEL=0 to compare.
 *
 * Build (see README for the exact argv):
 *   cc -std=c11 -O2 -Wall -Wextra -Werror -o /tmp/perf_self_capability \
 *      perf_self_capability.c perf_ring_parse.c
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <errno.h>
#include <inttypes.h>
#include <linux/perf_event.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#include "perf_ring_parse.h"

#define PERF_RING_DATA_PAGES 8u          /* 32 KiB data ring, bounded */
#define PERF_WAKEUP_EVENTS 1u
#define PERF_SLEEP_ROUNDS 4
#define PERF_SLEEP_NS 150000000L         /* 150 ms each: 600 ms total */
#define PERF_TOTAL_BUDGET_NS 900000000L  /* absolute deadline, under the 1 s bound */
#define PERF_MAX_RECORDS 4096            /* hard parse cap */
#define PERF_CPU_SLOTS 256u

#ifndef PERF_PROBE_EXCLUDE_KERNEL
#define PERF_PROBE_EXCLUDE_KERNEL 1      /* self-test decides whether to keep it */
#endif

/* Every diagnostic value is uint64_t printed with PRIu64, and the compiler checks the
 * pairing: a mismatch becomes -Werror at build time. */
#if defined(__GNUC__) || defined(__clang__)
#define FORMAT_PRINTF(fmt_index, first_arg) \
    __attribute__((format(printf, fmt_index, first_arg)))
#else
#define FORMAT_PRINTF(fmt_index, first_arg)
#endif

/* The reviewed contract ABI: one 8-byte header plus the 24-byte sample_id this probe
 * requests. Anything else would make the byte arithmetic in perf_ring_parse wrong. */
_Static_assert(sizeof(struct perf_event_header) == 8,
               "perf_event_header must be 8 bytes for the layout arithmetic");

static char g_fatal[512];

static void fatal(const char *format, ...) FORMAT_PRINTF(1, 2);

static void fatal(const char *format, ...)
{
    va_list args;
    va_start(args, format);
    vsnprintf(g_fatal, sizeof g_fatal, format, args);
    va_end(args);
}

static int errno_class(int err)
{
    switch (err) {
    case EACCES:
    case EPERM:
        return 1; /* permission */
    case ENOSYS:
    case ENOENT:
    case EOPNOTSUPP:
    case EINVAL:
        return 2; /* unsupported or unavailable */
    case EMFILE:
    case ENFILE:
    case ENOMEM:
        return 3; /* resource */
    default:
        return 4;
    }
}

static const char *errno_class_name(int klass)
{
    switch (klass) {
    case 1: return "permission";
    case 2: return "unsupported";
    case 3: return "resource";
    default: return "other";
    }
}

static bool is_positive_power_of_two(uint64_t value)
{
    return value != 0 && (value & (value - 1)) == 0;
}

/* Monotonic nanoseconds; returns false and fills g_fatal when the clock fails. */
static bool monotonic_ns(int clock_id, uint64_t *out)
{
    struct timespec now;
    if (clock_gettime(clock_id, &now) != 0) {
        int saved = errno;                       /* saved before any I/O */
        fatal("clock_gettime(%d) failed: %s", clock_id, strerror(saved));
        return false;
    }
    if (now.tv_sec < 0 || now.tv_nsec < 0) {
        fatal("clock_gettime(%d) returned a negative time", clock_id);
        return false;
    }
    *out = (uint64_t)now.tv_sec * 1000000000ull + (uint64_t)now.tv_nsec;
    return true;
}

/* Bounded sleeps: EINTR restarts the remaining interval but the loop always stops at
 * the absolute deadline, so the total can never run away. */
static bool bounded_sleeps(uint64_t deadline_ns)
{
    for (int round = 0; round < PERF_SLEEP_ROUNDS; round++) {
        uint64_t now_ns;
        if (!monotonic_ns(CLOCK_MONOTONIC, &now_ns)) {
            return false;
        }
        if (now_ns >= deadline_ns) {
            return true;
        }
        uint64_t remaining = deadline_ns - now_ns;
        uint64_t request_ns = ((uint64_t)PERF_SLEEP_NS < remaining) ? (uint64_t)PERF_SLEEP_NS
                                                                   : remaining;
        struct timespec request;
        request.tv_sec = (time_t)(request_ns / 1000000000ull);
        request.tv_nsec = (long)(request_ns % 1000000000ull);
        while (nanosleep(&request, &request) != 0) {
            if (errno != EINTR) {
                int saved = errno;               /* saved before any I/O */
                fatal("nanosleep failed: %s", strerror(saved));
                return false;
            }
            if (!monotonic_ns(CLOCK_MONOTONIC, &now_ns)) {
                return false;
            }
            if (now_ns >= deadline_ns) {
                return true;
            }
        }
    }
    return true;
}

struct probe_state {
    pid_t pid;
    pid_t tid;
    int fd;
    struct perf_event_attr attr;
    struct perf_event_mmap_page *meta;
    unsigned char *data;
    size_t map_size;
    uint64_t data_size;
    bool mapped;
};

/* Every failure path must still print a complete, valid JSON object on stdout. These
 * paths never ran the parser, so the reason is the real condition, never "ok". */
static void emit_failure_json(const struct probe_state *state, const char *reason,
                              uint64_t observed, uint64_t expected, int saved_errno)
{
    /* errno is unreliable after any stdio call, so the caller passes the value it saved
     * at the failing syscall and this function formats only that value. */
    const char *errno_text = saved_errno == 0 ? "" : strerror(saved_errno);
    printf("{\n");
    printf("  \"tool\": \"perf_self_capability\",\n");
    printf("  \"version\": \"v2\",\n");
    printf("  \"classification\": \"capability_probe_only\",\n");
    printf("  \"full_acceptance\": false,\n");
    printf("  \"recorder\": false,\n");
    printf("  \"thread\": {\"tid\": %d, \"pid\": %d},\n", (int)state->tid, (int)state->pid);
    printf("  \"contract\": {\"pid_argument\": 0, \"cpu_argument\": -1, \"group_fd\": -1, "
           "\"flags\": \"PERF_FLAG_FD_CLOEXEC\", \"inherit\": %u, "
           "\"exclude_kernel\": %u},\n",
           (unsigned)state->attr.inherit, (unsigned)state->attr.exclude_kernel);
    printf("  \"observed\": %" PRIu64 ",\n", observed);
    printf("  \"ring\": null,\n");
    printf("  \"switches\": null,\n");
    printf("  \"anomalies\": null,\n");
    printf("  \"failure\": {\"reason\": \"%s\", \"errno\": %" PRIu64
           ", \"errno_text\": \"%s\", \"expected\": %" PRIu64 "},\n",
           reason, (uint64_t)saved_errno, errno_text, expected);
    printf("  \"verdict\": \"failed\",\n");
    printf("  \"verdict_reason\": \"%s\",\n", reason);
    printf("  \"detail\": \"%s\"\n", g_fatal[0] ? g_fatal : reason);
    printf("}\n");
}

/* Signature: (state, summary, elapsed_ns, head, tail, cleanup_ok, timing_ok, failure,
 * cpu_seen). The counter-example harness must pass the new `failure` flag before
 * cpu_seen:
 *     report_json(&state, &summary, 1000000000ull, 0, 0, true, true, true, NULL);
 * Everything else in the call is unchanged. `failure` is the overall probe failure flag
 * from main; true means the verdict must be "failed" regardless of summary->ok. */
static void report_json(const struct probe_state *state, const perf_parse_summary *summary,
                        uint64_t elapsed_ns, uint64_t head, uint64_t tail,
                        bool cleanup_ok, bool timing_ok, bool failure,
                        const unsigned char *cpu_seen)
{
    /* Success requires all of: the parser's own status is OK (never only summary->ok),
     * no overall failure, successful cleanup, a sane clock and an elapsed time under the
     * one-second bound. A timeout with a successful parse must not report capable. */
    bool ok = (summary->status == PERF_PARSE_OK) && summary->ok && !failure && cleanup_ok
              && timing_ok && elapsed_ns < 1000000000ull;
    printf("{\n");
    printf("  \"tool\": \"perf_self_capability\",\n");
    printf("  \"version\": \"v2\",\n");
    printf("  \"classification\": \"capability_probe_only\",\n");
    printf("  \"full_acceptance\": false,\n");
    printf("  \"recorder\": false,\n");
    printf("  \"thread\": {\"tid\": %d, \"pid\": %d},\n", (int)state->tid, (int)state->pid);
    printf("  \"contract\": {\n");
    printf("    \"pid_argument\": 0,\n");
    printf("    \"cpu_argument\": -1,\n");
    printf("    \"group_fd\": -1,\n");
    printf("    \"flags\": \"PERF_FLAG_FD_CLOEXEC\",\n");
    printf("    \"inherit\": %u,\n", (unsigned)state->attr.inherit);
    printf("    \"exclude_kernel\": %u,\n", (unsigned)state->attr.exclude_kernel);
    printf("    \"type\": \"PERF_TYPE_SOFTWARE\",\n");
    printf("    \"config\": \"PERF_COUNT_SW_DUMMY\",\n");
    printf("    \"context_switch\": %u,\n", (unsigned)state->attr.context_switch);
    printf("    \"sample_id_all\": %u,\n", (unsigned)state->attr.sample_id_all);
    printf("    \"sample_type\": [\"PERF_SAMPLE_TID\", \"PERF_SAMPLE_TIME\", "
           "\"PERF_SAMPLE_CPU\"],\n");
    printf("    \"use_clockid\": %u, \"clockid\": \"CLOCK_MONOTONIC\",\n",
           (unsigned)state->attr.use_clockid);
    printf("    \"attr_size_used\": %u,\n", (unsigned)state->attr.size);
    printf("    \"ring_data_pages\": %u, \"data_size\": %" PRIu64 ",\n",
           PERF_RING_DATA_PAGES, state->data_size);
    printf("    \"sleep_rounds\": %d, \"sleep_ns_each\": %ld, \"budget_ns\": %ld\n",
           PERF_SLEEP_ROUNDS, PERF_SLEEP_NS, PERF_TOTAL_BUDGET_NS);
    printf("  },\n");
    printf("  \"ring\": {\"records\": %" PRIu64 ", \"bytes_consumed\": %" PRIu64
           ", \"pending_at_start\": %" PRIu64 ", \"pending_at_end\": %" PRIu64 ",\n",
           summary->records, summary->bytes_consumed, summary->pending_at_start,
           summary->pending_at_end);
    printf("           \"record_limit\": %d, \"head\": %" PRIu64 ", \"tail\": %" PRIu64
           "},\n", PERF_MAX_RECORDS, head, tail);
    printf("  \"switches\": {\"switch_records\": %" PRIu64
           ", \"switch_cpu_wide_records\": %" PRIu64 ", \"out\": %" PRIu64
           ", \"in\": %" PRIu64 ",\n", summary->switch_records,
           summary->switch_cpu_wide_records, summary->switch_out, summary->switch_in);
    printf("               \"preempt_out\": %" PRIu64 ", \"double_out\": %" PRIu64
           ", \"double_in\": %" PRIu64 ", \"trailing_out\": %" PRIu64 ",\n",
           summary->preempt_out, summary->double_out, summary->double_in,
           summary->trailing_out);
    printf("               \"time_regressions\": %" PRIu64 ",\n",
           summary->time_regressions);
    printf("               \"first_time_ns\": %" PRIu64 ", \"last_time_ns\": %" PRIu64
           ", \"cpu_last\": %u, \"cpus_seen\": %" PRIu64 "},\n",
           summary->first_time_ns, summary->last_time_ns, summary->last_cpu,
           summary->cpus_seen);
    printf("  \"anomalies\": {\"lost_events\": %" PRIu64 ", \"lost_records\": %" PRIu64
           ", \"lost_samples_records\": %" PRIu64 ",\n", summary->lost_events,
           summary->lost_records, summary->lost_samples_records);
    printf("                \"unknown_records\": %" PRIu64 ", \"malformed\": %" PRIu64
           ", \"foreign_records\": %" PRIu64 ", \"missing_identity\": %" PRIu64 "},\n",
           summary->unknown_records, summary->malformed, summary->foreign_records,
           summary->missing_identity);
    printf("  \"elapsed_ns\": %" PRIu64 ", \"under_one_second\": %s,\n", elapsed_ns,
           elapsed_ns < 1000000000ull ? "true" : "false");
    printf("  \"cpus_observed\": [");
    bool first = true;
    for (uint32_t cpu = 0; cpu < PERF_CPU_SLOTS; cpu++) {
        if (cpu_seen != NULL && cpu_seen[cpu]) {
            printf("%s%u", first ? "" : ", ", cpu);
            first = false;
        }
    }
    printf("],\n");
    printf("  \"sampling\": {\"instruction_pointer\": false, \"stack\": false, "
           "\"other_thread_data\": false, \"cpu_wide\": false},\n");
    printf("  \"verdict\": \"%s\",\n", ok ? "self_thread_switch_capable" : "failed");
    printf("  \"verdict_reason\": \"%s\",\n", perf_parse_status_name(summary->status));
    printf("  \"detail\": \"%s\"\n", ok ? "own-thread PERF_RECORD_SWITCH parsed"
                                         : (g_fatal[0] ? g_fatal : summary->first_problem));
    printf("}\n");
}

int main(void)
{
    struct probe_state state;
    memset(&state, 0, sizeof state);
    perf_parse_summary summary;
    memset(&summary, 0, sizeof summary);
    unsigned char cpu_seen[PERF_CPU_SLOTS];
    memset(cpu_seen, 0, sizeof cpu_seen);

    state.pid = getpid();
    state.tid = (pid_t)syscall(SYS_gettid);
    int saved_errno = errno;      /* errno only counts when a call actually failed */
    if (state.tid <= 0) {
        errno = saved_errno;
    }
    state.fd = -1;
    state.attr.type = PERF_TYPE_SOFTWARE;
    state.attr.size = sizeof state.attr;
    state.attr.config = PERF_COUNT_SW_DUMMY;
    state.attr.sample_period = 1;
    state.attr.sample_type = PERF_SAMPLE_TID | PERF_SAMPLE_TIME | PERF_SAMPLE_CPU;
    state.attr.disabled = 1;
    state.attr.inherit = 0;
    state.attr.sample_id_all = 1;
    state.attr.context_switch = 1;
    state.attr.wakeup_events = PERF_WAKEUP_EVENTS;
    state.attr.use_clockid = 1;
    state.attr.clockid = CLOCK_MONOTONIC;
    state.attr.exclude_kernel = PERF_PROBE_EXCLUDE_KERNEL ? 1 : 0;

    if (state.pid <= 0 || state.tid <= 0) {
        int identity_errno = (state.tid <= 0) ? saved_errno : 0;
        snprintf(g_fatal, sizeof g_fatal, "cannot determine this thread's identity");
        fprintf(stderr, "%s\n", g_fatal);
        emit_failure_json(&state, "identity_unavailable", 0, 0, identity_errno);
        return 2;
    }

    long page_long = sysconf(_SC_PAGESIZE);
    int sysconf_errno = (page_long <= 0) ? errno : 0;   /* saved before any I/O */
    if (page_long <= 0) {
        emit_failure_json(&state, "sysconf_failed", 0, 0, sysconf_errno);
        return 2;
    }
    uint64_t page_size = (uint64_t)page_long;
    if (!is_positive_power_of_two(page_size)) {
        emit_failure_json(&state, "page_size_not_power_of_two", page_size, 0, 0);
        return 2;
    }
    state.data_size = page_size * PERF_RING_DATA_PAGES;
    state.map_size = (size_t)(page_size + state.data_size);

    state.fd = (int)syscall(SYS_perf_event_open, &state.attr, 0, -1, -1,
                            PERF_FLAG_FD_CLOEXEC);
    if (state.fd < 0) {
        int open_errno = errno;               /* saved immediately */
        int klass = errno_class(open_errno);
        snprintf(g_fatal, sizeof g_fatal,
                 "perf_event_open(pid=0, cpu=-1, inherit=0, exclude_kernel=%u) failed: "
                 "%s (errno %d, class %s)", (unsigned)state.attr.exclude_kernel,
                 strerror(open_errno), open_errno, errno_class_name(klass));
        fprintf(stderr, "%s\n", g_fatal);
        emit_failure_json(&state,
                          klass == 1 ? "permission_denied"
                                     : klass == 2 ? "unsupported" : "open_failed",
                          0, 0, open_errno);
        return 2;
    }

    void *mapping = mmap(NULL, state.map_size, PROT_READ | PROT_WRITE, MAP_SHARED,
                         state.fd, 0);
    if (mapping == MAP_FAILED) {
        int mmap_errno = errno;               /* saved before close() can overwrite it */
        emit_failure_json(&state, "mmap_failed", state.map_size, 0, mmap_errno);
        close(state.fd);
        return 2;
    }
    state.mapped = true;
    state.meta = (struct perf_event_mmap_page *)mapping;
    state.data = (unsigned char *)mapping + page_size;

    /* Fixed kernel 6.6 target: the kernel must report the exact geometry we mapped.
     * No zero fallback and no silent downgrade to our own guess. */
    if (state.meta->data_offset != page_size) {
        emit_failure_json(&state, "meta_data_offset_mismatch", state.meta->data_offset,
                          page_size, 0);
        munmap(mapping, state.map_size);
        close(state.fd);
        return 2;
    }
    if (state.meta->data_size != state.data_size
            || !is_positive_power_of_two(state.meta->data_size)
            || state.meta->data_size > state.data_size) {
        emit_failure_json(&state, "meta_data_size_mismatch", state.meta->data_size,
                          state.data_size, 0);
        munmap(mapping, state.map_size);
        close(state.fd);
        return 2;
    }

    int failure = 0;
    const char *failure_name = NULL;   /* ioctl / timing / cleanup condition */
    int failure_errno = 0;             /* saved at the failing call, never re-read */
    if (ioctl(state.fd, PERF_EVENT_IOC_RESET, 0) != 0) {
        failure = 2;
        failure_name = "reset_failed";
        failure_errno = errno;                     /* saved immediately */
        fprintf(stderr, "PERF_EVENT_IOC_RESET failed: %s\n", strerror(failure_errno));
    } else if (ioctl(state.fd, PERF_EVENT_IOC_ENABLE, 0) != 0) {
        failure = 2;
        failure_name = "enable_failed";
        failure_errno = errno;                     /* saved immediately */
        fprintf(stderr, "PERF_EVENT_IOC_ENABLE failed: %s\n", strerror(failure_errno));
    }

    uint64_t start_ns = 0, deadline_ns = 0;
    bool timing_ok = true;
    if (failure == 0) {
        if (!monotonic_ns(CLOCK_MONOTONIC, &start_ns)) {
            failure = 2;
            failure_name = "clock_failed";
            timing_ok = false;
        } else {
            deadline_ns = start_ns + PERF_TOTAL_BUDGET_NS;
            if (!bounded_sleeps(deadline_ns)) {
                failure = 2;
                failure_name = "sleep_failed";
                timing_ok = false;
            }
        }
    }

    /* Disable first; only then take the single stable snapshot of the ring. */
    bool disabled = false;
    if (failure == 0) {
        if (ioctl(state.fd, PERF_EVENT_IOC_DISABLE, 0) != 0) {
            failure = 2;
            failure_name = "disable_failed";
            failure_errno = errno;                 /* saved immediately */
            fprintf(stderr, "PERF_EVENT_IOC_DISABLE failed: %s\n",
                    strerror(failure_errno));
        } else {
            disabled = true;
        }
    }

    uint64_t head = 0, tail = 0, first_head = 0, drain_head = 0;
    bool parse_ok = false;
    uint64_t end_ns = 0;
    bool cleanup_ok = true;
    if (failure == 0 && disabled) {
        __sync_synchronize();
        head = state.meta->data_head;
        tail = state.meta->data_tail;
        first_head = head;
        parse_ok = perf_ring_parse(state.data, state.data_size, tail, head,
                                   PERF_MAX_RECORDS, (int32_t)state.pid, (int32_t)state.tid,
                                   state.meta->data_head, cpu_seen, sizeof cpu_seen,
                                   &summary);
        /* A record completed between disable and the snapshot would be unparsed; if the
         * head moved, drain once more. Anything left after that is a real anomaly. */
        __sync_synchronize();
        drain_head = state.meta->data_head;
        if (parse_ok && drain_head != first_head) {
            parse_ok = perf_ring_parse(state.data, state.data_size, state.meta->data_tail,
                                       drain_head, PERF_MAX_RECORDS, (int32_t)state.pid,
                                       (int32_t)state.tid, state.meta->data_head, cpu_seen,
                                       sizeof cpu_seen, &summary);
            head = drain_head;
        }
    }
    if (!monotonic_ns(CLOCK_MONOTONIC, &end_ns)) {
        if (failure == 0) {
            failure = 2;
            failure_name = "clock_failed";
        }
        timing_ok = false;
    }
    uint64_t elapsed_ns = (end_ns > start_ns) ? (end_ns - start_ns) : 0;

    if (state.mapped && munmap(mapping, state.map_size) != 0) {
        cleanup_ok = false;
        int munmap_errno = errno;                  /* saved immediately */
        fprintf(stderr, "munmap failed: %s\n", strerror(munmap_errno));
    }
    if (close(state.fd) != 0) {
        cleanup_ok = false;
        int close_errno = errno;                   /* saved immediately */
        fprintf(stderr, "close(perf fd) failed: %s\n", strerror(close_errno));
    }

    state.fd = -1;
    /* A parse success must never stand in for an ioctl, timing or cleanup failure. */
    if (failure == 0 && !parse_ok) {
        failure = 1;
        fprintf(stderr, "ring parse failed: %s (%s)\n",
                perf_parse_status_name(summary.status), summary.first_problem);
    }
    if (failure == 0 && !timing_ok) {
        failure = 1;
        summary.status = PERF_PARSE_PROBE_FAILURE;
        snprintf(summary.first_problem, sizeof summary.first_problem, "timing_failed");
    }
    if (failure == 0 && !cleanup_ok) {
        failure = 1;
        summary.status = PERF_PARSE_PROBE_FAILURE;
        snprintf(summary.first_problem, sizeof summary.first_problem, "cleanup_failed");
    }
    if (failure == 0 && elapsed_ns >= 1000000000ull) {
        failure = 1;
        summary.status = PERF_PARSE_PROBE_FAILURE;
        snprintf(summary.first_problem, sizeof summary.first_problem,
                 "exceeded_one_second");
        fprintf(stderr, "probe took %" PRIu64 " ns, over the 1 s bound\n", elapsed_ns);
    }
    if (failure != 0 && failure_name != NULL) {
        /* An ioctl/timing condition that never reached the parser: report the real
         * reason, and never leave the parser's "ok" standing in for it. The parser's
         * own status is preserved when it already failed, so verdict_reason keeps the
         * parse result instead of being flattened to probe_failure. */
        if (summary.status == PERF_PARSE_OK) {
            summary.status = PERF_PARSE_PROBE_FAILURE;
            snprintf(summary.first_problem, sizeof summary.first_problem, "%s",
                     failure_name);
        }
        if (g_fatal[0] == '\0') {
            snprintf(g_fatal, sizeof g_fatal, "%s", failure_name);
        }
    }
    /* The final verdict uses the explicit overall failure flag. */
    report_json(&state, &summary, elapsed_ns, head, tail, cleanup_ok, timing_ok,
                failure != 0, cpu_seen);
    return failure == 0 ? 0 : 1;
}
