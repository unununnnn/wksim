#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/perf_event.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/utsname.h>
#include <time.h>
#include <unistd.h>

/* Linux 6.0+ UAPI bit; the installed userspace header can predate this flag. */
#define WKSIM_PERF_FORMAT_LOST (1ull << 4)

static int run_case(const char *directory, const char *name, unsigned sleeps,
                    bool expect_loss) {
    struct perf_event_attr attr;
    memset(&attr, 0, sizeof attr);
    attr.type = PERF_TYPE_SOFTWARE;
    attr.size = sizeof attr;
    attr.config = PERF_COUNT_SW_DUMMY;
    attr.sample_period = 1;
    attr.sample_type = PERF_SAMPLE_TID | PERF_SAMPLE_TIME | PERF_SAMPLE_CPU;
    attr.read_format = WKSIM_PERF_FORMAT_LOST;
    attr.disabled = 1;
    attr.inherit = 0;
    attr.context_switch = 1;
    attr.sample_id_all = 1;
    attr.exclude_kernel = 1;
    attr.use_clockid = 1;
    attr.clockid = CLOCK_MONOTONIC;
    int fd = (int)syscall(SYS_perf_event_open, &attr, 0, -1, -1, PERF_FLAG_FD_CLOEXEC);
    if (fd < 0) { perror("perf_event_open with PERF_FORMAT_LOST"); return 2; }
    long page = sysconf(_SC_PAGESIZE);
    if (page <= 0) { close(fd); return 2; }
    size_t map_bytes = (size_t)page * 2;
    void *mapping = mmap(NULL, map_bytes, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (mapping == MAP_FAILED) { perror("mmap"); close(fd); return 2; }
    struct perf_event_mmap_page *meta = mapping;
    bool ok = meta->data_offset == (uint64_t)page && meta->data_size == (uint64_t)page;
    if (ok) ok = ioctl(fd, PERF_EVENT_IOC_ENABLE, 0) == 0;
    for (unsigned i = 0; ok && i < sleeps; ++i) {
        struct timespec pause = {0, 1000000};
        while (nanosleep(&pause, &pause) != 0) {
            if (errno != EINTR) { ok = false; break; }
        }
    }
    if (ioctl(fd, PERF_EVENT_IOC_DISABLE, 0) != 0) ok = false;
    uint64_t counters[2] = {UINT64_MAX, UINT64_MAX};
    ssize_t got;
    do { got = read(fd, counters, sizeof counters); } while (got < 0 && errno == EINTR);
    if (got != (ssize_t)sizeof counters) ok = false;

    uint64_t head = __atomic_load_n(&meta->data_head, __ATOMIC_ACQUIRE);
    uint64_t tail = __atomic_load_n(&meta->data_tail, __ATOMIC_RELAXED);
    unsigned char *data = (unsigned char *)mapping + page;
    uint64_t records = 0, queued_lost = 0, position = 0;
    if (tail != 0 || head > (uint64_t)page) ok = false;
    while (ok && position < head) {
        struct perf_event_header header;
        if (head - position < sizeof header) { ok = false; break; }
        memcpy(&header, data + position, sizeof header);
        if (header.size < sizeof header || header.size > head - position) { ok = false; break; }
        if (header.type == PERF_RECORD_LOST) queued_lost++;
        position += header.size;
        records++;
    }
    if (expect_loss) ok = ok && counters[1] > 0 && queued_lost == 0;
    else ok = ok && counters[1] == 0 && records >= 2 && queued_lost == 0;
    char path[4096];
    int length = snprintf(path, sizeof path, "%s/%s.raw", directory, name);
    if (length < 0 || (size_t)length >= sizeof path) ok = false;
    else {
        int output = open(path, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
        if (output < 0) ok = false;
        else {
            if (head <= (uint64_t)page && write(output, data, (size_t)head) != (ssize_t)head) ok = false;
            if (close(output) != 0) ok = false;
        }
    }
    if (munmap(mapping, map_bytes) != 0) ok = false;
    if (close(fd) != 0) ok = false;
    printf("{\"case\":\"%s\",\"passed\":%s,\"read_bytes\":%zd,"
           "\"event_value\":%" PRIu64 ",\"kernel_lost\":%" PRIu64 ","
           "\"ring_head\":%" PRIu64 ",\"ring_tail\":%" PRIu64 ","
           "\"queued_records\":%" PRIu64 ",\"queued_lost_records\":%" PRIu64 "}\n",
           name, ok ? "true" : "false", got, counters[0], counters[1],
           head, tail, records, queued_lost);
    return ok ? 0 : 1;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    struct utsname host;
    if (uname(&host) != 0) return 2;
    printf("{\"kernel\":\"%s\",\"pid\":%ld,\"self_only\":true,"
           "\"read_format\":16,\"ring_pages\":1,\"reader\":false}\n",
           host.release, (long)getpid());
    int first = run_case(argv[1], "normal", 2, false);
    if (first) return first;
    return run_case(argv[1], "overflow_disabled_without_drain", 256, true);
}
