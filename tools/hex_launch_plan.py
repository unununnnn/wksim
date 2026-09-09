"""Print a static Hex parameter plan; never launch or mutate flight controllers."""
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build_hex_model_candidate import ANGLES, SPINS, canonical, make_config, sha


def launch_plan():
    config = make_config()
    params = config["parameters"]
    radius = params["ModelParam_uavR"]["value"]
    ratio = params["ModelParam_rotorCm"]["value"] / params["ModelParam_rotorCt"]["value"]
    ap = {"FRAME_CLASS": 2, "FRAME_TYPE": 1, "MOT_PWM_MIN": 1000, "MOT_PWM_MAX": 2000,
          "MOT_BAT_VOLT_MIN": 0, "MOT_BAT_VOLT_MAX": 0, "SIM_RATE_HZ": 1000,
          "ARMING_CHECK": 1, "SR0_POSITION": 10, "SR0_EXTRA1": 10, "SR0_EXTRA3": 5}
    for channel in range(1, 7):
        ap.update({f"SERVO{channel}_FUNCTION": channel + 32,
                   f"SERVO{channel}_MIN": 1000, f"SERVO{channel}_MAX": 2000})
    px4 = {"MAV_TYPE": 13, "CA_AIRFRAME": 0, "CA_ROTOR_COUNT": 6, "CA_R_REV": 0}
    for motor, (angle, spin) in enumerate(zip(ANGLES, SPINS)):
        x, y = radius * math.cos(math.radians(angle)), radius * math.sin(math.radians(angle))
        geometry = {"PX": 0. if abs(x) < 1e-15 else x, "PY": y, "PZ": 0.,
                    "AX": 0., "AY": 0., "AZ": -1., "CT": 6.5, "KM": -spin * ratio, "TILT": 0}
        px4.update({f"CA_ROTOR{motor}_{name}": value for name, value in geometry.items()})
    px4.update({f"PWM_MAIN_FUNC{channel}": 100 + channel if channel <= 6 else 0 for channel in range(1, 17)})
    plan = dict(schema="wksim.hex-launch-plan.v1", model_identity=config["model_identity"],
        status="static_candidate_not_flight_admitted", ap_parameters=ap,
        ap_parameter_file="".join(f"{name} {value}\n" for name, value in ap.items()),
        px4_parameters=px4, px4_environment={
            "PX4_SYS_AUTOSTART": "10016", "PX4_SIM_MODEL": "none_iris",
            "PX4_SIMULATOR": "", "PX4_SIM_HOST_ADDR": "127.0.0.1", "PX4_SIM_HOSTNAME": "",
            "PX4_SIM_SPEED_FACTOR": "1", **{"PX4_PARAM_" + k: str(v) for k, v in px4.items()}},
        px4_profile="custom source-template Hex X via explicit overrides of POSIX 10016; no POSIX 6001",
        allocation_ct_basis="6.5 is pinned PX4 default output-signal coefficient, NOT native rotorCt in rad/s units",
        requirements=["Fresh process and parameter storage for each stack/epoch; clean scoped environment",
            "Verify sealed FC binary, build runtime scripts, source and patch identities before launch",
            "Read back every listed parameter after startup and before arming; account for FLOAT32 storage",
            "AP defaults order: copter.parm, independent Hex file, late-created DDS defaults LAST",
            "PX4 original simulator_mavlink route, simulator port 4560+instance; original DDS and MAVLink routing",
            "Separate experimental launch identity and preflight; never relabel or bypass production Quad admission",
            "Freeze mission, thresholds, cold-reset evidence and six-rotor UE contract before flight"])
    plan["plan_identity"] = "sha256:" + sha(canonical(plan).encode())
    return plan


if __name__ == "__main__":
    print(json.dumps(launch_plan(), indent=2, allow_nan=False))
