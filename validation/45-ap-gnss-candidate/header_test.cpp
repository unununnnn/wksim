// Logic-only native C++ fixture. Does not prove AP injection or flight.
#include "SIM_WksimGNSS.h"
#include <string>
struct Data {
    unsigned timestamp_ms = 100;
    double latitude = 40, longitude = 116, altitude = 50;
    double speedN = 0, speedE = 0, speedD = 0;
    double yaw_deg = 0, roll_deg = 0, pitch_deg = 0;
    bool have_lock = true;
    double horizontal_acc = 1, vertical_acc = 1, speed_acc = 0;
    unsigned num_sats = 10;
};
int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    const std::string mode(argv[1]);
    auto &c = WksimGNSS::context();
    Data d;
    c.tick = 200;
    WksimGNSS::sensor_created(0);
    if (mode == "late_generation") { c.tick = 4000; WksimGNSS::sensor_created(0); return 1; }
    if (mode == "generation") {
        WksimGNSS::sample(0, d, 199000);
        WksimGNSS::sensor_created(0);
        return c.generation[0] == 2 && c.source[0] == 0 && !c.fresh[0] ? 0 : 1;
    }
    if (mode == "warmup" || mode == "warmup_repeat") {
        c.tick = 2000; d.timestamp_ms = 0;
        if (WksimGNSS::sample(0, d, 1999000)) return 1;
        if (mode == "warmup_repeat") { c.tick = 2200; WksimGNSS::sample(0, d, 2199000); return 1; }
        c.tick = 2200; d.timestamp_ms = 2000;
        return WksimGNSS::sample(0, d, 2199000) ? 0 : 1;
    }
    if (mode == "truth") { WksimGNSS::model_ms(199000); return 1; }
    if (mode == "future") d.timestamp_ms = 201;
    if (mode == "stale") c.tick = 601;
    if (mode == "hal") { WksimGNSS::sample(0, d, 200000); return 1; }
    if (mode == "nofresh") { WksimGNSS::suppress(0); return 1; }
    WksimGNSS::sample(0, d, (c.tick - 1) * 1000);
    if (mode == "replay") { WksimGNSS::sample(0, d, (c.tick - 1) * 1000); return 1; }
    if (mode == "short") { WksimGNSS::written(0, "abc", 3, 2, false); return 1; }
    if (mode == "budget") { c.tick = 601; d.timestamp_ms = 101; WksimGNSS::sample(0, d, 600000); }
    if (mode == "boundaries") {
        c.tick = 3999; if (WksimGNSS::suppress(0)) return 1;
        c.tick = 4000; if (!WksimGNSS::suppress(0)) return 1;
        c.tick = 5999; if (!WksimGNSS::suppress(0)) return 1;
        c.tick = 6000; if (WksimGNSS::suppress(0)) return 1;
    }
    return 0;
}
