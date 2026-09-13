// SPDX-License-Identifier: GPL-3.0-or-later
// Flight scheduling extension of the retained #109 native sensor boundary.
#pragma once
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <cstdint>

namespace WksimGNSS {
struct Context {
    unsigned long long tick = 0;
    unsigned long long start = 0, end = 0;
    bool scheduled = false;
    unsigned long long born[2] = {};
    bool fresh[2] = {};
    unsigned long long source[2] = {};
    bool warmed[2] = {};
    unsigned generation[2] = {};
    FILE *trace = nullptr;
};
inline Context &context() { static Context value; return value; }
inline FILE *trace()
{
    auto &c = context();
    if (!c.trace) {
        const char *path = getenv("WKSIM_GNSS_TRACE");
        c.trace = path ? fopen(path, "wx") : nullptr;
        if (!c.trace) { fprintf(stderr, "WKSIM missing/existing trace\n"); exit(109); }
    }
    return c.trace;
}
inline void flush() { if (fflush(trace()) != 0 || ferror(trace())) exit(109); }
inline void hex(const char *p, size_t n)
{
    for (size_t i=0; i<n; i++) fprintf(trace(), "%02x", unsigned(uint8_t(p[i])));
}
inline void fail(const char *reason)
{
    fprintf(trace(), "FAIL\t%llu\t%s\n", context().tick, reason);
    flush();
    exit(109);
}
inline void plan(const char *suffix)
{
    auto &c = context();
    const char *key = "\"gnss_plan\":\"";
    if (strncmp(suffix, key, strlen(key)) != 0) {
        if (c.scheduled || strstr(suffix, "gnss_plan")) fail("missing_or_misplaced_plan");
        return;
    }
    unsigned long long start = 0, end = 0;
    int consumed = 0;
    if (sscanf(suffix, "\"gnss_plan\":\"%llu:%llu\",%n", &start, &end, &consumed) != 2 ||
        !consumed || strstr(suffix + consumed, "gnss_plan")) fail("invalid_plan");
    char canonical[128];
    snprintf(canonical, sizeof(canonical), "\"gnss_plan\":\"%llu:%llu\",", start, end);
    if (strncmp(suffix, canonical, strlen(canonical))) fail("noncanonical_plan");
    if (!c.scheduled) {
        if (start < c.tick + 1000 || start > 165000 || end != start + 15000 || end > 180000)
            fail("late_or_invalid_plan");
        c.start = start; c.end = end; c.scheduled = true;
        fprintf(trace(), "PLAN\t%llu\t%llu\t%llu\n", c.tick, start, end); flush();
    } else if (c.start != start || c.end != end) fail("plan_changed");
}
inline void receive(const char *raw)
{
    // Log before validating. Canonical prefix disallows duplicate identity fields.
    fprintf(trace(), "JSON\t"); hex(raw, strlen(raw)); fprintf(trace(), "\n"); flush();
    char run[33] = {}, epoch[33] = {};
    unsigned long long tick = 0;
    int consumed = 0;
    if (sscanf(raw, "{\"wksim\":\"%32[0-9a-f]:%32[0-9a-f]:1:%llu\",%n",
               run, epoch, &tick, &consumed) != 3 || consumed == 0 ||
        strlen(run) != 32 || strlen(epoch) != 32 ||
        strstr(raw + consumed, "wksim") != nullptr) fail("invalid_envelope");
    const char *expected_run = getenv("WKSIM_RUN");
    const char *expected_epoch = getenv("WKSIM_EPOCH");
    if (!expected_run || !expected_epoch || strcmp(run, expected_run) ||
        strcmp(epoch, expected_epoch)) fail("foreign_identity");
    char canonical[128];
    snprintf(canonical, sizeof(canonical), "{\"wksim\":\"%s:%s:1:%llu\",", run, epoch, tick);
    if (strncmp(raw, canonical, strlen(canonical)) ||
        tick != context().tick + 1 || tick > 180000) fail("nonconsecutive_tick");
    context().tick = tick;
    context().fresh[0] = context().fresh[1] = false;
    plan(raw + consumed);
}
inline void timestamp(double seconds, bool no_lockstep, bool no_time_sync)
{
    if (!std::isfinite(seconds) || std::abs(seconds * 1000000.0 - context().tick * 1000.0) > 0.0001 ||
        no_lockstep || no_time_sync) fail("timestamp_or_lockstep");
}
inline uint32_t model_ms(uint64_t truth_us)
{
    if (truth_us != context().tick * 1000) fail("truth_tick_mismatch");
    return uint32_t(context().tick);
}
inline void sensor_created(unsigned instance)
{
    if (instance > 1) fail("instance");
    auto &c = context();
    if (c.scheduled && c.tick >= c.start && c.tick > c.end + 30000)
        fail("sensor_recreated_outside_recovery_window");
    c.generation[instance]++;
    c.born[instance] = c.tick;
    c.source[instance] = 0;
    c.warmed[instance] = false;
    c.fresh[instance] = false;
    fprintf(trace(), "GENERATION\t%llu\t%u\t%u\n", c.tick, instance, c.generation[instance]); flush();
}
template <typename Data> inline bool sample(unsigned instance, const Data &d, uint64_t hal_us)
{
    if (instance > 1) fail("instance");
    auto &c = context();
    fprintf(trace(), "SAMPLE\t%llu\t%u\t%u\t%llu\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%u\t%.17g\t%.17g\t%.17g\t%u\t%u\n",
            c.tick, instance, unsigned(d.timestamp_ms), (unsigned long long)hal_us,
            d.latitude, d.longitude, double(d.altitude), d.speedN, d.speedE, d.speedD,
            d.yaw_deg, d.roll_deg, d.pitch_deg, unsigned(d.have_lock),
            double(d.horizontal_acc), double(d.vertical_acc), double(d.speed_acc), unsigned(d.num_sats), c.generation[instance]);
    flush();
    // timestamp_ms is the native delayed/interpolated GPS_Data time, not UBX TOW.
    // sim_update runs before stop_clock: HAL still names the previous tick.
    if (hal_us != (c.tick - 1) * 1000) fail("hal_phase_mismatch");
    // Native interpolation initially uses a zero-filled history slot. Preserve
    // the rejected sample and wait for a genuine captured endpoint.
    if (d.timestamp_ms == 0 && !c.warmed[instance]) {
        c.warmed[instance] = true;
        fprintf(trace(), "WARMUP\t%llu\t%u\n", c.tick, instance); flush();
        return false;
    }
    if (d.timestamp_ms < c.born[instance] || d.timestamp_ms > c.tick ||
        c.tick - d.timestamp_ms > 500 || d.timestamp_ms <= c.source[instance]) fail("stale_or_replayed_sample");
    if (!std::isfinite(d.latitude) || !std::isfinite(d.longitude) || !std::isfinite(d.altitude) ||
        !std::isfinite(d.speedN) || !std::isfinite(d.speedE) || !std::isfinite(d.speedD)) fail("invalid_sample");
    c.source[instance] = d.timestamp_ms;
    c.fresh[instance] = true;
    return true;
}
inline bool suppress(unsigned instance)
{
    if (instance > 1 || !context().fresh[instance]) fail("write_without_fresh_sample");
    return context().scheduled && context().tick >= context().start && context().tick < context().end;
}
inline void written(unsigned instance, const char *p, size_t size, long result, bool suppressed)
{
    fprintf(trace(), "WRITE\t%llu\t%u\t%u\t%ld\t", context().tick, instance, unsigned(suppressed), result);
    hex(p, size); fprintf(trace(), "\t%u\n", context().generation[instance]); flush();
    if (!suppressed && result != long(size)) fail("short_or_failed_serial_write");
}
}
