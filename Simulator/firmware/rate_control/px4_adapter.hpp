// SPDX-License-Identifier: Apache-2.0
// wksim's experimental PX4 SITL rate-control seam. Native PID is unchanged.
#pragma once

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <initializer_list>
#include "predictive_rate.hpp"

class WksimRateAdapter {
public:
    WksimRateAdapter()
    {
        const char *name = std::getenv("WKSIM_RATE_ALGORITHM");
        if (!name || std::strcmp(name, "native") == 0) { _algorithm = 0; }
        else if (std::strcmp(name, "pid") == 0) { _algorithm = 1; }
        else if (std::strcmp(name, "lqr") == 0) { _algorithm = 2; }
        else if (std::strcmp(name, "mpc") == 0) { _algorithm = 3; }
        else { _valid = false; }
        const char *path = std::getenv("WKSIM_RATE_TRACE");
        if (path && path[0]) {
            // Exclusive creation preserves earlier evidence. The experiment
            // supervisor supplies a new absolute path in its private run.
            _trace = std::fopen(path, "wx");
            if (!_trace) { _valid = false; }
            else {
                std::setvbuf(_trace, nullptr, _IOFBF, 65536);
                std::fprintf(_trace, "sample_us,sequence,requested,effective,armed,landed,dt,compute_ns,"
                    "p,q,r,p_sp,q_sp,r_sp,p_dot,q_dot,r_dot,"
                    "raw_x,raw_y,raw_z,applied_x,applied_y,applied_z,thrust_x,thrust_y,thrust_z,"
                    "status,solver_sweeps,solver_residual,reset\n");
            }
        } else if (_algorithm != 0) { _valid = false; }
    }

    ~WksimRateAdapter() { if (_trace) { std::fclose(_trace); } }
    bool valid() const { return _valid; }

    matrix::Vector3f update(RateControl &pid, const matrix::Vector3f &rates,
        const matrix::Vector3f &target, const matrix::Vector3f &acceleration,
        float dt, bool landed, bool armed, uint64_t sample_us)
    {
        _rates = rates; _target = target; _acceleration = acceleration;
        _dt = dt; _landed = landed; _armed = armed; _sample_us = sample_us;
        const uint64_t began = monotonic_ns();
        _effective = _algorithm; _status = 0; _solver = {};
        _reset = landed || !armed || sample_us <= _previous_sample ||
                 (_previous_sample && sample_us-_previous_sample > 20000);
        _previous_sample = sample_us;
        if (_algorithm < 2) {
            // The equivalent adapter executes the native object once with
            // its original gains, integrator, saturation and reset ordering.
            _raw = pid.update(rates, target, acceleration, dt, landed);
        } else {
            if (_reset) { _predictive.reset(); }
            double error[3]{}, derivative[3]{};
            for (int i = 0; i < 3; ++i) {
                error[i] = double(rates(i))-double(target(i));
                derivative[i] = double(acceleration(i));
            }
            _solver = _predictive.update(unsigned(_algorithm), error, derivative, double(dt));
            if (_solver.valid && monotonic_ns()-began <= 500000) {
                for (int i = 0; i < 3; ++i) { _raw(i) = float(_solver.torque[i]); }
                pid.resetIntegral(); // Inactive native PID must not retain stale integral.
            } else {
                // Explicit recorded fallback; any airborne fallback invalidates
                // a LQR/MPC comparison run. Never label native output as MPC.
                _status = _solver.valid ? 2 : 1;
                _effective = 1;
                _predictive.reset();
                _raw = pid.update(rates, target, acceleration, dt, landed);
            }
        }
        _compute_ns = monotonic_ns() - began;
        ++_sequence;
        return _raw;
    }

    void record_applied(const matrix::Vector3f &torque, const matrix::Vector3f &thrust)
    {
        if (!_trace) { return; }
        std::fprintf(_trace, "%llu,%llu,%d,%d,%d,%d,%.9g,%llu",
            (unsigned long long)_sample_us, (unsigned long long)_sequence,
            _algorithm, _effective, (int)_armed, (int)_landed, (double)_dt,
            (unsigned long long)_compute_ns);
        for (const auto &vector : {_rates, _target, _acceleration, _raw, torque, thrust}) {
            for (int i = 0; i < 3; ++i) { std::fprintf(_trace, ",%.9g", (double)vector(i)); }
        }
        std::fprintf(_trace, ",%d,%u,%.17g,%d\n", _status, _solver.sweeps, _solver.residual, int(_reset));
        // Flush on ground and in bounded batches. Logging is identical for
        // both selectors; source/sample clocks remain native simulation time.
        if (!_armed || _sequence % 250 == 0) { std::fflush(_trace); }
    }

private:
    static uint64_t monotonic_ns()
    {
        timespec now{};
        clock_gettime(CLOCK_MONOTONIC, &now);
        return uint64_t(now.tv_sec) * 1000000000ULL + uint64_t(now.tv_nsec);
    }
    FILE *_trace{nullptr};
    bool _valid{true}, _landed{true}, _armed{false}, _reset{false};
    int _algorithm{0}, _effective{0}, _status{0};
    float _dt{0.f};
    uint64_t _sample_us{0}, _sequence{0}, _compute_ns{0}, _previous_sample{0};
    matrix::Vector3f _rates{}, _target{}, _acceleration{}, _raw{};
    wksim_rate::PredictiveRate _predictive;
    wksim_rate::Result _solver{};
};
