// wksim bridge to a locally supplied, generated model. No vendor code is vendored.
// The reviewed model has shared static parameters: use one process per vehicle.
#include "Exp1_MinModelTemp.h"
#include <algorithm>
#include <cmath>
#include <memory>

namespace {
int step_model_internal(void* handle, const double* commands, int count,
                        const double* terrain, int terrain_count, int steps,
                        double* output, int output_count) noexcept {
    if (!handle || !commands || !output || count != 16 || output_count != 120 ||
        steps < 1 || steps > 1000) return 1;
    for (int i = 0; i < count; ++i)
        if (!std::isfinite(commands[i]) || commands[i] < 0 || commands[i] > 1)
            return 1;
    if (terrain != nullptr) {
        if (terrain_count != 15) return 1;
        for (int i = 0; i < terrain_count; ++i)
            if (!std::isfinite(terrain[i])) return 1;
    }
    auto* model = static_cast<MulticopterModelClass*>(handle);
    std::copy_n(commands, count, model->Exp1_MinModelTemp_U.inPWMs);
    if (terrain != nullptr) {
        std::copy_n(terrain, terrain_count, model->Exp1_MinModelTemp_U.TerrainIn15d);
    } else {
        std::fill_n(model->Exp1_MinModelTemp_U.TerrainIn15d, 15, 0.0);
    }
    for (int i = 0; i < steps; ++i) {
        model->step();
        if (rtmGetErrorStatus(model->getRTM())) return 2;
        const auto& state = model->Exp1_MinModelTemp_Y;
        std::copy_n(state.VehileInfo60d, 60, output);
        std::copy_n(state.HILSensor30d, 30, output + 60);
        std::copy_n(state.HILGPS30d, 30, output + 90);
        for (int j = 0; j < output_count; ++j)
            if (!std::isfinite(output[j])) return 3;
    }
    return 0;
}
}

extern "C" {
void* wk_model_create() noexcept {
    try {
        auto model = std::make_unique<MulticopterModelClass>();
        model->initialize();
        model->Exp1_MinModelTemp_U = {};
        return model.release();
    } catch (...) { return nullptr; }
}

void wk_model_destroy(void* handle) noexcept {
    if (!handle) return;
    auto* model = static_cast<MulticopterModelClass*>(handle);
    model->terminate();
    delete model;
}

// Inputs: 16 normalized actuator commands. Output: Vehicle60, Sensor30, GPS30.
// Explicitly resets TerrainIn15d to zero so default steps never inherit prior terrain.
// Return codes: 0 success, 1 invalid arguments, 2 model error, 3 non-finite state.
int wk_model_step(void* handle, const double* commands, int count, int steps,
                  double* output, int output_count) noexcept {
    return step_model_internal(handle, commands, count, nullptr, 0, steps, output, output_count);
}

// Extended C ABI: 16 actuator commands + 15 terrain elevations.
// Validates finite terrain inputs before advancing; does not step on failure.
// Return codes: 0 success, 1 invalid arguments, 2 model error, 3 non-finite state.
int wk_model_step_with_terrain(void* handle, const double* commands, int count,
                               const double* terrain, int terrain_count, int steps,
                               double* output, int output_count) noexcept {
    if (!terrain || terrain_count != 15) return 1;
    return step_model_internal(handle, commands, count, terrain, terrain_count, steps, output, output_count);
}
}
