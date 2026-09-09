// wksim bridge to a locally supplied, generated model. No vendor code is vendored.
// The reviewed model has shared static parameters: use one process per vehicle.
#include "Exp1_MinModelTemp.h"
#include <algorithm>
#include <cmath>
#include <memory>

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
// Return codes: 0 success, 1 invalid arguments, 2 model error, 3 non-finite state.
int wk_model_step(void* handle, const double* commands, int count, int steps,
                  double* output, int output_count) noexcept {
    if (!handle || !commands || !output || count != 16 || output_count != 120 ||
        steps < 1 || steps > 1000) return 1;
    for (int i = 0; i < count; ++i)
        if (!std::isfinite(commands[i]) || commands[i] < 0 || commands[i] > 1)
            return 1;
    auto* model = static_cast<MulticopterModelClass*>(handle);
    std::copy_n(commands, count, model->Exp1_MinModelTemp_U.inPWMs);
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
