// SPDX-License-Identifier: Apache-2.0
// Separate candidate: the baseline wrapper and generated source stay unchanged.
#include "motor_efficiency_native.h"
#define wk_model_create wk_base_create
#define wk_model_destroy wk_base_destroy
#define wk_model_step wk_base_step
#include "base_wrapper.cpp"
#undef wk_model_create
#undef wk_model_destroy
#undef wk_model_step
#include <cstdint>

double wk_motor_eta[4] = {1., 1., 1., 1.};
namespace {
void* owner = nullptr;
bool used = false, stepping = false;
uint64_t ticks = 0;
int samples = 0;
double stages[160] = {};
}

void wk_efficiency_sample(int motor, double time, bool major, double omega,
                         double ct, double cm, double thrust, double torque_delta,
                         double spin) noexcept {
    if (!stepping || samples >= 16 || motor < 0 || motor >= 4) { samples = 17; return; }
    double* row = stages + samples++ * 10;
    const double values[] = {time, double(major), double(motor), wk_motor_eta[motor],
                             omega, ct*omega*omega, cm*omega*omega, thrust, torque_delta, spin};
    std::copy_n(values, 10, row);
}

extern "C" {
void* wk_model_create() noexcept {
    if (used) return nullptr;
    used = true;
    owner = wk_base_create();
    return owner;
}

void wk_model_destroy(void* handle) noexcept {
    if (!handle || handle != owner || stepping) return;
    wk_base_destroy(handle);
    owner = nullptr;
    std::fill_n(wk_motor_eta, 4, 1.);
}

int wk_model_set_efficiency(void* handle, int motor, double eta) noexcept {
    if (!handle || handle != owner || stepping || motor != 0 ||
        !std::isfinite(eta) || (eta != 1. && eta != .97)) return 1;
    wk_motor_eta[motor] = eta;
    return 0;
}

int wk_model_get_efficiency(void* handle, double* output, int count) noexcept {
    if (!handle || handle != owner || !output || count != 4) return 1;
    std::copy_n(wk_motor_eta, 4, output);
    return 0;
}

int wk_model_random_state(void* handle, uint32_t* output, int count) noexcept {
    if (!handle || handle != owner || !output || count != 17 || stepping) return 1;
    static_cast<MulticopterModelClass*>(handle)->wk_random_state(output);
    return 0;
}

int wk_model_efficiency_stages(void* handle, double* output, int count) noexcept {
    if (!handle || handle != owner || !output || count != 160 || stepping || samples != 16) return -1;
    std::copy_n(stages, 160, output);
    return 16;
}

uint64_t wk_model_tick(void* handle) noexcept {
    return handle && handle == owner ? ticks : UINT64_MAX;
}

int wk_model_step(void* handle, const double* commands, int count, int steps,
                  double* output, int output_count) noexcept {
    if (!handle || handle != owner || stepping || steps != 1) return 1;
    samples = 0;
    stepping = true;
    int result = wk_base_step(handle, commands, count, 1, output, output_count);
    stepping = false;
    if (result) return result;
    if (samples != 16) return 4;
    ++ticks;
    return 0;
}
}
