/* Link with --wrap=pthread_join. No actual thread or perf event is created. */
#include "wksim_perf_stream.c"

int __wrap_pthread_join(pthread_t thread, void **result) {
    (void)thread; (void)result;
    return ESRCH;
}

int main(void) {
    struct wksim_perf_stream stream;
    memset(&stream, 0, sizeof stream);
    if (pthread_mutex_init(&stream.error_lock, NULL) != 0) return 2;
    stream.reader_running = true;
    int result = join_reader(&stream, true);
    bool pass = result == ESRCH && stream.reader_running &&
        !stream.reader_joined && stream.join_failed;
    printf("{\"passed\":%s,\"join_result\":%d,\"reader_running\":%s,"
           "\"reader_joined\":%s,\"join_failed\":%s}\n",
           pass ? "true" : "false", result,
           stream.reader_running ? "true" : "false",
           stream.reader_joined ? "true" : "false",
           stream.join_failed ? "true" : "false");
    if (pass) {
        void *retained = NULL;
        int aborted = start_abort(&stream, EIO, &retained);
        int saved_errno = errno;
        bool handed_back = aborted == -1 && saved_errno == EIO &&
            retained == &stream && stream.reader_running && stream.join_failed;
        printf("{\"failed_start_handle_returned\":%s}\n",
               handed_back ? "true" : "false");
        pass = pass && handed_back;
    }
    pthread_mutex_destroy(&stream.error_lock);
    return pass ? 0 : 1;
}
