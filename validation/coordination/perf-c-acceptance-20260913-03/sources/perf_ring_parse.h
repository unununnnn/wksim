/*
 * perf_ring_parse.h -- ring-record parser for the self-thread switch capability probe.
 *
 * Extracted so the parser can be linked into a synthetic negative self-test without
 * opening any perf event. Only PERF_RECORD_SWITCH can ever produce success:
 *
 *   - PERF_RECORD_SWITCH_CPU_WIDE is a different record with different fields; it is
 *     counted and reported but never contributes to success.
 *   - every switch record must carry both the calling thread's pid AND tid in its
 *     sample_id; a foreign pid, a foreign tid or a missing identity fails.
 *   - PERF_RECORD_LOST carries {u64 id; u64 lost} after the header, so `lost` is the
 *     SECOND u64 (offset 16); PERF_RECORD_LOST_SAMPLES carries a single {u64 lost} at
 *     offset 8. Either one fails the probe.
 *   - unknown record types fail the probe; they are not skipped silently.
 *   - leftover bytes, the record cap, a head that moved while reading, and unbalanced
 *     in/out pairing all fail the probe. A positive in/out count alone is not success.
 */
#ifndef PERF_RING_PARSE_H
#define PERF_RING_PARSE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Parse verdicts. State anomalies (7-13) are distinct from record anomalies so a
 * caller can report which condition actually occurred. */
typedef enum {
    PERF_PARSE_OK = 0,
    PERF_PARSE_BAD_ARGUMENT = 1,
    PERF_PARSE_RING_UNUSABLE = 2,
    PERF_PARSE_TRUNCATED = 3,        /* ring content ended mid-record */
    PERF_PARSE_RECORD_LIMIT = 4,     /* parse cap reached with bytes still pending */
    PERF_PARSE_MALFORMED = 5,        /* implausible header, size or sample_id */
    PERF_PARSE_LOST = 6,             /* PERF_RECORD_LOST */
    PERF_PARSE_LOST_SAMPLES = 7,     /* PERF_RECORD_LOST_SAMPLES */
    PERF_PARSE_UNKNOWN_RECORD = 8,   /* a record type this probe does not understand */
    PERF_PARSE_CPU_WIDE_RECORD = 9,  /* PERF_RECORD_SWITCH_CPU_WIDE is not usable here */
    PERF_PARSE_FOREIGN_THREAD = 10,  /* switch record for another pid or tid */
    PERF_PARSE_NO_SWITCH = 11,       /* no PERF_RECORD_SWITCH for this thread */
    PERF_PARSE_INCOMPLETE_PAIR = 12, /* out,in alternation broken or unfinished */
    PERF_PARSE_HEAD_MOVED = 13,      /* the producer advanced while parsing */
    PERF_PARSE_NO_WINDOW = 14,       /* the observed span is not positive */
    PERF_PARSE_TIME_REGRESSION = 15, /* a later record carries a non-advancing time */
    PERF_PARSE_PROBE_FAILURE = 16    /* the probe failed before the parser could run */
} perf_parse_status;

typedef struct {
    uint64_t records;                /* records consumed */
    uint64_t bytes_consumed;
    uint64_t pending_at_start;
    uint64_t pending_at_end;
    uint64_t switch_records;         /* PERF_RECORD_SWITCH for this thread only */
    uint64_t switch_cpu_wide_records;
    uint64_t lost_events;            /* sum of the LOST / LOST_SAMPLES counters */
    uint64_t lost_records;
    uint64_t lost_samples_records;
    uint64_t unknown_records;
    uint64_t malformed;
    uint64_t foreign_records;        /* switch records for another pid or tid */
    uint64_t missing_identity;       /* switch records with no usable sample_id */
    uint64_t switch_out;
    uint64_t switch_in;
    uint64_t preempt_out;
    uint64_t double_out;             /* two switch-outs without an intervening in */
    uint64_t double_in;              /* a switch-in with no open switch-out */
    uint64_t trailing_out;           /* the last record was a switch-out with no in */
    uint64_t time_regressions;       /* records whose time did not advance */
    uint64_t first_time_ns;
    uint64_t last_time_ns;
    uint32_t last_cpu;
    uint64_t cpus_seen;
    char first_problem[96];
    perf_parse_status status;
    bool ok;                         /* every condition below satisfied */
} perf_parse_summary;

/* Parse [data_tail, data_head) of the data area inside a mapped perf ring.
 *
 *   data         first byte of the data area (mapping + page size)
 *   data_size    size of the data area in bytes (positive power of two)
 *   record_limit hard cap on records consumed
 *   self_pid     expected sample_id pid (getpid())
 *   self_tid     expected sample_id tid (gettid())
 *   head_after   re-read data_head after parsing, to detect a moving head
 *
 * Never mutates the ring and never calls into perf. `summary` must be non-NULL and is
 * fully initialised even on failure. */
bool perf_ring_parse(const unsigned char *data, uint64_t data_size,
                     uint64_t tail, uint64_t head, uint64_t record_limit,
                     int32_t self_pid, int32_t self_tid, uint64_t head_after,
                     unsigned char *cpu_seen, size_t cpu_seen_len,
                     perf_parse_summary *summary);

/* Human-readable status name for reporting. */
const char *perf_parse_status_name(perf_parse_status status);

#endif /* PERF_RING_PARSE_H */
