#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "wksim_perf_stream.h"
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

static int mode, counter_reads;
ssize_t __real_read(int fd, void *buffer, size_t count);
ssize_t __wrap_read(int fd, void *buffer, size_t count) {
    if (count != 16) return __real_read(fd, buffer, count);
    counter_reads++;
    if (mode == 2 || (mode == 1 && counter_reads <= 3)) {
        errno = EINTR;
        return -1;
    }
    if (mode == 3) {
        uint64_t values[2];
        ssize_t result = __real_read(fd, values, sizeof values);
        if (result != 16) return result;
        memcpy(buffer, values, 8);
        return 8; /* Deliberately malformed counter-read length. */
    }
    return __real_read(fd, buffer, count);
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    for (mode = 1; mode <= 3; ++mode) {
        counter_reads = 0;
        char raw[4096], meta[4096];
        int a = snprintf(raw, sizeof raw, "%s/read-%d.raw", argv[1], mode);
        int b = snprintf(meta, sizeof meta, "%s/read-%d.meta.json", argv[1], mode);
        if (a < 0 || b < 0 || (size_t)a >= sizeof raw || (size_t)b >= sizeof meta) return 2;
        void *handle = NULL;
        if (wksim_perf_start(&handle) != 0) return 2;
        struct timespec pause = {0, 10000000};
        while (nanosleep(&pause, &pause) != 0)
            if (errno != EINTR) break;
        int result = wksim_perf_stop(&handle, raw, meta);
        int expected_result = mode == 1 ? 0 : -1;
        int expected_reads = mode == 1 ? 4 : mode == 2 ? 8 : 1;
        bool passed = result == expected_result && counter_reads == expected_reads && handle == NULL;
        printf("{\"mode\":%d,\"passed\":%s,\"stop_result\":%d,"
               "\"counter_reads\":%d,\"handle_released\":%s}\n",
               mode, passed ? "true" : "false", result, counter_reads,
               handle == NULL ? "true" : "false");
        if (!passed) return 1;
    }
    return 0;
}
