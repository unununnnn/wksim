"""Run real EGO against explicit static-state/clock fixtures, without a flight controller."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import xmlrpc.client

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools.publish_ego_profile_scene import (float32_round_trip, payload_identity,
                                           source_points, validate_pointcloud_message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(out):
    for ns in ("net", "ipc", "mnt"):
        if os.readlink("/proc/self/ns/" + ns) == os.readlink("/proc/1/ns/" + ns):
            raise ValueError("private " + ns + " namespace required")
    os.environ.update(ROS_MASTER_URI="http://127.0.0.1:11321", ROS_IP="127.0.0.1",
                      ROS_HOME=str(out / "ros-home"), ROS_LOG_DIR=str(out / "ros-logs"))
    launch = REPO / "Modules/ego_planner_swarm/plan_manage/launch_for_prometheus/advanced_param_wksim_single_box.xml"
    binary = Path("/root/wksim-ego-local-pGqjgO/devel/lib/ego_planner/ego_planner_node")
    sources = [Path(__file__).resolve(), launch, REPO / "tools/publish_ego_profile_scene.py",
               REPO / "Simulator/wksim_planning/scene_profile.py"]
    report = dict(status="failed", scope="real planner with static fixtures only",
                  physical_acceptance=False, source_sha256={str(p): digest(p) for p in sources},
                  planner_binary=dict(path=str(binary), sha256=digest(binary)),
                  fixture=dict(odom=[-4.0, 0.0, 3.0], command_control_is_synthetic=True,
                               clock_step_ns=1_000_000, goal=[4.0, 0.0, 3.0]),
                  namespace={n: os.readlink("/proc/self/ns/" + n) for n in ("net", "ipc", "mnt")})
    children, logs = {}, []
    rospy = None
    clock_pub = None
    current_tick = 0
    published_clouds = 0
    map_observation = {}

    def start(name, argv):
        log = (out / (name + ".log")).open("x")
        logs.append(log)
        children[name] = subprocess.Popen(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                                          start_new_session=True)
        return children[name]

    try:
        start("roscore", ["roscore", "-p", "11321"])
        socket.setdefaulttimeout(1)
        deadline = time.monotonic() + 15
        while True:
            try:
                if xmlrpc.client.ServerProxy(os.environ["ROS_MASTER_URI"]).getPid("/ego_fixture")[0] == 1:
                    break
            except (OSError, xmlrpc.client.Error):
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("ROS master startup")
            time.sleep(0.05)
        import rospy as ros
        rospy = ros
        from nav_msgs.msg import Odometry
        from prometheus_msgs.msg import UAVControlState
        from rosgraph_msgs.msg import Clock
        from sensor_msgs.msg import PointCloud2
        from sensor_msgs import point_cloud2
        from std_msgs.msg import Header
        from traj_utils.msg import Bspline
        rospy.set_param("/use_sim_time", True)
        rospy.init_node("wksim_ego_static_fixture", disable_signals=True)
        clock_pub = rospy.Publisher("/clock", Clock, queue_size=1, latch=True)
        odom_pub = rospy.Publisher("/uav1/prometheus/odom", Odometry, queue_size=2)
        state_pub = rospy.Publisher("/uav1/prometheus/control_state", UAVControlState, queue_size=2)
        cloud_pub = rospy.Publisher("/map_generator/global_cloud", PointCloud2, queue_size=1, latch=True)
        cloud = point_cloud2.create_cloud_xyz32(Header(frame_id="world"), float32_round_trip(source_points()))
        validate_pointcloud_message(cloud)
        report["cloud"] = payload_identity()
        report["cloud"]["wire_data_sha256"] = hashlib.sha256(bytes(cloud.data)).hexdigest()
        received, lock = [], threading.Lock()
        map_ready = threading.Event()

        def on_map(message):
            if map_ready.is_set():
                return
            for x, y, z in point_cloud2.read_points(message, field_names=("x", "y", "z"), skip_nans=True):
                if abs(x) < 0.11 and abs(y) < 0.11 and abs(z - 3.0) < 0.11:
                    map_observation.update(frame=message.header.frame_id,
                                           stamp_ns=message.header.stamp.to_nsec(),
                                           points=message.width * message.height,
                                           obstacle_interior_observed=True,
                                           data_sha256=hashlib.sha256(bytes(message.data)).hexdigest())
                    map_ready.set()
                    return

        def on_bspline(message):
            with lock:
                if received:
                    return
                wire = io.BytesIO()
                message.serialize(wire)
                payload = dict(drone_id=message.drone_id, order=message.order, traj_id=message.traj_id,
                               start_time=message.start_time.to_nsec(), knots=list(message.knots),
                               pos_pts=[[p.x, p.y, p.z] for p in message.pos_pts],
                               yaw_pts=list(message.yaw_pts), yaw_dt=message.yaw_dt)
                received.append(dict(payload=payload, wire=wire.getvalue(), received_tick=current_tick,
                                     ros_time_ns=rospy.Time.now().to_nsec(), wall_ns=time.monotonic_ns()))

        subscriber = rospy.Subscriber("/uav1/planning/bspline", Bspline, on_bspline, queue_size=1)
        map_subscriber = rospy.Subscriber("/uav1_ego_planner_node/grid_map/occupancy_inflate",
                                         PointCloud2, on_map, queue_size=1)
        planner = start("planner", ["roslaunch", str(launch)])
        deadline = time.monotonic() + 30
        last_cloud_wall = None
        while time.monotonic() < deadline:
            current_tick += 1
            stamp = rospy.Time(1 + current_tick // 1000, current_tick % 1000 * 1_000_000)
            clock_pub.publish(Clock(clock=stamp))
            if current_tick % 10 == 0:
                odom = Odometry()
                odom.header.stamp, odom.header.frame_id = stamp, "world"
                odom.child_frame_id = "base_link"
                odom.pose.pose.position.x, odom.pose.pose.position.z = -4.0, 3.0
                odom.pose.pose.orientation.w = 1.0
                odom_pub.publish(odom)
                state = UAVControlState()
                state.header.stamp, state.header.frame_id = stamp, "world"
                state.uav_id = 1
                state.control_state = 2 if current_tick >= 1500 and map_ready.is_set() else 0
                state_pub.publish(state)
            # The scene is static. Stop retransmitting after the planner has
            # published occupied voxels inside the known obstacle.
            now = time.monotonic()
            if (not map_ready.is_set() and current_tick >= 100 and cloud_pub.get_num_connections()
                    and (last_cloud_wall is None or now - last_cloud_wall >= 1.0)):
                cloud.header.stamp = stamp
                cloud_pub.publish(cloud)
                published_clouds += 1
                last_cloud_wall = now
            with lock:
                sample = received[0] if received else None
            if sample:
                break
            if planner.poll() is not None:
                raise RuntimeError("planner launch exited before producing a trajectory")
            time.sleep(0.002)
        else:
            raise TimeoutError("EGO did not produce a B-spline within the fixture wall deadline")
        (out / "bspline.ros1").write_bytes(sample.pop("wire"))
        (out / "bspline.json").write_text(json.dumps(sample, indent=2, allow_nan=False) + "\n")
        report.update(status="pass", published_clouds=published_clouds,
                      planner_parameters=rospy.get_param("/uav1_ego_planner_node"),
                      trajectory_id=sample["payload"]["traj_id"],
                      received_tick=sample["received_tick"], final_fixture_tick=current_tick)
        subscriber.unregister()
        map_subscriber.unregister()
    except BaseException as error:
        report.update(error=repr(error), traceback=traceback.format_exc())
    finally:
        report.update(final_fixture_tick=current_tick, published_clouds=published_clouds,
                      observed_map=map_observation)
        for child in reversed(list(children.values())):
            if child.poll() is None:
                try: os.killpg(child.pid, signal.SIGINT)
                except ProcessLookupError: pass
                try: child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    child.wait(timeout=5)
        if rospy is not None:
            rospy.signal_shutdown("static planner fixture finished")
        for log in logs:
            log.close()
        report["children"] = {n: dict(pid=p.pid, returncode=p.returncode) for n, p in children.items()}
        report["source_unchanged"] = report["source_sha256"] == {str(p): digest(p) for p in sources}
        own_net = os.readlink("/proc/self/ns/net")
        leftovers = []
        for proc in Path("/proc").iterdir():
            if proc.name.isdigit() and int(proc.name) != os.getpid():
                try:
                    if os.readlink(proc / "ns/net") == own_net:
                        leftovers.append(int(proc.name))
                except (OSError, ProcessLookupError): pass
        report["remaining_local_namespace_pids"] = leftovers
        if leftovers or not report["source_unchanged"] or any(p.returncode for p in children.values()):
            report["status"] = "failed"
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report.get(k) for k in ("status", "error", "trajectory_id", "received_tick", "children")}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute() or not args.output.is_dir():
        raise ValueError("existing absolute persistent output directory required")
    sys.exit(run(args.output))
