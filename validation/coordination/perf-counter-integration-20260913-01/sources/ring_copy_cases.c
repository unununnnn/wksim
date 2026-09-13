/* Synthetic tests of the actual collector. No perf event or thread is opened. */
#include "wksim_perf_stream.c"

static unsigned char data[8192], saved[8192];
static struct perf_event_mmap_page page;
static int failures;

static void prepare(struct wksim_perf_stream *stream, uint64_t tail,
                    uint64_t count, uint64_t capacity) {
    memset(stream, 0, sizeof *stream);
    memset(&page, 0, sizeof page);
    memset(saved, 0xee, sizeof saved);
    for (size_t i = 0; i < sizeof data; ++i) data[i] = (unsigned char)(i % 251);
    if (pthread_mutex_init(&stream->error_lock, NULL) != 0) exit(2);
    stream->owner_tid = (int64_t)syscall(SYS_gettid);
    stream->meta = &page;
    stream->ring = data;
    stream->ring_bytes = sizeof data;
    stream->storage = saved;
    stream->storage_capacity = capacity;
    page.data_tail = tail;
    page.data_head = tail + count;
}

static void check(const char *name, bool passed) {
    printf("%s %s\n", name, passed ? "PASS" : "FAIL");
    failures += !passed;
}

int main(void) {
    struct wksim_perf_stream stream;
    prepare(&stream, 0, 53, sizeof saved);
    collect_available(&stream, sizeof data, sizeof data - 1);
    check("verbatim_unframed_bytes", stream.captured_bytes == 53 &&
          page.data_tail == 53 && memcmp(saved, data, 53) == 0 &&
          error_count_now(&stream) == 0);
    pthread_mutex_destroy(&stream.error_lock);

    prepare(&stream, 8180, 65, sizeof saved);
    unsigned char expected[65];
    for (size_t i = 0; i < sizeof expected; ++i)
        expected[i] = data[(8180 + i) % sizeof data];
    collect_available(&stream, sizeof data, sizeof data - 1);
    check("wrapped_bytes_keep_monotonic_tail", stream.captured_bytes == 65 &&
          page.data_tail == 8245 && memcmp(saved, expected, 65) == 0 &&
          error_count_now(&stream) == 0);
    pthread_mutex_destroy(&stream.error_lock);

    /* Large declared storage capacity makes this specifically a ring guard test.
     * The backing array also holds all pending bytes, so a broken guard produces
     * a failed assertion without relying on a memory overrun. */
    prepare(&stream, 0, sizeof data - 4096 + 1, 128 * 1024 * 1024);
    collect_available(&stream, sizeof data, sizeof data - 1);
    check("ring_pressure_rejects_before_copy", stream.captured_bytes == 0 &&
          page.data_tail == 0 && saved[0] == 0xee && error_count_now(&stream) > 0);
    pthread_mutex_destroy(&stream.error_lock);

    prepare(&stream, 0, 64, 32);
    collect_available(&stream, sizeof data, sizeof data - 1);
    check("storage_pressure_never_overruns", stream.captured_bytes <= 32 &&
          page.data_tail <= 32 && saved[32] == 0xee && error_count_now(&stream) > 0);
    pthread_mutex_destroy(&stream.error_lock);
    printf("4 cases, %d failures\n", failures);
    return failures ? 1 : 0;
}
