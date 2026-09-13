#define main capability_probe_main_unused
#include "perf_self_capability.c"
#undef main

/* Exercise the real formatter after a successful parse followed by timeout.
 * This calls no perf syscall, clock, sleep, mapping or probe main function. */
int main(void) {
    struct probe_state state;
    perf_parse_summary summary;
    memset(&state, 0, sizeof state);
    memset(&summary, 0, sizeof summary);
    summary.ok = true;
    summary.status = PERF_PARSE_PROBE_FAILURE;
    snprintf(summary.first_problem, sizeof summary.first_problem,
             "exceeded_one_second");
    report_json(&state, &summary, 1000000000ull, 0, 0, true, true, true, NULL);
    return 0;
}
