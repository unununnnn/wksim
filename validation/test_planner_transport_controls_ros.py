"""ROS-msg callback tests for the #102 Route-B planner transport node.

Gated behind WKSIM_TEST_PRIVATE_ROS=1 exactly like
validation/test_trajectory_bridge_ros.py; the main session owns running them
(no agent runs ROS/native). The receiver is stubbed with a shim that drives
the REAL pump with REAL encoded frames, so gate state, session events, and
outcome ordering are exercised end to end inside the node callbacks.
"""
import json
import os
import socket
import time
import unittest

PRIVATE_ROS = os.environ.get("WKSIM_TEST_PRIVATE_ROS") == "1"

if PRIVATE_ROS:
    import rclpy
    from geometry_msgs.msg import Point
    from prometheus_msgs.msg import TextInfo, UAVControlState
    from wksim_msgs.msg import SessionState

    from Simulator.wksim_planning.ego_evaluator import UniformBspline
    from Simulator.wksim_planning.ego_trajectory_adapter import TICK_NS
    from Simulator.wksim_runtime.bspline_tcp_envelope import BsplineTcpEncoder
    from Simulator.wksim_runtime.planner_transport_node import PlannerTransportNode


def free_port():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


if PRIVATE_ROS:

    class StubReceiver:
        """Drives the REAL pump with queued wire chunks (no socket)."""

        def __init__(self, pump, chunks):
            self._pump = pump
            self._chunks = list(chunks)

        def poll(self, *, identity, current_tick, fallback_yaw):
            chunk = self._chunks.pop(0) if self._chunks else b""
            return self._pump.feed(chunk, identity=identity,
                                   current_tick=current_tick,
                                   fallback_yaw=fallback_yaw)

        def drain(self, *, identity, current_tick, fallback_yaw):
            return self._pump.feed(b"", identity=identity,
                                   current_tick=current_tick,
                                   fallback_yaw=fallback_yaw)

    class RecordingSetupPublisher:
        def __init__(self):
            self.requests = []

        def publish(self, request):
            self.requests.append(request)


@unittest.skipUnless(PRIVATE_ROS, "requires WKSIM_TEST_PRIVATE_ROS=1 and a sourced ROS overlay")
class PlannerTransportNodeCallbackTests(unittest.TestCase):
    RUN = "planner-transport-test"
    MISSION = "mission-a"
    EPOCH = "a" * 32
    ANCHOR = 1_000_000_000
    SESSION = "0123456789abcdef0123456789abcdef"

    @classmethod
    def setUpClass(cls):
        rclpy.init(args=["--ros-args", "-p", "use_sim_time:=true"])

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.tick = 100
        self.wall = time.monotonic()

    def make_node(self, **overrides):
        kwargs = dict(
            run_id=self.RUN, mission_id=self.MISSION, uav_id=1,
            fallback_yaw=0.0, authority_anchor_ns=self.ANCHOR,
            listen_host="127.0.0.1", listen_port=free_port(),
            transport_session_id=self.SESSION,
            clock_ns=lambda: self.ANCHOR + self.tick * TICK_NS,
            monotonic_s=lambda: self.wall)
        kwargs.update(overrides)
        node = PlannerTransportNode(**kwargs)
        self.addCleanup(node.destroy_node)
        return node

    def control_node_kwargs(self):
        return dict(accept_control=True, cancel_mode="BRAKE",
                    expected_native_mode="BRAKE")

    def encoder(self):
        return BsplineTcpEncoder(self.SESSION)

    def test_production_clock_source_cannot_switch_to_wall_time(self):
        from rclpy.parameter import Parameter
        node = self.make_node(clock_ns=None)
        node.set_parameters([Parameter("use_sim_time", value=False)])
        self.assertIsNone(node._current_tick())
        self.assertEqual(node.fault_reason, "operation_clock_source_changed")

    def test_real_tcp_sender_hold_cancel_and_public_release(self):
        from types import SimpleNamespace
        from validation.test_planner_transport_receiver import sender
        node = self.make_node(**self.control_node_kwargs())
        commands, setups = RecordingSetupPublisher(), RecordingSetupPublisher()
        node.command_pub, node.setup_pub = commands, setups
        self.assertTrue(node.on_session_state(self.state()))
        connection = socket.create_connection(node._listener.getsockname())
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        stream = sender.OrderedFrameSender(self.encoder(), connection, accept_control=True)
        self.addCleanup(stream.close)
        stream.send_control({"kind": "gate", "open": True})
        stream.send_bspline(SimpleNamespace(**self.clear_payload()))
        self.assertTrue(node.on_receive_timer())
        self.assertEqual(len(commands.requests), 1)
        first = commands.requests[0]
        self.assertEqual((first.request_id, first.command.command_id), (31, 21))
        self.assertTrue(node.on_text_info(self.event("command_accepted", 31, command_id=21)))
        stream.send_control({"kind": "hold"})
        self.assertTrue(node.on_receive_timer())
        self.assertEqual(len(commands.requests), 1)
        self.tick += 10
        self.assertTrue(node.on_drive_timer())
        held = commands.requests[-1]
        self.assertEqual((held.request_id, held.command.command_id), (32, 22))
        self.assertEqual(held.command.move_mode, held.command.XYZ_POS)
        self.assertTrue(node.on_text_info(self.event("command_accepted", 32, command_id=22)))
        stream.send_control({"kind": "cancel"})
        self.assertTrue(node.on_receive_timer())
        self.assertTrue(node.on_drive_timer())
        self.assertEqual(len(setups.requests), 1)
        self.assertEqual(setups.requests[0].request_id, 33)
        self.assertEqual(node.session.last_command_id, 22)
        self.assertTrue(node.on_text_info(self.event("native_ack", 33, accepted=True, stage="simple")))
        self.assertFalse(node.egress.release["confirmed"])
        self.assertTrue(node.on_text_info(self.event("setup_completed", 33,
                                                   action="mode", value="BRAKE", native_mode="BRAKE")))
        self.assertTrue(node.on_drive_timer())
        self.assertTrue(node.egress.release["confirmed"])
        self.assertEqual(len(commands.requests), 2)

    def state(self, *, sequence=1, request_id=30, command_id=20, fresh=True):
        msg = SessionState(
            version=SessionState.VERSION, run_id=self.RUN,
            control_epoch=self.EPOCH, sequence=sequence,
            last_request_id=request_id, command_high_water=command_id,
            source_clock="fc_boot", source_received_valid=fresh,
            source_received_monotonic_s=self.wall,
            published_monotonic_s=self.wall)
        msg.state.uav_id = 1
        msg.state.connected = True
        msg.state.odom_valid = True
        msg.state.header.frame_id = "map"
        msg.state.header.stamp.sec = 1
        msg.control.uav_id = 1
        msg.control.control_state = UAVControlState.COMMAND_CONTROL
        msg.control.failsafe = False
        return msg


    def clear_payload(self, traj_id=1, tick=None):
        tick = self.tick if tick is None else tick
        cps = [(float(i) * 0.5, 3.0, 1.0) for i in range(7)]
        start_ns = self.ANCHOR + tick * TICK_NS
        return {
            "drone_id": 0, "order": 3, "traj_id": traj_id,
            "start_time": {"sec": start_ns // 1_000_000_000,
                           "nanosec": start_ns % 1_000_000_000},
            "knots": list(UniformBspline(3, cps, 0.1).knots),
            "pos_pts": [tuple(p) for p in cps], "yaw_pts": [], "yaw_dt": 0.0,
        }

    def bind(self, node, chunks=()):
        self.assertTrue(node.on_session_state(self.state()))
        node.receiver = StubReceiver(node.pump, chunks)
        node._ensure_connection = lambda: True

    def event(self, kind, request_id, message_type=None, **fields):
        if message_type is None:
            message_type = TextInfo.INFO
        payload = dict(event=kind, version=1, run_id=self.RUN,
                       control_epoch=self.EPOCH, request_id=request_id)
        payload.update(fields)
        return TextInfo(message_type=message_type, message=json.dumps(payload))

    # ---- construction ------------------------------------------------------
    def test_v1_default_has_no_setup_publisher_and_no_control(self):
        node = self.make_node()
        self.assertIsNone(node.setup_pub)
        self.assertFalse(node.accept_control)
        self.bind(node)
        self.assertFalse(node.pump.accept_control)

    def test_control_mode_requires_explicit_release_targets(self):
        with self.assertRaises(ValueError):
            self.make_node(accept_control=True)
        with self.assertRaises(ValueError):
            self.make_node(accept_control=True, cancel_mode="OFFBOARD",
                           expected_native_mode="OFFBOARD")
        with self.assertRaises(ValueError):
            self.make_node(accept_control=1, cancel_mode="BRAKE",
                           expected_native_mode="BRAKE")

    def test_control_mode_wires_decoder_pump_and_setup_publisher(self):
        node = self.make_node(**self.control_node_kwargs())
        self.assertIsNotNone(node.setup_pub)
        self.bind(node)
        self.assertTrue(node.pump.accept_control)
        self.assertTrue(node.pump._decoder.accept_control)

    # ---- outcome-ordered control handling -----------------------------------
    def test_activation_with_gate_closed_faults_in_control_mode(self):
        node = self.make_node(**self.control_node_kwargs())
        encoder = self.encoder()
        self.bind(node, [encoder.encode_frame(self.clear_payload())])
        self.assertFalse(node.on_receive_timer())
        self.assertEqual(node.fault_reason, "activation_with_gate_closed")

    def test_v1_activation_still_publishes_without_gate(self):
        node = self.make_node()
        encoder = self.encoder()
        self.bind(node, [encoder.encode_frame(self.clear_payload())])
        self.assertTrue(node.on_receive_timer())
        self.assertEqual(node.egress.request_high_water, 31)
        self.assertEqual(node._next_drive_tick, 110)

    def test_gate_close_halt_and_reopen_never_resumes_old_trajectory(self):
        node = self.make_node(**self.control_node_kwargs())
        encoder = self.encoder()
        node.setup_pub = RecordingSetupPublisher()
        chunk = (encoder.encode_control_frame({"kind": "gate", "open": True})
                 + encoder.encode_frame(self.clear_payload())
                 + encoder.encode_control_frame({"kind": "gate", "open": False})
                 + encoder.encode_control_frame({"kind": "gate", "open": True}))
        self.bind(node, [chunk, b""])
        self.assertTrue(node.on_receive_timer())
        self.assertEqual(node.egress.request_high_water, 30)  # closed later in the same batch
        self.assertTrue(node._trajectory_halted)
        # Second receive: only the deferred gate frames; no new publish.
        self.assertTrue(node.on_receive_timer())
        self.assertEqual(node.egress.request_high_water, 30)
        # Drive timer while halted: no stepping, no fault, no new command.
        self.tick += 1
        self.assertFalse(node.on_drive_timer())
        self.assertEqual(node.egress.request_high_water, 30)

    def test_rejected_control_halts_previous_activation(self):
        node = self.make_node(**self.control_node_kwargs())
        encoder = self.encoder()
        chunk = (encoder.encode_control_frame({"kind": "gate", "open": True})
                 + encoder.encode_frame(self.clear_payload())
                 + encoder.encode_control_frame({"kind": "hold"}))
        self.bind(node, [chunk, b""])
        self.assertTrue(node.on_receive_timer())
        self.assertTrue(node.on_receive_timer())
        self.assertTrue(node._trajectory_halted)
        self.tick += 1
        self.assertFalse(node.on_drive_timer())
        self.assertEqual(node.egress.request_high_water, 30)

    def test_hold_outcome_is_not_an_activation(self):
        node = self.make_node(**self.control_node_kwargs())
        encoder = self.encoder()
        chunk = (encoder.encode_control_frame({"kind": "gate", "open": True})
                 + encoder.encode_control_frame({"kind": "hold"}))
        self.bind(node, [chunk])
        self.assertTrue(node.on_receive_timer())
        self.assertEqual(node.egress.request_high_water, 30)  # nothing published
        self.assertIsNone(node._next_drive_tick)

    # ---- cancel -> release machine -------------------------------------------
    def activate_with_pending(self, node):
        encoder = self.encoder()
        chunk = (encoder.encode_control_frame({"kind": "gate", "open": True})
                 + encoder.encode_frame(self.clear_payload()))
        self.bind(node, [chunk, b""])
        self.assertTrue(node.on_receive_timer())
        self.assertIsNotNone(node.egress.pending)
        return encoder

    def test_cancel_keeps_pending_and_enforces_ack_boundary(self):
        node = self.make_node(**self.control_node_kwargs())
        node.setup_pub = RecordingSetupPublisher()
        encoder = self.activate_with_pending(node)
        node.receiver = StubReceiver(
            node.pump, [encoder.encode_control_frame({"kind": "cancel"})])
        self.assertTrue(node.on_receive_timer())
        self.assertTrue(node._trajectory_halted)
        self.assertTrue(node._release_intent)
        self.assertIsNotNone(node.egress.pending)  # never cleared to fake cancel
        self.assertEqual(node.setup_pub.requests, [])
        # The original next-sample boundary still guards the pending ACK.
        self.tick += 10
        self.assertFalse(node.on_drive_timer())
        self.assertEqual(node.fault_reason, "ack_not_received_before_next_sample")

    def test_release_full_two_phase_flow(self):
        node = self.make_node(**self.control_node_kwargs())
        node.setup_pub = RecordingSetupPublisher()
        encoder = self.activate_with_pending(node)
        node.receiver = StubReceiver(
            node.pump, [encoder.encode_control_frame({"kind": "cancel"})])
        self.assertTrue(node.on_receive_timer())
        # ACK the pending command; the release goes out with the SHARED id.
        self.assertTrue(node.on_text_info(self.event(
            "command_accepted", 31, command_id=21)))
        self.assertTrue(node.on_drive_timer())
        self.assertEqual(len(node.setup_pub.requests), 1)
        request = node.setup_pub.requests[0]
        self.assertEqual(request.request_id, 32)
        self.assertEqual(request.run_id, self.RUN)
        self.assertEqual(request.control_epoch, self.EPOCH)
        self.assertEqual(request.setup.cmd, request.setup.SET_PX4_MODE)
        self.assertEqual(request.setup.px4_mode, "BRAKE")
        # setup_received and a lone ack do not confirm.
        self.assertTrue(node.on_text_info(self.event("setup_received", 32)))
        self.assertTrue(node.on_text_info(self.event(
            "native_ack", 32, accepted=True, stage="simple")))
        self.assertTrue(node._release_intent)
        self.assertTrue(node.on_text_info(self.event(
            "setup_completed", 32, action="mode", value="BRAKE",
            native_mode="BRAKE")))
        self.assertTrue(node.on_drive_timer())
        self.assertFalse(node._release_intent)
        self.assertIsNone(node.fault_reason)

    def test_release_deadline_is_fail_closed(self):
        node = self.make_node(**self.control_node_kwargs())
        node.setup_pub = RecordingSetupPublisher()
        encoder = self.activate_with_pending(node)
        node.receiver = StubReceiver(
            node.pump, [encoder.encode_control_frame({"kind": "cancel"})])
        self.assertTrue(node.on_receive_timer())
        self.assertTrue(node.on_text_info(self.event("command_accepted", 31, command_id=21)))
        self.assertTrue(node.on_drive_timer())
        self.wall += 11.0
        self.assertTrue(node.on_drive_timer())  # paused ROS time does not consume the operation deadline
        self.tick += 10001
        self.assertFalse(node.on_drive_timer())
        self.assertEqual(node.fault_reason,
                         "release_confirmation_deadline_exceeded")

    # ---- text_info routing and session correlation ----------------------------
    def test_text_info_routes_setup_and_command_events(self):
        node = self.make_node(**self.control_node_kwargs())
        node.setup_pub = RecordingSetupPublisher()
        self.bind(node)
        outcome, _ = None, None
        # No release in flight: setup events are ignored, not faults.
        self.assertTrue(node.on_text_info(self.event(
            "native_ack", 5, accepted=True, stage="simple")))
        self.assertIsNone(node.fault_reason)

    def test_session_state_correlates_in_flight_release(self):
        node = self.make_node(**self.control_node_kwargs())
        node.setup_pub = RecordingSetupPublisher()
        encoder = self.activate_with_pending(node)
        node.receiver = StubReceiver(
            node.pump, [encoder.encode_control_frame({"kind": "cancel"})])
        self.assertTrue(node.on_receive_timer())
        self.assertTrue(node.on_text_info(self.event(
            "command_accepted", 31, command_id=21)))
        self.assertTrue(node.on_drive_timer())
        self.assertEqual(len(node.setup_pub.requests), 1)
        # SessionState acknowledging exactly the release request_id is fine...
        self.assertTrue(node.on_session_state(self.state(sequence=2, request_id=32)))
        # ...but a higher last_request_id means an external writer: fail closed.
        self.assertFalse(node.on_session_state(self.state(sequence=3, request_id=33)))
        self.assertEqual(node.fault_reason, "external_request_writer")


if __name__ == "__main__":
    unittest.main()
