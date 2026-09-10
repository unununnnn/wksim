// Standalone post-step reference driver for unmodified 11.8 Simulink model.
// Evaluates full 31-input contract (16 inPWMs + 15 TerrainIn15d) with zero runtime MATLAB dependency.
// No observer hooks, callbacks, pseudo-major steps, or model ABI modifications.
#include "Exp1_MinModelTemp.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
struct Outputs {
    std::array<real_T, 60> vehicle;
    std::array<real_T, 30> sensor, gps;
};

struct Input {
    double time;
    std::array<double, 16> pwm;
    std::array<double, 15> terrain;
};

void copy_outputs(const ExtY_Exp1_MinModelTemp_T& y, Outputs& out) noexcept {
    std::copy_n(y.VehileInfo60d, 60, out.vehicle.begin());
    std::copy_n(y.HILSensor30d, 30, out.sensor.begin());
    std::copy_n(y.HILGPS30d, 30, out.gps.begin());
}

std::string quote(const std::string& text) {
    std::ostringstream out;
    out << '"';
    for (unsigned char ch : text) {
        if (ch == '"' || ch == '\\') out << '\\' << ch;
        else if (ch < 32 || ch >= 127)
            out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(ch);
        else out << ch;
    }
    out << '"';
    return out.str();
}

template<std::size_t N>
void array(std::ostream& out, const std::array<double, N>& values) {
    out << '[';
    for (std::size_t i = 0; i < N; ++i) {
        if (!std::isfinite(values[i])) throw std::runtime_error("Non-finite output");
        if (i) out << ',';
        out << values[i];
    }
    out << ']';
}

void outputs(std::ostream& out, const Outputs& values) {
    out << "{\"Vehicle60\":"; array(out, values.vehicle);
    out << ",\"Sensor30\":"; array(out, values.sensor);
    out << ",\"GPS30\":"; array(out, values.gps);
    out << '}';
}

bool same_time(double actual, double expected) {
    return std::isfinite(actual) && std::abs(actual - expected) <= 1e-12;
}

std::vector<Input> read_inputs(const std::string& path, std::string& raw) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file || file.tellg() < 0 || file.tellg() > 1024 * 1024)
        throw std::runtime_error("Input file missing or larger than 1 MiB");
    file.seekg(0);
    raw.assign(std::istreambuf_iterator<char>(file), {});
    if (file.bad()) throw std::runtime_error("Cannot read input file");
    for (unsigned char ch : raw)
        if (ch >= 127 || (ch < 32 && ch != '\n' && ch != '\r'))
            throw std::runtime_error("Input CSV must be plain ASCII");
    std::string header = "k,time_s";
    for (int i = 0; i < 16; ++i) header += ",inPWMs" + std::to_string(i);
    for (int i = 0; i < 15; ++i) header += ",TerrainIn15d" + std::to_string(i);
    std::istringstream lines(raw);
    std::string line;
    std::getline(lines, line);
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line != header) throw std::runtime_error("Unexpected input CSV header");
    std::vector<Input> rows;
    while (std::getline(lines, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (rows.size() >= 501 || line.empty() || line.back() == ',')
            throw std::runtime_error("Expected exactly 501 nonempty input rows");
        std::istringstream columns(line);
        std::string value;
        std::vector<std::string> cells;
        while (std::getline(columns, value, ',')) cells.push_back(value);
        if (cells.size() != 33 || cells[0] != std::to_string(rows.size()))
            throw std::runtime_error("Expected ordered k=0..500 and 31 input fields");
        std::array<double, 32> numbers{};
        for (std::size_t j = 0; j < numbers.size(); ++j) {
            std::size_t consumed = 0;
            numbers[j] = std::stod(cells[j + 1], &consumed);
            if (consumed != cells[j + 1].size() || !std::isfinite(numbers[j]))
                throw std::runtime_error("Expected finite numeric input fields");
        }
        Input row{};
        row.time = numbers[0];
        if (!same_time(row.time, rows.size() * 0.001))
            throw std::runtime_error("Input time differs from explicit 1 ms grid");
        std::copy_n(numbers.begin() + 1, 16, row.pwm.begin());
        std::copy_n(numbers.begin() + 17, 15, row.terrain.begin());
        for (double pwm : row.pwm)
            if (pwm < 0 || pwm > 1) throw std::runtime_error("PWM outside [0,1]");
        rows.push_back(row);
    }
    if (rows.size() != 501) throw std::runtime_error("Expected exactly 501 input rows");
    return rows;
}
}  // namespace

int main(int argc, char** argv) {
    unsigned attempted = 0, returned = 0, emitted = 0;
    std::unique_ptr<MulticopterModelClass> model;
    try {
        if (argc != 3 || (std::string(argv[1]) != "--validate-input" &&
                          std::string(argv[1]) != "--record")) {
            std::cerr << "Usage: generated_e0_post_reference --validate-input|--record input.csv\n";
            return 1;
        }
        std::string raw;
        const auto rows = read_inputs(argv[2], raw);
        std::cout << std::setprecision(17);
        if (std::string(argv[1]) == "--validate-input") {
            std::cout << "{\"status\":\"input_valid\",\"rows\":501,\"bound_inputs\":[\"inPWMs[16]\",\"TerrainIn15d[15]\"]}\n";
            return 0;
        }

        std::cout << "{\"schema_version\":1,\"kind\":\"post_reference_start\",\"bound_inputs\":[\"inPWMs[16]\",\"TerrainIn15d[15]\"],"
                  << "\"expected_calls\":501,\"comparison_end_s\":0.5,\"expected_engine_end_s\":0.501}\n"
                  << std::flush;

        model = std::make_unique<MulticopterModelClass>();
        model->initialize();
        if (rtmGetErrorStatus(model->getRTM())) throw std::runtime_error("Model initialize error");

        for (std::size_t k = 0; k < rows.size(); ++k) {
            const auto& input = rows[k];
            const double before = model->getRTM()->Timing.t[0];
            if (!same_time(before, k * 0.001)) throw std::runtime_error("Pre-step model clock differs");

            // Complete 31-input binding: 16 PWM + 15 Terrain
            std::copy_n(input.pwm.begin(), 16, model->Exp1_MinModelTemp_U.inPWMs);
            std::copy_n(input.terrain.begin(), 15, model->Exp1_MinModelTemp_U.TerrainIn15d);

            ++attempted;
            model->step();
            ++returned;
            if (rtmGetErrorStatus(model->getRTM())) throw std::runtime_error("Model step error");

            const double after = model->getRTM()->Timing.t[0];
            if (!same_time(after, (k + 1) * 0.001)) throw std::runtime_error("Post-step model clock differs");

            Outputs post;
            copy_outputs(model->Exp1_MinModelTemp_Y, post);

            std::ostringstream sample;
            sample << std::setprecision(17)
                   << "{\"schema_version\":1,\"kind\":\"post_reference_sample\",\"k\":" << k
                   << ",\"call_number\":" << returned << ",\"input_time_s\":" << input.time
                   << ",\"engine_before_s\":" << before << ",\"engine_after_s\":" << after
                   << ",\"inPWMs\":";
            array(sample, input.pwm);
            sample << ",\"TerrainIn15d\":"; array(sample, input.terrain);
            sample << ",\"post_step_api\":"; outputs(sample, post);
            sample << ",\"step_status\":\"complete\"}\n";
            std::cout << sample.str() << std::flush;
            if (!std::cout) throw std::runtime_error("Output write failed");
            ++emitted;
        }
        model->terminate();

        std::cout << "{\"schema_version\":1,\"kind\":\"post_reference_end\",\"status\":\"complete\","
                  << "\"attempted_calls\":" << attempted << ",\"returned_calls\":" << returned
                  << ",\"emitted_samples\":" << emitted << ",\"comparison_end_s\":0.5,\"engine_end_s\":"
                  << model->getRTM()->Timing.t[0] << "}\n" << std::flush;
        return std::cout ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr << "{\"status\":\"failed\",\"error\":" << quote(error.what())
                  << ",\"attempted_calls\":" << attempted << ",\"returned_calls\":" << returned
                  << ",\"emitted_samples\":" << emitted << "}\n";
        if (model) model->terminate();
        return 1;
    }
}
