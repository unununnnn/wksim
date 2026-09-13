"""Isolated real ROS2 -> ros1_bridge -> ROS1 transport fixture, never FC input."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import xmlrpc.client

STAMPS = (1_000_000_000, 1_020_000_000, 1_040_000_000)
TOPICS = ("/clock", "/wksim_bridge_probe/odom", "/wksim_bridge_probe/control",
          "/wksim_bridge_probe/boxes", "/wksim_bridge_probe/detections")
BRIDGE_ROOT = Path("/root/wksim-ros1-bridge-humble-8oGKuV")


def expected(index):
    return {
        "stamp_ns": STAMPS[index], "frame": "world", "child": "base_link",
        "position": [1.25 + index, -2.5, 3.0],
        "velocity": [0.125, -0.25, 0.5], "orientation": [0.0, 0.0, 0.0, 1.0],
        "uav_id": 1, "control_state": 2, "pos_controller": 0,
        "failsafe": index == 1,
    }


def ros1(out):
    import rospy
    from nav_msgs.msg import Odometry
    from prometheus_msgs.msg import BoundingBoxes, MultiDetectionInfoSub, UAVControlState
    from rosgraph_msgs.msg import Clock

    rospy.set_param("/use_sim_time", True)
    rospy.init_node("wksim_bridge_fixture_receiver", disable_signals=True)
    latest, lock = {}, threading.Lock()

    def receive_clock(msg):
        with lock:
            latest["clock"] = msg.clock.to_nsec()

    def receive_odom(msg):
        p, v, q = msg.pose.pose.position, msg.twist.twist.linear, msg.pose.pose.orientation
        with lock:
            latest["odom"] = {
                "stamp_ns": msg.header.stamp.to_nsec(), "frame": msg.header.frame_id,
                "child": msg.child_frame_id, "position": [p.x, p.y, p.z],
                "velocity": [v.x, v.y, v.z], "orientation": [q.x, q.y, q.z, q.w],
            }

    def receive_control(msg):
        with lock:
            latest["control"] = {
                "stamp_ns": msg.header.stamp.to_nsec(), "frame": msg.header.frame_id,
                "uav_id": msg.uav_id, "control_state": msg.control_state,
                "pos_controller": msg.pos_controller, "failsafe": msg.failsafe,
            }

    def receive_boxes(msg):
        with lock:
            latest["boxes"] = dict(stamp_ns=msg.header.stamp.to_nsec(),
                                   values=[box.Class for box in msg.bounding_boxes])

    def receive_detections(msg):
        with lock:
            latest["detections"] = dict(stamp_ns=msg.header.stamp.to_nsec(),
                                        values=[item.trackIds for item in msg.detection_infos])

    subscriptions = [rospy.Subscriber(topic, cls, callback, queue_size=10)
                     for topic, cls, callback in zip(
                         TOPICS, (Clock, Odometry, UAVControlState, BoundingBoxes, MultiDetectionInfoSub),
                         (receive_clock, receive_odom, receive_control, receive_boxes, receive_detections))]
    records = []
    (out / "receiver-ready").touch(exist_ok=False)
    try:
        for index, stamp in enumerate(STAMPS):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                with lock:
                    sample = dict(latest)
                if (sample.get("clock") == stamp and
                        sample.get("odom", {}).get("stamp_ns") == stamp and
                        sample.get("control", {}).get("stamp_ns") == stamp and
                        sample.get("boxes", {}).get("stamp_ns") == stamp and
                        sample.get("detections", {}).get("stamp_ns") == stamp and
                        rospy.Time.now().to_nsec() == stamp):
                    break
                time.sleep(0.01)  # Wall time: a paused ROS clock must not deadlock the test.
            else:
                raise RuntimeError(f"ROS1 sample {index} incomplete: {sample}")
            merged = dict(sample["odom"], **sample["control"])
            assert merged == expected(index), (merged, expected(index))
            assert sample["boxes"]["values"] == ["fixture-" + str(index)]
            assert sample["detections"]["values"] == [1000 + index]
            before = rospy.Time.now().to_nsec()
            time.sleep(0.12)
            after = rospy.Time.now().to_nsec()
            assert before == after == stamp, (before, after, stamp)
            records.append(dict(index=index, observed=sample, frozen_ros_time_ns=after))
            (out / f"sample-{index}-received").touch(exist_ok=False)
        report = dict(scope="synthetic reverse-message and paused-clock transport only",
                      physical_acceptance=False, records=records,
                      namespace={n: os.readlink("/proc/self/ns/" + n) for n in ("net", "ipc", "mnt")})
        (out / "ros1-result.json").write_text(json.dumps(report, indent=2) + "\n")
    finally:
        for subscription in subscriptions:
            subscription.unregister()
        rospy.signal_shutdown("owned bridge fixture finished")


def ros2(out):
    import rclpy
    from rclpy.utilities import get_rmw_implementation_identifier
    from nav_msgs.msg import Odometry
    from prometheus_msgs.msg import (BoundingBox, BoundingBoxes, DetectionInfoSub,
                                     MultiDetectionInfoSub, UAVControlState)
    from rosgraph_msgs.msg import Clock

    rclpy.init(args=[])
    node = rclpy.create_node("wksim_bridge_fixture_publisher")
    publishers = [node.create_publisher(cls, topic, 10)
                  for cls, topic in zip((Clock, Odometry, UAVControlState,
                                         BoundingBoxes, MultiDetectionInfoSub), TOPICS)]
    try:
        for index, stamp in enumerate(STAMPS):
            data = expected(index)
            clock, odom, control = Clock(), Odometry(), UAVControlState()
            boxes, detections = BoundingBoxes(), MultiDetectionInfoSub()
            sec, nanosec = divmod(stamp, 1_000_000_000)
            clock.clock.sec, clock.clock.nanosec = sec, nanosec
            for msg in (odom, control, boxes, detections):
                msg.header.stamp.sec, msg.header.stamp.nanosec = sec, nanosec
                msg.header.frame_id = data["frame"]
            odom.child_frame_id = data["child"]
            for axis, value in zip("xyz", data["position"]):
                setattr(odom.pose.pose.position, axis, value)
            for axis, value in zip("xyz", data["velocity"]):
                setattr(odom.twist.twist.linear, axis, value)
            odom.pose.pose.orientation.w = 1.0
            control.uav_id, control.control_state = data["uav_id"], data["control_state"]
            control.pos_controller, control.failsafe = data["pos_controller"], data["failsafe"]
            box = BoundingBox()
            box.class_name = "fixture-" + str(index)
            boxes.bounding_boxes = [box]
            detection = DetectionInfoSub()
            detection.track_ids = 1000 + index
            detections.num_objs = 1
            detections.detection_infos = [detection]
            deadline = time.monotonic() + 20
            while not (out / f"sample-{index}-received").exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"ROS1 receipt timed out for sample {index}")
                for publisher, message in zip(publishers, (clock, odom, control, boxes, detections)):
                    publisher.publish(message)
                rclpy.spin_once(node, timeout_sec=0.02)
                time.sleep(0.03)
        (out / "ros2-result.json").write_text(json.dumps(dict(samples=3, commands_sent=0)) + "\n")
    finally:
        graph = {}
        for topic in TOPICS:
            graph[topic] = {}
            for label, query in (("publishers", node.get_publishers_info_by_topic),
                                 ("subscriptions", node.get_subscriptions_info_by_topic)):
                graph[topic][label] = [dict(node=info.node_name, gid=list(info.endpoint_gid),
                                          reliability=str(info.qos_profile.reliability),
                                          durability=str(info.qos_profile.durability)) for info in query(topic)]
        details = dict(pid=os.getpid(), rmw=get_rmw_implementation_identifier(), graph=graph,
                       libraries=sorted({line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines()
                                         if any(name in line for name in ("libfastrtps", "libfastcdr", "librmw_"))}))
        (out / "publisher-runtime.json").write_text(json.dumps(details, indent=2) + "\n")
        node.destroy_node()
        rclpy.shutdown()


def run_probe(out, *, external_publisher=False, localhost_only=True):
    """Own all fixture processes within the caller's private namespaces."""
    clean = dict(os.environ)
    for key in ("CMAKE_PREFIX_PATH", "AMENT_PREFIX_PATH", "COLCON_PREFIX_PATH",
                "LD_LIBRARY_PATH", "PYTHONPATH", "ROS_PACKAGE_PATH", "ROS_DISTRO",
                "PKG_CONFIG_PATH"):
        clean.pop(key, None)
    clean.update(PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                 ROS_MASTER_URI="http://127.0.0.1:11319", ROS_IP="127.0.0.1",
                 ROS_DOMAIN_ID="79", ROS_LOCALHOST_ONLY="1" if localhost_only else "0", PYTHONDONTWRITEBYTECODE="1",
                 ROS_HOME=str(out / "ros-home"), ROS_LOG_DIR=str(out / "ros-logs"))
    ros1_setup = "source /opt/ros/noetic/setup.bash; source /root/wksim-ego-local-pGqjgO/devel/setup.bash; "
    ros2_setup = "source /opt/ros/humble/setup.bash; source " + str(BRIDGE_ROOT / "messages_ws/install/setup.bash") + "; "
    bridge_setup = ros1_setup + ros2_setup + "source " + str(BRIDGE_ROOT / "bridge_ws/install-full-ego/local_setup.bash") + "; "
    children, logs = {}, []
    report = dict(status="failed", physical_acceptance=False, topics=TOPICS,
                  external_publisher=external_publisher,
                  namespace_scan_scope="current distribution proc view")

    def launch(name, setup, argv):
        log = (out / (name + ".log")).open("x")
        logs.append(log)
        child = subprocess.Popen(["bash", "-c", "set -e; " + setup + 'exec "$@"', "fixture", *argv],
                                 cwd=out, env=clean, start_new_session=True,
                                 stdout=log, stderr=subprocess.STDOUT)
        children[name] = child
        return child

    def wait_until(predicate, seconds, label, allowed_exits=()):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            failed = {n: p.returncode for n, p in children.items()
                      if p.poll() is not None and (n not in allowed_exits or p.returncode != 0)}
            if failed:
                raise RuntimeError(f"{label}: processes exited early: {failed}")
            time.sleep(0.05)
        raise TimeoutError(label)

    def master_ready():
        try:
            reply = xmlrpc.client.ServerProxy(clean["ROS_MASTER_URI"]).getPid("/wksim_fixture_probe")
            return reply[0] == 1
        except (OSError, xmlrpc.client.Error):
            return False

    socket.setdefaulttimeout(1)
    try:
        launch("roscore", ros1_setup, ["roscore", "-p", "11319"])
        wait_until(master_ready, 15, "private ROS master readiness")
        launch("receiver", ros1_setup, [sys.executable, "-B", str(Path(__file__).resolve()), "ros1", str(out)])
        wait_until(lambda: (out / "receiver-ready").exists(), 15, "ROS1 subscriber readiness")
        binary = BRIDGE_ROOT / "bridge_ws/install-full-ego/lib/ros1_bridge/dynamic_bridge"
        # Colcon uses an isolated package prefix.
        if not binary.is_file():
            binary = BRIDGE_ROOT / "bridge_ws/install-full-ego/ros1_bridge/lib/ros1_bridge/dynamic_bridge"
        launch("bridge", bridge_setup, [str(binary), "--bridge-all-2to1-topics"])
        if external_publisher:
            wait_until(lambda: (out / "ros2-result.json").exists(), 75,
                       "external ROS2 fixture publication", allowed_exits=("receiver",))
        else:
            publisher = launch("publisher", ros2_setup, [sys.executable, "-B", str(Path(__file__).resolve()), "ros2", str(out)])
            if publisher.wait(timeout=75) != 0:
                raise RuntimeError("ROS2 fixture publication failed")
        if children["receiver"].wait(timeout=5) != 0:
            raise RuntimeError("ROS1 fixture verification failed")
        if any(children[name].poll() is not None for name in ("bridge", "roscore")):
            raise RuntimeError("bridge or ROS master exited before fixture completion")
        assert (out / "ros1-result.json").is_file() and (out / "ros2-result.json").is_file()
        report["status"] = "pass"
    except Exception as error:
        report["error"] = repr(error)
    finally:
        bridge = children.get("bridge")
        if bridge is not None and bridge.poll() is None:
            try:
                proc = Path("/proc") / str(bridge.pid)
                selected = ("FASTRTPS_DEFAULT_PROFILES_FILE", "FASTDDS_DEFAULT_PROFILES_FILE",
                            "ROS_DOMAIN_ID", "ROS_LOCALHOST_ONLY", "RMW_IMPLEMENTATION")
                entries = [part.split(b"=", 1) for part in (proc / "environ").read_bytes().split(b"\0") if b"=" in part]
                details = dict(pid=bridge.pid,
                               environment={k.decode(): v.decode() for k, v in entries if k.decode() in selected},
                               libraries=sorted({line.split()[-1] for line in (proc / "maps").read_text().splitlines()
                                                 if any(name in line for name in ("libfastrtps", "libfastcdr", "librmw_"))}))
                (out / "bridge-runtime.json").write_text(json.dumps(details, indent=2) + "\n")
            except (OSError, UnicodeError) as error:
                report["runtime_capture_error"] = repr(error)
        for child in reversed(list(children.values())):
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.wait(timeout=5)
        for log in logs:
            log.close()
        report["children"] = {n: dict(pid=p.pid, returncode=p.returncode) for n, p in children.items()}
        own_net = os.readlink("/proc/self/ns/net")
        leftovers = []
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit() or int(proc.name) == os.getpid():
                continue
            try:
                if os.readlink(proc / "ns/net") == own_net:
                    leftovers.append(int(proc.name))
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                pass
        report["remaining_namespace_pids"] = leftovers
        if leftovers:
            report["status"] = "failed"
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(output=str(out), **report)))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("run", "ros1", "ros2"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    for ns in ("net", "ipc", "mnt"):
        if os.readlink("/proc/self/ns/" + ns) == os.readlink("/proc/1/ns/" + ns):
            raise RuntimeError("private " + ns + " namespace required")
    if not args.output.is_absolute() or not args.output.is_dir():
        raise ValueError("existing absolute output directory required")
    sys.exit({"run": run_probe, "ros1": ros1, "ros2": ros2}[args.role](args.output))
