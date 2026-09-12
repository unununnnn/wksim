"""Installed-only v2 receive/release smoke with explicit synthetic state; no FC."""
import json
import os
from pathlib import Path
import socket
import sys
import time

import rclpy
from rosgraph_msgs.msg import Clock
from wksim_msgs.msg import SessionState
from prometheus_msgs.msg import UAVControlState
from Simulator.wksim_runtime.bspline_tcp_envelope import BsplineTcpEncoder
from Simulator.wksim_runtime.planner_transport_node import PlannerTransportNode


class Capture:
    def __init__(self): self.messages = []
    def publish(self, message): self.messages.append(message)


prefix = Path(sys.argv[1]).resolve()
node = None
peer = None
rclpy.init(args=["--ros-args", "-p", "use_sim_time:=true"])
try:
    node = PlannerTransportNode(run_id="installed-v2", mission_id="no-flight",
                                uav_id=1, fallback_yaw=0.0, authority_anchor_ns=1_000_000_000,
                                listen_host="127.0.0.1", listen_port=39194,
                                transport_session_id="a" * 32, accept_control=True,
                                cancel_mode="BRAKE", expected_native_mode="BRAKE")
    publisher = node.create_publisher(Clock, "/clock", 10)
    clock = Clock(); clock.clock.sec = 1
    deadline = time.monotonic() + 5
    while node.get_clock().now().nanoseconds != 1_000_000_000:
        if time.monotonic() >= deadline: raise TimeoutError("installed ROS clock did not initialize")
        publisher.publish(clock)
        rclpy.spin_once(node, timeout_sec=0.02)
    now = time.monotonic()
    state = SessionState(version=SessionState.VERSION, run_id="installed-v2",
                         control_epoch="b" * 32, sequence=1,
                         source_received_valid=True, source_received_monotonic_s=now,
                         published_monotonic_s=now)
    state.state.uav_id = state.control.uav_id = 1
    state.state.connected = state.state.odom_valid = True
    state.state.header.frame_id = "map"; state.state.header.stamp.sec = 1
    state.control.control_state = UAVControlState.COMMAND_CONTROL
    assert node.on_session_state(state)
    commands, setups = Capture(), Capture()
    node.command_pub, node.setup_pub = commands, setups
    peer = socket.create_connection(("127.0.0.1", 39194))
    encoder = BsplineTcpEncoder("a" * 32)
    peer.sendall(encoder.encode_control_frame({"kind": "gate", "open": False}) +
                 encoder.encode_control_frame({"kind": "cancel"}))
    assert node.on_receive_timer()
    assert node.on_drive_timer()
    assert not commands.messages and len(setups.messages) == 1
    setup = setups.messages[0]
    assert setup.request_id == 1 and setup.setup.cmd == setup.setup.SET_PX4_MODE
    assert setup.setup.px4_mode == "BRAKE" and setup.control_epoch == "b" * 32
    assert node.session.state == "CANCELLED" and not node.egress.release["confirmed"]
    modules = {}
    for name, module in sorted(sys.modules.items()):
        if name.startswith("Simulator.") and getattr(module, "__file__", None):
            path = Path(module.__file__).resolve()
            assert path.is_relative_to(prefix), (name, str(path))
            modules[name] = str(path)
    report = dict(scope="installed v2 receive and generated setup assembly only",
                  cwd=os.getcwd(), module_paths=modules, production_use_sim_time=True,
                  transport_high_water=node.pump._decoder.high_water_sequence,
                  session_state=node.session.state, request_id=setup.request_id,
                  requested_mode=setup.setup.px4_mode, command_outputs=0,
                  setup_captured_not_published=True, release_confirmed=False,
                  physical_acceptance=False)
finally:
    if peer is not None: peer.close()
    if node is not None: node.destroy_node()
    rclpy.shutdown()
report["cleanup_complete"] = True
print(json.dumps(report, indent=2))
