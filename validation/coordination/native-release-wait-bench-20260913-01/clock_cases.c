#define _POSIX_C_SOURCE 199309L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static int test_clock_gettime(clockid_t id, struct timespec *sample);
#define clock_gettime test_clock_gettime
#include "native_release_wait.c"
#undef clock_gettime

struct reading { int64_t seconds; long nanoseconds; int error; };
static const struct reading *readings;
static size_t count, cursor;
static int checks;

static int test_clock_gettime(clockid_t id, struct timespec *sample) {
    if (id != CLOCK_MONOTONIC || cursor >= count) abort();
    const struct reading value = readings[cursor++];
    if (value.error) return -1;
    sample->tv_sec = (time_t)value.seconds;
    sample->tv_nsec = value.nanoseconds;
    return 0;
}

static void check(const char *label, int64_t deadline, const struct reading *values,
                  size_t length, int status, int64_t expected, size_t expected_reads) {
    int64_t observed = -123;
    readings = values; count = length; cursor = 0;
    int actual = wk_release_wait_until(deadline, &observed);
    if (actual != status || cursor != expected_reads ||
        (actual == 0 && (observed != expected || observed < deadline))) {
        fprintf(stderr, "%s: status=%d observed=%lld reads=%zu\n", label,
                actual, (long long)observed, cursor);
        exit(1);
    }
    checks++;
}

#define NS(value) {(value) / 1000000000LL, (value) % 1000000000LL, 0}
#define COUNT(array) (sizeof(array) / sizeof((array)[0]))

int main(void) {
    const struct reading past[] = {NS(100)};
    const struct reading spin[] = {NS(100), NS(100), NS(102)};
    const struct reading edge[] = {NS(0), NS(1000000)};
    const struct reading failed[] = {{0, 0, 1}};
    const struct reading later_failed[] = {NS(100), {0, 0, 1}};
    const struct reading regressed[] = {NS(100), NS(99)};
    const struct reading negative_sec[] = {{-1, 0, 0}};
    const struct reading negative_nsec[] = {{0, -1, 0}};
    const struct reading invalid_nsec[] = {{0, 1000000000L, 0}};
    const struct reading maximum[] = {NS(INT64_MAX)};
    const struct reading overflow[] = {{INT64_MAX / 1000000000LL,
                                        INT64_MAX % 1000000000LL + 1, 0}};
    const struct reading overflow_sec[] = {{INT64_MAX / 1000000000LL + 1, 0, 0}};
    check("negative deadline", -1, NULL, 0, 1, 0, 0);
    readings = NULL; count = cursor = 0;
    if (wk_release_wait_until(0, NULL) != 1 || cursor != 0) return 1;
    checks++;
    check("past", 99, past, COUNT(past), 0, 100, 1);
    check("exact", 100, past, COUNT(past), 0, 100, 1);
    check("spin and equal sample", 101, spin, COUNT(spin), 0, 102, 3);
    check("exact 1ms entry", 1000000, edge, COUNT(edge), 0, 1000000, 2);
    check("beyond entry cap", 1000101, past, COUNT(past), 4, 0, 1);
    check("initial clock failure", 1, failed, COUNT(failed), 2, 0, 1);
    check("later clock failure", 101, later_failed, COUNT(later_failed), 2, 0, 2);
    check("clock regression", 101, regressed, COUNT(regressed), 3, 0, 2);
    check("negative seconds", 1, negative_sec, COUNT(negative_sec), 2, 0, 1);
    check("negative nanoseconds", 1, negative_nsec, COUNT(negative_nsec), 2, 0, 1);
    check("invalid nanoseconds", 1, invalid_nsec, COUNT(invalid_nsec), 2, 0, 1);
    check("int64 maximum", INT64_MAX, maximum, COUNT(maximum), 0, INT64_MAX, 1);
    check("overflow nanoseconds", INT64_MAX, overflow, COUNT(overflow), 2, 0, 1);
    check("overflow seconds", INT64_MAX, overflow_sec, COUNT(overflow_sec), 2, 0, 1);
    printf("{\"status\":\"passed\",\"checks\":%d,\"scope\":\"compiled C with controlled clock; no performance claim\"}\n", checks);
    return 0;
}
