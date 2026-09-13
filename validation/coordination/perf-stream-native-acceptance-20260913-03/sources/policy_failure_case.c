#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "wksim_perf_stream.h"
#include <dirent.h>
#include <errno.h>
#include <linux/perf_event.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>

static int enable_calls;
static int policy_reads;
int __real_ioctl(int fd, unsigned long request, ...);
int __wrap_ioctl(int fd, unsigned long request, ...) {
    if (request == PERF_EVENT_IOC_ENABLE) enable_calls++;
    /* The recorder's RESET/ENABLE/DISABLE calls all use zero as argument 3. */
    return __real_ioctl(fd, request, 0);
}
int __wrap_pthread_getschedparam(pthread_t thread, int *policy,
                                struct sched_param *param) {
    (void)thread;
    policy_reads++;
    *policy = SCHED_FIFO;
    param->sched_priority = 98;
    return 0; /* Fake a bad readback, without changing any actual thread policy. */
}
static int entries(const char *path) {
    DIR *dir = opendir(path);
    if (!dir) return -1;
    int count = 0;
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL)
        if (entry->d_name[0] != '.') count++;
    closedir(dir);
    return count;
}
int main(void) {
    int fd_before = entries("/proc/self/fd");
    int tasks_before = entries("/proc/self/task");
    void *handle = NULL;
    int result = wksim_perf_start(&handle);
    int saved_errno = errno;
    int fd_after = entries("/proc/self/fd");
    int tasks_after = entries("/proc/self/task");
    int pass = result == -1 && saved_errno == EPERM && handle == NULL &&
        policy_reads == 1 && enable_calls == 0 && fd_before >= 0 &&
        fd_before == fd_after && tasks_before == 1 && tasks_after == 1;
    printf("{\"passed\":%s,\"result\":%d,\"saved_errno\":%d,"
           "\"policy_reads\":%d,\"enable_calls\":%d,"
           "\"fd_before\":%d,\"fd_after\":%d,"
           "\"tasks_before\":%d,\"tasks_after\":%d}\n",
           pass ? "true" : "false", result, saved_errno,
           policy_reads, enable_calls, fd_before, fd_after, tasks_before, tasks_after);
    return pass ? 0 : 1;
}
