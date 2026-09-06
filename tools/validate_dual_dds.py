"""One isolated ROS2 graph, two native FC missions, one independent observer."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from ardupilot_msgs.msg import Status
from geometry_msgs.msg import PoseStamped
from px4_msgs.msg import VehicleStatus, VehicleLocalPosition

from sitl_dds import enu_to_ned, px4_topic

REPO = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    if os.readlink("/proc/self/ns/net") == os.readlink("/proc/1/ns/net") or os.environ.get("ROS_DOMAIN_ID") != "77":
        parser.error("Use run-dds-validation.sh both in its private network namespace / domain 77")
    directory = Path(tempfile.mkdtemp(prefix="dual-dds-", dir=REPO / "validation"))
    print(json.dumps({"result_dir": str(directory)}), flush=True)
    result = {"status": "failed", "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "scope": "two simultaneous native DDS quad-X missions and ground Agent reconnection; not Prometheus/UE/full-product acceptance",
              "network_namespace": os.readlink("/proc/self/ns/net"), "domain_id": 77,
              "observer_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    latest, received_at, counts, children, logs = {}, {}, {}, {}, []
    first_both_armed, last_both_armed, armed_samples = None, None, 0
    started = time.monotonic()
    rclpy.init(args=[])
    node = rclpy.create_node("wksim_dual_native_observer")
    subscriptions = []
    topics = {"ap_status": (Status, "/ap/status"), "ap_position": (PoseStamped, "/ap/pose/filtered"),
              "px4_status": (VehicleStatus, px4_topic("out", "vehicle_status", VehicleStatus)),
              "px4_position": (VehicleLocalPosition, px4_topic("out", "vehicle_local_position", VehicleLocalPosition))}

    def received(key, message):
        latest[key] = message
        received_at[key] = time.monotonic()
        counts[key] = counts.get(key, 0) + 1

    def pump():
        nonlocal first_both_armed, last_both_armed, armed_samples
        rclpy.spin_once(node, timeout_sec=0.01)
        if "ap_status" in latest and "px4_status" in latest:
            ap, px = latest["ap_status"], latest["px4_status"]
            if px.system_id != 22:
                raise RuntimeError("PX4 namespace contains an unexpected vehicle identity")
            if (ap.armed and px.arming_state == px.ARMING_STATE_ARMED
                    and all(time.monotonic() - received_at[key] < 0.5 for key in ("ap_status", "px4_status"))):
                first_both_armed = first_both_armed or time.monotonic()
                last_both_armed = time.monotonic()
                armed_samples += 1

    def interrupted(signum, frame):
        raise RuntimeError(f"Dual validation interrupted by signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        for key, (cls, topic) in topics.items():
            subscriptions.append(node.create_subscription(cls, topic, lambda msg, k=key: received(k, msg), qos_profile_sensor_data))
        for stack in ("arducopter", "px4"):
            log = (directory / f"{stack}.log").open("x", encoding="utf-8")
            logs.append(log)
            children[stack] = subprocess.Popen([sys.executable, str(REPO / "tools/validate_sitl_physics.py"),
                "--stack", stack, "--dds-workspace", str(args.workspace), "--ready-barrier", str(directory)],
                stdout=log, stderr=subprocess.STDOUT, cwd=REPO, start_new_session=True)
        while not all((directory / f"{stack}.ready").is_file() for stack in children) or len(latest) != len(topics):
            if time.monotonic() - started > 65 or any(child.poll() is not None for child in children.values()):
                raise RuntimeError("Both stacks did not reach native DDS readiness; inspect child logs")
            pump()
        graph = {}
        for key, (_, topic) in topics.items():
            endpoints = node.get_publishers_info_by_topic(topic)
            if len(endpoints) != 1:
                raise RuntimeError(f"Expected one native publisher for {topic}, got {len(endpoints)}")
            graph[key] = {"topic": topic, "publishers": [{"node_name": e.node_name, "namespace": e.node_namespace,
                "type": e.topic_type, "gid": list(e.endpoint_gid), "qos": str(e.qos_profile)} for e in endpoints]}
        result["native_publishers"] = graph
        result["graph_topics"] = node.get_topic_names_and_types()
        result["graph_services"] = node.get_service_names_and_types()
        with (directory / "go").open("x") as marker:
            marker.write("Both native stacks observed, unique publishers, release missions.\n")
        print("Both native stacks observed in one graph; simultaneous missions released", flush=True)
        while any(child.poll() is None for child in children.values()):
            if time.monotonic() - started > 150:
                raise TimeoutError("Dual mission wall-clock watchdog")
            pump()
        result["missions"] = {}
        for stack, child in children.items():
            child_dir = Path(json.loads((directory / f"{stack}.ready").read_text())["result_dir"])
            child_result = child_dir / "result.json"
            data = json.loads(child_result.read_text())
            result["missions"][stack] = {"exit_code": child.returncode, "status": data["status"],
                "result": str(child_result), "sha256": hashlib.sha256(child_result.read_bytes()).hexdigest(),
                "truth": data.get("truth"), "reconnect": data.get("dds_reconnect"), "error": data.get("error")}
            if child.returncode or data["status"] != "pass":
                raise RuntimeError(f"{stack} mission failed: {data.get('error')}")
        if not armed_samples:
            raise RuntimeError("No simultaneous armed state was actually observed")
        if latest["ap_status"].armed or latest["px4_status"].arming_state == latest["px4_status"].ARMING_STATE_ARMED:
            raise RuntimeError("Observer did not independently see both vehicles disarmed")
        ap = latest["ap_position"].pose.position
        px = latest["px4_position"]
        final_positions = {"arducopter": enu_to_ned([ap.x, ap.y, ap.z]), "px4": [px.x, px.y, px.z]}
        if any(not all(math.isfinite(v) for v in pos) or abs(pos[2]) >= 0.3 for pos in final_positions.values()):
            raise RuntimeError("Observer did not independently see both vehicles on the ground")
        result["final_observed_positions_ned"] = final_positions
        result["status"] = "pass"
    except Exception as error:
        result["error"] = str(error)
    finally:
        for child in children.values():
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    # All descendants belong to this newly created process group.
                    os.killpg(child.pid, signal.SIGTERM)
                    child.wait(timeout=5)
        for log in logs:
            log.close()
        node.destroy_node()
        rclpy.shutdown()
        result["observed_message_counts"] = counts
        result["simultaneously_armed_observations"] = armed_samples
        result["simultaneously_armed_span_wall_seconds"] = last_both_armed - first_both_armed if armed_samples else 0
        result["wall_seconds"] = time.monotonic() - started
        result["children_reaped"] = all(child.poll() is not None for child in children.values())
        (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in result.items() if key in (
            "status", "error", "missions", "observed_message_counts", "simultaneously_armed_observations",
            "simultaneously_armed_span_wall_seconds", "children_reaped")}, indent=2), flush=True)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
