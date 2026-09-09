"""Read-only static Hex X contract probe. Never builds, loads or runs a model.

Run in WSL with explicit local ZIP and pinned AP/PX4 source roots. Only hashes,
parameter values and derived geometry are printed; vendor source is not copied.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import zipfile

ARCHIVE_SHA = "d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed"
MEMBERS = {
    "Exp1_MinModelTemp.cpp": "a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019",
    "Exp1_MinModelTemp.h": "2d89ad1b492c5e70e80682a9f53896e0538260946a0180a2ca44e500ba1589bd",
}
AP_COMMIT = "1511f27194f1dcc3728270883047bdf022b3fd53"
PX4_COMMIT = "d6f12ad1c4f70ad3230afd7d86e971421e02fef4"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def one(pattern, source):
    matches = list(re.finditer(pattern, source, re.S))
    require(len(matches) == 1, "Expected exactly one source match: " + pattern)
    return matches[0]


def git_source(root, commit, paths):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], timeout=15)
    require(git("rev-parse", "HEAD").decode().strip() == commit, "FC commit differs")
    sources, hashes = {}, {}
    for path in paths:
        raw = (root / path).read_bytes()
        require(raw == git("show", commit + ":" + path), "FC source differs: " + path)
        sources[path] = raw.decode("utf-8")
        hashes[path] = sha(raw)
    return sources, {"root": str(root), "commit": commit, "files_sha256": hashes}


def probe(archive, ap_root, px4_root):
    require(sha(archive.read_bytes()) == ARCHIVE_SHA, "Archive SHA256 differs")
    with zipfile.ZipFile(archive) as zipped:
        sources = {}
        for name, expected in MEMBERS.items():
            raw = zipped.read("e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/" + name)
            require(sha(raw) == expected, "Generated member SHA256 differs: " + name)
            sources[name] = raw.decode("latin1")
    cpp = sources["Exp1_MinModelTemp.cpp"]
    arrays = {}
    for name, size in [("d", 10), ("e", 80), ("c", 80)]:
        match = one(r"static const \w+ " + name + r"\[" + str(size) + r"\] = \{(.*?)\};", cpp)
        arrays[name] = [float(v.strip()) for v in match[1].split(",")]
        require(len(arrays[name]) == size, "Generated table size differs")
    require("s297_iter = d[uavType - 1];" in cpp and
            "s305_iter = (10 * rtb_Sum_i + uavType) - 1;" in cpp,
            "Generated table selection differs")
    parameters = {}
    for match in re.finditer(r"// Variable: (Model\w+)\s*(?://[^\r\n]*\s*)+([{}0-9., +Ee\-]+),", cpp):
        name, value = match.groups()
        require(name not in parameters, "Duplicate initializer: " + name)
        parameters[name] = ([float(v.strip()) for v in value.strip(" {}\r\n").split(",")]
                            if "{" in value else float(value))
    require(len(parameters) == 22 and "ModelParam_uavMotNumbs" not in parameters,
            "Named generated parameter layout differs")
    require(parameters["ModelParam_uavType"] == 3 and parameters["ModelParam_3DType"] == 3,
            "Original model defaults differ")
    require(arrays["d"][4] == 6, "Hex X rotor count differs")
    angles = [math.degrees(arrays["e"][10 * i + 4]) % 360 for i in range(6)]
    spins = [int(arrays["c"][10 * i + 4]) for i in range(6)]
    require(all(abs(a - b) < 1e-10 for a, b in zip(angles, [90, 270, 330, 150, 30, 210]))
            and spins == [1, -1, 1, -1, -1, 1], "Hex X table contract differs")
    for i in range(6):
        one(r"Exp1_MinModelTemp_U.inPWMs\[" + str(i) +
            r"\], &Exp1_MinModelTemp_B.MotorNonlinearDynamic" + str(i + 1) + r",", cpp)
        one(r"VehileInfo60d\[" + str(16 + i) + r"\] = .*?MotorNonlinearDynamic" +
            str(i + 1) + r"\.Motor_Dynamics.x;", cpp)
    radius = parameters["ModelParam_uavR"]
    rotors = [{"input_index": i, "angle_deg": angles[i], "source_spin": spins[i],
               "position_frd_m": [radius * math.cos(math.radians(angles[i])),
                                  radius * math.sin(math.radians(angles[i])), 0.0],
               "rpm_output_index": 16 + i} for i in range(6)]
    ap_path = "libraries/AP_Motors/AP_MotorsMatrix.cpp"
    ap, ap_evidence = git_source(ap_root, AP_COMMIT, [ap_path,
        "libraries/AP_Motors/AP_MotorsMatrix.h", "libraries/AP_Motors/AP_Motors_Class.h",
        "libraries/AP_Motors/AP_Motors_Class.cpp", "libraries/SRV_Channel/SRV_Channel.h",
        "Tools/autotest/default_params/copter-hexa.parm", "Tools/autotest/default_params/copter-X.parm"])
    body = one(r"bool AP_MotorsMatrix::setup_hexa_matrix\(.*?case MOTOR_FRAME_TYPE_X: \{(.*?)break;", ap[ap_path])[1]
    rows = re.findall(r"\{\s*(-?\d+), AP_MOTORS_MATRIX_YAW_FACTOR_(CW|CCW),\s*(\d+) \}", body)
    require(len(rows) == 6, "AP Hexa X row count differs")
    require(all(abs(float(row[0]) % 360 - angles[i]) < 1e-10 and
                (1 if row[1] == "CW" else -1) == spins[i] for i, row in enumerate(rows)),
            "AP Hexa X source order/spin does not match")
    require(re.search(r"MOTOR_FRAME_HEXA\s*=\s*2,", ap["libraries/AP_Motors/AP_Motors_Class.h"])
            and re.search(r"MOTOR_FRAME_TYPE_X\s*=\s*1,", ap["libraries/AP_Motors/AP_Motors_Class.h"]),
            "AP frame enum differs")
    px_path = "ROMFS/px4fmu_common/init.d/airframes/6001_hexa_x"
    px, px_evidence = git_source(px4_root, PX4_COMMIT, [px_path,
        "ROMFS/px4fmu_common/init.d-posix/rcS", "src/modules/control_allocator/module.yaml",
        "src/modules/control_allocator/VehicleActuatorEffectiveness/ActuatorEffectivenessRotors.cpp",
        "src/modules/simulation/simulator_mavlink/SimulatorMavlink.cpp"])
    px_params = dict(re.findall(r"^param set-default (\w+) ([^\s]+)$", px[px_path], re.M))
    require(px_params["CA_ROTOR_COUNT"] == "6", "PX4 rotor count differs")
    px_defaults = {key: float(one(r"CA_ROTOR\$\{i\}_" + key + r":.*?default: ([^\s]+)",
                                  px["src/modules/control_allocator/module.yaml"])[1])
                   for key in ["AX", "AY", "AZ", "CT", "KM"]}
    require(px_defaults == {"AX": 0, "AY": 0, "AZ": -1, "CT": 6.5, "KM": .05},
            "PX4 rotor defaults differ")
    px_rotors = []
    for i in range(6):
        x = float(px_params["CA_ROTOR%d_PX" % i])
        y = float(px_params["CA_ROTOR%d_PY" % i])
        km = float(px_params.get("CA_ROTOR%d_KM" % i, px_defaults["KM"]))
        angle = math.degrees(math.atan2(y, x)) % 360
        require(abs(angle - angles[i]) < 0.2 and (1 if km < 0 else -1) == spins[i],
                "PX4 nominal order/spin differs")
        px_rotors.append({"index": i, "position_body": [x, y, 0], "km": km,
                          "angle_deg": angle, "angle_difference_deg": angle - angles[i]})
    return {"schema": "wksim.hex-static-source.v1", "scope": "static source only; no build/run/flight/render",
            "archive_sha256": ARCHIVE_SHA, "members_sha256": MEMBERS,
            "source_defaults": parameters, "candidate_uavType": 5, "motor_count": 6,
            "rotors": rotors, "ap": {**ap_evidence, "frame_class": 2, "frame_type": 1,
                                     "motor_test_order": [int(r[2]) for r in rows]},
            "px4": {**px_evidence, "rotors": px_rotors, "source_rotor_defaults": px_defaults,
                    "posix_6001_files": [str(p.relative_to(px4_root)) for p in
                        (px4_root / "ROMFS/px4fmu_common/init.d-posix/airframes").glob("6001_*")]},
            "derived_abs_torque_thrust_ratio_m": parameters["ModelParam_rotorCm"] / parameters["ModelParam_rotorCt"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--ap-source", required=True, type=Path)
    parser.add_argument("--px4-source", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(probe(args.archive, args.ap_source, args.px4_source), indent=2, allow_nan=False))
