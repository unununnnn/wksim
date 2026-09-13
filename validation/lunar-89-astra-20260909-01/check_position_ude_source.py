#!/usr/bin/env python3
"""Fixed original UDE oracle. Linux g++/Eigen; only small offline processes.

--describe exposes the predeclared protocol; --evidence creates a NEW directory.
Inputs use rational arithmetic and literal quaternions, no platform trig input.
Tolerance is fixed before execution: abs=2e-6, rel=2e-7 for all 16 channels.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Simulator"))
sys.path.insert(0, str(ROOT / "tools"))
from check_position_pid_source import ROS_SHELL, STATE_SHELL, recorded_process, f32
from wksim_control.position_pid import PIDState, PIDReference, NativeThrustConfig
from wksim_control.position_ude import PositionUDE, UDEConfig, UPSTREAM_COMMIT, UPSTREAM_UDE_PATH, UPSTREAM_UDE_SHA256

PINS = {
    UPSTREAM_UDE_PATH: UPSTREAM_UDE_SHA256,
    "Modules/uav_control/include/Position_Controller/controller_utils.h": "ba38d5e7f801976926d051801001dddddf946dd0d51bfb9ec49d026bd409da2b",
    "Modules/common/include/geometry_utils.h": "2a6fdcaec06800d18bb09b6ee9c13c4bfca486f6d383a89eefdea26831cd2fe8",
    "Modules/common/include/math_utils.h": "1be2080dc4515e51a4655833c0407aec28b5560828ed15deff2c105968e74b95",
    "Modules/common/include/printf_utils.h": "b7cf15d1da79733ac7069e0d0cef620193a4176e7bd98d02682e7523c85b388e",
}
ABS_TOL, REL_TOL = 2e-6, 2e-7
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
#define private public
#include "pos_controller_UDE.h"
#undef private
int main() {
    ros::NodeHandle nh;
    double mass, hover, kp, kd, t, limit, tilt;
    if (!(std::cin >> mass >> hover >> kp >> kd >> t >> limit >> tilt)) return 2;
    nh.values = {{"ude_gain/quad_mass",mass},{"ude_gain/hov_percent",hover},
        {"ude_gain/Kp_xy",kp},{"ude_gain/Kp_z",kp},{"ude_gain/Kd_xy",kd},
        {"ude_gain/Kd_z",kd},{"ude_gain/T_ude",t},{"ude_gain/pxy_int_max",limit},
        {"ude_gain/pz_int_max",limit},{"ude_gain/tilt_angle_max",tilt}};
    std::ostringstream quiet;
    auto *normal = std::cout.rdbuf(quiet.rdbuf());
    pos_controller_UDE ude;
    ude.init(nh);
    std::cout.rdbuf(normal);
    int reset;
    float hz;
    while (std::cin >> reset >> hz) {
        prometheus_msgs::UAVState state;
        Desired_State desired;
        for (int i=0;i<3;++i) std::cin >> state.position[i];
        for (int i=0;i<3;++i) std::cin >> state.velocity[i];
        std::cin >> state.attitude_q.w >> state.attitude_q.x >> state.attitude_q.y >> state.attitude_q.z;
        for (int i=0;i<3;++i) std::cin >> desired.pos[i];
        for (int i=0;i<3;++i) std::cin >> desired.vel[i];
        for (int i=0;i<3;++i) std::cin >> desired.acc[i];
        std::cin >> desired.yaw;
        if (!std::cin) return 3;
        quiet.str("");
        std::cout.rdbuf(quiet.rdbuf());
        if (reset) ude.init(nh);
        ude.set_current_state(state);
        ude.set_desired_state(desired);
        auto out = ude.update(hz);
        std::cout.rdbuf(normal);
        std::cout << std::defaultfloat << std::setprecision(17);
        for (int i=0;i<3;++i) std::cout << ude.integral[i] << ' ';
        for (int i=0;i<3;++i) std::cout << ude.u_l[i] << ' ';
        for (int i=0;i<3;++i) std::cout << ude.u_d[i] << ' ';
        for (int i=0;i<3;++i) std::cout << ude.F_des[i] << ' ';
        for (int i=0;i<4;++i) std::cout << out[i] << ' ';
        std::cout << '\n';
    }
}
'''


def protocol():
    rows = []
    def add(label, reset=0, hz=200, pos=(0, 0, 0), vel=(0, 0, 0),
            q=(1, 0, 0, 0), ref=(0, 0, 0), rv=(0, 0, 0), acc=(0, 0, 0), yaw=0):
        rows.append({"label": label, "values": [reset, hz, *map(f32, pos), *map(f32, vel),
                                                *q, *ref, *rv, *acc, yaw]})
    add("hover", reset=1)
    for e in (-3.001, -3, -0.501, -0.5, -0.499, 0, 0.499, 0.5, 0.501, 3, 3.001):
        add("error-boundary", reset=1, ref=(e, -e, e), rv=(e, -e, e))
    for i in range(1000):
        add("integral-memory-and-disturbance-limit", reset=int(i == 0), ref=(0.25, -0.25, 0.125))
    add("clearing-cycle-uses-old-integral", ref=(0.5, -0.5, 0.5))
    add("after-clear", ref=(0.25, -0.25, 0.125))
    add("reset-after-history", reset=1, ref=(0.25, -0.25, 0.125))
    for az in (-20, -8, 0, 30):
        add("force-limits", reset=1, acc=(20, -20, az))
    for q in ((0.8, 0.6, 0, 0), (0.8, 0, 0.6, 0), (0.8, 0, 0, 0.6), (0, 1, 0, 0)):
        add("attitude-projection", reset=1, q=q, acc=(0.5, -0.3, 0.2), yaw=-0.7)
    for i in range(200):
        add("moving-reference-variable-dt", reset=int(i % 51 == 0), hz=(40, 50, 100, 200)[i % 4],
            pos=(i/1000, -i/2000, i/4000), vel=(0.1, -0.2, 0.05),
            ref=(0.1, 0.2, 0.3), rv=(0.01, -0.02, 0.03), acc=(0.02, -0.01, 0.03))
    return {"cases": rows, "configurations": [[2, 0.5, 0.5, 2, 1, 1, 20],
                [1.25, 0.75, 1.5, 2.5, 0.25, 0.125, 12]],
            "absolute_tolerance": ABS_TOL, "relative_tolerance": REL_TOL,
            "channels": ["integral_xyz", "u_l_xyz", "u_d_xyz", "force_xyz", "rpy", "collective"],
            "source_pins": PINS, "upstream_commit": UPSTREAM_COMMIT,
            "fixture_sha256": hashlib.sha256((ROS_SHELL+STATE_SHELL+CPP).encode()).hexdigest(),
            "dt_boundary": "Python consumes float32(1/float32(hz)) for original comparison only",
            "excluded": ["inactive: explicit port-only reset/reject", "zero Fz: rejected",
                         "ROS/FC/model/flight/performance", "tracking error diagnostic windows"]}


def run(evidence):
    evidence.mkdir(parents=True, exist_ok=False)
    frozen = protocol()
    raw = json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()
    (evidence / "protocol.json").write_bytes(raw)
    try:
        identities = {}
        for name, pin in PINS.items():
            data = (ROOT/name).read_bytes()
            if hashlib.sha256(data).hexdigest() != pin:
                raise ValueError(f"source pin mismatch: {name}")
            original = subprocess.run(["git", "show", f"{UPSTREAM_COMMIT}:{name}"],
                                      cwd=ROOT, capture_output=True, check=True).stdout
            if data.replace(b"\r\n", b"\n") != original:
                raise ValueError(f"upstream blob mismatch: {name}")
            identities[name] = {"working_sha256": pin, "upstream_lf_sha256": hashlib.sha256(original).hexdigest()}
            (evidence/Path(name).name).write_bytes(data)
        for name in ("Simulator/wksim_control/position_ude.py", "Simulator/wksim_control/position_pid.py",
                     "tools/check_position_ude_source.py", "tools/check_position_pid_source.py",
                     "validation/test_position_ude.py"):
            data = (ROOT/name).read_bytes()
            identities[name] = hashlib.sha256(data).hexdigest()
            (evidence/Path(name).name).write_bytes(data)
        (evidence/"identities.json").write_text(json.dumps(identities, indent=2))
        with tempfile.TemporaryDirectory(prefix="wksim-ude-oracle-") as temp:
            path = Path(temp)
            for name, content in (("ros/ros.h", ROS_SHELL), ("prometheus_msgs/UAVState.h", STATE_SHELL), ("oracle.cpp", CPP)):
                target = path/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
                (evidence/target.name).write_text(content)
            compiler = shutil.which("g++")
            if not compiler:
                raise RuntimeError("g++ required")
            recorded_process([compiler, "--version"], evidence, "compiler")
            recorded_process(["dpkg-query", "-W", "libeigen3-dev"], evidence, "eigen")
            binary = path/"oracle"
            recorded_process([compiler, "-std=c++17", "-O0", "-I", str(path), "-I", "/usr/include/eigen3",
                "-I", str(ROOT/"Modules/common/include"), "-I", str(ROOT/"Modules/uav_control/include/Position_Controller"),
                str(path/"oracle.cpp"), "-o", str(binary)], evidence, "compile", timeout=60)
            (evidence/"binary-sha256.txt").write_text(hashlib.sha256(binary.read_bytes()).hexdigest())
            errors = [0.0]*16
            for ci, conf in enumerate(frozen["configurations"]):
                text = " ".join(map(str, conf))+"\n"+"\n".join(" ".join(map(str, c["values"])) for c in frozen["cases"])+"\n"
                lines = recorded_process([str(binary)], evidence, f"config-{ci}", input_text=text).stdout.splitlines()
                if len(lines) != len(frozen["cases"]):
                    raise AssertionError("original output count mismatch")
                mass, hover, kp, kd, t, limit, tilt = conf
                cfg = UDEConfig(f32(mass), (kp,)*3, (kd,)*3, t, (f32(limit),)*3, f32(tilt))
                ude = PositionUDE(cfg)
                mapping = NativeThrustConfig("px4", "oracle-only", cfg.mass_kg, f32(hover))
                with (evidence/f"config-{ci}.comparison.jsonl").open("w") as log:
                    for case, line in zip(frozen["cases"], lines):
                        row = case["values"]
                        if row[0]:
                            ude.reset("fixture")
                        state = PIDState(tuple(row[2:5]), tuple(row[5:8]), tuple(row[8:12]))
                        ref = PIDReference(tuple(row[12:15]), tuple(row[15:18]), tuple(row[18:21]), row[21])
                        out = ude.update(state, ref, dt_s=f32(1/f32(row[1])), external_control_active=True)
                        actual = (*out.integral, *out.nominal_acceleration_enu, *out.disturbance_acceleration_enu,
                                  *out.force_enu_n, *out.roll_pitch_yaw_enu_rad,
                                  mapping.normalized_collective(out, model_identity="oracle-only"))
                        original = list(map(float, line.split()))
                        passed = len(original) == 16 and all(math.isfinite(b) and math.isclose(a, b, abs_tol=ABS_TOL, rel_tol=REL_TOL)
                                                           for a, b in zip(actual, original))
                        log.write(json.dumps({"case": case, "python": actual, "original": original, "passed": passed})+"\n")
                        if not passed:
                            raise AssertionError(f"comparison failed: {case['label']}")
                        errors = [max(e, abs(a-b)) for e, a, b in zip(errors, actual, original)]
        result = {"passed": True, "samples": len(frozen["cases"])*len(frozen["configurations"]),
                  "channels": 16, "max_errors": errors, "protocol_sha256": hashlib.sha256(raw).hexdigest(),
                  "absolute_tolerance": ABS_TOL, "relative_tolerance": REL_TOL}
    except Exception as error:
        (evidence/"failure.txt").write_text(traceback.format_exc())
        (evidence/"result.json").write_text(json.dumps({"passed": False, "error": str(error)}))
        raise
    (evidence/"result.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if not args.describe and args.evidence is None:
        parser.error("--evidence NEW_DIRECTORY required")
    print(json.dumps(protocol() if args.describe else run(args.evidence.resolve()), indent=2))
