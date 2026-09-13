#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "wksim_perf_stream.h"
#include <dirent.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>

static int attribute_check;
static int create_calls;
int __wrap_pthread_create(pthread_t *thread, const pthread_attr_t *attr,
                          void *(*start)(void *), void *argument) {
    (void)thread; (void)start; (void)argument;
    int inherit = -1, policy = -1;
    struct sched_param param = { .sched_priority = -1 };
    create_calls++;
    attribute_check = attr != NULL &&
        pthread_attr_getinheritsched(attr, &inherit) == 0 &&
        pthread_attr_getschedpolicy(attr, &policy) == 0 &&
        pthread_attr_getschedparam(attr, &param) == 0 &&
        inherit == PTHREAD_EXPLICIT_SCHED && policy == SCHED_OTHER &&
        param.sched_priority == 0;
    return EAGAIN;
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
    int pass = result == -1 && saved_errno == EAGAIN && handle == NULL &&
        create_calls == 1 && attribute_check && fd_before >= 0 &&
        fd_before == fd_after && tasks_before == 1 && tasks_after == 1;
    printf("{\"passed\":%s,\"start_result\":%d,\"saved_errno\":%d,"
           "\"explicit_other_attributes\":%s,\"create_calls\":%d,"
           "\"fd_before\":%d,\"fd_after\":%d,"
           "\"tasks_before\":%d,\"tasks_after\":%d}\n",
           pass ? "true" : "false", result, saved_errno,
           attribute_check ? "true" : "false", create_calls,
           fd_before, fd_after, tasks_before, tasks_after);
    return pass ? 0 : 1;
}
