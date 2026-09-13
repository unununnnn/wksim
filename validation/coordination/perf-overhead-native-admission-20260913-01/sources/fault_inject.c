/*
 * fault_inject.c -- optional link-time fault injection for bench_overhead.c.
 *
 * This file is NOT part of the delivered measurement path and is never linked into a
 * normal run. Main compiles it only for fault cases:
 *
 *   cc -std=c11 -O2 -Wall -Wextra -Werror -pthread -I <recorder-dir> \
 *      -o bench-fault bench_overhead.c fault_inject.c -L <private-lib-dir> \
 *      -Wl,-rpath,<private-lib-dir> -lwksim_perf_stream \
 *      -Wl,--wrap=clock_gettime -Wl,--wrap=getrusage -Wl,--wrap=fclose \
 *      -Wl,--wrap=wksim_perf_stop
 *
 * The recorder is deliberately a shared library in the fault build. Therefore --wrap only
 * intercepts the benchmark object's calls; the recorder reader thread keeps using libc and
 * cannot race the benchmark-only call counters below.
 *
 * Behaviour is selected by environment variables; with none set every wrapper forwards to
 * the real function unchanged, so the fault binary is byte-comparable to the normal one:
 *
 *   WKSIM_FI_CLOCK_FAIL_AT=N   the Nth benchmark clock_gettime call returns -1/EINVAL.
 *                              Call 1 measures start_begin before start; call 2 measures
 *                              start_end after start; call 3 obtains t0 before the loop.
 *   WKSIM_FI_GETRUSAGE_FAIL_AT=N  the Nth benchmark getrusage call returns -1/EINVAL. Calls
 *                              1/2 are baseline SELF/THREAD; calls 3/4 are closing SELF/THREAD.
 *   WKSIM_FI_GETRUSAGE_FAIL_WHO=thread|process|any  which scope of that call must fail
 *                              (default any). "process" fails RUSAGE_SELF only.
 *   WKSIM_FI_FCLOSE_FAIL_AT=N  the Nth wrapped fclose really closes the stream, then reports
 *                              EOF. With this set every close index is logged, proving the
 *                              other close still executes while the run fails.
 *   WKSIM_FI_STOP_REPORT_FAILURE=1  call the real successful stop, then report -1 with the
 *                              handle already consumed. This isolates finding 1.
 *   WKSIM_FI_TRACE_STOP=1      log that the benchmark reached the stop wrapper.
 *
 * Expected outcomes (Main runs these; the owner of this file claims no native result):
 *   - any injected failure  -> exit status non-zero;
 *   - after-start clock or getrusage injection -> the stop trace is present and no result.json
 *     or timing.csv is accepted as a complete run;
 *   - fclose failure -> the process reports outputs not accepted and exits non-zero;
 *   - the un-injected fault binary still produces the same exit status 0 and the same two
 *     files as the normal binary.
 */
#define _GNU_SOURCE
#include "wksim_perf_stream.h"
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

int __real_clock_gettime(clockid_t clock_id, struct timespec *value);
int __real_getrusage(int who, struct rusage *usage);
int __real_fclose(FILE *stream);
int __real_wksim_perf_stop(void **handle, const char *raw_path, const char *metadata_path);

static unsigned long call_index(bool is_clock, bool is_rusage)
{
    static unsigned long clock_calls, rusage_calls, fclose_calls;
    if (is_clock) {
        return ++clock_calls;
    }
    if (is_rusage) {
        return ++rusage_calls;
    }
    return ++fclose_calls;
}

static unsigned long fail_at(const char *env)
{
    const char *text = getenv(env);
    if (text == NULL || text[0] == '\0') {
        return 0;
    }
    char *end = NULL;
    unsigned long value = strtoul(text, &end, 10);
    return (end != text && *end == '\0') ? value : 0;
}

int __wrap_clock_gettime(clockid_t clock_id, struct timespec *value)
{
    const unsigned long index = call_index(true, false);
    if (index == fail_at("WKSIM_FI_CLOCK_FAIL_AT")) {
        fprintf(stderr, "fault_inject: clock_gettime call %lu fails by request\n", index);
        errno = EINVAL;
        return -1;
    }
    return __real_clock_gettime(clock_id, value);
}

int __wrap_getrusage(int who, struct rusage *usage)
{
    const unsigned long index = call_index(false, true);
    const unsigned long target = fail_at("WKSIM_FI_GETRUSAGE_FAIL_AT");
    const char *scope = getenv("WKSIM_FI_GETRUSAGE_FAIL_WHO");
    bool scope_matches = scope == NULL || scope[0] == '\0' || strcmp(scope, "any") == 0;
    if (scope != NULL && strcmp(scope, "thread") == 0) {
        scope_matches = who == RUSAGE_THREAD;
    } else if (scope != NULL && strcmp(scope, "process") == 0) {
        scope_matches = who == RUSAGE_SELF;
    }
    if (target != 0 && index == target && scope_matches) {
        fprintf(stderr, "fault_inject: getrusage(%d) call %lu fails by request\n", who, index);
        errno = EINVAL;
        return -1;
    }
    return __real_getrusage(who, usage);
}

int __wrap_fclose(FILE *stream)
{
    const unsigned long index = call_index(false, false);
    const unsigned long target = fail_at("WKSIM_FI_FCLOSE_FAIL_AT");
    if (target != 0) {
        fprintf(stderr, "fault_inject: fclose call %lu observed\n", index);
    }
    if (index == target) {
        /* Report the failure to the caller but still release the stream, so the injector
         * itself leaks neither the descriptor nor the FILE. The bench must treat the
         * reported EOF as a failed close. */
        fprintf(stderr, "fault_inject: fclose call %lu reports failure by request\n", index);
        (void)__real_fclose(stream);
        errno = EIO;
        return EOF;
    }
    return __real_fclose(stream);
}

int __wrap_wksim_perf_stop(void **handle, const char *raw_path, const char *metadata_path)
{
    if (fail_at("WKSIM_FI_TRACE_STOP") == 1) {
        fprintf(stderr, "fault_inject: wksim_perf_stop called\n");
    }
    const int rc = __real_wksim_perf_stop(handle, raw_path, metadata_path);
    if (rc == 0 && fail_at("WKSIM_FI_STOP_REPORT_FAILURE") == 1) {
        fprintf(stderr, "fault_inject: successful stop reports failure with consumed handle\n");
        errno = EIO;
        return -1;
    }
    return rc;
}
