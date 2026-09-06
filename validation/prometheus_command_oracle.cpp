// Validation only: compile the pinned original calculation/acceptance methods.
// ROS2 generated types replace ROS1 types; publishing records a local bool only.
#include <Eigen/Core>
#include <prometheus_msgs/msg/uav_command.hpp>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <memory>
#include <string>

namespace prometheus_msgs { using UAVCommand = msg::UAVCommand; }
#include "upstream_command_aliases.inc"
using namespace std;
constexpr auto RED = "", TAIL = "";

struct StopValue { bool data = false; };
struct StopPublisher {
    int last = -1;
    void publish(StopValue value) { last = value.data; }
};

class UAV_controller {
public:
    enum CONTROL_STATE { INIT, RC_POS_CONTROL, COMMAND_CONTROL, LAND_CONTROL };
    CONTROL_STATE control_state = COMMAND_CONTROL;
    prometheus_msgs::UAVCommand uav_command, uav_command_last;
    Eigen::Vector3d pos_des = Eigen::Vector3d::Zero(), vel_des = pos_des, acc_des = pos_des;
    Eigen::Vector3d global_pos_des = pos_des, uav_pos = pos_des, Hover_position = pos_des;
    Eigen::Vector3d Takeoff_position{9., 18., 2.};
    Eigen::Vector4d u_att = Eigen::Vector4d::Zero();
    double yaw_des = 0, yaw_rate_des = 0, uav_yaw = 0, Hover_yaw = 0;
    float Takeoff_height = 3.;
    bool enable_external_control = true;
    struct { double x = 1., y = 2.; } offset_pose;
    string node_name = "oracle";
    StopValue stop_control_state;
    StopPublisher stop_control_state_pub;
    UAV_controller() { uav_command.agent_cmd = prometheus_msgs::UAVCommand::INIT_POS_HOVER; }
    void set_command_des();
    void rotation_yaw(double, float[2], float[2]);
    void uav_cmd_cb(const prometheus_msgs::UAVCommand::ConstSharedPtr &);
};

#include "upstream_command_methods.inc"

int main() {
    UAV_controller controller;
    int reset, agent, level, mode, yaw_rate_mode;
    uint32_t id;
    cout << setprecision(17);
    while (cin >> reset >> agent >> level >> mode >> id) {
        if (reset) controller = UAV_controller{};
        prometheus_msgs::UAVCommand command;
        command.agent_cmd = agent;
        command.control_level = level;
        command.move_mode = mode;
        command.command_id = id;
        for (int i = 0; i < 3; i++) cin >> controller.uav_pos[i];
        cin >> controller.uav_yaw;
        for (auto& v: command.position_ref) cin >> v;
        for (auto& v: command.velocity_ref) cin >> v;
        for (auto& v: command.acceleration_ref) cin >> v;
        cin >> command.yaw_ref >> yaw_rate_mode >> command.yaw_rate_ref;
        command.yaw_rate_mode = yaw_rate_mode;
        for (auto& v: command.att_ref) cin >> v;
        cin >> command.latitude >> command.longitude >> command.altitude;
        if (!cin) return 2;
        controller.stop_control_state_pub.last = -1;
        controller.uav_cmd_cb(make_shared<const prometheus_msgs::UAVCommand>(command));
        if (controller.control_state == UAV_controller::COMMAND_CONTROL) controller.set_command_des();
        cout << "RESULT " << controller.control_state << ' ' << controller.stop_control_state_pub.last;
        for (auto vector: {controller.pos_des, controller.vel_des, controller.acc_des})
            for (int i=0; i<3; i++) cout << ' ' << vector[i];
        cout << ' ' << controller.yaw_des << ' ' << controller.yaw_rate_des;
        for (int i=0; i<4; i++) cout << ' ' << controller.u_att[i];
        for (int i=0; i<3; i++) cout << ' ' << controller.global_pos_des[i];
        cout << '\n';
    }
}
