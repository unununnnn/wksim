#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "wksim_perf_stream.h"
#include <errno.h>
#include <stdio.h>
#include <sys/mman.h>
#include <time.h>

static int injected;
int __real_munmap(void *address, size_t length);
int __wrap_munmap(void *address, size_t length) {
    int result = __real_munmap(address, length);
    if (result == 0) {
        injected++;
        errno = EIO;
        return -1; /* Report failure while actually releasing this test's memory. */
    }
    return result;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    char raw[4096], meta[4096];
    int n = snprintf(raw, sizeof raw, "%s/cleanup.raw", argv[1]);
    int m = snprintf(meta, sizeof meta, "%s/cleanup.meta.json", argv[1]);
    if (n < 0 || m < 0 || (size_t)n >= sizeof raw || (size_t)m >= sizeof meta) return 2;
    void *handle = NULL;
    int start = wksim_perf_start(&handle);
    if (start != 0) {
        fprintf(stderr, "start failed: %s\n", wksim_perf_last_error());
        return 2;
    }
    struct timespec delay = {0, 10000000};
    while (nanosleep(&delay, &delay) != 0)
        if (errno != EINTR) break;
    int stop = wksim_perf_stop(&handle, raw, meta);
    printf("{\"start_result\":%d,\"stop_result\":%d,"
           "\"injected_munmap_failures\":%d}\n", start, stop, injected);
    /* The Python caller also verifies that metadata records the failed cleanup. */
    return stop == -1 && injected >= 1 && handle == NULL ? 0 : 1;
}
