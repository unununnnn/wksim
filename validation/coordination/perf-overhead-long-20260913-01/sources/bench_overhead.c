/*
 * wksim_perf_overhead_bench.c -- minimal paired self-thread recorder overhead driver.
 *
 * One process = one row. The synthetic pacing loop reproduces the group-release
 * arithmetic of Simulator/wksim_runtime/joint_rate.py begin_group():
 *     ideal[k]    = start_ns + k * period_ns              (the requested schedule)
 *     earliest[k] = max(ideal[k], actual_start[k-1] + period_ns)
 *     actual[k]   = when the loop actually reaches earliest[k]
 * `earliest` is what forbids catch-up: a late group cannot release sooner than one full
 * period after the previous group actually started, so oversleep is never repaid and the
 * requested schedule never shifts. The real runner's health callback, 4-tick grouping,
 * rate changes and latency latches are NOT implemented here. The identical body and
 * schedule run in both modes; only whether the recorder module is started and stopped
 * around the loop differs. No scheduler, affinity, sysctl, rlimit, frequency, model,
 * controller or firmware code is touched.
 *
 * Outputs, created exclusively (the directory must already exist and be empty):
 *   <dir>/result.json   concise summary, written only after the capture ended
 *   <dir>/timing.csv    one row per iteration in ORIGINAL order, never sorted:
 *                       index,ideal_start_ns,earliest_start_ns,actual_start_ns,end_ns
 * Percentiles, deltas and deadline accounting are computed offline; this program emits no
 * threshold, no verdict and no percentile. Claim limit: a synthetic pacing loop is not the
 * simulator, not a controller and not a flight, and says nothing about true whole-flight
 * overhead even at a real rate window's duration and period. Native status: unverified;
 * this source has not been compiled or run in this checkout.
 *
 * Failure handling is fail-closed and single-exit: once the recorder has been started, every
 * later failure (clock, getrusage, sleep, recorder return code, retained ownership) is
 * recorded by name and then leaves through the same owner-thread wksim_perf_stop call before
 * any file is written, so a live handle is never abandoned by an early return. A nonzero
 * start or stop code always yields a non-zero exit status. The recorder API, ownership rule
 * and error checks are preserved: a non-NULL handle after start or stop means ownership was
 * retained, in which case nothing further is touched, it is reported, and the status is
 * non-zero. Stop is never retried and such a handle is never freed.
 *
 *   cc -std=c11 -O2 -Wall -Wextra -Werror -pthread -I <recorder-dir> -o bench \
 *      wksim_perf_overhead_bench.c <recorder-dir>/wksim_perf_stream.c
 *   bench <duration_ns> <period_ns> <disabled|enabled> <existing-empty-dir>
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "wksim_perf_stream.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

#define MAX_ITERATIONS 1000000u          /* bounds the fixed timing row array */
#define MAX_DURATION_NS 3600000000000ull /* 1 h: keeps start + duration in range */
#define MIN_PERIOD_NS 1000000ull         /* 1 ms: below this the loop is a spin test */
#define MAX_PERIOD_NS 1000000000ull      /* 1 s */
#define PATH_BYTES 1024
#define BODY_ROUNDS 512u
#define NS_PER_SEC 1000000000ull

struct row { uint64_t index, ideal, earliest, actual, end; };
struct cpu { uint64_t user_ns, sys_ns; int64_t nvcsw, nivcsw, minflt, majflt; };

/* Recorder lifecycle and call-span state, kept in one place so every path after a
 * successful start leaves through the same owner-thread stop and release. */
struct run_state {
    void *handle;
    bool retained;
    int start_rc, stop_rc;
    bool spans_ok;
    uint64_t start_begin, start_end, stop_begin, stop_end;
};

static bool now_ns(uint64_t *out)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        return false;
    }
    *out = (uint64_t)ts.tv_sec * NS_PER_SEC + (uint64_t)ts.tv_nsec;
    return true;
}

static uint64_t ns_of(const struct timeval *tv)
{
    return (uint64_t)tv->tv_sec * NS_PER_SEC + (uint64_t)tv->tv_usec * 1000ull;
}

/* Fill `thread` from RUSAGE_THREAD and `process` from RUSAGE_SELF; false on any error. */
static bool cpu_now(struct cpu *thread, struct cpu *process)
{
    struct rusage self, own;
    if (getrusage(RUSAGE_SELF, &self) != 0 || getrusage(RUSAGE_THREAD, &own) != 0) {
        return false;
    }
    thread->user_ns = ns_of(&own.ru_utime);
    thread->sys_ns = ns_of(&own.ru_stime);
    thread->nvcsw = own.ru_nvcsw;
    thread->nivcsw = own.ru_nivcsw;
    thread->minflt = own.ru_minflt;
    thread->majflt = own.ru_majflt;
    process->user_ns = ns_of(&self.ru_utime);
    process->sys_ns = ns_of(&self.ru_stime);
    process->nvcsw = self.ru_nvcsw;
    process->nivcsw = self.ru_nivcsw;
    process->minflt = self.ru_minflt;
    process->majflt = self.ru_majflt;
    return true;
}

/* Absolute-deadline wait: TIMER_ABSTIME cannot accumulate drift the way a relative sleep
 * does, and every failure is reported instead of ignored. */
static bool wait_until(uint64_t deadline_ns)
{
    struct timespec abs;
    abs.tv_sec = (time_t)(deadline_ns / NS_PER_SEC);
    abs.tv_nsec = (long)(deadline_ns % NS_PER_SEC);
    for (;;) {
        int rc = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &abs, NULL);
        if (rc == 0) {
            return true;
        }
        if (rc != EINTR) {
            fprintf(stderr, "bench: clock_nanosleep failed: %s\n", strerror(rc));
            return false;
        }
    }
}

/* Round a requested duration down to a whole number of periods: fixed count, no partial
 * interval, and a hard bound on how much storage and time the loop may use. */
static bool plan_iterations(uint64_t duration, uint64_t period, uint64_t *count)
{
    if (period < MIN_PERIOD_NS || period > MAX_PERIOD_NS || duration < period
            || duration > MAX_DURATION_NS) {
        return false;
    }
    const uint64_t planned = duration / period;
    if (planned == 0 || planned > MAX_ITERATIONS) {
        return false;
    }
    *count = planned;
    return true;
}

/* The one synthetic body, byte-for-byte identical in both modes. */
static uint64_t run_body(uint64_t seed)
{
    volatile uint64_t acc = seed;
    for (uint32_t round = 0; round < BODY_ROUNDS; round++) {
        acc = acc * 6364136223846793005ull + 1442695040888963407ull;
    }
    return acc;
}

static bool parse_u64(const char *text, uint64_t *out)
{
    char *end = NULL;
    errno = 0;
    unsigned long long value = strtoull(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0') {
        return false;
    }
    *out = (uint64_t)value;
    return true;
}

/* Write the summary and one CSV row per completed iteration, in original order. Each FILE
 * is opened, checked and closed separately: a failure on the first never abandons the
 * second, and neither close is skipped by short-circuit evaluation. `*reason` names the
 * first failure; "ok" means both files were written and closed. */
static bool write_outputs(const char *json_path, const char *csv_path, const struct row *rows,
                          uint64_t count, const char *json, const char **reason)
{
    bool ok = true;
    *reason = "ok";

    FILE *jf = fopen(json_path, "wx");
    if (jf == NULL) {
        fprintf(stderr, "bench: cannot create %s: %s\n", json_path, strerror(errno));
        ok = false;
        *reason = "json_open";
    } else {
        if (fputs(json, jf) < 0) {
            fprintf(stderr, "bench: cannot write %s\n", json_path);
            ok = false;
            *reason = "json_write";
        }
        if (fclose(jf) != 0) {
            fprintf(stderr, "bench: cannot close %s: %s\n", json_path, strerror(errno));
            ok = false;
            if (strcmp(*reason, "ok") == 0) {
                *reason = "json_close";
            }
        }
    }

    FILE *cf = fopen(csv_path, "wx");
    if (cf == NULL) {
        fprintf(stderr, "bench: cannot create %s: %s\n", csv_path, strerror(errno));
        ok = false;
        if (strcmp(*reason, "ok") == 0) {
            *reason = "csv_open";
        }
    } else {
        for (uint64_t k = 0; k < count; k++) {
            if (fprintf(cf, "%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
                        rows[k].index, rows[k].ideal, rows[k].earliest, rows[k].actual,
                        rows[k].end) <= 0) {
                fprintf(stderr, "bench: cannot write %s\n", csv_path);
                ok = false;
                if (strcmp(*reason, "ok") == 0) {
                    *reason = "csv_write";
                }
                break;
            }
        }
        if (fclose(cf) != 0) {
            fprintf(stderr, "bench: cannot close %s: %s\n", csv_path, strerror(errno));
            ok = false;
            if (strcmp(*reason, "ok") == 0) {
                *reason = "csv_close";
            }
        }
    }
    return ok;
}

int main(int argc, char **argv)
{
    if (argc != 5) {
        fprintf(stderr, "usage: %s <duration_ns> <period_ns> <disabled|enabled> <dir>\n",
                argv[0]);
        return 2;
    }
    uint64_t duration = 0, period = 0;
    if (!parse_u64(argv[1], &duration) || !parse_u64(argv[2], &period)) {
        fprintf(stderr, "bench: duration and period must be decimal integers\n");
        return 2;
    }
    const bool enabled = strcmp(argv[3], "enabled") == 0;
    if (!enabled && strcmp(argv[3], "disabled") != 0) {
        fprintf(stderr, "bench: mode must be disabled or enabled\n");
        return 2;
    }
    uint64_t count = 0;
    if (!plan_iterations(duration, period, &count)) {
        fprintf(stderr, "bench: need %llu <= period <= %llu, period <= duration <= %llu ns, "
                "duration/period <= %u\n", (unsigned long long)MIN_PERIOD_NS,
                (unsigned long long)MAX_PERIOD_NS, (unsigned long long)MAX_DURATION_NS,
                MAX_ITERATIONS);
        return 2;
    }
    const char *dir = argv[4];
    char json_path[PATH_BYTES], csv_path[PATH_BYTES];
    char raw_path[PATH_BYTES], meta_path[PATH_BYTES];
    /* snprintf's return value is the length it would have written, so comparing against the
     * buffer size is what detects a truncated path. */
    const int json_len = snprintf(json_path, sizeof json_path, "%s/result.json", dir);
    const int csv_len = snprintf(csv_path, sizeof csv_path, "%s/timing.csv", dir);
    const int raw_len = snprintf(raw_path, sizeof raw_path, "%s/switch.raw", dir);
    const int meta_len = snprintf(meta_path, sizeof meta_path, "%s/switch.meta.json", dir);
    if (json_len < 0 || (size_t)json_len >= sizeof json_path
            || csv_len < 0 || (size_t)csv_len >= sizeof csv_path
            || raw_len < 0 || (size_t)raw_len >= sizeof raw_path
            || meta_len < 0 || (size_t)meta_len >= sizeof meta_path) {
        fprintf(stderr, "bench: output path is too long for the %d-byte buffer\n", PATH_BYTES);
        return 2;
    }
    const char *outputs[] = { json_path, csv_path, enabled ? raw_path : NULL,
                              enabled ? meta_path : NULL };
    for (size_t i = 0; i < sizeof outputs / sizeof outputs[0]; i++) {
        if (outputs[i] != NULL && access(outputs[i], F_OK) == 0) {
            fprintf(stderr, "bench: refusing to overwrite %s\n", outputs[i]);
            return 2;
        }
    }
    struct row *rows = calloc((size_t)count, sizeof *rows);
    if (rows == NULL) {
        fprintf(stderr, "bench: cannot allocate %" PRIu64 " timing rows\n", count);
        return 2;
    }

    struct run_state state;
    memset(&state, 0, sizeof state);
    state.spans_ok = now_ns(&state.start_begin);
    if (enabled) {
        state.start_rc = wksim_perf_start(&state.handle);
        if (state.start_rc != 0 || state.handle == NULL) {
            state.retained = state.handle != NULL;
            if (state.start_rc == 0) {
                fprintf(stderr, "bench: start reported success with a NULL handle\n");
            } else {
                fprintf(stderr, "bench: wksim_perf_start: %s\n", wksim_perf_last_error());
            }
            fprintf(stderr, "bench: no measurement was written\n");
            free(rows);
            return 3; /* a failed start is not a run */
        }
    }
    state.spans_ok = state.spans_ok && now_ns(&state.start_end);

    struct cpu thread_before, process_before, thread_after, process_after;
    state.spans_ok = state.spans_ok && cpu_now(&thread_before, &process_before);
    uint64_t t0 = 0;
    state.spans_ok = state.spans_ok && now_ns(&t0);
    char failure[64];
    failure[0] = '\0';
    if (!state.spans_ok) {
        snprintf(failure, sizeof failure, "instrumentation_before_loop");
    }

    uint64_t checksum = 1, previous_actual = 0;
    bool sleep_ok = true, loop_clock_ok = true;
    for (uint64_t k = 0; failure[0] == '\0' && k < count; k++) {
        const uint64_t ideal = t0 + k * period;
        const uint64_t after_previous = previous_actual + period;
        const uint64_t earliest = k == 0 ? ideal
                                         : (after_previous > ideal ? after_previous : ideal);
        if (!wait_until(earliest)) {
            sleep_ok = false;
            break;
        }
        uint64_t actual = 0, end = 0;
        if (!now_ns(&actual)) {
            loop_clock_ok = false;
            break;
        }
        checksum = run_body(checksum);
        if (!now_ns(&end)) {
            loop_clock_ok = false;
            break;
        }
        rows[k] = (struct row){ k, ideal, earliest, actual, end };
        previous_actual = actual;
    }
    uint64_t t2 = 0;
    const bool closing_ok = now_ns(&t2) && cpu_now(&thread_after, &process_after);

    /* Single owner-thread exit: the recorder is stopped whenever it was started, on every
     * failure path, before any file is written. */
    bool stop_spans_ok = now_ns(&state.stop_begin);
    if (enabled) {
        state.stop_rc = wksim_perf_stop(&state.handle, raw_path, meta_path);
        if (state.stop_rc != 0) {
            state.retained = state.handle != NULL;
            fprintf(stderr, "bench: wksim_perf_stop: %s\n", wksim_perf_last_error());
        } else if (state.handle != NULL) {
            state.retained = true; /* contract: non-NULL means ownership was retained */
        }
    }
    stop_spans_ok = stop_spans_ok && now_ns(&state.stop_end);

    if (failure[0] == '\0' && !closing_ok) {
        snprintf(failure, sizeof failure, "instrumentation_after_loop");
    }
    if (failure[0] == '\0' && !sleep_ok) {
        snprintf(failure, sizeof failure, "wait_failed");
    }
    if (failure[0] == '\0' && !loop_clock_ok) {
        snprintf(failure, sizeof failure, "loop_clock_failed");
    }
    if (failure[0] == '\0' && !stop_spans_ok) {
        snprintf(failure, sizeof failure, "stop_span_unmeasured");
    }
    /* Defect 1: a nonzero recorder code is a failure even when the handle was already
     * cleared, so the exit status can never be 0 after a recorder error. */
    if (failure[0] == '\0' && enabled && (state.start_rc != 0 || state.stop_rc != 0)) {
        snprintf(failure, sizeof failure, "recorder_rc");
    }
    if (failure[0] == '\0' && state.retained) {
        snprintf(failure, sizeof failure, "ownership_retained");
    }

    const uint64_t completed = (failure[0] == '\0') ? count : 0;
    int exit_code = 3;
    if (failure[0] != '\0') {
        fprintf(stderr, "bench: run incomplete: %s (sleep_ok=%d clock_ok=%d retained=%d "
                "spans_ok=%d start_rc=%d stop_rc=%d)\n", failure, (int)sleep_ok,
                (int)loop_clock_ok, (int)state.retained, (int)state.spans_ok,
                state.start_rc, state.stop_rc);
    } else {
        const uint64_t owner_cpu = (thread_after.user_ns + thread_after.sys_ns)
                                   - (thread_before.user_ns + thread_before.sys_ns);
        const uint64_t proc_cpu = (process_after.user_ns + process_after.sys_ns)
                                  - (process_before.user_ns + process_before.sys_ns);
        char json[4096];
        const int jn = snprintf(json, sizeof json,
            "{\"tool\": \"wksim_perf_overhead_bench\", \"version\": 2, "
            "\"classification\": \"diagnostic_only\", \"full_acceptance\": false, "
            "\"native_verified\": false,\n"
            " \"claim\": \"synthetic pacing loop, not simulator, not controller, not flight; "
            "no true whole-flight overhead\",\n"
            " \"mode\": \"%s\", \"requested_duration_ns\": %" PRIu64
            ", \"requested_period_ns\": %" PRIu64 ", \"iterations\": %" PRIu64 ",\n"
            " \"measurement\": {\"clock\": \"CLOCK_MONOTONIC\", \"sleep\": "
            "\"clock_nanosleep(TIMER_ABSTIME)\", \"catchup\": false, \"release\": "
            "\"earliest[k]=max(ideal[k],actual_start[k-1]+period_ns)\", \"loop_span_ns\": %"
            PRIu64 ", \"recorder_start_span_ns\": %" PRIu64 ", \"recorder_stop_span_ns\": %"
            PRIu64 ", \"body_checksum\": %" PRIu64 ", \"cpu_window\": \"getrusage "
            "THREAD/SELF read after start returned and before stop was called; start and "
            "stop spans are outside it\"},\n"
            " \"cpu\": {\"owner_thread\": {\"user_ns\": %" PRIu64 ", \"sys_ns\": %" PRIu64
            ", \"cpu_ns\": %" PRIu64 ", \"nvcsw\": %" PRId64 ", \"nivcsw\": %" PRId64
            ", \"minflt\": %" PRId64 ", \"majflt\": %" PRId64 "}, \"process\": "
            "{\"user_ns\": %" PRIu64 ", \"sys_ns\": %" PRIu64 ", \"cpu_ns\": %" PRIu64
            "}},\n"
            " \"recorder\": {\"enabled\": %s, \"start_rc\": %d, \"stop_rc\": %d, "
            "\"retained\": %s},\n"
            " \"timing_rows\": %" PRIu64 ", \"timing_file\": \"timing.csv\", "
            "\"caveat\": \"percentiles and deltas are computed offline; no threshold "
            "verdict is contained here\"}\n",
            enabled ? "enabled" : "disabled", duration, period, count, (t2 > t0 ? t2 - t0 : 0),
            state.start_end - state.start_begin, state.stop_end - state.stop_begin, checksum,
            thread_after.user_ns - thread_before.user_ns,
            thread_after.sys_ns - thread_before.sys_ns, owner_cpu,
            thread_after.nvcsw - thread_before.nvcsw, thread_after.nivcsw - thread_before.nivcsw,
            thread_after.minflt - thread_before.minflt,
            thread_after.majflt - thread_before.majflt,
            process_after.user_ns - process_before.user_ns,
            process_after.sys_ns - process_before.sys_ns, proc_cpu,
            enabled ? "true" : "false", state.start_rc, state.stop_rc,
            state.retained ? "true" : "false", completed);
        const char *write_reason = "ok";
        if (jn < 0 || (size_t)jn >= sizeof json) {
            fprintf(stderr, "bench: the summary does not fit its buffer\n");
        } else if (write_outputs(json_path, csv_path, rows, completed, json, &write_reason)
                   && strcmp(write_reason, "ok") == 0) {
            printf("bench: mode=%s iterations=%" PRIu64 " loop_ns=%" PRIu64
                   " owner_cpu_ns=%" PRIu64 " process_cpu_ns=%" PRIu64 "\n",
                   enabled ? "enabled" : "disabled", count, t2 - t0, owner_cpu, proc_cpu);
            exit_code = 0;
        } else {
            fprintf(stderr, "bench: outputs not accepted: %s\n", write_reason);
        }
    }
    if (state.retained) {
        /* Reported, never repaired here: the recorder still owns the handle. */
        fprintf(stderr, "bench: recorder ownership was retained; nothing further was freed\n");
        exit_code = 3;
    }
    free(rows);
    return exit_code;
}
