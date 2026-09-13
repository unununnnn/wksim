
#pragma once
#include <string>
namespace prometheus_msgs {
struct UAVState {
    float position[3]{};
    float velocity[3]{};
    struct Quaternion { double w{1}, x{}, y{}, z{}; } attitude_q;
    std::string mode;
};
}
