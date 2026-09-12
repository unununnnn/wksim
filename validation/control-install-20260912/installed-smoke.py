"""Installation-only smoke; no planner, flight controller, or command input."""
import json
import os
from pathlib import Path
import sys

import rclpy
from Simulator.wksim_runtime import bspline_tcp_envelope as envelope
from Simulator.wksim_runtime.planner_transport_node import PlannerTransportNode
from Simulator.wksim_runtime.trajectory_bridge import build_ros_command_request


prefix = Path(sys.argv[1]).resolve()
node = None
rclpy.init(args=["--ros-args", "-p", "use_sim_time:=true"])
try:
    decoder = envelope.BsplineTcpDecoder("0123456789abcdef0123456789abcdef")
    node = PlannerTransportNode(
        run_id="control-installed-smoke", mission_id="no-flight-smoke",
        uav_id=1, fallback_yaw=0.0, authority_anchor_ns=1_000_000_000,
        listen_host="127.0.0.1", listen_port=39193,
        transport_session_id="0123456789abcdef0123456789abcdef",
    )
    assert node.get_parameter("use_sim_time").value is True
    assert node.fault_reason is None and node.session is None
    assert node._listener.getsockname() == ("127.0.0.1", 39193)
    paths = {}
    for name, module in sorted(sys.modules.items()):
        if name.startswith("Simulator.") and getattr(module, "__file__", None):
            path = Path(module.__file__).resolve()
            assert path.is_relative_to(prefix), (name, str(path))
            paths[name] = str(path)
    assert not envelope.ROS1_MSG_FILE.exists()
    assert not envelope.ROS2_MSG_FILE.exists()
    selected = envelope._message_paths()
    assert all(path.resolve().is_relative_to(prefix) for path in selected)
    record = {
        "version": 1, "scope": "installed-imports-and-node-construction-only",
        "cwd": os.getcwd(), "install_prefix": str(prefix),
        "module_paths": paths, "message_pins": [str(p) for p in selected],
        "decoder_constructed": True, "node_constructed": True,
        "production_use_sim_time": True, "session_received": False,
        "commands_sent": 0, "physical_acceptance": False,
        "network_namespace": os.readlink("/proc/self/ns/net"),
        "ipc_namespace": os.readlink("/proc/self/ns/ipc"),
    }
finally:
    if node is not None:
        node.destroy_node()
        assert node._listener is None
    rclpy.shutdown()
record["cleanup_complete"] = True
print(json.dumps(record, indent=2))
