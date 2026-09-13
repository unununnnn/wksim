/*
 * wksim_perf_stream_demo.c -- short self-thread demo for wksim_perf_stream.
 *
 * Usage:
 *   wksim_perf_stream_demo <output-dir> [raw-name] [meta-name]
 *
 * Defaults are `switch-stream.raw` and `switch-stream.meta.json` inside the given
 * directory. The directory must already exist; the two output files are created
 * exclusively, so an existing file makes the run fail without overwriting anything.
 *
 * The demo records the calling thread only:
 *   start -> four short sleeps (~600 ms total) -> stop
 *
 * It writes no fixture of its own and fabricates no evidence. Exit status is 0 only
 * when start, all four sleeps, stop, both output files and the demo's own post-checks
 * succeeded. Every failure prints one line to stderr and exits non-zero.
 *
 * Build:
 *   cc -std=c11 -O2 -Wall -Wextra -Werror -pthread \
 *      -o wksim_perf_stream_demo wksim_perf_stream_demo.c wksim_perf_stream.c
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
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define DEMO_SLEEP_ROUNDS 4
#define DEMO_SLEEP_NS 150000000L          /* 150 ms each, about 600 ms total */
#define DEMO_PATH_BYTES 4096

static int fail(const char *what)
{
    fprintf(stderr, "demo: %s failed: %s\n", what, wksim_perf_last_error());
    return 2;
}

static int short_sleeps(int rounds, long nanoseconds)
{
    for (int index = 0; index < rounds; index++) {
        struct timespec request;
        request.tv_sec = nanoseconds / 1000000000L;
        request.tv_nsec = nanoseconds % 1000000000L;
        while (nanosleep(&request, &request) != 0) {
            if (errno != EINTR) {
                int saved = errno;
                fprintf(stderr, "demo: nanosleep failed at round %d: %s\n", index,
                        strerror(saved));
                return -1;
            }
        }
    }
    return 0;
}

static bool is_directory(const char *path)
{
    struct stat info;
    if (stat(path, &info) != 0) {
        return false;
    }
    return S_ISDIR(info.st_mode);
}

/* Independent readback: the demo must not trust its own writer. The two checks below
 * are read-only and never repair or rewrite anything. */
static int check_outputs(const char *raw_path, const char *meta_path)
{
    int raw_fd = open(raw_path, O_RDONLY | O_CLOEXEC);
    if (raw_fd < 0) {
        fprintf(stderr, "demo: cannot reopen raw output: %s\n", strerror(errno));
        return -1;
    }
    struct stat raw_info;
    if (fstat(raw_fd, &raw_info) != 0) {
        int saved = errno;
        close(raw_fd);
        fprintf(stderr, "demo: fstat raw output failed: %s\n", strerror(saved));
        return -1;
    }
    close(raw_fd);
    if (raw_info.st_size <= 0) {
        fprintf(stderr, "demo: raw output is empty\n");
        return -1;
    }
    if (raw_info.st_size % 8 != 0) {
        fprintf(stderr, "demo: raw output is %lld bytes, not 8-byte aligned as perf "
                "records are\n", (long long)raw_info.st_size);
        return -1;
    }

    int meta_fd = open(meta_path, O_RDONLY | O_CLOEXEC);
    if (meta_fd < 0) {
        fprintf(stderr, "demo: cannot reopen metadata: %s\n", strerror(errno));
        return -1;
    }
    char meta[8192];
    ssize_t got = read(meta_fd, meta, sizeof meta - 1);
    int read_errno = errno;
    close(meta_fd);
    if (got <= 0) {
        fprintf(stderr, "demo: metadata is empty: %s\n", strerror(read_errno));
        return -1;
    }
    meta[got] = '\0';

    /* Minimal textual checks: the required markers must be present and the capture must
     * not claim incomplete. Offline acceptance owns full schema validation. */
    static const char *const required[] = {
        "\"schema\": \"wksim.perf_switch_stream.v1\"",
        "\"classification\": \"diagnostic_only\"",
        "\"full_acceptance\": false",
        "\"collector_complete\": true",
        "\"clock_id\": \"CLOCK_MONOTONIC\"",
        "\"reader_policy_name\": \"SCHED_OTHER\"",
        "\"collector_errors\": []",
        /* Never claim a proven-lossless capture: this module cannot prove it (G9). */
        "\"losslessness_proven\": false",
        /* Geometry must have been cross-checked against the mapping, not defaulted. */
        "\"meta_geometry_exact\": true",
        "\"reader_joined\": true",
        "\"join_failed\": false",
    };
    for (size_t index = 0; index < sizeof required / sizeof required[0]; index++) {
        if (strstr(meta, required[index]) == NULL) {
            fprintf(stderr, "demo: metadata is missing %s\n", required[index]);
            return -1;
        }
    }
    printf("demo: raw %lld bytes, metadata %zd bytes, markers verified\n",
           (long long)raw_info.st_size, got);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 2 || argc > 4) {
        fprintf(stderr, "usage: %s <output-dir> [raw-name] [meta-name]\n", argv[0]);
        return 2;
    }
    const char *directory = argv[1];
    const char *raw_name = argc >= 3 ? argv[2] : "switch-stream.raw";
    const char *meta_name = argc >= 4 ? argv[3] : "switch-stream.meta.json";

    if (!is_directory(directory)) {
        fprintf(stderr, "demo: output directory does not exist: %s\n", directory);
        return 2;
    }
    if (strchr(raw_name, '/') != NULL || strchr(meta_name, '/') != NULL) {
        fprintf(stderr, "demo: names must not contain a path separator\n");
        return 2;
    }
    char raw_path[DEMO_PATH_BYTES];
    char meta_path[DEMO_PATH_BYTES];
    int raw_len = snprintf(raw_path, sizeof raw_path, "%s/%s", directory, raw_name);
    int meta_len = snprintf(meta_path, sizeof meta_path, "%s/%s", directory, meta_name);
    if (raw_len < 0 || (size_t)raw_len >= sizeof raw_path || meta_len < 0
            || (size_t)meta_len >= sizeof meta_path) {
        fprintf(stderr, "demo: output path is too long\n");
        return 2;
    }

    /* Refuse to overwrite before touching the recorder. The recorder also creates both
     * files exclusively, so this pre-check is a convenience, not the guarantee. */
    if (access(raw_path, F_OK) == 0 || access(meta_path, F_OK) == 0) {
        fprintf(stderr, "demo: refusing to overwrite an existing file (%s or %s)\n",
                raw_path, meta_path);
        return 2;
    }

    void *handle = NULL;
    if (wksim_perf_start(&handle) != 0) {
        return fail("wksim_perf_start");
    }
    printf("demo: recording this thread; %d sleeps of %ld ns\n", DEMO_SLEEP_ROUNDS,
           DEMO_SLEEP_NS);
    if (short_sleeps(DEMO_SLEEP_ROUNDS, DEMO_SLEEP_NS) != 0) {
        /* Still stop, so the handle is released and no reader or mapping leaks. The
         * run already failed, so the stop result must not turn it into success. */
        if (wksim_perf_stop(handle, raw_path, meta_path) != 0) {
            fprintf(stderr, "demo: stop after sleep failure also failed: %s\n",
                    wksim_perf_last_error());
        }
        return 2;
    }
    if (wksim_perf_stop(handle, raw_path, meta_path) != 0) {
        return fail("wksim_perf_stop");
    }
    printf("demo: capture stopped; wrote %s and %s\n", raw_path, meta_path);

    if (check_outputs(raw_path, meta_path) != 0) {
        return 2;
    }
    return 0;
}
