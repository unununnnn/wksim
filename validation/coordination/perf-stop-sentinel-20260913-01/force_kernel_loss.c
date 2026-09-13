#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <stdatomic.h>
#include <stdbool.h>
#include <string.h>
#include <stddef.h>
struct wksim_perf_stream;
static _Atomic(struct wksim_perf_stream *) test_stream;
static _Atomic bool test_intercepted, test_paused, test_resume;
static size_t test_chunk;
static void *test_memcpy(void *dst, const void *src, size_t count);

/* A test-only scheduling fault, not a production recorder option. The reader
 * pauses after copying a sufficiently large prefix but before publishing tail.
 * The owner then creates enough real switches to overflow the kernel ring. */
#define WKSIM_PERF_POLL_NS 100000000L
#define memcpy test_memcpy
#include "wksim_perf_stream.c"
#undef memcpy

static void *test_memcpy(void *dst, const void *src, size_t count) {
    void *result = memcpy(dst, src, count);
    struct wksim_perf_stream *stream = atomic_load_explicit(&test_stream, memory_order_acquire);
    bool expected = false;
    if (stream != NULL && pthread_equal(pthread_self(), stream->reader) && count >= 8192
            && (uintptr_t)dst >= (uintptr_t)stream->storage
            && (uintptr_t)dst < (uintptr_t)stream->storage + stream->storage_capacity
            && atomic_compare_exchange_strong(&test_intercepted, &expected, true)) {
        test_chunk = count;
        atomic_store_explicit(&test_paused, true, memory_order_release);
        while (!atomic_load_explicit(&test_resume, memory_order_acquire)) {
            struct timespec pause = {0, 1000000};
            (void)nanosleep(&pause, NULL);
        }
    }
    return result;
}

static bool owner_switch(void) {
    struct timespec pause = {0, 1000};
    while (nanosleep(&pause, &pause) != 0) {
        if (errno != EINTR) return false;
    }
    return true;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    char raw[4096], meta[4096];
    int a = snprintf(raw, sizeof raw, "%s/forced-loss.raw", argv[1]);
    int b = snprintf(meta, sizeof meta, "%s/forced-loss.meta.json", argv[1]);
    if (a < 0 || b < 0 || (size_t)a >= sizeof raw || (size_t)b >= sizeof meta) return 2;
    void *handle = NULL;
    if (wksim_perf_start(&handle) != 0) return 2;
    atomic_store_explicit(&test_stream, handle, memory_order_release);
    uint64_t start, now;
    if (!monotonic_ns(CLOCK_MONOTONIC, &start)) return 2;
    bool workload_ok = true;
    while (!atomic_load_explicit(&test_paused, memory_order_acquire)) {
        if (!owner_switch() || !monotonic_ns(CLOCK_MONOTONIC, &now)
                || now - start > 3000000000ull) {
            workload_ok = false;
            break;
        }
    }
    unsigned count = 0;
    if (workload_ok) {
        for (; count < 20000; ++count) {
            if (!owner_switch() || !monotonic_ns(CLOCK_MONOTONIC, &now)
                    || now - start > 6000000000ull) {
                workload_ok = false;
                break;
            }
        }
    }
    atomic_store_explicit(&test_resume, true, memory_order_release);
    int stop = wksim_perf_stop(&handle, raw, meta);
    atomic_store_explicit(&test_stream, NULL, memory_order_release);
    printf("{\"test_only\":true,\"paused_copy_bytes\":%zu,"
           "\"owner_sleep_calls\":%u,\"workload_completed\":%s,"
           "\"stop_result\":%d,\"handle_released\":%s}\n",
           test_chunk, count, workload_ok ? "true" : "false", stop,
           handle == NULL ? "true" : "false");
    /* The caller independently scans raw records for real LOST and runs the
     * strict consumer. This workload alone cannot declare its own success. */
    return workload_ok && handle == NULL ? 0 : 1;
}
