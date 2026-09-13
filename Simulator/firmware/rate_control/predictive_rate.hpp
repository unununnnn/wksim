// SPDX-License-Identifier: Apache-2.0
// Pure C++14 position-free rate control. No firmware, ROS, UE or heap dependency.
#pragma once
#include <cmath>
#ifdef WKSIM_AP_DESIGN
#include "generated_ap_design.hpp"
#else
#include "generated_design.hpp"
#endif

namespace wksim_rate {
struct Result {
    double torque[3]{};
    unsigned sweeps{0};
    double residual{0.0};
    bool valid{false};
};

class PredictiveRate {
public:
    void reset()
    {
        for (auto &axis : _warm) { for (double &value : axis) { value = 0.0; } }
    }

    Result update(unsigned algorithm, const double error[3], const double acceleration[3], double dt)
    {
        Result result{};
        if ((algorithm != 2 && algorithm != 3) || !std::isfinite(dt) ||
            std::fabs(dt-design_dt) > design_dt*0.05) { reset(); return result; }
        for (unsigned axis = 0; axis < 3; ++axis) {
            if (!std::isfinite(error[axis]) || !std::isfinite(acceleration[axis])) { reset(); return result; }
        }
        for (unsigned axis = 0; axis < 3; ++axis) {
            const double x[2] = {error[axis], acceleration[axis]};
            if (algorithm == 2) {
                result.torque[axis] = bound(-gain[axis][0]*x[0]-gain[axis][1]*x[1]);
                continue;
            }
            double f[horizon]{};
            double u[horizon]{};
            for (unsigned i = 0; i < horizon; ++i) {
                f[i] = linear[axis][i][0]*x[0]+linear[axis][i][1]*x[1];
                u[i] = _warm[axis][i+1 < horizon ? i+1 : i];
            }
            bool converged = false;
            for (unsigned sweep = 1; sweep <= 48; ++sweep) {
                for (unsigned i = 0; i < horizon; ++i) {
                    double gradient = f[i];
                    for (unsigned j = 0; j < horizon; ++j) { gradient += hessian[axis][i][j]*u[j]; }
                    u[i] = bound(u[i]-gradient/hessian[axis][i][i]);
                }
                double residual = 0.0;
                for (unsigned i = 0; i < horizon; ++i) {
                    double gradient = f[i];
                    for (unsigned j = 0; j < horizon; ++j) { gradient += hessian[axis][i][j]*u[j]; }
                    // Box KKT: only inward feasible descent counts at a bound.
                    if (u[i] <= -torque_limit && gradient > 0.0) { gradient = 0.0; }
                    if (u[i] >= torque_limit && gradient < 0.0) { gradient = 0.0; }
                    if (std::fabs(gradient) > residual) { residual = std::fabs(gradient); }
                }
                if (sweep > result.sweeps) { result.sweeps = sweep; }
                result.residual = residual;
                if (residual <= 1e-5) {
                    converged = true; break;
                }
            }
            if (!converged) { reset(); return result; }
            for (unsigned i = 0; i < horizon; ++i) { _warm[axis][i] = u[i]; }
            result.torque[axis] = u[0];
        }
        for (double value : result.torque) {
            if (!std::isfinite(value)) { reset(); return Result{}; }
        }
        result.valid = true;
        return result;
    }

private:
    static double bound(double value)
    {
        return value < -torque_limit ? -torque_limit : value > torque_limit ? torque_limit : value;
    }
    double _warm[3][horizon]{};
};
}
