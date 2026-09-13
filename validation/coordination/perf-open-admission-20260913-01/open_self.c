#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <errno.h>
#include <linux/perf_event.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

int main(void) {
    int failed = 0;
    printf("{\"scope\":\"self thread, open and close only; never enabled\",\"pid\":%ld,\"attempts\":[", (long)getpid());
    for (int excluded = 0; excluded <= 1; ++excluded) {
        struct perf_event_attr attr;
        memset(&attr, 0, sizeof attr);
        attr.type = PERF_TYPE_SOFTWARE;
        attr.size = sizeof attr;
        attr.config = PERF_COUNT_SW_DUMMY;
        attr.disabled = 1;
        attr.inherit = 0;
        attr.context_switch = 1;
        attr.sample_id_all = 1;
        attr.sample_type = PERF_SAMPLE_TID | PERF_SAMPLE_TIME | PERF_SAMPLE_CPU;
        attr.use_clockid = 1;
        attr.clockid = CLOCK_MONOTONIC;
        attr.exclude_kernel = excluded;
        int fd = (int)syscall(SYS_perf_event_open, &attr, 0, -1, -1, PERF_FLAG_FD_CLOEXEC);
        int open_error = fd < 0 ? errno : 0;
        int close_error = 0;
        if (fd >= 0 && close(fd) != 0) close_error = errno;
        printf("%s{\"exclude_kernel\":%d,\"opened\":%s,\"open_errno\":%d,\"close_errno\":%d}",
               excluded ? "," : "", excluded, fd >= 0 ? "true" : "false", open_error, close_error);
        if (close_error) failed = 1;
    }
    puts("],\"switch_records_verified\":false}");
    return failed;
}
