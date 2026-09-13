/*
 * ds_perf_ring_acceptance.c -- independent synthetic acceptance cases for the
 * author's perf ring parser (perf_ring_parse.h / perf_ring_parse.c).
 *
 * Independent of the author's selftest: it links the parser's public entry point
 * only, builds its ring bytes here, and never reads or greps the parser source.
 * Every case states its expectations before it runs and fails on a different
 * status or counter. No case asserts a success the header's contract forbids.
 *
 * head/tail semantics used here (perf): head and tail are MONOTONIC producer and
 * consumer counters, not ring indices. Only the address used to touch the data
 * area is masked; a record that runs past the end of the data area wraps in the
 * ADDRESS only, so tail + record_size may legitimately exceed data_size. This
 * file therefore never takes head modulo data_size.
 *
 * Counter discipline: only counters whose order the public contract implies are
 * asserted. Counting counters (how far a failed record got) are not asserted.
 *
 * Build (by main only; this file is not compiled or run here):
 *   cc -std=c11 -O2 -Wall -Wextra -Werror -I <author dir> \
 *      -o /tmp/ds_perf_ring_acceptance ds_perf_ring_acceptance.c \
 *      <author dir>/perf_ring_parse.c
 *   /tmp/ds_perf_ring_acceptance ; echo "exit=$?"
 *
 * Layout arithmetic (fixed sample_type = TID|TIME|CPU):
 *   header { u32 type; u16 misc; u16 size; } = 8 bytes, size a multiple of 8
 *   sample_id = { u32 pid; u32 tid; u64 time; u32 cpu; u32 res; } = 24
 *   PERF_RECORD_SWITCH          = 8 + 24 = 32
 *   PERF_RECORD_SWITCH_CPU_WIDE = 8 + 8 (next_prev) + 24 = 40
 *   PERF_RECORD_LOST            = 8 + {u64 id}@+8 + {u64 lost}@+16
 *   PERF_RECORD_LOST_SAMPLES    = 8 + {u64 lost}@+8
 */
#include "perf_ring_parse.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#define TEST_PID 1000
#define TEST_TID 1001

#define REC_SWITCH 14u
#define REC_SWITCH_CPU_WIDE 15u
#define REC_LOST 2u
#define REC_LOST_SAMPLES 13u
#define REC_UNKNOWN 71u

#define MISC_SWITCH_OUT (1u << 13)
#define MISC_OUT_PREEMPT (1u << 14)

#define SWITCH_BYTES 32u
#define CPU_WIDE_BYTES 40u
#define LOST_BYTES 24u
#define LOST_SAMPLES_BYTES 16u
#define UNKNOWN_BYTES 16u
#define HDR_BYTES 8u

/* Counter selector for an expectation entry. */
enum counter_id {
    C_RECORDS = 0,
    C_SWITCH_RECORDS,
    C_SWITCH_OUT,
    C_SWITCH_IN,
    C_DOUBLE_OUT,
    C_DOUBLE_IN,
    C_TRAILING_OUT,
    C_TIME_REGRESSIONS,
    C_CPU_WIDE,
    C_FOREIGN,
    C_LOST_RECORDS,
    C_LOST_SAMPLES_RECORDS,
    C_LOST_EVENTS,
    C_MALFORMED,
    C_UNKNOWN,
    C_CPUS_SEEN
};

typedef struct {
    enum counter_id id;
    uint64_t want;
} counter_expect;

static int failures;
static int cases;
static char detail_buffer[256];

static uint64_t counter_value(const perf_parse_summary *summary, enum counter_id id)
{
    switch (id) {
    case C_RECORDS: return summary->records;
    case C_SWITCH_RECORDS: return summary->switch_records;
    case C_SWITCH_OUT: return summary->switch_out;
    case C_SWITCH_IN: return summary->switch_in;
    case C_DOUBLE_OUT: return summary->double_out;
    case C_DOUBLE_IN: return summary->double_in;
    case C_TRAILING_OUT: return summary->trailing_out;
    case C_TIME_REGRESSIONS: return summary->time_regressions;
    case C_CPU_WIDE: return summary->switch_cpu_wide_records;
    case C_FOREIGN: return summary->foreign_records;
    case C_LOST_RECORDS: return summary->lost_records;
    case C_LOST_SAMPLES_RECORDS: return summary->lost_samples_records;
    case C_LOST_EVENTS: return summary->lost_events;
    case C_MALFORMED: return summary->malformed;
    case C_UNKNOWN: return summary->unknown_records;
    case C_CPUS_SEEN: return summary->cpus_seen;
    default: return 0;
    }
}

static const char *status_name_or_unknown(perf_parse_status status)
{
    const char *name = perf_parse_status_name(status);
    return name != NULL ? name : "(null)";
}

static void store_u16(unsigned char *at, unsigned int value)
{
    at[0] = (unsigned char)(value & 0xffu);
    at[1] = (unsigned char)((value >> 8) & 0xffu);
}

static void store_u32(unsigned char *at, uint32_t value)
{
    for (int i = 0; i < 4; i++) {
        at[i] = (unsigned char)((value >> (8 * i)) & 0xffu);
    }
}

static void store_u64(unsigned char *at, uint64_t value)
{
    for (int i = 0; i < 8; i++) {
        at[i] = (unsigned char)((value >> (8 * i)) & 0xffu);
    }
}

/* Write a record at a MONOTONIC ring offset; only the address is masked, so a
 * record may straddle the end of the data area exactly as the kernel's does. */
static void ring_store(unsigned char *data, uint64_t data_size, uint64_t offset,
                       const unsigned char *record, uint64_t length)
{
    uint64_t mask = data_size - 1u;
    for (uint64_t i = 0; i < length; i++) {
        data[(offset + i) & mask] = record[i];
    }
}

static uint64_t make_header(unsigned char *record, unsigned int type, unsigned int misc,
                            unsigned int size)
{
    memset(record, 0, size);
    store_u32(record, type);
    store_u16(record + 4, misc);
    store_u16(record + 6, (unsigned int)size);
    return size;
}

static uint64_t make_switch(unsigned char *record, unsigned int misc, uint64_t time_ns,
                            uint32_t cpu, int32_t pid, int32_t tid)
{
    make_header(record, REC_SWITCH, misc, SWITCH_BYTES);
    store_u32(record + HDR_BYTES, (uint32_t)pid);
    store_u32(record + HDR_BYTES + 4, (uint32_t)tid);
    store_u64(record + HDR_BYTES + 8, time_ns);
    store_u32(record + HDR_BYTES + 16, cpu);
    return SWITCH_BYTES;
}

static uint64_t make_switch_default(unsigned char *record, unsigned int misc,
                                    uint64_t time_ns, uint32_t cpu)
{
    return make_switch(record, misc, time_ns, cpu, TEST_PID, TEST_TID);
}

static uint64_t make_cpu_wide(unsigned char *record, unsigned int misc, uint64_t time_ns,
                              uint32_t cpu, int32_t pid, int32_t tid)
{
    make_header(record, REC_SWITCH_CPU_WIDE, misc, CPU_WIDE_BYTES);
    store_u64(record + HDR_BYTES, 0x1111222233334444ull);   /* next_prev, unused here */
    store_u32(record + HDR_BYTES + 8, (uint32_t)pid);
    store_u32(record + HDR_BYTES + 12, (uint32_t)tid);
    store_u64(record + HDR_BYTES + 16, time_ns);
    store_u32(record + HDR_BYTES + 24, cpu);
    return CPU_WIDE_BYTES;
}

static uint64_t make_lost(unsigned char *record, uint64_t id, uint64_t lost)
{
    make_header(record, REC_LOST, 0, LOST_BYTES);
    store_u64(record + 8, id);
    store_u64(record + 16, lost);
    return LOST_BYTES;
}

static uint64_t make_lost_samples(unsigned char *record, uint64_t lost)
{
    make_header(record, REC_LOST_SAMPLES, 0, LOST_SAMPLES_BYTES);
    store_u64(record + 8, lost);
    return LOST_SAMPLES_BYTES;
}

static uint64_t make_unknown(unsigned char *record)
{
    return make_header(record, REC_UNKNOWN, 0, UNKNOWN_BYTES);
}

static uint64_t compose(unsigned char *data, uint64_t data_size,
                        const unsigned char *const *record_ptrs,
                        const uint64_t *record_lens, size_t count)
{
    uint64_t offset = 0;
    memset(data, 0, (size_t)data_size);
    for (size_t i = 0; i < count; i++) {
        ring_store(data, data_size, offset, record_ptrs[i], record_lens[i]);
        offset += record_lens[i];
    }
    return offset;   /* monotonic head offset, never taken modulo data_size */
}

static void report(const char *case_id, const char *what, int passed)
{
    cases++;
    if (!passed) {
        failures++;
    }
    printf("%-4s %-52s %s   %s\n", case_id, what, passed ? "PASS" : "FAIL", detail_buffer);
    fflush(stdout);
}

/*
 * Expectation source: either an explicit list of counters that the public
 * contract fixes, or "status only" when the counter's order is private. The
 * `expect` pointer is a properly typed array, or NULL with expect_count 0.
 */
static void run_case(const char *case_id, const char *what,
                     const unsigned char *data, uint64_t data_size,
                     uint64_t tail, uint64_t head, uint64_t record_limit,
                     uint64_t head_after,
                     perf_parse_status expected, bool expect_ok,
                     const counter_expect *expect, size_t expect_count)
{
    unsigned char cpu_seen[8];
    perf_parse_summary summary;
    bool ok = perf_ring_parse(data, data_size, tail, head, record_limit,
                              TEST_PID, TEST_TID, head_after, cpu_seen,
                              sizeof cpu_seen, &summary);
    int passed = (ok == expect_ok) && (summary.status == expected);
    int counter_failed = 0;

    if (passed && expect != NULL) {
        for (size_t i = 0; i < expect_count; i++) {
            uint64_t got = counter_value(&summary, expect[i].id);
            if (got != expect[i].want) {
                passed = 0;
                counter_failed = 1;
                snprintf(detail_buffer, sizeof detail_buffer,
                         "counter %d expected=%" PRIu64 " observed=%" PRIu64 " (status=%s)",
                         (int)expect[i].id, expect[i].want, got,
                         status_name_or_unknown(summary.status));
                break;
            }
        }
    }
    if (passed) {
        snprintf(detail_buffer, sizeof detail_buffer, "status=%s records=%" PRIu64,
                 status_name_or_unknown(expected), summary.records);
    } else if (!counter_failed) {
        snprintf(detail_buffer, sizeof detail_buffer,
                 "expected=%s observed=%s(%d) problem=\"%s\"",
                 status_name_or_unknown(expected), status_name_or_unknown(summary.status),
                 (int)summary.status, summary.first_problem);
    }
    report(case_id, what, passed);
}

int main(void)
{
    unsigned char ring[256];
    unsigned char records[8][64];

    /* A: the first record straddles the end of the data area. In perf terms only
     *    the ADDRESS wraps: tail = 240, that record is 32 bytes, the next is 32
     *    bytes, so head = 304 (monotonic), NOT 304 % 256. */
    {
        uint64_t len0 = make_switch_default(records[0], MISC_SWITCH_OUT, 1000, 3);
        uint64_t len1 = make_switch_default(records[1], 0, 2000, 3);
        uint64_t tail = 240;
        uint64_t head = tail + len0 + len1;                 /* 304, monotonic */
        memset(ring, 0, sizeof ring);
        ring_store(ring, sizeof ring, tail, records[0], len0);   /* bytes 240..271 */
        ring_store(ring, sizeof ring, tail + len0, records[1], len1);
        const counter_expect expect[] = {
            {C_RECORDS, 2}, {C_SWITCH_RECORDS, 2}, {C_SWITCH_OUT, 1}, {C_SWITCH_IN, 1},
            {C_DOUBLE_OUT, 0}, {C_DOUBLE_IN, 0}, {C_TRAILING_OUT, 0},
            {C_TIME_REGRESSIONS, 0}, {C_CPUS_SEEN, 1},
        };
        run_case("A", "record straddles data-area end; head stays monotonic",
                 ring, sizeof ring, tail, head, 8, head, PERF_PARSE_OK, true,
                 expect, sizeof expect / sizeof expect[0]);
    }

    /* B: two out/in pairs in a row must both be accepted. */
    {
        uint64_t len[4];
        len[0] = make_switch_default(records[0], MISC_SWITCH_OUT, 1000, 1);
        len[1] = make_switch_default(records[1], 0, 2000, 1);
        len[2] = make_switch_default(records[2], MISC_SWITCH_OUT, 3000, 2);
        len[3] = make_switch_default(records[3], 0, 4000, 2);
        const unsigned char *ptrs[4] = {records[0], records[1], records[2], records[3]};
        uint64_t head = compose(ring, sizeof ring, ptrs, len, 4);
        const counter_expect expect[] = {
            {C_RECORDS, 4}, {C_SWITCH_RECORDS, 4}, {C_SWITCH_OUT, 2}, {C_SWITCH_IN, 2},
            {C_DOUBLE_OUT, 0}, {C_DOUBLE_IN, 0}, {C_TRAILING_OUT, 0},
            {C_TIME_REGRESSIONS, 0}, {C_CPUS_SEEN, 2},
        };
        run_case("B", "two legal out/in pairs", ring, sizeof ring, 0, head, 8, head,
                 PERF_PARSE_OK, true, expect, sizeof expect / sizeof expect[0]);
    }

    /* C: out,out must be rejected; the second out has no outstanding in. */
    {
        uint64_t len[2];
        len[0] = make_switch_default(records[0], MISC_SWITCH_OUT, 1000, 1);
        len[1] = make_switch_default(records[1], MISC_SWITCH_OUT, 2000, 1);
        const unsigned char *ptrs[2] = {records[0], records[1]};
        uint64_t head = compose(ring, sizeof ring, ptrs, len, 2);
        const counter_expect expect[] = {
            {C_SWITCH_OUT, 2}, {C_SWITCH_IN, 0}, {C_DOUBLE_OUT, 1}, {C_TRAILING_OUT, 1},
        };
        run_case("C", "double out is rejected", ring, sizeof ring, 0, head, 8, head,
                 PERF_PARSE_INCOMPLETE_PAIR, false, expect, sizeof expect / sizeof expect[0]);
    }

    /* D: a leading in with no outstanding out must be rejected. */
    {
        uint64_t len[1];
        len[0] = make_switch_default(records[0], 0, 1000, 1);
        const unsigned char *ptrs[1] = {records[0]};
        uint64_t head = compose(ring, sizeof ring, ptrs, len, 1);
        const counter_expect expect[] = {
            {C_SWITCH_OUT, 0}, {C_SWITCH_IN, 1}, {C_DOUBLE_IN, 1},
        };
        run_case("D", "leading in without out is rejected", ring, sizeof ring, 0, head, 8, head,
                 PERF_PARSE_INCOMPLETE_PAIR, false, expect, sizeof expect / sizeof expect[0]);
    }

    /* E: a genuine interior regression: out(1000) -> in(2000) -> out(1500) ->
     *    in(3000). The pair is balanced, the span 1000..3000 is positive and the
     *    last record is an in, so only the interior 2000 -> 1500 step can fail. */
    {
        uint64_t len[4];
        len[0] = make_switch_default(records[0], MISC_SWITCH_OUT, 1000, 1);
        len[1] = make_switch_default(records[1], 0, 2000, 1);
        len[2] = make_switch_default(records[2], MISC_SWITCH_OUT, 1500, 1);
        len[3] = make_switch_default(records[3], 0, 3000, 1);
        const unsigned char *ptrs[4] = {records[0], records[1], records[2], records[3]};
        uint64_t head = compose(ring, sizeof ring, ptrs, len, 4);
        const counter_expect expect[] = {
            {C_SWITCH_OUT, 2}, {C_SWITCH_IN, 2}, {C_TRAILING_OUT, 0},
            {C_TIME_REGRESSIONS, 1},
        };
        run_case("E", "interior time regression inside a balanced pair",
                 ring, sizeof ring, 0, head, 8, head,
                 PERF_PARSE_TIME_REGRESSION, false, expect, sizeof expect / sizeof expect[0]);
    }

    /* F: PERF_RECORD_SWITCH_CPU_WIDE is counted but never usable. */
    {
        uint64_t len[2];
        len[0] = make_switch_default(records[0], MISC_SWITCH_OUT, 1000, 1);
        len[1] = make_cpu_wide(records[1], 0, 2000, 1, TEST_PID, TEST_TID);
        const unsigned char *ptrs[2] = {records[0], records[1]};
        uint64_t head = compose(ring, sizeof ring, ptrs, len, 2);
        const counter_expect expect[] = {
            {C_CPU_WIDE, 1}, {C_SWITCH_RECORDS, 1}, {C_SWITCH_OUT, 1}, {C_SWITCH_IN, 0},
        };
        run_case("F", "CPU_WIDE record is counted and rejected", ring, sizeof ring, 0, head, 8,
                 head, PERF_PARSE_CPU_WIDE_RECORD, false, expect, sizeof expect / sizeof expect[0]);
    }

    /* G: a switch record for another tid is foreign even with a valid out first. */
    {
        uint64_t len[2];
        len[0] = make_switch_default(records[0], MISC_SWITCH_OUT, 1000, 1);
        len[1] = make_switch(records[1], 0, 2000, 1, TEST_PID, (int32_t)(TEST_TID + 1));
        const unsigned char *ptrs[2] = {records[0], records[1]};
        uint64_t head = compose(ring, sizeof ring, ptrs, len, 2);
        const counter_expect expect[] = {
            {C_FOREIGN, 1}, {C_SWITCH_OUT, 1}, {C_SWITCH_IN, 0}, {C_TRAILING_OUT, 1},
        };
        run_case("G", "foreign tid switch record is rejected", ring, sizeof ring, 0, head, 8,
                 head, PERF_PARSE_FOREIGN_THREAD, false, expect, sizeof expect / sizeof expect[0]);
    }

    /* H: PERF_RECORD_LOST with id != lost, so the reported count must be the
     *    SECOND u64 after the header (offset 16). A parser that used the first
     *    would report 7 and cannot pass. */
    {
        uint64_t len[1];
        len[0] = make_lost(records[0], 7u, 2093u);
        const unsigned char *ptrs[1] = {records[0]};
        uint64_t head = compose(ring, sizeof ring, ptrs, len, 1);
        const counter_expect expect[] = {
            {C_LOST_RECORDS, 1}, {C_LOST_EVENTS, 2093}, {C_LOST_SAMPLES_RECORDS, 0},
        };
        run_case("H", "LOST: lost@offset16=2093, id=7 differs", ring, sizeof ring, 0, head, 8,
                 head, PERF_PARSE_LOST, false, expect, sizeof expect / sizeof expect[0]);
    }

    /* H2: PERF_RECORD_LOST_SAMPLES is its own branch with {u64 lost}@+8 and its own
     *     status. Counter order on this private path is not asserted. */
    {
        uint64_t len[1];
        len[0] = make_lost_samples(records[0], 5u);
        const unsigned char *ptrs[1] = {records[0]};
        uint64_t head = compose(ring, sizeof ring, ptrs, len, 1);
        const counter_expect expect[] = {
            {C_LOST_SAMPLES_RECORDS, 1}, {C_LOST_RECORDS, 0}, {C_LOST_EVENTS, 5},
        };
        run_case("H2", "LOST_SAMPLES: lost@offset8=5 has its own status",
                 ring, sizeof ring, 0, head, 8, head,
                 PERF_PARSE_LOST_SAMPLES, false, expect, sizeof expect / sizeof expect[0]);
    }

    /* I: the record's declared size runs past head, so the record is not fully
     *    read. Status is the public fact; whether a partially read record has
     *    already been counted is private, so no counter is asserted here. */
    {
        uint64_t len[1];
        len[0] = make_switch_default(records[0], MISC_SWITCH_OUT, 1000, 1);
        store_u16(records[0] + 6, 64);          /* declare 64 bytes, only 32 present */
        const unsigned char *ptrs[1] = {records[0]};
        uint64_t head = compose(ring, sizeof ring, ptrs, len, 1);
        run_case("I", "record size beyond head is truncated", ring, sizeof ring, 0, head, 8,
                 head, PERF_PARSE_TRUNCATED, false, NULL, 0);
    }

    /* J: an empty ring (tail == head) holds no switch record. */
    {
        memset(ring, 0, sizeof ring);
        const counter_expect expect[] = {
            {C_SWITCH_RECORDS, 0}, {C_CPU_WIDE, 0},
        };
        run_case("J", "empty ring reports no switch record", ring, sizeof ring, 0, 0, 8, 0,
                 PERF_PARSE_NO_SWITCH, false, expect, sizeof expect / sizeof expect[0]);
    }

    /* K: an unknown record type is rejected, not skipped. */
    {
        uint64_t len[1];
        len[0] = make_unknown(records[0]);
        const unsigned char *ptrs[1] = {records[0]};
        uint64_t head = compose(ring, sizeof ring, ptrs, len, 1);
        const counter_expect expect[] = {
            {C_UNKNOWN, 1}, {C_SWITCH_RECORDS, 0},
        };
        run_case("K", "unknown record type is rejected", ring, sizeof ring, 0, head, 8, head,
                 PERF_PARSE_UNKNOWN_RECORD, false, expect, sizeof expect / sizeof expect[0]);
    }

    /* L (extra): a trailing out with no closing in, positive window. */
    {
        uint64_t len[3];
        len[0] = make_switch_default(records[0], MISC_SWITCH_OUT, 1000, 1);
        len[1] = make_switch_default(records[1], 0, 2000, 1);
        len[2] = make_switch_default(records[2], MISC_SWITCH_OUT, 3000, 1);
        const unsigned char *ptrs[3] = {records[0], records[1], records[2]};
        uint64_t head = compose(ring, sizeof ring, ptrs, len, 3);
        const counter_expect expect[] = {
            {C_SWITCH_OUT, 2}, {C_SWITCH_IN, 1}, {C_TRAILING_OUT, 1},
        };
        run_case("L", "trailing out with no closing in", ring, sizeof ring, 0, head, 8, head,
                 PERF_PARSE_INCOMPLETE_PAIR, false, expect, sizeof expect / sizeof expect[0]);
    }

    printf("\n%d cases, %d failed\n", cases, failures);
    return failures == 0 ? 0 : 1;
}
