/*
 * perf_self_capability_selftest.c -- synthetic negative tests for the ring parser.
 *
 * Buildable and runnable by main without any perf event, ring mapping, sleep or native
 * activity: every case writes records into an in-memory buffer and calls
 * perf_ring_parse directly. Each case names the real failure condition it pins.
 *
 *   cc -std=c11 -O2 -Wall -Wextra -Werror -o /tmp/perf_self_capability_selftest \
 *      perf_self_capability_selftest.c perf_ring_parse.c
 *
 * Exit 0 when every expectation holds.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <linux/perf_event.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "perf_ring_parse.h"

#define SYNTH_SELF_PID 4001
#define SYNTH_SELF_TID 4001
#define SYNTH_FOREIGN_TID 4002
#define SYNTH_RING_BYTES 1024u
#define SYNTH_TIME_BASE 1000000ull
#define SYNTH_TIME_STEP 5000ull
#define MISC_SWITCH_OUT (1u << 13)

static unsigned char g_ring[SYNTH_RING_BYTES];
static uint64_t g_used;
static uint64_t g_time_cursor;
static int g_failures;
static int g_checks;

static void reset_ring(void)
{
    memset(g_ring, 0, sizeof g_ring);
    g_used = 0;
    g_time_cursor = SYNTH_TIME_BASE;
}

/* Write { u32 pid, tid; u64 time; u32 cpu, res; } at the sample_id position. */
static void put_sample_id(unsigned char *out, int32_t pid, int32_t tid, uint64_t time_ns,
                          uint32_t cpu)
{
    uint32_t reserved = 0;
    memcpy(out, &pid, 4);
    memcpy(out + 4, &tid, 4);
    memcpy(out + 8, &time_ns, 8);
    memcpy(out + 16, &cpu, 4);
    memcpy(out + 20, &reserved, 4);
}

static void append_header(uint32_t type, uint16_t misc, uint16_t size)
{
    struct perf_event_header header;
    header.type = type;
    header.misc = misc;
    header.size = size;
    memcpy(g_ring + g_used, &header, sizeof header);
    g_used += sizeof header;
}

/* PERF_RECORD_SWITCH: header + sample_id (24 bytes) = 32 bytes. */
static uint64_t append_switch(uint16_t misc, int32_t pid, int32_t tid, uint64_t time_ns)
{
    uint64_t start = g_used;
    append_header(PERF_RECORD_SWITCH, misc, (uint16_t)(sizeof(struct perf_event_header) + 24));
    put_sample_id(g_ring + g_used, pid, tid, time_ns, 3);
    g_used += 24;
    return start;
}

static uint64_t append_switch_stamped(uint16_t misc, int32_t pid, int32_t tid)
{
    g_time_cursor += SYNTH_TIME_STEP;
    return append_switch(misc, pid, tid, g_time_cursor);
}

/* PERF_RECORD_SWITCH_CPU_WIDE: header + next_prev_pid/tid + sample_id = 40 bytes. */
static void append_cpu_wide(int32_t pid, int32_t tid)
{
    append_header(PERF_RECORD_SWITCH_CPU_WIDE, 0,
                  (uint16_t)(sizeof(struct perf_event_header) + 8 + 24));
    int32_t next_prev_pid = 77, next_prev_tid = 78;
    memcpy(g_ring + g_used, &next_prev_pid, 4);
    memcpy(g_ring + g_used + 4, &next_prev_tid, 4);
    g_used += 8;
    g_time_cursor += SYNTH_TIME_STEP;
    put_sample_id(g_ring + g_used, pid, tid, g_time_cursor, 3);
    g_used += 24;
}

/* PERF_RECORD_LOST: header + { u64 id; u64 lost; } = 28 bytes. */
static uint64_t append_lost(uint64_t id, uint64_t lost)
{
    uint64_t start = g_used;
    append_header(PERF_RECORD_LOST, 0, (uint16_t)(sizeof(struct perf_event_header) + 16));
    memcpy(g_ring + g_used, &id, 8);
    memcpy(g_ring + g_used + 8, &lost, 8);
    g_used += 16;
    return start;
}

/* PERF_RECORD_LOST_SAMPLES: header + { u64 lost; } = 20 bytes. */
static uint64_t append_lost_samples(uint64_t lost)
{
    uint64_t start = g_used;
    append_header(PERF_RECORD_LOST_SAMPLES, 0,
                  (uint16_t)(sizeof(struct perf_event_header) + 8));
    memcpy(g_ring + g_used, &lost, 8);
    g_used += 8;
    return start;
}

static uint64_t append_unknown(uint32_t type, uint32_t payload_bytes)
{
    uint64_t start = g_used;
    uint32_t total = (uint32_t)sizeof(struct perf_event_header) + payload_bytes;
    append_header(type, 0, (uint16_t)total);
    for (uint32_t index = 0; index < payload_bytes; index++) {
        g_ring[g_used + index] = 0xAB;
    }
    g_used += payload_bytes;
    return start;
}

static void damage_size(uint64_t record_start, uint16_t size)
{
    memcpy(g_ring + record_start + 6, &size, 2);   /* header.size is the third u16 */
}

static perf_parse_summary run_parse(uint64_t tail, uint64_t head, uint64_t head_after,
                                    uint64_t record_limit)
{
    perf_parse_summary summary;
    unsigned char cpu_seen[256];
    perf_ring_parse(g_ring, SYNTH_RING_BYTES, tail, head, record_limit, SYNTH_SELF_PID,
                    SYNTH_SELF_TID, head_after, cpu_seen, sizeof cpu_seen, &summary);
    return summary;
}

static void check(const char *name, bool condition, const char *detail)
{
    g_checks++;
    if (condition) {
        printf("  ok    %-34s %s\n", name, detail);
    } else {
        g_failures++;
        printf("  FAIL  %-34s %s\n", name, detail);
    }
}

static void case_clean_pair_is_accepted(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("clean_out_in_pair", summary.ok && summary.status == PERF_PARSE_OK,
          perf_parse_status_name(summary.status));
    check("clean_pair_counts", summary.switch_records == 2 && summary.switch_out == 1
              && summary.switch_in == 1 && summary.double_out == 0
              && summary.double_in == 0 && summary.trailing_out == 0,
          "out=1 in=1");
}

static void case_accepts_two_clean_pairs_in_alternation(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped((uint16_t)(MISC_SWITCH_OUT | (1u << 14)), SYNTH_SELF_PID,
                          SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("two_alternating_pairs_ok", summary.ok && summary.switch_out == 2
              && summary.switch_in == 2 && summary.preempt_out == 1
              && summary.double_out == 0 && summary.double_in == 0,
          perf_parse_status_name(summary.status));
}

static void case_rejects_double_out_then_double_in(void)
{
    /* out, out, in, in: both counts are positive and equal, so a counter-based check
     * would have passed it; the alternation state machine must not. */
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("double_out_then_double_in_fails", !summary.ok
              && summary.status == PERF_PARSE_INCOMPLETE_PAIR
              && summary.double_out == 1 && summary.double_in == 1,
          perf_parse_status_name(summary.status));
}

static void case_rejects_trailing_out(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("trailing_out_fails", !summary.ok
              && summary.status == PERF_PARSE_INCOMPLETE_PAIR
              && summary.trailing_out == 1,
          perf_parse_status_name(summary.status));
}

static void case_rejects_interior_time_regression(void)
{
    /* the first and last timestamps still span forward, so a first/last-only check
     * would pass while the middle record goes backwards */
    reset_ring();
    append_switch(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID, 1000);
    append_switch(0, SYNTH_SELF_PID, SYNTH_SELF_TID, 900);          /* backwards */
    append_switch(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID, 5000);
    append_switch(0, SYNTH_SELF_PID, SYNTH_SELF_TID, 6000);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("interior_time_regression_fails", !summary.ok
              && summary.status == PERF_PARSE_TIME_REGRESSION
              && summary.time_regressions == 1,
          perf_parse_status_name(summary.status));
}

static void case_rejects_equal_interior_time(void)
{
    reset_ring();
    append_switch(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID, 1000);
    append_switch(0, SYNTH_SELF_PID, SYNTH_SELF_TID, 1000);         /* not advancing */
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("non_advancing_time_fails", !summary.ok
              && summary.status == PERF_PARSE_TIME_REGRESSION,
          perf_parse_status_name(summary.status));
}

static void case_rejects_preempt_flag_on_in(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped((uint16_t)(1u << 14), SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("preempt_on_in_fails", !summary.ok
              && summary.status == PERF_PARSE_MALFORMED,
          perf_parse_status_name(summary.status));
}

static void case_rejects_wrong_switch_size(void)
{
    /* With the fixed sample_type, 32 bytes is the only legal switch record size, so a
     * 40-byte record is malformed. The header now claims a different length, so the
     * stream cannot be resynchronised: the parse stops at that record and reports why. */
    reset_ring();
    uint64_t start = append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID,
                                           SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    damage_size(start, 40);     /* that is the cpu-wide size, not this record's */
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("wrong_switch_size_fails", !summary.ok
              && summary.status == PERF_PARSE_MALFORMED
              && summary.malformed >= 1 && summary.records == 1,
          perf_parse_status_name(summary.status));
}

static void case_tolerates_null_summary(void)
{
    /* a NULL summary must not be dereferenced: no crash, just false */
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    bool returned = perf_ring_parse(g_ring, SYNTH_RING_BYTES, 0, g_used, 4096,
                                    SYNTH_SELF_PID, SYNTH_SELF_TID, g_used, NULL, 0,
                                    NULL);
    check("null_summary_no_crash", !returned, "returned false without dereferencing");
}

static void case_rejects_trailing_bytes(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used + 4, g_used + 4, 4096);
    check("leftover_bytes_fail", !summary.ok && summary.status == PERF_PARSE_TRUNCATED,
          perf_parse_status_name(summary.status));
}

static void case_rejects_single_record(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("single_record_fails", !summary.ok && summary.status == PERF_PARSE_INCOMPLETE_PAIR,
          perf_parse_status_name(summary.status));
}

static void case_rejects_in_without_out(void)
{
    reset_ring();
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("in_without_out_fails", !summary.ok
              && summary.status == PERF_PARSE_INCOMPLETE_PAIR,
          perf_parse_status_name(summary.status));
}

static void case_rejects_unbalanced_with_both_kinds_present(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("unbalanced_pair_fails", !summary.ok
              && summary.status == PERF_PARSE_INCOMPLETE_PAIR,
          perf_parse_status_name(summary.status));
}

static void case_rejects_foreign_tid(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_FOREIGN_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("foreign_tid_fails", !summary.ok
              && summary.status == PERF_PARSE_FOREIGN_THREAD
              && summary.foreign_records == 1,
          perf_parse_status_name(summary.status));
}

static void case_rejects_foreign_pid(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID + 1, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID + 1, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("foreign_pid_fails", !summary.ok
              && summary.status == PERF_PARSE_FOREIGN_THREAD,
          perf_parse_status_name(summary.status));
}

static void case_rejects_zero_identity(void)
{
    /* A record whose sample_id carries no identity is malformed regardless of the
     * reader, so it is classified as missing_identity and never as another thread's
     * traffic (pid 0 merely differs from the caller's pid). */
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, 0, 0);
    append_switch_stamped(0, 0, 0);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("zero_identity_fails", !summary.ok
              && summary.status == PERF_PARSE_MALFORMED
              && summary.missing_identity == 2 && summary.foreign_records == 0,
          perf_parse_status_name(summary.status));
}

static void case_rejects_partial_zero_identity(void)
{
    /* only one half of the identity is zero: the same rule applies */
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, 0);
    append_switch_stamped(0, SYNTH_SELF_PID, 0);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("partial_zero_identity_fails", !summary.ok
              && summary.status == PERF_PARSE_MALFORMED
              && summary.missing_identity == 2 && summary.foreign_records == 0,
          perf_parse_status_name(summary.status));
}

static void case_rejects_cpu_wide(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_cpu_wide(SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("cpu_wide_fails", !summary.ok
              && summary.status == PERF_PARSE_CPU_WIDE_RECORD
              && summary.switch_cpu_wide_records == 1,
          perf_parse_status_name(summary.status));
}

static void case_rejects_unknown_record(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_unknown(99, 8);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("unknown_record_fails", !summary.ok
              && summary.status == PERF_PARSE_UNKNOWN_RECORD
              && summary.unknown_records == 1,
          perf_parse_status_name(summary.status));
}

static void case_reads_the_second_u64_of_lost(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_lost(0xDEADBEEFull, 7u);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("lost_reads_second_u64", !summary.ok && summary.status == PERF_PARSE_LOST
              && summary.lost_events == 7,
          "lost=7 (not the id 0xDEADBEEF)");
}

static void case_rejects_lost_samples_separately(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_lost_samples(5u);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("lost_samples_fails", !summary.ok
              && summary.status == PERF_PARSE_LOST_SAMPLES && summary.lost_events == 5,
          perf_parse_status_name(summary.status));
}

static void case_rejects_truncated_record(void)
{
    reset_ring();
    uint64_t start = append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    damage_size(start, 4096);   /* larger than the ring: the record cannot fit */
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("oversized_record_fails", !summary.ok && summary.malformed == 1,
          perf_parse_status_name(summary.status));
}

static void case_rejects_misaligned_or_tiny_record(void)
{
    reset_ring();
    uint64_t start = append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    damage_size(start, 33);     /* not 8-byte aligned */
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("misaligned_size_fails", !summary.ok && summary.malformed == 1,
          perf_parse_status_name(summary.status));

    reset_ring();
    start = append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    damage_size(start, 8);      /* smaller than a switch record needs */
    summary = run_parse(0, g_used, g_used, 4096);
    check("undersized_switch_fails", !summary.ok
              && summary.status == PERF_PARSE_MALFORMED && summary.malformed >= 1,
          perf_parse_status_name(summary.status));
}

static void case_rejects_record_limit(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 1);
    check("record_limit_fails", !summary.ok
              && summary.status == PERF_PARSE_RECORD_LIMIT,
          perf_parse_status_name(summary.status));
}

static void case_rejects_moving_head(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    append_switch_stamped(0, SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(0, g_used, g_used + 8, 4096);
    check("moving_head_fails", !summary.ok && summary.status == PERF_PARSE_HEAD_MOVED,
          perf_parse_status_name(summary.status));
}

static void case_rejects_no_window(void)
{
    /* Two accepted records can never leave a non-positive span: the per-record check
     * rejects the non-advancing second timestamp first, so time_regression is the
     * observable reason here. PERF_PARSE_NO_WINDOW stays as a defensive backstop for a
     * single accepted record (which the pairing check also rejects). */
    reset_ring();
    append_switch(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID, 5000);
    append_switch(0, SYNTH_SELF_PID, SYNTH_SELF_TID, 5000);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("zero_time_span_fails", !summary.ok
              && summary.status == PERF_PARSE_TIME_REGRESSION
              && summary.time_regressions == 1,
          perf_parse_status_name(summary.status));
}

static void case_rejects_no_switch(void)
{
    reset_ring();
    append_unknown(1, 8);
    perf_parse_summary summary = run_parse(0, g_used, g_used, 4096);
    check("no_switch_fails", !summary.ok && summary.switch_records == 0,
          perf_parse_status_name(summary.status));
}

static void case_rejects_empty_ring(void)
{
    reset_ring();
    perf_parse_summary summary = run_parse(0, 0, 0, 4096);
    check("empty_ring_fails", !summary.ok && summary.status == PERF_PARSE_NO_SWITCH,
          perf_parse_status_name(summary.status));
}

static void case_rejects_unusable_ring(void)
{
    reset_ring();
    append_switch_stamped(MISC_SWITCH_OUT, SYNTH_SELF_PID, SYNTH_SELF_TID);
    perf_parse_summary summary = run_parse(SYNTH_RING_BYTES + 64, 64, 64, 4096);
    check("head_tail_overrun_fails", !summary.ok
              && summary.status == PERF_PARSE_RING_UNUSABLE,
          perf_parse_status_name(summary.status));
}

static void case_rejects_non_power_of_two_ring(void)
{
    perf_parse_summary summary;
    unsigned char cpu_seen[256];
    perf_ring_parse(g_ring, 1000, 0, 0, 4096, SYNTH_SELF_PID, SYNTH_SELF_TID, 0,
                    cpu_seen, sizeof cpu_seen, &summary);
    check("non_power_of_two_fails", !summary.ok
              && summary.status == PERF_PARSE_BAD_ARGUMENT,
          perf_parse_status_name(summary.status));
}

int main(void)
{
    printf("perf_ring_parse synthetic self-test (%d bytes of ring, no perf event)\n",
           (int)SYNTH_RING_BYTES);
    case_clean_pair_is_accepted();
    case_accepts_two_clean_pairs_in_alternation();
    case_rejects_double_out_then_double_in();
    case_rejects_trailing_out();
    case_rejects_interior_time_regression();
    case_rejects_equal_interior_time();
    case_rejects_preempt_flag_on_in();
    case_rejects_wrong_switch_size();
    case_tolerates_null_summary();
    case_rejects_trailing_bytes();
    case_rejects_single_record();
    case_rejects_in_without_out();
    case_rejects_unbalanced_with_both_kinds_present();
    case_rejects_foreign_tid();
    case_rejects_foreign_pid();
    case_rejects_zero_identity();
    case_rejects_partial_zero_identity();
    case_rejects_cpu_wide();
    case_rejects_unknown_record();
    case_reads_the_second_u64_of_lost();
    case_rejects_lost_samples_separately();
    case_rejects_truncated_record();
    case_rejects_misaligned_or_tiny_record();
    case_rejects_record_limit();
    case_rejects_moving_head();
    case_rejects_no_window();
    case_rejects_no_switch();
    case_rejects_empty_ring();
    case_rejects_unusable_ring();
    case_rejects_non_power_of_two_ring();
    printf("%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
