#!/usr/bin/env python3
"""Compare Python with the unchanged upstream C++ PID and real system Eigen.

Run on Linux with g++/Eigen installed. --describe freezes fixtures without build.
ROS NodeHandle and UAVState are shells only; all controller/math code is original.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Simulator"))
from wksim_control import PIDConfig, PIDReference, PIDState, NativeThrustConfig, select_controller
from wksim_control.position_pid import UPSTREAM_PID_PATH, UPSTREAM_PID_SHA256

PINS = {
    UPSTREAM_PID_PATH: UPSTREAM_PID_SHA256,
    "Modules/uav_control/include/Position_Controller/controller_utils.h": "ba38d5e7f801976926d051801001dddddf946dd0d51bfb9ec49d026bd409da2b",
    "Modules/common/include/geometry_utils.h": "2a6fdcaec06800d18bb09b6ee9c13c4bfca486f6d383a89eefdea26831cd2fe8",
    "Modules/common/include/math_utils.h": "1be2080dc4515e51a4655833c0407aec28b5560828ed15deff2c105968e74b95",
    "Modules/common/include/printf_utils.h": "b7cf15d1da79733ac7069e0d0cef620193a4176e7bd98d02682e7523c85b388e",
}
ABS_TOL = 2e-6
REL_TOL = 2e-7
FROZEN_PROTOCOL_SHA256 = "076bd5bbd3502fe11eacc4189c21e24bbf1a300fe4daf5b4493710be35914f61"
ROS_SHELL = r'''
#pragma once
#include <string>
#include <unordered_map>
namespace ros {
struct NodeHandle {
    std::unordered_map<std::string, double> values;
    template<class T> void param(const std::string &name, T &out, T fallback) {
        const auto found = values.find(name);
        out = found == values.end() ? fallback : static_cast<T>(found->second);
    }
};
}
'''
STATE_SHELL = r'''
#pragma once
#include <string>
namespace prometheus_msgs {
struct UAVState {
    float position[3]{};
    float velocity[3]{};
    struct Quaternion { double w{1}, x{}, y{}, z{}; } attitude_q;
    std::string mode;
};
}
'''
CPP = r'''
#include <Eigen/Eigen>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <vector>
#include <ros/ros.h>
#include <prometheus_msgs/UAVState.h>
#include "math_utils.h"
#include "controller_utils.h"
#include "geometry_utils.h"
#include "printf_utils.h"
// All dependencies were parsed above. Only this class's private visibility
// changes; original function bodies and original files remain untouched.
#define private public
#include "pos_controller_PID.h"
#undef private
int main() {
    ros::NodeHandle nh;
    double mass, hover, kp, kv, ki, limit, tilt;
    if (!(std::cin >> mass >> hover >> kp >> kv >> ki >> limit >> tilt)) return 2;
    nh.values = {{"pid_gain/quad_mass", mass}, {"pid_gain/hov_percent", hover},
        {"pid_gain/Kp_xy", kp}, {"pid_gain/Kp_z", kp},
        {"pid_gain/Kv_xy", kv}, {"pid_gain/Kv_z", kv},
        {"pid_gain/Kvi_xy", ki}, {"pid_gain/Kvi_z", ki},
        {"pid_gain/pxy_int_max", limit}, {"pid_gain/pz_int_max", limit},
        {"pid_gain/tilt_angle_max", tilt}};
    std::ostringstream quiet;
    auto *normal = std::cout.rdbuf(quiet.rdbuf());
    pos_controller_PID pid;
    pid.init(nh);
    // Original init omits initialization. Define a zero starting condition in
    // the fixture; do not assert that upstream already initialized this state.
    pid.int_e_v.setZero();
    std::cout.rdbuf(normal);
    int reset, active;
    float hz;
    while (std::cin >> reset >> active >> hz) {
        prometheus_msgs::UAVState state;
        Desired_State desired;
        for (int i=0; i<3; ++i) std::cin >> state.position[i];
        for (int i=0; i<3; ++i) std::cin >> state.velocity[i];
        std::cin >> state.attitude_q.w >> state.attitude_q.x >> state.attitude_q.y >> state.attitude_q.z;
        for (int i=0; i<3; ++i) std::cin >> desired.pos[i];
        for (int i=0; i<3; ++i) std::cin >> desired.vel[i];
        for (int i=0; i<3; ++i) std::cin >> desired.acc[i];
        std::cin >> desired.yaw;
        if (!std::cin) return 3;
        state.mode = active ? "OFFBOARD" : "MANUAL";
        if (reset) pid.int_e_v.setZero();
        pid.set_current_state(state);
        pid.set_desired_state(desired);
        quiet.str("");
        std::cout.rdbuf(quiet.rdbuf());
        Eigen::Vector4d out = pid.update(hz);
        std::cout.rdbuf(normal);
        std::cout << std::defaultfloat << std::setprecision(17);
        for (int i=0; i<3; ++i) std::cout << pid.int_e_v[i] << ' ';
        for (int i=0; i<3; ++i) std::cout << pid.F_des[i] << ' ';
        for (int i=0; i<4; ++i) std::cout << out[i] << ' ';
        std::cout << '\n';
    }
}
'''


def f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


def fixtures():
    cases = []
    def add(label, *, reset=0, active=1, hz=100, pos=(0, 0, 0), vel=(0, 0, 0),
            q=(1, 0, 0, 0), ref=(0, 0, 0), rv=(0, 0, 0), acc=(0, 0, 0), yaw=0):
        cases.append({"label": label, "values": [reset, active, hz,
            *map(f32, pos), *map(f32, vel), *q, *ref, *rv, *acc, yaw]})
    add("hover", reset=1)
    for error in (-3.001, -3, -0.5, -0.21, -0.2, -0.1, 0.1, 0.2, 0.21, 0.5, 3, 3.001):
        add("error-boundaries", reset=1, ref=(error, -error, error), rv=(error, -error, error))
    for _ in range(600):
        add("integral-saturation", ref=(0.1, -0.1, 0.3))
    for i in range(20):
        add("moving-reference-reset", ref=(0.1, -0.1, 0.3), rv=(0.01, 0, 0), hz=40)
    add("inactive-reset", active=0, ref=(0.1, -0.1, 0.3))
    for az in (-20, -8, 0, 30):
        add("force-scale-tilt", reset=1, acc=(2, -2, az))
    for roll, pitch, yaw in ((0, 0, 90), (20, -15, 45), (-25, 10, -120), (180, 0, 0)):
        r, p, y = [math.radians(a) / 2 for a in (roll, pitch, yaw)]
        cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
        q = (cr*cp*cy+sr*sp*sy, sr*cp*cy-cr*sp*sy, cr*sp*cy+sr*cp*sy, cr*cp*sy-sr*sp*cy)
        add("current-attitude-projection", reset=1, q=q, acc=(0.5, -0.3, 0.2), yaw=-0.7)
    for i in range(300):
        t = i / 100
        add("deterministic-trace", reset=int(i % 100 == 0), active=int(i % 47 != 0),
            hz=(40, 50, 100, 200)[i % 4], pos=(0.1*math.sin(t), 0.2*math.cos(t), 0.05*t),
            vel=(0.1*math.cos(t), -0.2*math.sin(t), 0.05), ref=(0.1, -0.1, 0.25),
            rv=(0, 0, 0) if i < 150 else (0.05, 0, 0),
            acc=(0.03*math.sin(t), -0.02*math.cos(t), 0.01), yaw=0.2)
    return cases


def protocol():
    rows = fixtures()
    return {
        "cases": rows,
        "configurations": [[2.0, 0.5, 2.0, 2.0, 0.3, 0.5, 10.0],
                           [1.25, 0.75, 1.5, 2.5, 0.25, 0.02, 12.0]],
        "comparison": ["integral_xyz", "limited_force_enu_xyz", "rpy_enu", "normalized_collective"],
        "absolute_tolerance": ABS_TOL, "relative_tolerance": REL_TOL,
        "excluded": ["undefined uninitialized upstream integral", "zero vertical force division",
                     "ROS transport or timing", "native flight controller", "physical hover law"],
        "source_pins": PINS,
        "fixture_code_sha256": hashlib.sha256((ROS_SHELL + STATE_SHELL + CPP).encode()).hexdigest(),
    }


def recorded_process(command, evidence, tag, *, input_text=None, timeout=30):
    """Persist raw subprocess output even on nonzero status or timeout."""
    metadata = {"argv": command, "timeout_s": timeout}
    if input_text is not None:
        (evidence / f"{tag}.input.txt").write_text(input_text, encoding="utf-8")
    try:
        result = subprocess.run(command, input=input_text, capture_output=True,
                                text=True, timeout=timeout)
        metadata["returncode"] = result.returncode
        stdout, stderr = result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        metadata["timed_out"] = True
        stdout, stderr = error.stdout or "", error.stderr or ""
        result = None
    for name, value in (("stdout", stdout), ("stderr", stderr)):
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        (evidence / f"{tag}.{name}.txt").write_text(value, encoding="utf-8")
    (evidence / f"{tag}.process.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if result is None:
        raise RuntimeError(f"{tag} timed out; partial output retained")
    result.check_returncode()
    return result


def run(compiler, eigen, evidence, protocol_path):
    evidence = evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    raw_protocol = protocol_path.read_bytes()
    (evidence / "protocol.json").write_bytes(raw_protocol)
    for name, value in (("ros-shell.h", ROS_SHELL), ("UAVState-shell.h", STATE_SHELL), ("oracle.cpp", CPP)):
        (evidence / name).write_text(value, encoding="utf-8")
    for source in (Path(__file__), ROOT / "Simulator/wksim_control/position_pid.py",
                   ROOT / "Simulator/wksim_control/__init__.py"):
        shutil.copyfile(source, evidence / source.name)
    try:
        if hashlib.sha256(raw_protocol).hexdigest() != FROZEN_PROTOCOL_SHA256:
            raise ValueError("input protocol does not match the preapproved frozen bytes")
        frozen = json.loads(raw_protocol)
        if frozen["fixture_code_sha256"] != hashlib.sha256((ROS_SHELL + STATE_SHELL + CPP).encode()).hexdigest():
            raise ValueError("oracle fixture code differs from the frozen protocol")
        if frozen["source_pins"] != PINS or frozen["absolute_tolerance"] != ABS_TOL or frozen["relative_tolerance"] != REL_TOL:
            raise ValueError("source pins or tolerances differ from the frozen protocol")
        result = run_comparison(compiler, eigen, evidence, frozen)
    except Exception as error:
        (evidence / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        (evidence / "result.json").write_text(json.dumps({"passed": False, "error": str(error)}, indent=2), encoding="utf-8")
        raise
    (evidence / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def run_comparison(compiler, eigen, evidence, frozen):
    for name, expected in PINS.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"original source pin differs: {name}")
    compiler = shutil.which(compiler)
    if not compiler or not (eigen / "Eigen/Eigen").is_file():
        raise RuntimeError("g++ and real Eigen headers are required")
    version = recorded_process([compiler, "--version"], evidence, "compiler-version").stdout.splitlines()[0]
    macros = eigen / "Eigen/src/Core/util/Macros.h"
    (evidence / "eigen-version.txt").write_text("\n".join(line for line in macros.read_text().splitlines()
        if line.startswith(("#define EIGEN_WORLD_VERSION", "#define EIGEN_MAJOR_VERSION", "#define EIGEN_MINOR_VERSION"))), encoding="utf-8")
    errors = [0.0] * 10
    with tempfile.TemporaryDirectory(prefix="wksim-pid-oracle-") as temporary:
        path = Path(temporary)
        (path / "ros").mkdir()
        (path / "prometheus_msgs").mkdir()
        (path / "ros/ros.h").write_text(ROS_SHELL)
        (path / "prometheus_msgs/UAVState.h").write_text(STATE_SHELL)
        (path / "oracle.cpp").write_text(CPP)
        executable = path / "oracle"
        command = [compiler, "-std=c++17", "-O0", "-I", str(path), "-I", str(eigen),
                   "-I", str(ROOT / "Modules/common/include"),
                   "-I", str(ROOT / "Modules/uav_control/include/Position_Controller"),
                   str(path / "oracle.cpp"), "-o", str(executable)]
        recorded_process(command, evidence, "compile", timeout=60)
        (evidence / "binary-sha256.txt").write_text(hashlib.sha256(executable.read_bytes()).hexdigest(), encoding="utf-8")
        for conf_index, conf in enumerate(frozen["configurations"]):
            mass, hover, kp, kv, ki, limit, tilt = conf
            data = " ".join(map(str, conf)) + "\n" + "\n".join(" ".join(map(str, x["values"])) for x in frozen["cases"]) + "\n"
            raw = recorded_process([str(executable)], evidence, f"config-{conf_index}", input_text=data)
            lines = raw.stdout.splitlines()
            if len(lines) != len(frozen["cases"]):
                raise AssertionError("original output count differs")
            # Mirror ROS float fields/parameters at the fixture boundary.
            config = PIDConfig(f32(mass), (kp,)*3, (kv,)*3, (ki,)*3, (f32(limit),)*3, f32(tilt))
            pid = select_controller("pid", config)
            mapping = NativeThrustConfig("px4", "oracle-only", config.mass_kg, f32(hover))
            with (evidence / f"config-{conf_index}.comparison.jsonl").open("w", encoding="utf-8") as comparison:
                for index, (case, line) in enumerate(zip(frozen["cases"], lines)):
                    row = case["values"]
                    if row[0]:
                        pid.reset("fixture")
                    state = PIDState(tuple(row[3:6]), tuple(row[6:9]), tuple(row[9:13]))
                    reference = PIDReference(tuple(row[13:16]), tuple(row[16:19]), tuple(row[19:22]), row[22])
                    out = pid.update(state, reference, dt_s=1 / f32(row[2]), external_control_active=bool(row[1]))
                    actual = (*out.integral, *out.force_enu_n, *out.roll_pitch_yaw_enu_rad,
                              mapping.normalized_collective(out, model_identity="oracle-only"))
                    original = list(map(float, line.split()))
                    comparisons = [math.isclose(a, b, abs_tol=ABS_TOL, rel_tol=REL_TOL) for a, b in zip(actual, original)]
                    comparison.write(json.dumps({"index": index, "label": case["label"], "input": row,
                        "python": actual, "original_cpp": original, "channel_passed": comparisons}) + "\n")
                    comparison.flush()
                    if len(original) != 10:
                        raise AssertionError(f"invalid original result {line!r}")
                    for channel, (a, b) in enumerate(zip(actual, original)):
                        errors[channel] = max(errors[channel], abs(a-b))
                        if not comparisons[channel]:
                            raise AssertionError(f"case {index} {case['label']} channel {channel}: Python {a} C++ {b}")
        result = {
            "passed": True, "samples": len(frozen["cases"]) * len(frozen["configurations"]),
            "channels_per_sample": 10, "max_absolute_error_per_channel": errors,
            "protocol_sha256": hashlib.sha256(json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "compiler": version, "evidence": str(evidence),
            "eigen": str(eigen), "binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "source_pins": PINS, "absolute_tolerance": ABS_TOL, "relative_tolerance": REL_TOL,
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--compiler", default="g++")
    parser.add_argument("--eigen", type=Path, default=Path("/usr/include/eigen3"))
    parser.add_argument("--evidence", type=Path, help="required new directory for retained inputs, logs and comparisons")
    parser.add_argument("--protocol", type=Path, help="required frozen canonical JSON; do not regenerate platform sin/cos inputs")
    args = parser.parse_args()
    if not args.describe and (args.evidence is None or args.protocol is None):
        parser.error("--evidence and --protocol are required for a build/run")
    print(json.dumps(protocol() if args.describe else run(args.compiler, args.eigen, args.evidence, args.protocol), indent=2))
