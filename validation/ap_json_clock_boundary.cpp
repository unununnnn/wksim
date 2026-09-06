// The algorithm lives ONLY in the generated includes extracted from AP source.
#include <cfloat>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string>
using std::isfinite;
#include "positive.inc"

class Aircraft {
public:
    uint64_t time_now_us = 0, last_time_us = 0, frame_time_us = 1000;
    uint64_t last_timestamp_us = 0, frame_counter = 0;
    double last_timestamp_s = 0;
    uint32_t last_received_bitmask = 0x55;
    bool use_time_sync = true;
    struct { double timestamp_s = 0; bool no_lockstep = false; } state;
    unsigned sync_calls = 0, adjust_calls = 0;
    float adjusted_rate = 0;
    void sync_frame_time() { ++sync_calls; }
    void adjust_frame_time(float rate) { ++adjust_calls; adjusted_rate = rate; }
    void time_advance();
    void input(double timestamp) {
        state.timestamp_s = timestamp;
#include "json_clock.inc"
    }
};
#include "aircraft_time.inc"

static unsigned assertions = 0;
static void equal(uint64_t got, uint64_t want, const std::string &label) {
    ++assertions;
    if (got != want) {
        std::cerr << "FAIL " << label << " actual=" << got << " expected=" << want << '\n';
        std::exit(1);
    }
}

static void sequence(unsigned count, uint64_t step, bool sync = true, bool no_lockstep = false) {
    Aircraft a;
    a.use_time_sync = sync;
    a.state.no_lockstep = no_lockstep;
    uint64_t first_bad = 0, first_actual = 0;
    for (unsigned i = 1; i <= count; ++i) {
        a.input(static_cast<double>(i * step) / 1000000.0);
        if (a.time_now_us != i * step && first_bad == 0) {
            first_bad = i;
            first_actual = a.time_now_us;
        }
    }
    std::cout << "samples=" << count << " step_us=" << step << " final_us=" << a.time_now_us
              << " expected_us=" << count * step << " first_bad_tick=" << first_bad
              << " first_bad_actual_us=" << first_actual << '\n';
    equal(a.time_now_us, count * step, "sequence final clock");
    equal(first_bad, 0, "every tick exact");
    equal(a.frame_counter, count, "frame count");
    equal(a.sync_calls, sync ? count : 0, "sync calls");
    equal(a.adjust_calls, sync && !no_lockstep ? count : 0, "adjust calls");
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    const std::string name = argv[1];
    if (name == "1ms-10004") sequence(10004, 1000);
    else if (name == "1ms-long") sequence(200000, 1000);
    else if (name == "4ms") sequence(25001, 4000);
    else if (name == "sync-disabled") sequence(10004, 1000, false);
    else if (name == "no-lockstep") sequence(10004, 1000, true, true);
    else if (name == "duplicate") {
        Aircraft a;
        a.input(0.001);
        const auto calls = a.sync_calls;
        for (unsigned i = 0; i < 10004; ++i) a.input(0.001);
        equal(a.time_now_us, 1000, "duplicate does not advance");
        equal(a.sync_calls, calls, "duplicate does not call time_advance");
        equal(a.frame_counter, 10005, "duplicate frame count");
    } else if (name == "fractional") {
        Aircraft a;
        a.input(0.001);
        // 0.2us is positive by AP's epsilon, but rounds to the same absolute us.
        a.input(0.0010002);
        equal(a.time_now_us, 1000, "same quantized microsecond cannot add a frame");
        equal(a.sync_calls, 1, "same quantized microsecond cannot time_advance");
        equal(a.adjust_calls, 1, "same quantized microsecond cannot adjust");
    } else if (name == "fractional-drift") {
        Aircraft a;
        a.input(0.001);
        // Third-us inputs avoid exact half-us ties: binary64 seconds cannot
        // in general represent a decimal half-us exactly. The oracle remains
        // integer arithmetic independent of the source's quantization.
        for (uint64_t i = 1; i <= 20000; ++i) {
            const uint64_t thirds = 3000 + 4 * i;
            a.input(static_cast<double>(thirds) / 3000000.0);
            equal(a.time_now_us, (thirds + 1) / 3, "fractional absolute quantization tick " + std::to_string(i));
        }
    } else if (name == "invalid") {
        Aircraft a;
        a.input(0.001);
        for (double value : {-1.0, std::numeric_limits<double>::infinity(),
                             std::numeric_limits<double>::quiet_NaN(), 1.0e300}) {
            a.input(value);
            equal(a.time_now_us, 1000, "invalid input cannot advance boot time");
            equal(a.frame_counter, 1, "invalid input cannot advance frame");
        }
        a.input(0.002);
        equal(a.time_now_us, 2000, "invalid input cannot poison next timestamp");
    } else if (name == "overflow") {
        Aircraft a;
        a.time_now_us = UINT64_MAX - 500;
        a.last_time_us = a.time_now_us;
        a.input(0.001);
        equal(a.time_now_us, UINT64_MAX - 500, "boot accumulator cannot wrap");
        equal(a.frame_counter, 0, "overflow input rejected");
    } else if (name == "reset") {
        Aircraft a;
        a.time_now_us = 7000000;
        a.last_time_us = 7000000;
        a.input(0.01);
        equal(a.time_now_us, 7010000, "old boot bias");
        const auto calls = a.sync_calls;
        a.input(0.002);
        equal(a.time_now_us, 7010000, "reset preserves boot time");
        equal(a.last_received_bitmask, 0, "reset clears bitmask");
        equal(a.sync_calls, calls, "reset cannot time_advance");
        for (uint64_t i = 1; i <= 10004; ++i) {
            a.input(static_cast<double>(2000 + i * 1000) / 1000000.0);
            equal(a.time_now_us, 7010000 + i * 1000, "post-reset increment " + std::to_string(i));
        }
    } else return 2;
    std::cout << "PASS " << name << " assertions=" << assertions << '\n';
}
