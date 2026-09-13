
#include <Eigen/Eigen>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <vector>
#include <bitset>
#include <memory>
#include <ros/ros.h>
#include <prometheus_msgs/UAVState.h>
#include "math_utils.h"
#include "controller_utils.h"
#include "geometry_utils.h"
#include "printf_utils.h"
// Dependencies parsed; expose controller/filter state without changing bodies.
#define private public
#include "pos_controller_NE.h"
#undef private
int main() {
    ros::NodeHandle nh;
    double mass, hover, kp, kd, tu, tn, limit, tilt;
    if (!(std::cin >> mass >> hover >> kp >> kd >> tu >> tn >> limit >> tilt)) return 2;
    nh.values = {{"ne_gain/quad_mass", mass}, {"ne_gain/hov_percent", hover},
        {"ne_gain/Kp_xy", kp}, {"ne_gain/Kp_z", kp},
        {"ne_gain/Kd_xy", kd}, {"ne_gain/Kd_z", kd},
        {"ne_gain/T_ude", tu}, {"ne_gain/T_ne", tn},
        {"ne_gain/pxy_int_max", limit}, {"ne_gain/pz_int_max", limit},
        {"ne_gain/tilt_angle_max", tilt}};
    std::ostringstream quiet;
    auto *normal = std::cout.rdbuf();
    std::unique_ptr<pos_controller_NE> ne;
    int reset;
    float hz;
    while (std::cin >> reset >> hz) {
        prometheus_msgs::UAVState state;
        Desired_State desired;
        Eigen::Vector3d initial;
        for (int i=0; i<3; ++i) std::cin >> state.position[i];
        for (int i=0; i<3; ++i) std::cin >> state.velocity[i];
        std::cin >> state.attitude_q.w >> state.attitude_q.x >> state.attitude_q.y >> state.attitude_q.z;
        for (int i=0; i<3; ++i) std::cin >> desired.pos[i];
        for (int i=0; i<3; ++i) std::cin >> desired.vel[i];
        for (int i=0; i<3; ++i) std::cin >> desired.acc[i];
        std::cin >> desired.yaw;
        for (int i=0; i<3; ++i) std::cin >> initial[i];
        if (!std::cin || (!ne && !reset)) return 3;
        quiet.str("");
        std::cout.rdbuf(quiet.rdbuf());
        if (reset) {
            // Reconstruct: original init alone does NOT reset filter history.
            ne.reset(new pos_controller_NE());
            ne->init(nh);
            ne->set_initial_pos(initial);
        }
        ne->set_current_state(state);
        ne->set_desired_state(desired);
        Eigen::Vector4d out = ne->update(hz);
        std::cout.rdbuf(normal);
        std::cout << std::defaultfloat << std::setprecision(17);
        auto vector = [](const Eigen::Vector3d& v) { for(int i=0;i<3;++i) std::cout << v[i] << ' '; };
        vector(ne->integral); vector(ne->integral_LLF);
        std::cout << ne->LPF_x.Output_prev << ' ' << ne->LPF_y.Output_prev << ' ' << ne->LPF_z.Output_prev << ' ';
        std::cout << ne->HPF_x.Output_prev << ' ' << ne->HPF_y.Output_prev << ' ' << ne->HPF_z.Output_prev << ' ';
        std::cout << ne->HPF_x.Input_prev << ' ' << ne->HPF_y.Input_prev << ' ' << ne->HPF_z.Input_prev << ' ';
        std::cout << ne->LLF_x.Output_prev << ' ' << ne->LLF_y.Output_prev << ' ' << ne->LLF_z.Output_prev << ' ';
        std::cout << ne->LLF_x.Input_prev << ' ' << ne->LLF_y.Input_prev << ' ' << ne->LLF_z.Input_prev << ' ';
        vector(ne->NoiseEstimator); vector(ne->u_l); vector(ne->u_d); vector(ne->F_des);
        for(int i=0;i<4;++i) std::cout << out[i] << ' ';
        std::cout << '\n';
    }
}
