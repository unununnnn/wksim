/*
 * perf_ring_parse.c -- strict composer of the perf ring records this probe accepts.
 *
 * See perf_ring_parse.h for the acceptance rules. This file is deliberately small and
 * has no dependency on the perf syscall, so the synthetic self-test can link it.
 */
#include "perf_ring_parse.h"

#include <inttypes.h>
#include <linux/perf_event.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define REC_SWITCH_TYPE PERF_RECORD_SWITCH                    /* 14 */
#define REC_SWITCH_CPU_WIDE_TYPE PERF_RECORD_SWITCH_CPU_WIDE  /* 15 */
#define REC_LOST_TYPE PERF_RECORD_LOST                        /* 2 */
#define REC_LOST_SAMPLES_TYPE PERF_RECORD_LOST_SAMPLES        /* 13 */

#define MISC_SWITCH_OUT (1u << 13)
#define MISC_SWITCH_OUT_PREEMPT (1u << 14)

/* sample_id for sample_type = PERF_SAMPLE_TID | PERF_SAMPLE_TIME | PERF_SAMPLE_CPU:
 *   { u32 pid, tid; }  -> 8 bytes
 *   { u64 time; }      -> 8 bytes
 *   { u32 cpu, res; }  -> 8 bytes
 * With that fixed sample_type an accepted switch record has exactly one size.
 */
#define SAMPLE_ID_BYTES 24u
#define SWITCH_BODY_BYTES SAMPLE_ID_BYTES
#define SWITCH_RECORD_BYTES (sizeof(struct perf_event_header) + SWITCH_BODY_BYTES)
#define SWITCH_CPU_WIDE_RECORD_BYTES \
    (sizeof(struct perf_event_header) + 8u + SAMPLE_ID_BYTES)

/* Layout arithmetic (8-byte header: u32 type, u16 misc, u16 size):
 *   PERF_RECORD_SWITCH          header(8) + sample_id(24)      = 32 bytes exactly
 *   PERF_RECORD_SWITCH_CPU_WIDE header(8) + next_prev(8) + 24  = 40 bytes exactly
 *   PERF_RECORD_LOST            header(8) + {u64 id} at +8 + {u64 lost} at +16
 *                               -> `lost` is the SECOND u64 after the header
 *   PERF_RECORD_LOST_SAMPLES    header(8) + {u64 lost} at +8
 */
#define LOST_ID_OFFSET 8u          /* record offset of the id u64 */
#define LOST_COUNT_OFFSET 16u      /* record offset of the lost u64 (second u64) */
#define LOST_BODY_BYTES 16u
#define LOST_SAMPLES_COUNT_OFFSET 8u
#define LOST_SAMPLES_BODY_BYTES 8u

/* Every diagnostic value is a uint64_t and is printed with PRIu64, so the variadic
 * arguments always match the format string by construction. The attribute asks the
 * compiler to verify that too: a mismatch becomes -Werror at build time. */
#if defined(__GNUC__) || defined(__clang__)
#define FORMAT_PRINTF(fmt_index, first_arg) \
    __attribute__((format(printf, fmt_index, first_arg)))
#else
#define FORMAT_PRINTF(fmt_index, first_arg)
#endif

static void set_problem(perf_parse_summary *summary, perf_parse_status status,
                        const char *format, ...) FORMAT_PRINTF(3, 4);

static void set_problem(perf_parse_summary *summary, perf_parse_status status,
                        const char *format, ...)
{
    if (summary->status != PERF_PARSE_OK) {
        return;   /* keep the first condition that fired */
    }
    summary->status = status;
    va_list args;
    va_start(args, format);
    vsnprintf(summary->first_problem, sizeof summary->first_problem, format, args);
    va_end(args);
}

static void copy_ring(unsigned char *out, const unsigned char *data, uint64_t size,
                      uint64_t mask, uint64_t offset, uint64_t length)
{
    uint64_t pos = offset & mask;
    uint64_t first = size - pos;
    if (first > length) {
        first = length;
    }
    memcpy(out, data + pos, (size_t)first);
    if (length > first) {
        memcpy(out + first, data, (size_t)(length - first));
    }
}

const char *perf_parse_status_name(perf_parse_status status)
{
    switch (status) {
    case PERF_PARSE_OK: return "ok";
    case PERF_PARSE_BAD_ARGUMENT: return "bad_argument";
    case PERF_PARSE_RING_UNUSABLE: return "ring_unusable";
    case PERF_PARSE_TRUNCATED: return "truncated_bytes";
    case PERF_PARSE_RECORD_LIMIT: return "record_limit";
    case PERF_PARSE_MALFORMED: return "malformed";
    case PERF_PARSE_LOST: return "lost_events";
    case PERF_PARSE_LOST_SAMPLES: return "lost_samples";
    case PERF_PARSE_UNKNOWN_RECORD: return "unknown_record";
    case PERF_PARSE_CPU_WIDE_RECORD: return "cpu_wide_record";
    case PERF_PARSE_FOREIGN_THREAD: return "foreign_thread";
    case PERF_PARSE_NO_SWITCH: return "no_switch_record";
    case PERF_PARSE_INCOMPLETE_PAIR: return "incomplete_pair";
    case PERF_PARSE_HEAD_MOVED: return "head_moved";
    case PERF_PARSE_NO_WINDOW: return "no_time_window";
    case PERF_PARSE_TIME_REGRESSION: return "time_regression";
    case PERF_PARSE_PROBE_FAILURE: return "probe_failure";
    default: return "unknown";
    }
}

bool perf_ring_parse(const unsigned char *data, uint64_t data_size,
                     uint64_t tail, uint64_t head, uint64_t record_limit,
                     int32_t self_pid, int32_t self_tid, uint64_t head_after,
                     unsigned char *cpu_seen, size_t cpu_seen_len,
                     perf_parse_summary *summary)
{
    if (summary == NULL) {
        return false;   /* nothing to report into; never dereference first */
    }
    memset(summary, 0, sizeof *summary);
    summary->status = PERF_PARSE_OK;
    if (cpu_seen != NULL && cpu_seen_len > 0) {
        memset(cpu_seen, 0, cpu_seen_len);
    }
    if (data == NULL || data_size < sizeof(struct perf_event_header)
            || (data_size & (data_size - 1)) != 0) {
        set_problem(summary, PERF_PARSE_BAD_ARGUMENT,
                    "data_size %" PRIu64 " is not a positive power of two", data_size);
        return false;
    }
    if (head < tail || (head - tail) > data_size) {
        set_problem(summary, PERF_PARSE_RING_UNUSABLE,
                    "head %" PRIu64 " tail %" PRIu64 " exceed data_size %" PRIu64,
                    head, tail, data_size);
        return false;
    }

    uint64_t mask = data_size - 1;
    uint64_t pending = head - tail;
    summary->pending_at_start = pending;
    unsigned char *scratch = malloc((size_t)data_size);
    if (scratch == NULL) {
        set_problem(summary, PERF_PARSE_BAD_ARGUMENT, "scratch allocation failed");
        return false;
    }

    /* Strict alternation out, in, out, in ...:
     *   out is legal exactly when no switch-in is outstanding (!awaiting_in)
     *   in  is legal exactly when one is outstanding (awaiting_in)
     * so out,out,in,in cannot be read as two pairs and two legal pairs are accepted. */
    bool awaiting_in = false;
    uint64_t previous_time_ns = 0;

    while (pending >= sizeof(struct perf_event_header)) {
        if (summary->records >= record_limit) {
            set_problem(summary, PERF_PARSE_RECORD_LIMIT,
                        "record limit %" PRIu64 " reached with %" PRIu64 " bytes pending",
                        record_limit, pending);
            break;
        }
        struct perf_event_header header;
        copy_ring((unsigned char *)&header, data, data_size, mask, tail, sizeof header);
        if (header.size < sizeof header || header.size > data_size
                || (header.size & 7u) != 0) {
            summary->malformed++;
            set_problem(summary, PERF_PARSE_MALFORMED,
                        "header size %" PRIu64 " outside [%" PRIu64 ", %" PRIu64
                        "] at offset %" PRIu64,
                        (uint64_t)header.size, (uint64_t)sizeof header, data_size, tail);
            break;
        }
        if (header.size > pending) {
            summary->malformed++;
            set_problem(summary, PERF_PARSE_TRUNCATED,
                        "%" PRIu64 " bytes pending cannot hold a %" PRIu64 "-byte record",
                        pending, (uint64_t)header.size);
            break;
        }
        copy_ring(scratch, data, data_size, mask, tail, header.size);
        summary->records++;
        summary->bytes_consumed += header.size;
        const unsigned char *body = scratch + sizeof(struct perf_event_header);

        if (header.type == REC_SWITCH_TYPE) {
            if (header.size != SWITCH_RECORD_BYTES) {
                /* the fixed sample_type makes any other size a different layout */
                summary->malformed++;
                set_problem(summary, PERF_PARSE_MALFORMED,
                            "switch record is %" PRIu64 " bytes, expected exactly %" PRIu64,
                            (uint64_t)header.size, (uint64_t)SWITCH_RECORD_BYTES);
            } else {
                int32_t pid, tid;
                uint64_t time_ns;
                uint32_t cpu, reserved;
                memcpy(&pid, body, 4);
                memcpy(&tid, body + 4, 4);
                memcpy(&time_ns, body + 8, 8);
                memcpy(&cpu, body + 16, 4);
                memcpy(&reserved, body + 20, 4);
                (void)reserved;
                bool is_out = (header.misc & MISC_SWITCH_OUT) != 0;
                bool is_preempt = (header.misc & MISC_SWITCH_OUT_PREEMPT) != 0;
                /* An unusable identity is a malformed record whoever produced it, so it
                 * is classified before the foreign-thread test. Testing "foreign" first
                 * would report a zero-identity record as another thread's traffic and
                 * leave missing_identity permanently at zero. */
                if (pid == 0 || tid == 0) {
                    summary->missing_identity++;
                    set_problem(summary, PERF_PARSE_MALFORMED,
                                "switch record carries no identity (pid %" PRIu64
                                " tid %" PRIu64 ")",
                                (uint64_t)(int64_t)pid, (uint64_t)(int64_t)tid);
                } else if (pid != self_pid || tid != self_tid) {
                    summary->foreign_records++;
                    set_problem(summary, PERF_PARSE_FOREIGN_THREAD,
                                "switch record for pid %" PRIu64 " tid %" PRIu64,
                                (uint64_t)(int64_t)pid, (uint64_t)(int64_t)tid);
                } else if (!is_out && is_preempt) {
                    /* SWITCH_OUT_PREEMPT only qualifies a switch-away */
                    summary->malformed++;
                    set_problem(summary, PERF_PARSE_MALFORMED,
                                "switch-in record carries the preempt flag (misc %" PRIu64 ")",
                                (uint64_t)header.misc);
                } else {
                    summary->switch_records++;
                    if (is_out) {
                        summary->switch_out++;
                        if (!awaiting_in) {
                            awaiting_in = true;
                        } else {
                            summary->double_out++;
                            set_problem(summary, PERF_PARSE_INCOMPLETE_PAIR,
                                        "two switch-outs in a row at record %" PRIu64,
                                        summary->records);
                        }
                        if (is_preempt) {
                            summary->preempt_out++;
                        }
                    } else {
                        summary->switch_in++;
                        if (awaiting_in) {
                            awaiting_in = false;
                        } else {
                            summary->double_in++;
                            set_problem(summary, PERF_PARSE_INCOMPLETE_PAIR,
                                        "switch-in without an open switch-out at record "
                                        "%" PRIu64, summary->records);
                        }
                    }
                    if (summary->first_time_ns == 0) {
                        summary->first_time_ns = time_ns;
                    } else if (time_ns <= previous_time_ns) {
                        summary->time_regressions++;
                        set_problem(summary, PERF_PARSE_TIME_REGRESSION,
                                    "time %" PRIu64 " does not advance past %" PRIu64
                                    " at record %" PRIu64,
                                    time_ns, previous_time_ns, summary->records);
                    }
                    previous_time_ns = time_ns;
                    summary->last_time_ns = time_ns;
                    summary->last_cpu = cpu;
                    if (cpu_seen != NULL && cpu < cpu_seen_len && !cpu_seen[cpu]) {
                        cpu_seen[cpu] = 1;
                        summary->cpus_seen++;
                    }
                }
            }
        } else if (header.type == REC_SWITCH_CPU_WIDE_TYPE) {
            summary->switch_cpu_wide_records++;
            set_problem(summary, PERF_PARSE_CPU_WIDE_RECORD,
                        "cpu-wide switch record %" PRIu64 " bytes; this probe accepts only "
                        "PERF_RECORD_SWITCH", (uint64_t)header.size);
        } else if (header.type == REC_LOST_TYPE) {
            if (header.size < sizeof header + LOST_BODY_BYTES) {
                summary->malformed++;
                set_problem(summary, PERF_PARSE_MALFORMED,
                            "lost record size %" PRIu64 " is below %" PRIu64,
                            (uint64_t)header.size,
                            (uint64_t)(sizeof header + LOST_BODY_BYTES));
            } else {
                uint64_t id, lost;
                /* both are body-relative: the header is sizeof(header) bytes long */
                memcpy(&id, body + LOST_ID_OFFSET - sizeof header, 8);        /* +0 */
                memcpy(&lost, body + LOST_COUNT_OFFSET - sizeof header, 8);    /* +8 */
                (void)id;
                summary->lost_records++;
                summary->lost_events += (lost == 0) ? 1 : lost;
                set_problem(summary, PERF_PARSE_LOST,
                            "PERF_RECORD_LOST reports %" PRIu64 " lost records (id %" PRIu64 ")",
                            lost, id);
            }
        } else if (header.type == REC_LOST_SAMPLES_TYPE) {
            if (header.size < sizeof header + LOST_SAMPLES_BODY_BYTES) {
                summary->malformed++;
                set_problem(summary, PERF_PARSE_MALFORMED,
                            "lost-samples record size %" PRIu64 " is below %" PRIu64,
                            (uint64_t)header.size,
                            (uint64_t)(sizeof header + LOST_SAMPLES_BODY_BYTES));
            } else {
                uint64_t lost;
                memcpy(&lost, body + LOST_SAMPLES_COUNT_OFFSET - sizeof header, 8);
                summary->lost_samples_records++;
                summary->lost_events += (lost == 0) ? 1 : lost;
                set_problem(summary, PERF_PARSE_LOST_SAMPLES,
                            "PERF_RECORD_LOST_SAMPLES reports %" PRIu64 " lost samples",
                            lost);
            }
        } else {
            summary->unknown_records++;
            set_problem(summary, PERF_PARSE_UNKNOWN_RECORD,
                        "record type %" PRIu64 " size %" PRIu64 " is not understood",
                        (uint64_t)header.type, (uint64_t)header.size);
        }

        tail += header.size;
        pending = head - tail;
    }

    summary->trailing_out = awaiting_in ? 1 : 0;
    summary->pending_at_end = pending;
    free(scratch);

    if (summary->status == PERF_PARSE_OK && pending > 0) {
        set_problem(summary, PERF_PARSE_TRUNCATED,
                    "%" PRIu64 " bytes remain after the last complete record", pending);
    }
    if (summary->status == PERF_PARSE_OK && head_after != head) {
        set_problem(summary, PERF_PARSE_HEAD_MOVED,
                    "data_head moved from %" PRIu64 " to %" PRIu64 " while parsing",
                    head, head_after);
    }
    if (summary->status == PERF_PARSE_OK
            && summary->switch_records + summary->switch_cpu_wide_records == 0) {
        set_problem(summary, PERF_PARSE_NO_SWITCH,
                    "no PERF_RECORD_SWITCH observed in %" PRIu64 " pending bytes",
                    summary->pending_at_start);
    }
    if (summary->status == PERF_PARSE_OK
            && (summary->switch_in == 0 || summary->switch_out == 0)) {
        set_problem(summary, PERF_PARSE_INCOMPLETE_PAIR,
                    "switch-out %" PRIu64 " and switch-in %" PRIu64 " do not form a pair",
                    summary->switch_out, summary->switch_in);
    }
    if (summary->status == PERF_PARSE_OK && summary->trailing_out != 0) {
        set_problem(summary, PERF_PARSE_INCOMPLETE_PAIR,
                    "the last switch-out never got its switch-in");
    }
    if (summary->status == PERF_PARSE_OK
            && (summary->last_time_ns <= summary->first_time_ns)) {
        set_problem(summary, PERF_PARSE_NO_WINDOW,
                    "time span %" PRIu64 "..%" PRIu64 " is not positive",
                    summary->first_time_ns, summary->last_time_ns);
    }
    summary->ok = (summary->status == PERF_PARSE_OK);
    return summary->ok;
}
