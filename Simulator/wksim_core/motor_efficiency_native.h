// SPDX-License-Identifier: Apache-2.0
#pragma once
extern double wk_motor_eta[4];
void wk_efficiency_sample(int motor, double time, bool major, double omega,
                         double ct, double cm, double thrust, double torque_delta,
                         double spin) noexcept;
