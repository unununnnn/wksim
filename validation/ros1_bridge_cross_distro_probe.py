"""Ubuntu ROS2 publisher and Rfly ROS1 bridge in one owned network, separate IPC."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Simulator.wksim_runtime import netns_handoff
from validation import ros1_bridge_reverse_probe as reverse


def namespaces():
    return {name: os.readlink("/proc/self/ns/" + name) for name in ("net", "ipc", "mnt")}


def source_hashes():
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
        Path(__file__).resolve(), Path(netns_handoff.__file__).resolve(), Path(reverse.__file__).resolve())}


def wait_file(path, timeout):
    deadline = time.monotonic() + timeout
    while not path.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError("waiting for " + str(path))
        time.sleep(0.02)


def run(role, shared, out, udp_profile=None):
    if udp_profile is not None:
        if not udp_profile.is_absolute() or not udp_profile.is_file():
            raise ValueError("existing absolute Fast DDS profile required")
        os.environ["FASTRTPS_DEFAULT_PROFILES_FILE"] = str(udp_profile)
        # Humble RMW appends SHM after loading XML when localhost_only is true.
        # Containment here is the owned netns plus the XML loopback whitelist.
        os.environ["ROS_LOCALHOST_ONLY"] = "0"
    before = source_hashes()
    report = dict(status="failed", role=role, distro=os.environ.get("WSL_DISTRO_NAME"),
                  boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                  initial_namespaces=namespaces(), source_sha256=before,
                  physical_acceptance=False)
    if udp_profile is not None:
        report["udp_profile"] = dict(path=str(udp_profile), sha256=hashlib.sha256(udp_profile.read_bytes()).hexdigest())
    try:
        for name in ("ipc", "mnt"):
            if report["initial_namespaces"][name] == os.readlink("/proc/1/ns/" + name):
                raise ValueError("private " + name + " namespace required")
        if role == "owner":
            report["handoff"] = netns_handoff.export_namespace(shared, "cross-distro-ros-fixture", timeout=60)
            wait_file(out / "receiver-ready", 20)
            reverse.ros2(out)
        else:
            wait_file(shared / "grant.json", 30)
            report["handoff"] = netns_handoff.enter_namespace(shared, "cross-distro-ros-fixture")
            if not Path("/opt/ros/noetic/setup.bash").is_file():
                raise ValueError("Rfly Noetic filesystem missing after entry")
            if reverse.run_probe(out, external_publisher=True,
                                 localhost_only=udp_profile is None) != 0:
                raise RuntimeError("cross-distribution bridge fixture failed")
        report["status"] = "pass"
    except BaseException as error:
        report.update(error=repr(error), traceback=traceback.format_exc())
    finally:
        report["final_namespaces"] = namespaces()
        report["source_unchanged"] = source_hashes() == before
        if not report["source_unchanged"]:
            report["status"] = "failed"
        with (out / (role + "-result.json")).open("x") as result:
            json.dump(report, result, indent=2)
            result.write("\n")
    print(json.dumps(report))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("owner", "visitor"))
    parser.add_argument("shared", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--udp-profile", type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute() or not args.output.is_dir():
        raise ValueError("existing absolute persistent evidence directory required")
    sys.exit(run(args.role, args.shared, args.output, args.udp_profile))
