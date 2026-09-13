// SPDX-License-Identifier: Apache-2.0
// SITL-only ArduCopter RPY output takeover. Native PID still computes upstream.
#pragma once
#define WKSIM_AP_DESIGN
#include "predictive_rate.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

class WksimAPRateAdapter {
public:
    WksimAPRateAdapter()
    {
        const char *name=std::getenv("WKSIM_RATE_ALGORITHM");
        if (!name || std::strcmp(name,"native")==0) _algorithm=0;
        else if (std::strcmp(name,"pid")==0) _algorithm=1;
        else if (std::strcmp(name,"lqr")==0) _algorithm=2;
        else if (std::strcmp(name,"mpc")==0) _algorithm=3;
        else AP_HAL::panic("Invalid wksim rate algorithm");
        const char *path=std::getenv("WKSIM_RATE_TRACE");
        if (path && path[0]) {
            _trace=std::fopen(path,"wx");
            if (!_trace) AP_HAL::panic("Cannot create wksim rate trace");
            std::setvbuf(_trace,nullptr,_IOFBF,65536);
            std::fprintf(_trace,"sample_us,sequence,requested,effective,armed,landed,dt,compute_ns,"
                "p,q,r,p_sp,q_sp,r_sp,p_dot,q_dot,r_dot,raw_x,raw_y,raw_z,"
                "applied_x,applied_y,applied_z,thrust_x,thrust_y,thrust_z,status,solver_sweeps,solver_residual,reset\n");
        } else if (_algorithm) AP_HAL::panic("A rate experiment requires its trace");
    }
    ~WksimAPRateAdapter() { if (_trace) std::fclose(_trace); }

    // Returns true only when predictive output replaced native PID+feedforward.
    bool update(AP_Motors &motors, const Vector3f &target, const Vector3f &gyro, float dt, uint64_t sample)
    {
        const uint64_t began=monotonic_ns();
        const bool ground=motors.get_spool_state()!=AP_Motors::SpoolState::THROTTLE_UNLIMITED;
        const bool reset=ground || !motors.armed() || !_previous_sample || sample<=_previous_sample || sample-_previous_sample>20000;
        double acceleration[3]{},error[3]{};
        const double alpha=1.0-std::exp(-2.0*3.141592653589793*25.0*double(dt));
        for (unsigned i=0;i<3;++i) {
            if (reset) _acceleration[i]=0.0;
            else _acceleration[i]+=alpha*((double(gyro[i])-_previous_gyro[i])/double(dt)-_acceleration[i]);
            acceleration[i]=_acceleration[i];error[i]=double(gyro[i])-double(target[i]);_previous_gyro[i]=double(gyro[i]);
        }
        _previous_sample=sample;
        double output[3]={double(motors.get_roll())+double(motors.get_roll_ff()),
            double(motors.get_pitch())+double(motors.get_pitch_ff()),double(motors.get_yaw())+double(motors.get_yaw_ff())};
        unsigned effective=_algorithm,status=0;
        wksim_rate::Result solved{};
        bool replaced=false;
        if (_algorithm>=2) {
            if (reset) _controller.reset();
            solved=_controller.update(_algorithm,error,acceleration,double(dt));
            if (solved.valid && monotonic_ns()-began<=500000) {
                for (unsigned i=0;i<3;++i) output[i]=solved.torque[i];
                motors.set_roll(float(output[0]));motors.set_pitch(float(output[1]));motors.set_yaw(float(output[2]));
                motors.set_roll_ff(0.f);motors.set_pitch_ff(0.f);motors.set_yaw_ff(0.f);
                replaced=true;
            } else {effective=1;status=solved.valid?2:1;_controller.reset();}
        }
        const uint64_t elapsed=monotonic_ns()-began;
        if (_trace) {
            std::fprintf(_trace,"%llu,%llu,%u,%u,%d,%d,%.9g,%llu",(unsigned long long)sample,
                (unsigned long long)++_sequence,_algorithm,effective,int(motors.armed()),int(ground),double(dt),(unsigned long long)elapsed);
            for (unsigned i=0;i<3;++i) std::fprintf(_trace,",%.9g",double(gyro[i]));
            for (unsigned i=0;i<3;++i) std::fprintf(_trace,",%.9g",double(target[i]));
            for (double value:acceleration) std::fprintf(_trace,",%.17g",value);
            for (double value:output) std::fprintf(_trace,",%.17g",value);
            std::fprintf(_trace,",%.9g,%.9g,%.9g,0,0,%.9g,%u,%u,%.17g,%d\n",
                double(motors.get_roll())+double(motors.get_roll_ff()),
                double(motors.get_pitch())+double(motors.get_pitch_ff()),
                double(motors.get_yaw())+double(motors.get_yaw_ff()),double(motors.get_throttle()),
                status,solved.sweeps,solved.residual,int(reset));
            if (!motors.armed() || _sequence%250==0) std::fflush(_trace);
        }
        return replaced;
    }
private:
    static uint64_t monotonic_ns() {timespec t{};clock_gettime(CLOCK_MONOTONIC,&t);return uint64_t(t.tv_sec)*1000000000ULL+uint64_t(t.tv_nsec);}
    // Lua headers can remap the FILE token to APFS_FILE. Keep the actual
    // stdio return type without depending on that include order.
    decltype(std::fopen("", "")) _trace{nullptr};
    unsigned _algorithm{0};uint64_t _sequence{0},_previous_sample{0};
    double _previous_gyro[3]{},_acceleration[3]{};
    wksim_rate::PredictiveRate _controller;
};
