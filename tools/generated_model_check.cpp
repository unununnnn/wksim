// Diagnostic only: bounded model smoke checks, not a flight controller or host.
#include "Exp1_MinModelTemp.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>

using Snapshot = std::array<double, 120>;

Snapshot run_case(double throttle) {
    auto model = std::make_unique<MulticopterModelClass>();
    model->initialize();
    model->Exp1_MinModelTemp_U = {};
    for (int motor = 0; motor < 4; ++motor)
        model->Exp1_MinModelTemp_U.inPWMs[motor] = throttle;
    Snapshot values{};
    for (int step = 0; step < 2000; ++step) {
        model->step();
        if (rtmGetErrorStatus(model->getRTM()))
            throw std::runtime_error(rtmGetErrorStatus(model->getRTM()));
        const auto& output = model->Exp1_MinModelTemp_Y;
        std::copy_n(output.VehileInfo60d, 60, values.begin());
        std::copy_n(output.HILSensor30d, 30, values.begin() + 60);
        std::copy_n(output.HILGPS30d, 30, values.begin() + 90);
        for (double value : values)
            if (!std::isfinite(value)) throw std::runtime_error("non-finite output");
        const double expected_time = (step + 1) * 0.001;
        if (std::abs(model->getRTM()->Timing.t[0] - expected_time) > 1e-9)
            throw std::runtime_error("model clock does not advance by 1ms");
    }
    model->terminate();
    return values;
}

void print_values(const Snapshot& values) {
    std::cout << '[';
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index) std::cout << ',';
        std::cout << values[index];
    }
    std::cout << ']';
}

int main() {
    try {
        const auto idle = run_case(0.0);
        const auto powered = run_case(0.65);
        const auto repeated = run_case(0.65);
        double repeat_delta = 0.0;
        double input_delta = 0.0;
        for (std::size_t index = 0; index < powered.size(); ++index)
            repeat_delta = std::max(repeat_delta, std::abs(powered[index] - repeated[index]));
        // Compare position and rotor outputs; this is input sensitivity, not physical accuracy.
        for (int index : {6, 7, 8, 16, 17, 18, 19})
            input_delta = std::max(input_delta, std::abs(powered[index] - idle[index]));
        if (repeat_delta > 1e-9) throw std::runtime_error("same-build repeat differs");
        if (input_delta < 0.01) throw std::runtime_error("no observable input response");
        std::cout << std::setprecision(17)
                  << "{\"status\":\"pass\",\"steps_per_case\":2000,"
                  << "\"cases\":3,\"model_step_seconds\":0.001,"
                  << "\"simulated_seconds_per_case\":2,\"repeat_max_abs_delta\":"
                  << repeat_delta << ",\"input_response_max_abs_delta\":" << input_delta
                  << ",\"output_layout\":\"Vehicle60,Sensor30,GPS30\",\"idle\":";
        print_values(idle);
        std::cout << ",\"powered\":";
        print_values(powered);
        std::cout << ",\"repeated\":";
        print_values(repeated);
        std::cout << "}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "model smoke check failed: " << error.what() << '\n';
        return 1;
    }
}
