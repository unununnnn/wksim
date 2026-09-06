// Validation only. The original methods publish into local typed recorders.
// POD fields mirror the used MAVROS message members; no ROS node or wire I/O.
#include <Eigen/Eigen>
#include <prometheus_msgs/msg/uav_command.hpp>
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <string>
#include "upstream_math_utils.h"
namespace prometheus_msgs { using UAVCommand = msg::UAVCommand; }
#include "upstream_command_aliases.inc"
using namespace std;

struct Vec3 { double x=0, y=0, z=0; };
namespace mavros_msgs {
struct PositionTarget {
    static constexpr uint16_t IGNORE_VX=8, IGNORE_VY=16, IGNORE_VZ=32,
        IGNORE_AFX=64, IGNORE_AFY=128, IGNORE_AFZ=256, IGNORE_YAW_RATE=2048;
    static constexpr uint8_t FRAME_LOCAL_NED=1;
    uint16_t type_mask=0;
    uint8_t coordinate_frame=0;
    Vec3 position, velocity, acceleration_or_force;
    float yaw=0, yaw_rate=0;
};
struct AttitudeTarget {
    static constexpr uint8_t IGNORE_ROLL_RATE=1, IGNORE_PITCH_RATE=2, IGNORE_YAW_RATE=4;
    uint8_t type_mask=0;
    struct { double x=0,y=0,z=0,w=1; } orientation;
    float thrust=0;
};
struct GlobalPositionTarget {
    static constexpr uint8_t FRAME_GLOBAL_REL_ALT=6;
    uint8_t coordinate_frame=0;
    uint16_t type_mask=0;
    double latitude=0, longitude=0;
    float altitude=0, yaw=0;
};
}
template<class T> struct Recorder {
    bool published=false;
    T value;
    void publish(const T& message) { value=message; published=true; }
};

class UAV_controller {
public:
    enum CONTROL_STATE { INIT, RC_POS_CONTROL, COMMAND_CONTROL, LAND_CONTROL };
    CONTROL_STATE control_state=COMMAND_CONTROL;
    prometheus_msgs::UAVCommand uav_command;
    struct { array<float,3> position{}; string mode="OFFBOARD"; } uav_state;
    bool quick_land=false, vel_control=false, yaw_control=false, vel_xy_control=false;
    float vel_control_grap=.04f, vel_control_Kp=1.8f, Speed_decision_range=.09f, yaw_decision_range=.0349f;
    Eigen::Vector3d prev_vel_sp=Eigen::Vector3d::Zero(), prev_vel_xy_sp=prev_vel_sp, current_pos=prev_vel_sp;
    Eigen::Vector3d pos_des=prev_vel_sp, vel_des=prev_vel_sp, global_pos_des=prev_vel_sp;
    Eigen::Vector4d u_att=Eigen::Vector4d::Zero();
    double current_yaw=0, prev_yaw_sp=0, yaw_des=0, yaw_rate_des=0;
    int move_orient=0, prev_move_orient=0, move_xy_orient=0, prev_move_xy_orient=0;
    Recorder<mavros_msgs::PositionTarget> px4_setpoint_raw_local_pub;
    Recorder<mavros_msgs::AttitudeTarget> px4_setpoint_raw_attitude_pub;
    Recorder<mavros_msgs::GlobalPositionTarget> px4_setpoint_raw_global_pub;
    void send_pos_cmd_to_px4_original_controller();
    void send_pos_setpoint(const Eigen::Vector3d&, float);
    void send_vel_setpoint(const Eigen::Vector3d&, float);
    void send_vel_setpoint_yaw_rate(const Eigen::Vector3d&, float);
    void send_vel_xy_pos_z_setpoint(const Eigen::Vector3d&, const Eigen::Vector3d&, float);
    void send_vel_xy_pos_z_setpoint_yaw_rate(const Eigen::Vector3d&, const Eigen::Vector3d&, float);
    void send_pos_vel_xyz_setpoint(const Eigen::Vector3d&, const Eigen::Vector3d&, float);
    void send_acc_xyz_setpoint(const Eigen::Vector3d&, float);
    void send_attitude_setpoint(Eigen::Vector4d&);
    void send_global_setpoint(const Eigen::Vector3d&, float);
};
#include "upstream_shaping_methods.inc"

int main() {
    UAV_controller c;
    int reset, mode;
    using Cmd=prometheus_msgs::UAVCommand;
    const int command_modes[]={Cmd::XYZ_POS, Cmd::XYZ_VEL, Cmd::XY_VEL_Z_POS,
        Cmd::TRAJECTORY, Cmd::XYZ_POS, Cmd::XYZ_ATT, Cmd::LAT_LON_ALT, Cmd::XYZ_VEL, Cmd::XY_VEL_Z_POS};
    cout << setprecision(17);
    while (cin >> reset >> mode) {
        if (mode<0 || mode>8) return 2;
        if (reset) c=UAV_controller{};
        for (auto& p:c.uav_state.position) cin >> p;
        for (int i=0;i<3;i++) cin >> c.pos_des[i];
        for (int i=0;i<3;i++) cin >> c.vel_des[i];
        Eigen::Vector3d acceleration;
        for (int i=0;i<3;i++) cin >> acceleration[i];
        for (int i=0;i<4;i++) cin >> c.u_att[i];
        for (int i=0;i<3;i++) cin >> c.global_pos_des[i];
        cin >> c.yaw_des >> c.yaw_rate_des;
        if (!cin) return 2;
        c.px4_setpoint_raw_local_pub.published=false;
        c.px4_setpoint_raw_attitude_pub.published=false;
        c.px4_setpoint_raw_global_pub.published=false;
        c.uav_command.Agent_CMD=prometheus_msgs::UAVCommand::Move;
        c.uav_command.Move_mode=command_modes[mode];
        c.uav_command.Yaw_Rate_Mode=mode>=7;
        if (mode==4) { c.send_acc_xyz_setpoint(acceleration,c.yaw_des); c.vel_control=c.yaw_control=c.vel_xy_control=false; }
        else c.send_pos_cmd_to_px4_original_controller();
        if (c.px4_setpoint_raw_local_pub.published) {
            const auto& p=c.px4_setpoint_raw_local_pub.value;
            cout << "RESULT 1 " << p.type_mask << ' ' << int(p.coordinate_frame);
            for (auto v:{p.position,p.velocity,p.acceleration_or_force}) cout << ' ' << v.x << ' ' << v.y << ' ' << v.z;
            cout << ' ' << p.yaw << ' ' << p.yaw_rate;
        } else if (c.px4_setpoint_raw_attitude_pub.published) {
            const auto& a=c.px4_setpoint_raw_attitude_pub.value;
            cout << "RESULT 2 " << int(a.type_mask) << ' ' << a.orientation.x << ' ' << a.orientation.y << ' ' << a.orientation.z << ' ' << a.orientation.w << ' ' << a.thrust;
        } else if (c.px4_setpoint_raw_global_pub.published) {
            const auto& g=c.px4_setpoint_raw_global_pub.value;
            cout << "RESULT 3 " << g.type_mask << ' ' << int(g.coordinate_frame) << ' ' << g.latitude << ' ' << g.longitude << ' ' << g.altitude << ' ' << g.yaw;
        } else cout << "RESULT 0";
        cout << '\n';
    }
}
