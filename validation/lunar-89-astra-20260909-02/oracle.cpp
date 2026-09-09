
#include <Eigen/Eigen>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <vector>
#include <ros/ros.h>
#include <prometheus_msgs/UAVState.h>
#include "math_utils.h"
#include "controller_utils.h"
#include "geometry_utils.h"
#include "printf_utils.h"
#define private public
#include "pos_controller_UDE.h"
#undef private
int main() {
    ros::NodeHandle nh;
    double mass, hover, kp, kd, t, limit, tilt;
    if (!(std::cin >> mass >> hover >> kp >> kd >> t >> limit >> tilt)) return 2;
    nh.values = {{"ude_gain/quad_mass",mass},{"ude_gain/hov_percent",hover},
        {"ude_gain/Kp_xy",kp},{"ude_gain/Kp_z",kp},{"ude_gain/Kd_xy",kd},
        {"ude_gain/Kd_z",kd},{"ude_gain/T_ude",t},{"ude_gain/pxy_int_max",limit},
        {"ude_gain/pz_int_max",limit},{"ude_gain/tilt_angle_max",tilt}};
    std::ostringstream quiet;
    auto *normal = std::cout.rdbuf(quiet.rdbuf());
    pos_controller_UDE ude;
    ude.init(nh);
    std::cout.rdbuf(normal);
    int reset;
    float hz;
    while (std::cin >> reset >> hz) {
        prometheus_msgs::UAVState state;
        Desired_State desired;
        for (int i=0;i<3;++i) std::cin >> state.position[i];
        for (int i=0;i<3;++i) std::cin >> state.velocity[i];
        std::cin >> state.attitude_q.w >> state.attitude_q.x >> state.attitude_q.y >> state.attitude_q.z;
        for (int i=0;i<3;++i) std::cin >> desired.pos[i];
        for (int i=0;i<3;++i) std::cin >> desired.vel[i];
        for (int i=0;i<3;++i) std::cin >> desired.acc[i];
        std::cin >> desired.yaw;
        if (!std::cin) return 3;
        quiet.str("");
        std::cout.rdbuf(quiet.rdbuf());
        if (reset) ude.init(nh);
        ude.set_current_state(state);
        ude.set_desired_state(desired);
        auto out = ude.update(hz);
        std::cout.rdbuf(normal);
        std::cout << std::defaultfloat << std::setprecision(17);
        for (int i=0;i<3;++i) std::cout << ude.integral[i] << ' ';
        for (int i=0;i<3;++i) std::cout << ude.u_l[i] << ' ';
        for (int i=0;i<3;++i) std::cout << ude.u_d[i] << ' ';
        for (int i=0;i<3;++i) std::cout << ude.F_des[i] << ' ';
        for (int i=0;i<4;++i) std::cout << out[i] << ' ';
        std::cout << '\n';
    }
}
