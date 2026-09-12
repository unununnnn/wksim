"""Actual ROS-message/loopback acceptance tests for the Route-B transport node.

The tests are opt-in because they need a sourced ROS 2 overlay.  They do not
start an executor, planner, ROS 1 peer, SITL, or a flight controller.  The
node's real ROS 2 messages are delivered directly to its callbacks, while a
real TCP loopback connection supplies the length-prefixed Bspline frame.

The first test is the end-to-end seam: one SessionState binds an epoch, one
loopback Bspline frame is admitted by the product pump, and the resulting
public message is a generated ``wksim_msgs/CommandRequest``.  The remaining
tests exercise the safety boundaries that the transport node owns: wire
identity, authority tick, state freshness, ACK correlation, and peer close.
"""

import json
import os
import socket
import unittest


PRIVATE_ROS = os.environ.get("WKSIM_TEST_PRIVATE_ROS") == "1"

if PRIVATE_ROS:
    import rclpy
    from prometheus_msgs.msg import TextInfo, UAVControlState
    from wksim_msgs.msg import CommandRequest, SessionState

    from Simulator.wksim_planning.ego_evaluator import UniformBspline
    from Simulator.wksim_planning.ego_trajectory_adapter import TICK_NS
    from Simulator.wksim_runtime.bspline_tcp_envelope import BsplineTcpEncoder
    from Simulator.wksim_runtime.planner_transport_node import PlannerTransportNode


class RecordingPublisher:
    """Publisher seam used only after the node has created its real ROS graph."""

    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


def free_loopback_port():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
    finally:
        probe.close()


@unittest.skipUnless(
    PRIVATE_ROS,
    "requires WKSIM_TEST_PRIVATE_ROS=1 and a sourced ROS 2 overlay",
)
class PlannerTransportNodeRosTests(unittest.TestCase):
    RUN = "planner-transport-node-ros"
    MISSION = "mission-route-b"
    EPOCH = "a" * 32
    TRANSPORT_SESSION = "0123456789abcdef0123456789abcdef"
    OTHER_TRANSPORT_SESSION = "fedcba9876543210fedcba9876543210"
    ANCHOR_NS = 1_000_000_000

    @classmethod
    def setUpClass(cls):
        rclpy.init(args=[])

    @classmethod
    def tearDownClass(cls):
        if rclpy.ok():
            rclpy.shutdown()

    def setUp(self):
        self.tick = 0
        self.wall = 50.0
        self.publisher = RecordingPublisher()
        self.node = PlannerTransportNode(
            run_id=self.RUN,
            mission_id=self.MISSION,
            uav_id=1,
            fallback_yaw=0.25,
            authority_anchor_ns=self.ANCHOR_NS,
            listen_host="127.0.0.1",
            listen_port=free_loopback_port(),
            transport_session_id=self.TRANSPORT_SESSION,
            clock_ns=lambda: self.ANCHOR_NS + self.tick * TICK_NS,
            monotonic_s=lambda: self.wall,
        )
        # Keep the node's generated subscriptions/timers, but capture the
        # actual generated CommandRequest at the final publish seam.
        self.node.command_pub = self.publisher
        self.addCleanup(self.close_node)

    def close_node(self):
        if getattr(self, "node", None) is None:
            return
        self.node.destroy_node()
        self.node = None

    def test_destroy_releases_owned_tcp_sockets(self):
        client = self.bind_and_connect()
        self.assertTrue(self.node._ensure_connection())
        listener, connection = self.node._listener, self.node._connection
        self.close_node()
        self.assertEqual(listener.fileno(), -1)
        self.assertEqual(connection.fileno(), -1)
        client.close()

    def test_idle_accepted_peer_does_not_block_ros_callbacks(self):
        client = self.bind_and_connect()
        self.addCleanup(client.close)
        self.assertTrue(self.node._ensure_connection())
        # Assert before polling so a regression fails instead of hanging CI.
        self.assertFalse(self.node._connection.getblocking())
        self.node.on_receive_timer()
        self.assertIsNone(self.node.fault_reason)
        self.assertTrue(self.node.on_session_state(self.state(sequence=2)))
        self.assertEqual(self.publisher.messages, [])

    def test_control_epoch_change_does_not_reset_same_transport_token(self):
        client = self.bind_and_connect()
        session = self.node.session
        self.assertFalse(self.node.on_session_state(self.state(epoch='b'*32)))
        self.assertEqual(self.node.fault_reason, 'control_epoch_changed_requires_new_transport_session')
        self.assertIs(self.node.session, session)
        self.assertIsNone(self.node._listener)
        self.assertIsNone(self.node._connection)
        self.assertEqual(self.publisher.messages, [])
        client.close()

    def state(self, *, epoch=None, sequence=1, request_id=30,
              command_id=20, fresh=True, control=True, run_id=None):
        msg = SessionState(
            version=SessionState.VERSION,
            run_id=self.RUN if run_id is None else run_id,
            control_epoch=self.EPOCH if epoch is None else epoch,
            sequence=sequence,
            last_request_id=request_id,
            command_high_water=command_id,
            source_clock="fc_boot",
            source_received_valid=fresh,
            source_received_monotonic_s=self.wall if fresh else 0.0,
            published_monotonic_s=self.wall if fresh else 0.0,
        )
        msg.state.uav_id = 1
        msg.state.connected = True
        msg.state.odom_valid = True
        msg.state.header.frame_id = "map"
        msg.state.header.stamp.sec = 1
        msg.control.uav_id = 1
        msg.control.control_state = (
            UAVControlState.COMMAND_CONTROL if control
            else UAVControlState.INIT
        )
        msg.control.failsafe = False
        return msg

    def payload(self, *, trajectory_id=1):
        # Same clear, order-3 spline used by the committed pump tests: y=3 is
        # outside the ego-single-box obstacle and inside the map bounds.
        cps = [(float(index) * 0.5, 3.0, 1.0) for index in range(7)]
        return {
            "drone_id": 0,
            "order": 3,
            "traj_id": trajectory_id,
            "start_time": {"sec": 1, "nanosec": 0},
            "knots": list(UniformBspline(3, cps, 0.1).knots),
            "pos_pts": [tuple(point) for point in cps],
            "yaw_pts": [],
            "yaw_dt": 0.0,
        }

    def connect(self):
        port = self.node._listener.getsockname()[1]
        client = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        self.addCleanup(client.close)
        return client

    def send_frame(self, client, *, session_id=None, trajectory_id=1):
        encoder = BsplineTcpEncoder(
            self.TRANSPORT_SESSION if session_id is None else session_id
        )
        client.sendall(encoder.encode_frame(self.payload(
            trajectory_id=trajectory_id)))

    def ack(self, request):
        return TextInfo(
            message_type=TextInfo.INFO,
            message=json.dumps({
                "event": "command_accepted",
                "version": 1,
                "run_id": self.RUN,
                "control_epoch": self.EPOCH,
                "request_id": request.request_id,
                "command_id": request.command.command_id,
            }),
        )

    def bind_and_connect(self):
        self.assertTrue(self.node.on_session_state(self.state()))
        return self.connect()

    def test_loopback_frame_reaches_real_command_request_on_shared_session(self):
        client = self.bind_and_connect()
        self.send_frame(client)

        self.assertTrue(self.node.on_receive_timer())
        self.assertEqual(len(self.publisher.messages), 1)
        request = self.publisher.messages[0]
        self.assertIsInstance(request, CommandRequest)
        self.assertEqual(
            (request.run_id, request.control_epoch, request.request_id),
            (self.RUN, self.EPOCH, 31),
        )
        self.assertEqual(request.command.command_id, 21)
        self.assertEqual(request.command.header.frame_id, "map")
        self.assertEqual(request.command.agent_cmd, request.command.MOVE)
        self.assertEqual(request.command.move_mode, request.command.TRAJECTORY)

        # This is the P1 seam under test: receive and publish must use one
        # TrajectorySession/adapter, so the generation and command high-water
        # are advanced by the same admitted wire frame.
        self.assertIs(self.node.pump._session, self.node.session)
        self.assertIs(self.node.pump._adapter, self.node.adapter)
        self.assertIs(self.node.egress.session, self.node.session)
        self.assertTrue(self.node.on_text_info(self.ack(request)))

        self.tick = 10
        self.assertTrue(self.node.on_drive_timer())
        second = self.publisher.messages[-1]
        self.assertIsInstance(second, CommandRequest)
        self.assertEqual((second.request_id, second.command.command_id), (32, 22))
        self.assertEqual(second.control_epoch, self.EPOCH)

    def test_wrong_wire_session_fails_closed_before_any_command(self):
        client = self.bind_and_connect()
        self.send_frame(client, session_id=self.OTHER_TRANSPORT_SESSION)

        # A session mismatch is a poison outcome and must latch the node in the
        # same callback; accepting the callback leaves an unsafe live socket.
        self.assertFalse(self.node.on_receive_timer())
        self.assertIsNotNone(self.node.fault_reason)
        self.assertEqual(self.publisher.messages, [])

    def test_off_grid_authority_tick_fails_closed_before_consuming_frame(self):
        client = self.bind_and_connect()
        self.tick = 0
        self.node._clock_ns = lambda: self.ANCHOR_NS + 1
        self.send_frame(client)

        self.assertFalse(self.node.on_receive_timer())
        self.assertEqual(self.node.fault_reason, "ros_clock_off_grid")
        self.assertEqual(self.publisher.messages, [])

    def test_stale_state_fails_closed_at_activation(self):
        self.wall = 50.0
        self.assertTrue(self.node.on_session_state(self.state(fresh=False)))
        client = self.connect()
        self.send_frame(client)

        self.assertFalse(self.node.on_receive_timer())
        self.assertEqual(
            self.node.fault_reason, "state_not_fresh_or_owned_at_activation"
        )
        self.assertEqual(self.publisher.messages, [])

    def test_wrong_ack_identity_keeps_pending_and_fails_at_next_sample(self):
        client = self.bind_and_connect()
        self.send_frame(client)
        self.assertTrue(self.node.on_receive_timer())
        request = self.publisher.messages[-1]

        wrong_epoch = self.ack(request)
        event = json.loads(wrong_epoch.message)
        event["control_epoch"] = "b" * 32
        wrong_epoch.message = json.dumps(event)
        # Identity-mismatched ACKs are ignored; the still-pending command must
        # therefore stop the next sample rather than authorize it.
        self.assertTrue(self.node.on_text_info(wrong_epoch))
        self.assertIsNotNone(self.node.egress.pending)
        self.tick = 10
        self.assertFalse(self.node.on_drive_timer())
        self.assertEqual(
            self.node.fault_reason, "ack_not_received_before_next_sample"
        )

    def test_peer_close_fails_closed_without_publishing(self):
        self.assertTrue(self.node.on_session_state(self.state()))
        client = self.connect()
        client.close()

        self.assertFalse(self.node.on_receive_timer())
        self.assertTrue(
            self.node.fault_reason.startswith(
                "transport_receive_failed:[connection_closed]"
            )
        )
        self.assertEqual(self.publisher.messages, [])


if __name__ == "__main__":
    unittest.main()
