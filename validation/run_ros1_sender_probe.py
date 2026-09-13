"""Actual ROS1 subscriptions -> sender process -> TCP decoder; no FC or ROS2 node."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import traceback
import xmlrpc.client

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.bspline_tcp_envelope import BsplineTcpDecoder

SID = "0123456789abcdef0123456789abcdef"
SENDER = REPO / "Modules/ego_planner_swarm/plan_manage/scripts/bspline_tcp_sender.py"


def run(out):
    for name in ("net", "ipc", "mnt"):
        if os.readlink("/proc/self/ns/" + name) == os.readlink("/proc/1/ns/" + name):
            raise ValueError("private " + name + " namespace required")
    os.environ.update(ROS_MASTER_URI="http://127.0.0.1:11323", ROS_IP="127.0.0.1",
                      ROS_HOME=str(out / "ros-home"), ROS_LOG_DIR=str(out / "ros-logs"))
    source_files = [Path(__file__).resolve(), SENDER, REPO / "Simulator/wksim_runtime/bspline_tcp_envelope.py"]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    report = dict(status="failed", physical_acceptance=False, source_sha256=hashes,
                  boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(), frames=[])
    children, logs = {}, []
    connection = None
    rospy = None
    wire = bytearray()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0)); listener.listen(1); listener.settimeout(10)

    def start(name, argv):
        log = (out / (name + ".log")).open("x"); logs.append(log)
        children[name] = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                          cwd=out, start_new_session=True)

    try:
        start("roscore", ["roscore", "-p", "11323"])
        socket.setdefaulttimeout(1)
        deadline = time.monotonic() + 15
        while True:
            try:
                if xmlrpc.client.ServerProxy(os.environ["ROS_MASTER_URI"]).getPid("/sender_fixture")[0] == 1: break
            except (OSError, xmlrpc.client.Error): pass
            if time.monotonic() >= deadline: raise TimeoutError("private ROS master startup")
            time.sleep(0.05)
        import rospy as ros
        rospy = ros
        from std_msgs.msg import Bool, Empty
        from traj_utils.msg import Bspline
        rospy.init_node("wksim_sender_fixture", disable_signals=True)
        publishers = {
            "gate": rospy.Publisher("/uav1/prometheus/command/ego_command_stop_pub", Bool, queue_size=1),
            "bspline": rospy.Publisher("/uav1/planning/bspline", Bspline, queue_size=1),
            "hold": rospy.Publisher("/bspline_tcp_sender/hold", Empty, queue_size=1),
            "cancel": rospy.Publisher("/bspline_tcp_sender/cancel", Empty, queue_size=1),
        }
        start("sender", [sys.executable, "-B", str(SENDER), "_accept_control:=true",
                         "_transport_session_id:=" + SID,
                         "_receiver_host:=127.0.0.1", "_receiver_port:=" + str(listener.getsockname()[1])])
        connection = listener.accept()[0]
        connection.settimeout(5)
        deadline = time.monotonic() + 10
        while not all(pub.get_num_connections() for pub in publishers.values()):
            if time.monotonic() >= deadline: raise TimeoutError("ROS1 input subscription readiness")
            if children["sender"].poll() is not None: raise RuntimeError("sender exited early")
            time.sleep(0.02)
        decoder = BsplineTcpDecoder(SID, accept_control=True)

        def receive():
            while True:
                frame = decoder.read_frame_any()
                if frame is not None:
                    report["frames"].append(dict(kind=frame[0], value=frame[1], envelope=decoder.last_envelope))
                    return frame
                data = connection.recv(65536)
                if not data: raise RuntimeError("sender closed before the expected frame")
                wire.extend(data); decoder.feed(data)

        publishers["gate"].publish(Bool(data=True))
        assert receive() == ("control", {"kind": "gate", "open": True})
        raw = (REPO / "validation/ego-planner-static-20260912-02/bspline.ros1").read_bytes()
        message = Bspline(); message.deserialize(raw)
        original_time = message.start_time.to_nsec()
        publishers["bspline"].publish(message)
        kind, payload = receive()
        assert kind == "bspline" and payload["traj_id"] == message.traj_id
        assert payload["start_time"] == original_time
        assert payload["knots"] == list(message.knots)
        assert payload["pos_pts"] == [(p.x, p.y, p.z) for p in message.pos_pts]
        publishers["hold"].publish(Empty())
        assert receive() == ("control", {"kind": "hold"})
        publishers["cancel"].publish(Empty())
        assert receive() == ("control", {"kind": "cancel"})
        assert [f["envelope"]["sequence"] for f in report["frames"]] == [1, 2, 3, 4]
        publishers["bspline"].publish(message)
        publishers["gate"].publish(Bool(data=True))
        connection.settimeout(0.3)
        try:
            extra = connection.recv(65536)
            if not extra:
                raise RuntimeError("sender closed during the post-cancel observation")
        except socket.timeout:
            extra = b""
        assert not extra, "unexpected post-cancel output"
        (out / "tcp-stream.bin").write_bytes(wire)
        report.update(status="pass", start_time_preserved_ns=original_time,
                      raw_message_sha256=hashlib.sha256(raw).hexdigest(),
                      tcp_stream_sha256=hashlib.sha256(wire).hexdigest(),
                      post_cancel_observation_wall_seconds=0.3)
    except BaseException as error:
        report.update(error=repr(error), traceback=traceback.format_exc())
    finally:
        (out / "tcp-stream.bin").write_bytes(wire)
        for child in reversed(list(children.values())):
            if child.poll() is None:
                try: os.killpg(child.pid, signal.SIGINT)
                except ProcessLookupError: pass
                try: child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    child.wait(timeout=5)
        if connection is not None: connection.close()
        listener.close()
        if rospy is not None: rospy.signal_shutdown("fixture finished")
        for log in logs: log.close()
        report["children"] = {name: dict(pid=p.pid, returncode=p.returncode) for name, p in children.items()}
        report["source_unchanged"] = hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
        if any(p.returncode for p in children.values()) or not report["source_unchanged"]: report["status"] = "failed"
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report.get(k) for k in ("status", "error", "start_time_preserved_ns", "children")}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute() or not args.output.is_dir(): raise ValueError("existing absolute output required")
    sys.exit(run(args.output))
