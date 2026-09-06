// Diagnostic only: actual generated DDS types and extracted firmware methods.
// Location and the external-control endpoint are typed recorders, not the FC.
#include <ardupilot_msgs/msg/GlobalPosition.h>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>

constexpr char MAP_FRAME[] = "map";
constexpr float pi = 3.14159265358979323846f;
float radians(float degrees) { return degrees * (pi / 180.0f); }
float wrap_PI(float angle) { return std::remainder(angle, 2 * pi); }
struct Location {
    enum class AltFrame { ABSOLUTE, ABOVE_HOME, ABOVE_TERRAIN };
    int32_t latitude, longitude, altitude;
    AltFrame frame;
    Location(int32_t lat, int32_t lon, int32_t alt, AltFrame f)
        : latitude(lat), longitude(lon), altitude(alt), frame(f) {}
};
struct Endpoint {
    bool accepted=true;
    unsigned position_calls=0, yaw_calls=0;
    float yaw=0;
    Location loc{0, 0, 0, Location::AltFrame::ABSOLUTE};
    bool set_global_position(const Location& value) { ++position_calls; loc=value; return accepted; }
    bool set_global_position_and_yaw(const Location& value, float angle) {
        ++yaw_calls; loc=value; yaw=angle; return accepted;
    }
};
Endpoint recorder;
namespace AP {
    Endpoint* instance=&recorder;
    Endpoint* externalcontrol() { return instance; }
}
class AP_DDS_External_Control {
public:
    static bool handle_global_position_control(ardupilot_msgs_msg_GlobalPosition&);
    static bool convert_alt_frame(uint8_t, Location::AltFrame&);
};
#include "firmware_position_methods.inc"

unsigned checks=0;
void require(bool condition, const char* description) {
    if (!condition) throw std::runtime_error(description);
    ++checks;
}
ardupilot_msgs_msg_GlobalPosition valid() {
    ardupilot_msgs_msg_GlobalPosition msg{};
    std::strcpy(msg.header.frame_id, "map");
    msg.coordinate_frame=6;
    msg.type_mask=0xDF8;
    msg.latitude=40.0;
    msg.longitude=116.0;
    msg.altitude=3.75f;
    return msg;
}
void rejected(ardupilot_msgs_msg_GlobalPosition msg) {
    recorder=Endpoint{};
    require(!AP_DDS_External_Control::handle_global_position_control(msg), "Invalid request was accepted");
    require(recorder.position_calls + recorder.yaw_calls == 0, "Rejected input reached control endpoint");
}
int main() {
    for (const auto frame : {5, 6, 11}) {
        auto msg=valid();
        msg.coordinate_frame=frame;
        msg.yaw=std::numeric_limits<float>::quiet_NaN(); // ignored fields stay ignored
        recorder=Endpoint{};
        require(AP_DDS_External_Control::handle_global_position_control(msg), "Position-only regression");
        require(recorder.position_calls == 1 && recorder.yaw_calls == 0, "Position-only dispatch");
        require(recorder.loc.latitude == 400000000 && recorder.loc.longitude == 1160000000
                && recorder.loc.altitude == 375, "Position quantization");
        const auto expected=frame == 5 ? Location::AltFrame::ABSOLUTE :
                            frame == 6 ? Location::AltFrame::ABOVE_HOME : Location::AltFrame::ABOVE_TERRAIN;
        require(recorder.loc.frame == expected, "Altitude frame mapping");
    }
    for (float yaw : {0.0f, pi/2, -pi/2, 3.0f, -3.0f}) {
        auto msg=valid();
        msg.type_mask=0x9F8;
        msg.yaw=yaw;
        recorder=Endpoint{};
        require(AP_DDS_External_Control::handle_global_position_control(msg), "Yaw target rejected");
        require(recorder.position_calls == 0 && recorder.yaw_calls == 1, "Yaw target silently dropped");
        require(std::abs(std::remainder(recorder.yaw - (pi/2-yaw), 2*pi)) < 1e-5f, "ENU to NED yaw");
    }
    for (int bit=0; bit<16; ++bit) {
        if (bit == 10) continue; // the one optional supported yaw ignore bit
        auto msg=valid();
        msg.type_mask ^= 1U << bit;
        rejected(msg);
    }
    for (auto frame : {0, 1, 7, 255}) { auto msg=valid(); msg.coordinate_frame=frame; rejected(msg); }
    auto msg=valid(); std::strcpy(msg.header.frame_id, "base_link"); rejected(msg);
    for (double value : {std::nan(""), double(INFINITY), double(-INFINITY), 90.01, -90.01}) {
        msg=valid(); msg.latitude=value; rejected(msg);
    }
    for (double value : {std::nan(""), double(INFINITY), double(-INFINITY), 180.01, -180.01}) {
        msg=valid(); msg.longitude=value; rejected(msg);
    }
    for (float value : {std::nanf(""), INFINITY, -INFINITY, 21474836.0f, -21474836.0f,
                        std::numeric_limits<float>::max()}) {
        msg=valid(); msg.altitude=value; rejected(msg);
    }
    for (float value : {std::nanf(""), INFINITY, -INFINITY}) {
        msg=valid(); msg.type_mask=0x9F8; msg.yaw=value; rejected(msg);
    }
    for (const auto mask : {0xDF8, 0x9F8}) {
        msg=valid(); msg.type_mask=mask;
        AP::instance=nullptr;
        require(!AP_DDS_External_Control::handle_global_position_control(msg), "Missing endpoint accepted");
        AP::instance=&recorder;
        recorder=Endpoint{};
        recorder.accepted=false;
        require(!AP_DDS_External_Control::handle_global_position_control(msg), "Endpoint failure discarded");
        require(recorder.position_calls + recorder.yaw_calls == 1, "Wrong endpoint dispatch count");
    }
    std::cout << "{\"status\":\"pass\",\"assertions\":" << checks << "}\n";
}
