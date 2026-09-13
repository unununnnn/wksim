/* Low-overhead deadline release candidate for wksim#84. Not wired into any
 * production pacer or runner; joint_rate.py keeps its 1ms monotonic polling,
 * health/sleep/4-tick/no-catch-up/100ms semantics untouched.
 *
 * wk_release_wait_until polls CLOCK_MONOTONIC and returns the first observed
 * time at or after deadline_ns. It busy-waits ONLY when the deadline is at
 * most 1ms ahead at entry; an already-past deadline returns the observed time
 * immediately. No sleep, allocation, logging, callback, affinity or priority
 * change, and no catch-up behavior. All failures are explicit status codes;
 * success is never reported early. Clock samples outside the exactly
 * representable int64-nanosecond range (or with an illegal tv_nsec) are
 * reported as WK_RELEASE_WAIT_CLOCK_FAILURE instead of invoking undefined
 * signed overflow.
 */
#define _POSIX_C_SOURCE 199309L
#include <stdint.h>
#include <time.h>

#define WK_RELEASE_WAIT_SPIN_LIMIT_NS 1000000LL

enum wk_release_wait_status {
    WK_RELEASE_WAIT_OK = 0,
    WK_RELEASE_WAIT_INVALID_ARGUMENT = 1,   /* NULL out pointer or deadline < 0 */
    WK_RELEASE_WAIT_CLOCK_FAILURE = 2,      /* clock_gettime(CLOCK_MONOTONIC) failed */
    WK_RELEASE_WAIT_CLOCK_REGRESSED = 3,    /* monotonic sample went backwards */
    WK_RELEASE_WAIT_DEADLINE_OUT_OF_RANGE = 4 /* deadline over 1ms ahead at entry */
};

static int read_monotonic_ns(int64_t *out_ns) {
    struct timespec sample;
    if (clock_gettime(CLOCK_MONOTONIC, &sample) != 0)
        return WK_RELEASE_WAIT_CLOCK_FAILURE;
    /* Include the representable part of the final int64-nanosecond second. */
    if (sample.tv_sec < 0 || sample.tv_sec > INT64_MAX / 1000000000LL ||
        sample.tv_nsec < 0L || sample.tv_nsec > 999999999L ||
        (sample.tv_sec == INT64_MAX / 1000000000LL &&
         sample.tv_nsec > INT64_MAX % 1000000000LL))
        return WK_RELEASE_WAIT_CLOCK_FAILURE;
    *out_ns = (int64_t)sample.tv_sec * 1000000000LL + (int64_t)sample.tv_nsec;
    return WK_RELEASE_WAIT_OK;
}

int wk_release_wait_until(int64_t deadline_ns, int64_t *observed_ns) {
    int64_t now, previous;
    int status;

    if (observed_ns == NULL || deadline_ns < 0)
        return WK_RELEASE_WAIT_INVALID_ARGUMENT;

    status = read_monotonic_ns(&now);
    if (status != WK_RELEASE_WAIT_OK)
        return status;

    if (now >= deadline_ns) {           /* already past: return observed time */
        *observed_ns = now;
        return WK_RELEASE_WAIT_OK;
    }
    if (deadline_ns - now > WK_RELEASE_WAIT_SPIN_LIMIT_NS)
        return WK_RELEASE_WAIT_DEADLINE_OUT_OF_RANGE;

    previous = now;
    for (;;) {                          /* bounded-entry busy wait, no sleeping */
        status = read_monotonic_ns(&now);
        if (status != WK_RELEASE_WAIT_OK)
            return status;
        if (now < previous)
            return WK_RELEASE_WAIT_CLOCK_REGRESSED;
        if (now >= deadline_ns) {
            *observed_ns = now;
            return WK_RELEASE_WAIT_OK;
        }
        previous = now;
    }
}
