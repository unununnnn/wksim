#!/usr/bin/env python3
"""Run unchanged Prometheus NE C++ against Python, with retained raw evidence.

Requires Linux g++/Eigen. Fixed rational fixtures and tolerances are declared
before compilation. No ROS nodes, model, FC, flight or performance measurement.
"""
import argparse
from dataclasses import astuple
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

from check_position_pid_source import ROS_SHELL, STATE_SHELL, recorded_process, f32, PINS as PID_PINS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Simulator"))
from wksim_control.position_ne import NEConfig, PositionNE, UPSTREAM_COMMIT, UPSTREAM_NE_PATH, UPSTREAM_NE_SHA256
from wksim_control.position_pid import PIDState, PIDReference, NativeThrustConfig

PINS = {k: v for k, v in PID_PINS.items() if not k.endswith("pos_controller_PID.h")}
PINS.update({
    UPSTREAM_NE_PATH: UPSTREAM_NE_SHA256,
    "Modules/uav_control/include/Filter/LowPassFilter.h": "892671fa20f732f8f8ab0868c04b4bfb3d6e0d700cf00d9e208900270e75de24",
    "Modules/uav_control/include/Filter/HighPassFilter.h": "4c7038cc2c0e8661e0983c96669fe65ec0c6d9689394d33c55d9e74908cdb731",
    "Modules/uav_control/include/Filter/LeadLagFilter.h": "0325494d48e5d37892a7d496b6b38b70a2cc39fa7224c4f6357bb40b6d5fff69",
})
ABS_TOL, REL_TOL = 2e-6, 2e-7
CPP = r'''
#include <Eigen/Eigen>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <vector>
#include <bitset>
#include <memory>
#include <ros/ros.h>
#include <prometheus_msgs/UAVState.h>
#include "math_utils.h"
#include "controller_utils.h"
#include "geometry_utils.h"
#include "printf_utils.h"
// Dependencies parsed; expose controller/filter state without changing bodies.
#define private public
#include "pos_controller_NE.h"
#undef private
int main() {
    ros::NodeHandle nh;
    double mass, hover, kp, kd, tu, tn, limit, tilt;
    if (!(std::cin >> mass >> hover >> kp >> kd >> tu >> tn >> limit >> tilt)) return 2;
    nh.values = {{"ne_gain/quad_mass", mass}, {"ne_gain/hov_percent", hover},
        {"ne_gain/Kp_xy", kp}, {"ne_gain/Kp_z", kp},
        {"ne_gain/Kd_xy", kd}, {"ne_gain/Kd_z", kd},
        {"ne_gain/T_ude", tu}, {"ne_gain/T_ne", tn},
        {"ne_gain/pxy_int_max", limit}, {"ne_gain/pz_int_max", limit},
        {"ne_gain/tilt_angle_max", tilt}};
    std::ostringstream quiet;
    auto *normal = std::cout.rdbuf();
    std::unique_ptr<pos_controller_NE> ne;
    int reset;
    float hz;
    while (std::cin >> reset >> hz) {
        prometheus_msgs::UAVState state;
        Desired_State desired;
        Eigen::Vector3d initial;
        for (int i=0; i<3; ++i) std::cin >> state.position[i];
        for (int i=0; i<3; ++i) std::cin >> state.velocity[i];
        std::cin >> state.attitude_q.w >> state.attitude_q.x >> state.attitude_q.y >> state.attitude_q.z;
        for (int i=0; i<3; ++i) std::cin >> desired.pos[i];
        for (int i=0; i<3; ++i) std::cin >> desired.vel[i];
        for (int i=0; i<3; ++i) std::cin >> desired.acc[i];
        std::cin >> desired.yaw;
        for (int i=0; i<3; ++i) std::cin >> initial[i];
        if (!std::cin || (!ne && !reset)) return 3;
        quiet.str("");
        std::cout.rdbuf(quiet.rdbuf());
        if (reset) {
            // Reconstruct: original init alone does NOT reset filter history.
            ne.reset(new pos_controller_NE());
            ne->init(nh);
            ne->set_initial_pos(initial);
        }
        ne->set_current_state(state);
        ne->set_desired_state(desired);
        Eigen::Vector4d out = ne->update(hz);
        std::cout.rdbuf(normal);
        std::cout << std::defaultfloat << std::setprecision(17);
        auto vector = [](const Eigen::Vector3d& v) { for(int i=0;i<3;++i) std::cout << v[i] << ' '; };
        vector(ne->integral); vector(ne->integral_LLF);
        std::cout << ne->LPF_x.Output_prev << ' ' << ne->LPF_y.Output_prev << ' ' << ne->LPF_z.Output_prev << ' ';
        std::cout << ne->HPF_x.Output_prev << ' ' << ne->HPF_y.Output_prev << ' ' << ne->HPF_z.Output_prev << ' ';
        std::cout << ne->HPF_x.Input_prev << ' ' << ne->HPF_y.Input_prev << ' ' << ne->HPF_z.Input_prev << ' ';
        std::cout << ne->LLF_x.Output_prev << ' ' << ne->LLF_y.Output_prev << ' ' << ne->LLF_z.Output_prev << ' ';
        std::cout << ne->LLF_x.Input_prev << ' ' << ne->LLF_y.Input_prev << ' ' << ne->LLF_z.Input_prev << ' ';
        vector(ne->NoiseEstimator); vector(ne->u_l); vector(ne->u_d); vector(ne->F_des);
        for(int i=0;i<4;++i) std::cout << out[i] << ' ';
        std::cout << '\n';
    }
}
'''


def fixtures():
    rows = []
    def add(label, reset=0, hz=200, pos=(0, 0, 0), vel=(0, 0, 0),
            q=(1, 0, 0, 0), ref=(0, 0, 0), rv=(0, 0, 0), acc=(0, 0, 0), yaw=0, initial=(0, 0, 0)):
        rows.append({"label": label, "values": [reset, hz, *pos, *vel, *q, *ref, *rv, *acc, yaw, *initial]})
    add("hover", reset=1)
    for sign in (-1, 1):
        for error in (3, 4, 99.5, 100, 100.5):
            add("threshold", reset=1, ref=(sign*error, sign*error, 0))
    for i in range(400):
        add("stateful-disturbance", reset=int(i == 0), pos=(.125, -.25, .5),
            vel=(.25, -.5, .125), ref=(.5, -.125, .75), rv=(.125, .25, -.125))
    for i in range(240):
        # Exact binary fractions, no platform sin/cos input regeneration.
        x = ((i % 32)-16)/32
        add("trajectory-reset", reset=int(i in (0, 120)), hz=(100, 200, 400)[i % 3],
            pos=(x, -x/2, x/4), vel=(-x/4, x/8, -x/16),
            ref=(x+.25, -x, 1), rv=(x/4, 0, 0), acc=(x, -x/2, x/4),
            q=(.5, .5, .5, .5), yaw=.75, initial=(1, -2, .5))
    for z in (-20, -9, 0, 20):
        add("force-limit", reset=1, acc=(20, -20, z))
    return rows


def protocol():
    return {"source_pins": PINS, "upstream_commit": UPSTREAM_COMMIT,
            "absolute_tolerance": ABS_TOL, "relative_tolerance": REL_TOL,
            "fixture_sha256": hashlib.sha256((ROS_SHELL+STATE_SHELL+CPP).encode()).hexdigest(),
            "configurations": [[2, .5, .5, 2, 1, 1, 1, 20], [1.25, .75, 1.5, 2.5, .5, .25, .125, 12]],
            "cases": fixtures(), "channels": 37,
            "dt_boundary": "Python receives float32(1/float32(hz)), matching original float dt"}


def run(evidence):
    evidence.mkdir(parents=True, exist_ok=False)
    frozen = protocol()
    (evidence / "protocol.json").write_text(json.dumps(frozen, sort_keys=True, indent=2), encoding="utf-8")
    sources = [Path(__file__), ROOT/"Simulator/wksim_control/position_ne.py",
               ROOT/"Simulator/wksim_control/position_pid.py", ROOT/"validation/test_position_ne.py",
               ROOT/"tools/check_position_pid_source.py"]
    identities = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    (evidence / "source-sha256.json").write_text(json.dumps(identities, indent=2), encoding="utf-8")
    try:
        for name, expected in PINS.items():
            raw = (ROOT/name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError(f"source pin differs: {name}")
            upstream = subprocess.run(["git", "show", f"{UPSTREAM_COMMIT}:{name}"], cwd=ROOT,
                                      capture_output=True, check=True).stdout
            if raw.replace(b"\r\n", b"\n") != upstream.replace(b"\r\n", b"\n"):
                raise ValueError(f"upstream source differs: {name}")
        recorded_process([sys.executable, "-m", "unittest", "validation.test_position_ne", "validation.test_position_pid", "-v"], evidence, "unit-tests")
        compiler = shutil.which("g++")
        if not compiler or not Path("/usr/include/eigen3/Eigen/Eigen").is_file():
            raise RuntimeError("Linux g++ and real Eigen required")
        recorded_process([compiler, "--version"], evidence, "compiler-version")
        errors = [0.0]*37
        with tempfile.TemporaryDirectory(prefix="wksim-ne-oracle-") as temp:
            path = Path(temp)
            for name, text in (("ros/ros.h", ROS_SHELL), ("prometheus_msgs/UAVState.h", STATE_SHELL), ("oracle.cpp", CPP)):
                dest = path/name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text, encoding="utf-8")
                (evidence/dest.name).write_text(text, encoding="utf-8")
            executable = path/"oracle"
            recorded_process([compiler, "-std=c++17", "-O0", "-I", str(path), "-I", "/usr/include/eigen3",
                              "-I", str(ROOT/"Modules/common/include"), "-I", str(ROOT/"Modules/uav_control/include"),
                              "-I", str(ROOT/"Modules/uav_control/include/Position_Controller"),
                              str(path/"oracle.cpp"), "-o", str(executable)], evidence, "compile", timeout=60)
            binary_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
            for index, conf in enumerate(frozen["configurations"]):
                mass, hover, kp, kd, tu, tn, limit, tilt = conf
                data = " ".join(map(str, conf))+"\n"+"\n".join(" ".join(map(str, r["values"])) for r in frozen["cases"])+"\n"
                result = recorded_process([str(executable)], evidence, f"config-{index}", input_text=data)
                lines = result.stdout.splitlines()
                if len(lines) != len(frozen["cases"]):
                    raise AssertionError("wrong C++ row count")
                ne = PositionNE(NEConfig(f32(mass), (kp,)*3, (kd,)*3, (f32(limit),)*3, tu, tn, f32(tilt)))
                mapping = NativeThrustConfig("px4", "oracle-only", f32(mass), f32(hover))
                with (evidence/f"config-{index}.comparison.jsonl").open("w", encoding="utf-8") as log:
                    for case, line in zip(frozen["cases"], lines):
                        row = case["values"]
                        if row[0]:
                            ne.reset("fixture", initial_position_enu=row[22:25])
                        state = PIDState(tuple(map(f32, row[2:5])), tuple(map(f32, row[5:8])), tuple(row[8:12]))
                        reference = PIDReference(tuple(row[12:15]), tuple(row[15:18]), tuple(row[18:21]), row[21])
                        out = ne.update(state, reference, dt_s=f32(1/f32(row[1])), external_control_active=True)
                        actual = [v for vec in astuple(out.memory) for v in vec] + list(out.noise_estimator+out.nominal_acceleration+out.disturbance_estimate+out.force_enu_n+out.roll_pitch_yaw_enu_rad) + [mapping.normalized_collective(out, model_identity="oracle-only")]
                        original = list(map(float, line.split()))
                        if len(original) != 37:
                            raise AssertionError("wrong C++ channel count")
                        passed = [math.isclose(a, b, abs_tol=ABS_TOL, rel_tol=REL_TOL) for a, b in zip(actual, original)]
                        log.write(json.dumps({"case": case, "python": actual, "cpp": original, "passed": passed})+"\n")
                        for ch, (a, b) in enumerate(zip(actual, original)):
                            errors[ch] = max(errors[ch], abs(a-b))
                        if not all(passed):
                            raise AssertionError(f"comparison failed: config {index}, {case}, channels {passed}")
        result = {"passed": True, "samples": len(frozen["cases"])*len(frozen["configurations"]), "channels": 37,
                  "max_absolute_error": errors, "binary_sha256": binary_hash, "source_pins": PINS,
                  "absolute_tolerance": ABS_TOL, "relative_tolerance": REL_TOL,
                  "boundary": "pure source comparison only; no flight/runtime/performance acceptance"}
    except Exception as error:
        (evidence/"failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        (evidence/"result.json").write_text(json.dumps({"passed": False, "error": str(error)}, indent=2), encoding="utf-8")
        raise
    (evidence/"result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True, help="new evidence directory")
    args = parser.parse_args()
    print(json.dumps(run(args.evidence.resolve()), indent=2))
