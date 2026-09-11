"""Generated-message callback and isolated real-RMW tests for the #102 bridge.

Callback tests require WKSIM_TEST_PRIVATE_ROS=1.  The peer-to-bridge DDS test also
requires WKSIM_TEST_PRIVATE_RMW=1 plus private net/ipc/mount namespaces and a fresh
/dev/shm; its synthetic peer ACK is transport evidence, not a flight-controller claim.
"""
import json
import os
import time
import unittest
from unittest.mock import patch


PRIVATE_ROS = os.environ.get("WKSIM_TEST_PRIVATE_ROS") == "1"
PRIVATE_RMW = os.environ.get("WKSIM_TEST_PRIVATE_RMW") == "1"

if PRIVATE_ROS:
    import rclpy
    from geometry_msgs.msg import Point
    from prometheus_msgs.msg import Bspline, TextInfo, UAVControlState
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rosgraph_msgs.msg import Clock
    from wksim_msgs.msg import CommandRequest, SessionState

    from Simulator.wksim_runtime.trajectory_bridge import (
        TICK_NS,
        TrajectoryBridgeNode,
    )


class RecordingPublisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


def require_isolation():
    if os.environ.get("ROS_DOMAIN_ID") != "79":
        raise RuntimeError("private RMW test requires ROS_DOMAIN_ID=79")
    for kind in ("net", "ipc", "mnt"):
        if os.readlink("/proc/self/ns/" + kind) == os.readlink("/proc/1/ns/" + kind):
            raise RuntimeError("private namespace required: " + kind)
    if "WK_SESSION_HOST_SHM_DEV" not in os.environ:
        raise RuntimeError("launcher must record WK_SESSION_HOST_SHM_DEV")
    if str(os.stat("/dev/shm").st_dev) == os.environ["WK_SESSION_HOST_SHM_DEV"]:
        raise RuntimeError("a fresh /dev/shm mount is required")


@unittest.skipUnless(PRIVATE_ROS, "requires WKSIM_TEST_PRIVATE_ROS=1 and a sourced ROS overlay")
class TrajectoryBridgeCallbackTests(unittest.TestCase):
    RUN = "trajectory-bridge-test"
    MISSION = "mission-a"
    EPOCH = "a" * 32
    ANCHOR = 1_000_000_000

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.tick = 100
        self.wall = time.monotonic()
        self.publisher = RecordingPublisher()
        self.node = TrajectoryBridgeNode(
            run_id=self.RUN,
            mission_id=self.MISSION,
            uav_id=1,
            fallback_yaw=0.25,
            authority_anchor_ns=self.ANCHOR,
            publisher_factory=lambda *_: self.publisher,
            clock_ns=lambda: self.ANCHOR + self.tick * TICK_NS,
            monotonic_s=lambda: self.wall,
        )
        self.addCleanup(self.node.destroy_node)

    def state(self, *, epoch=None, sequence=1, request_id=30, command_id=20,
              run_id=None, control=True, fresh=True):
        msg = SessionState(
            version=SessionState.VERSION,
            run_id=run_id or self.RUN,
            control_epoch=epoch or self.EPOCH,
            sequence=sequence,
            last_request_id=request_id,
            command_high_water=command_id,
            source_clock="fc_boot",
            source_received_valid=fresh,
            source_received_monotonic_s=self.wall,
            published_monotonic_s=self.wall,
        )
        msg.state.uav_id = 1
        msg.state.connected = True
        msg.state.odom_valid = True
        msg.state.header.frame_id = "map"
        msg.state.header.stamp.sec = 1
        msg.control.uav_id = 1
        msg.control.control_state = (
            UAVControlState.COMMAND_CONTROL if control else UAVControlState.INIT
        )
        msg.control.failsafe = False
        return msg

    def spline(self, trajectory_id=1, tick=None):
        tick = self.tick if tick is None else tick
        msg = Bspline(drone_id=0, order=3, traj_id=trajectory_id)
        start_ns = self.ANCHOR + tick * TICK_NS
        msg.start_time.sec = start_ns // 1_000_000_000
        msg.start_time.nanosec = start_ns % 1_000_000_000
        msg.knots = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7,
                     0.8, 0.9, 1.0]
        msg.pos_pts = [Point(x=float(index), y=0.0, z=1.0) for index in range(7)]
        msg.yaw_pts = []
        msg.yaw_dt = 0.0
        return msg

    def event(self, kind, request_id, command_id, *, epoch=None):
        message_type = (TextInfo.ERROR if kind in ("command_rejected", "control_revoked")
                        else TextInfo.INFO)
        return TextInfo(message_type=message_type, message=json.dumps(dict(
            event=kind,
            version=1,
            run_id=self.RUN,
            control_epoch=epoch or self.EPOCH,
            request_id=request_id,
            command_id=command_id,
        )))

    def initialize_and_publish(self):
        self.assertTrue(self.node.on_session_state(self.state()))
        self.assertTrue(self.node.on_bspline(self.spline()))
        self.assertEqual(len(self.publisher.messages), 1)
        return self.publisher.messages[-1]

    def test_high_water_pending_ack_and_next_ten_tick_output(self):
        first = self.initialize_and_publish()
        self.assertEqual((first.command.command_id, first.request_id), (21, 31))
        self.assertEqual((first.command.agent_cmd, first.command.move_mode),
                         (first.command.MOVE, first.command.TRAJECTORY))
        self.assertEqual(first.command.control_level, first.command.DEFAULT_CONTROL)
        self.assertEqual(first.command.header.frame_id, "map")
        self.assertEqual((first.command.header.stamp.sec,
                          first.command.header.stamp.nanosec), (1, 100_000_000))
        self.assertEqual(list(first.command.position_ref), [1.0, 0.0, 1.0])
        self.assertEqual(first.command.yaw_ref, 0.25)
        self.assertFalse(first.command.yaw_rate_mode)

        self.tick = 105
        self.assertFalse(self.node.on_timer())
        self.assertEqual(len(self.publisher.messages), 1)
        self.assertTrue(self.node.on_text_info(self.event("command_accepted", 31, 21)))
        self.tick = 110
        self.assertTrue(self.node.on_timer())
        second = self.publisher.messages[-1]
        self.assertEqual((second.command.command_id, second.request_id), (22, 32))

    def test_duplicate_trajectory_rejects_without_any_state_mutation(self):
        self.initialize_and_publish()
        self.assertTrue(self.node.on_text_info(self.event("command_accepted", 31, 21)))
        before = (
            self.node.session.state,
            self.node.session.generation,
            self.node.session.last_event_sequence,
            self.node.session.last_command_id,
            self.node.session._trajectory,
            self.node.session._sample,
            self.node.adapter.trajectory_id,
            self.node.adapter._last_tick,
            self.node.next_drive_tick,
        )

        self.assertFalse(self.node.on_bspline(self.spline(trajectory_id=1)))

        after = (
            self.node.session.state,
            self.node.session.generation,
            self.node.session.last_event_sequence,
            self.node.session.last_command_id,
            self.node.session._trajectory,
            self.node.session._sample,
            self.node.adapter.trajectory_id,
            self.node.adapter._last_tick,
            self.node.next_drive_tick,
        )
        self.assertEqual(after, before)
        self.assertEqual(len(self.publisher.messages), 1)

    def test_first_trajectory_must_start_at_the_exact_callback_tick(self):
        self.assertTrue(self.node.on_session_state(self.state()))
        self.assertFalse(self.node.on_bspline(self.spline(tick=101)))
        self.assertEqual(self.node.last_rejection, "start_tick_not_current")
        self.assertEqual((self.node.session.state, self.node.session.generation),
                         ("WAITING", 0))
        self.assertEqual(self.publisher.messages, [])

    def test_new_epoch_discards_pending_and_reseeds_both_high_waters(self):
        self.initialize_and_publish()
        new_epoch = "b" * 32
        self.assertTrue(self.node.on_session_state(self.state(
            epoch=new_epoch, sequence=1, request_id=60, command_id=50
        )))
        self.assertIsNone(self.node.pending)
        self.assertIsNone(self.node.next_drive_tick)
        self.assertEqual(self.node.adapter.trajectory_id, 0)

        self.assertTrue(self.node.on_bspline(self.spline(trajectory_id=1)))
        fresh = self.publisher.messages[-1]
        self.assertEqual(fresh.control_epoch, new_epoch)
        self.assertEqual((fresh.command.command_id, fresh.request_id), (51, 61))

    def test_trajectory_end_publishes_an_explicit_position_hold(self):
        self.assertTrue(self.node.on_session_state(self.state()))
        short = self.spline()
        short.pos_pts = short.pos_pts[:4]
        short.knots = [index * 0.01 for index in range(8)]
        self.assertTrue(self.node.on_bspline(short))
        self.assertTrue(self.node.on_text_info(self.event("command_accepted", 31, 21)))

        self.tick = 110
        self.assertTrue(self.node.on_timer())
        hold = self.publisher.messages[-1].command
        self.assertEqual(hold.move_mode, hold.XYZ_POS)
        self.assertEqual(list(hold.velocity_ref), [0.0, 0.0, 0.0])
        self.assertEqual(list(hold.acceleration_ref), [0.0, 0.0, 0.0])

    def test_rejection_locks_output(self):
        first = self.initialize_and_publish()
        self.assertFalse(self.node.on_text_info(self.event(
            "command_rejected", first.request_id, first.command.command_id
        )))
        self.assertEqual(self.node.fault_reason, "command_rejected")
        self.tick = 110
        self.assertFalse(self.node.on_timer())
        self.assertEqual(len(self.publisher.messages), 1)

    def test_external_writer_locks_output(self):
        self.assertTrue(self.node.on_session_state(self.state()))
        self.assertFalse(self.node.on_session_state(self.state(
            sequence=2, request_id=31, command_id=21
        )))
        self.assertEqual(self.node.fault_reason, "external_command_writer")
        self.assertFalse(self.node.on_bspline(self.spline()))
        self.assertEqual(self.publisher.messages, [])


    def test_pending_deadline_fails_closed(self):
        self.initialize_and_publish()
        self.assertTrue(self.node.on_session_state(self.state(
            sequence=2, request_id=31, command_id=21
        )))
        self.assertIsNotNone(self.node.pending)  # State high-water is telemetry, not ACK.
        self.tick = 110
        self.assertFalse(self.node.on_timer())
        self.assertEqual(self.node.fault_reason, "ack_not_received_before_next_sample")

    def test_missed_tick_fails_closed(self):
        self.initialize_and_publish()
        self.assertTrue(self.node.on_text_info(self.event("command_accepted", 31, 21)))
        self.tick = 111
        self.assertFalse(self.node.on_timer())
        self.assertEqual(self.node.fault_reason, "missed_adapter_tick")
        self.assertEqual(len(self.publisher.messages), 1)

    def test_wrong_ack_fails_closed(self):
        self.initialize_and_publish()
        self.assertFalse(self.node.on_text_info(self.event("command_accepted", 32, 21)))
        self.assertEqual(self.node.fault_reason, "other_command_writer_event")

    def test_control_revocation_fails_closed(self):
        self.initialize_and_publish()
        self.assertFalse(self.node.on_text_info(self.event("control_revoked", 31, 21)))
        self.assertEqual(self.node.fault_reason, "control_revoked")

    def test_request_id_exhaustion_never_publishes(self):
        self.assertTrue(self.node.on_session_state(self.state(
            request_id=2**64 - 1, command_id=20
        )))
        self.assertFalse(self.node.on_bspline(self.spline()))
        self.assertEqual(self.node.fault_reason, "request_id_exhausted")
        self.assertEqual(self.publisher.messages, [])
        self.assertEqual((self.node.session.state, self.node.session.generation),
                         ("WAITING", 0))

    def test_command_id_exhaustion_never_publishes(self):
        self.assertTrue(self.node.on_session_state(self.state(
            request_id=30, command_id=2**32 - 1
        )))
        self.assertFalse(self.node.on_bspline(self.spline()))
        self.assertEqual(self.node.fault_reason, "command_id_exhausted")
        self.assertEqual(self.publisher.messages, [])
        self.assertEqual((self.node.session.state, self.node.session.generation),
                         ("WAITING", 0))

    def test_clock_identity_and_state_anomalies_never_publish(self):
        self.assertFalse(self.node.on_session_state(self.state(run_id="other")))
        self.assertFalse(self.node.on_session_state(self.state(sequence=0)))
        self.assertFalse(self.node.on_bspline(self.spline()))
        self.assertEqual(self.publisher.messages, [])

        self.assertTrue(self.node.on_session_state(self.state(control=False)))
        self.assertFalse(self.node.on_bspline(self.spline()))
        self.assertEqual(self.publisher.messages, [])

        self.assertTrue(self.node.on_session_state(self.state(sequence=2)))
        self.tick = 100
        self.node._clock_ns = lambda: self.ANCHOR + self.tick * TICK_NS + 1
        self.assertFalse(self.node.on_bspline(self.spline()))
        self.assertEqual(self.node.fault_reason, "ros_clock_off_grid")
        self.assertEqual(self.publisher.messages, [])

    def test_clock_return_to_zero_is_a_latched_backward_jump(self):
        self.assertTrue(self.node.on_session_state(self.state()))
        self.assertEqual(self.node._current_tick(), 100)
        self.node._clock_ns = lambda: 0
        self.assertIsNone(self.node._current_tick())
        self.assertEqual(self.node.fault_reason, "ros_clock_moved_backwards")

        self.assertTrue(self.node.on_session_state(self.state(
            epoch="b" * 32, sequence=1
        )))
        self.assertEqual(self.node.fault_reason, "ros_clock_moved_backwards")
        self.assertFalse(self.node.on_bspline(self.spline()))
        self.assertEqual(self.publisher.messages, [])

    def test_unexpected_session_state_exception_fails_closed(self):
        with patch(
            "Simulator.wksim_runtime.trajectory_bridge._explicit_uint",
            side_effect=RuntimeError("unexpected"),
        ):
            self.assertFalse(self.node.on_session_state(self.state()))

        self.assertEqual(self.node.fault_reason, "internal_callback_error")
        self.assertIsNone(self.node.pending)
        self.assertIsNone(self.node.next_drive_tick)
        self.assertEqual(self.publisher.messages, [])

    def test_unexpected_bspline_exception_fails_closed(self):
        self.assertTrue(self.node.on_session_state(self.state()))
        with patch.object(
            self.node, "_normalized_bspline", side_effect=RuntimeError("unexpected")
        ):
            self.assertFalse(self.node.on_bspline(self.spline()))

        self.assertEqual(self.node.fault_reason, "internal_callback_error")
        self.assertIsNone(self.node.pending)
        self.assertIsNone(self.node.next_drive_tick)
        self.assertEqual(self.node.request_high_water, 30)
        self.assertEqual(self.node.session.last_command_id, 20)
        self.assertEqual(self.node.event_sequence, 0)
        self.assertEqual(self.node.adapter.trajectory_id, 0)
        self.assertIsNone(self.node.adapter._last_tick)
        self.assertEqual(self.publisher.messages, [])
        self.assertFalse(self.node.on_bspline(self.spline()))

    def test_unexpected_text_info_exception_fails_closed(self):
        self.initialize_and_publish()
        with patch(
            "Simulator.wksim_runtime.trajectory_bridge.json.loads",
            side_effect=RuntimeError("unexpected"),
        ):
            self.assertFalse(self.node.on_text_info(
                self.event("command_accepted", 31, 21)
            ))

        self.assertEqual(self.node.fault_reason, "internal_callback_error")
        self.assertIsNone(self.node.pending)
        self.assertIsNone(self.node.next_drive_tick)
        self.assertEqual(self.node.request_high_water, 31)
        self.assertEqual(self.node.session.last_command_id, 21)
        self.assertEqual(len(self.publisher.messages), 1)

    def test_unexpected_timer_exception_fails_closed(self):
        self.initialize_and_publish()
        self.assertTrue(self.node.on_text_info(
            self.event("command_accepted", 31, 21)
        ))
        self.tick = 110
        with patch.object(
            self.node.adapter, "step", side_effect=RuntimeError("unexpected")
        ):
            self.assertFalse(self.node.on_timer())

        self.assertEqual(self.node.fault_reason, "internal_callback_error")
        self.assertIsNone(self.node.pending)
        self.assertIsNone(self.node.next_drive_tick)
        self.assertEqual(self.node.request_high_water, 31)
        self.assertEqual(self.node.session.last_command_id, 21)
        self.assertEqual(len(self.publisher.messages), 1)


@unittest.skipUnless(PRIVATE_ROS and PRIVATE_RMW,
                     "requires isolated WKSIM_TEST_PRIVATE_RMW=1")
class PrivateTrajectoryBridgeRMWTests(unittest.TestCase):
    RUN = "trajectory-bridge-rmw"
    MISSION = "mission-rmw"
    EPOCH = "c" * 32
    ANCHOR = 1_000_000_000

    def setUp(self):
        require_isolation()
        rclpy.init(args=["--ros-args", "-p", "use_sim_time:=true"])
        self.addCleanup(rclpy.shutdown)
        self.peer = Node("trajectory_bridge_rmw_peer")
        self.bridge = TrajectoryBridgeNode(
            run_id=self.RUN,
            mission_id=self.MISSION,
            uav_id=1,
            fallback_yaw=0.25,
            authority_anchor_ns=self.ANCHOR,
        )
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.peer)
        self.executor.add_node(self.bridge)
        self.addCleanup(self.close_nodes)

        self.commands = []
        self.clock_pub = self.peer.create_publisher(Clock, "/clock", 10)
        self.state_pub = self.peer.create_publisher(
            SessionState, "/uav1/prometheus/v2/state", 10
        )
        self.spline_pub = self.peer.create_publisher(
            Bspline, "/uav1/planning/bspline", 10
        )
        self.info_pub = self.peer.create_publisher(
            TextInfo, "/uav1/prometheus/text_info", 10
        )
        self.command_sub = self.peer.create_subscription(
            CommandRequest, "/uav1/prometheus/v2/command",
            self.commands.append, 10,
        )
        self.until(lambda: self.clock_pub.get_subscription_count() > 0
                   and self.state_pub.get_subscription_count() == 1
                   and self.spline_pub.get_subscription_count() == 1
                   and self.info_pub.get_subscription_count() == 1
                   and self.peer.count_publishers(
                       "/uav1/prometheus/v2/command") == 1)

    def close_nodes(self):
        self.executor.remove_node(self.bridge)
        self.executor.remove_node(self.peer)
        self.bridge.destroy_node()
        self.peer.destroy_node()
        self.executor.shutdown()

    def until(self, predicate, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.executor.spin_once(timeout_sec=0.01)
            if predicate():
                return
        self.fail("private RMW condition timed out")

    def publish_clock(self, tick):
        stamp_ns = self.ANCHOR + tick * TICK_NS
        msg = Clock()
        msg.clock.sec = stamp_ns // 1_000_000_000
        msg.clock.nanosec = stamp_ns % 1_000_000_000
        self.clock_pub.publish(msg)
        self.until(lambda: self.bridge.get_clock().now().nanoseconds == stamp_ns)

    def state(self, epoch, sequence, request_id, command_id):
        now = time.monotonic()
        msg = SessionState(
            version=SessionState.VERSION,
            run_id=self.RUN,
            control_epoch=epoch,
            sequence=sequence,
            last_request_id=request_id,
            command_high_water=command_id,
            source_clock="fc_boot",
            source_received_valid=True,
            source_received_monotonic_s=now,
            published_monotonic_s=now,
        )
        msg.state.uav_id = 1
        msg.state.connected = True
        msg.state.odom_valid = True
        msg.state.header.frame_id = "map"
        msg.state.header.stamp.sec = 1
        msg.control.uav_id = 1
        msg.control.control_state = UAVControlState.COMMAND_CONTROL
        return msg

    def spline(self, trajectory_id, tick):
        msg = Bspline(drone_id=0, order=3, traj_id=trajectory_id)
        start_ns = self.ANCHOR + tick * TICK_NS
        msg.start_time.sec = start_ns // 1_000_000_000
        msg.start_time.nanosec = start_ns % 1_000_000_000
        msg.knots = [index * 0.1 for index in range(11)]
        msg.pos_pts = [Point(x=float(index), y=0.0, z=1.0) for index in range(7)]
        return msg

    def accepted(self, epoch, request_id, command_id):
        return TextInfo(message_type=TextInfo.INFO, message=json.dumps(dict(
            event="command_accepted",
            version=1,
            run_id=self.RUN,
            control_epoch=epoch,
            request_id=request_id,
            command_id=command_id,
        )))

    def test_real_rmw_high_waters_ack_timer_and_epoch_reset(self):
        self.publish_clock(100)
        self.state_pub.publish(self.state(self.EPOCH, 1, 30, 20))
        self.until(lambda: self.bridge.epoch == self.EPOCH)
        self.spline_pub.publish(self.spline(1, 100))
        self.until(lambda: len(self.commands) == 1)
        first = self.commands[0]
        self.assertEqual((first.request_id, first.command.command_id), (31, 21))
        self.assertEqual((first.command.agent_cmd, first.command.move_mode),
                         (first.command.MOVE, first.command.TRAJECTORY))

        self.publish_clock(105)
        self.executor.spin_once(timeout_sec=0.02)
        self.assertEqual(len(self.commands), 1)
        self.info_pub.publish(self.accepted(self.EPOCH, 31, 21))
        self.until(lambda: self.bridge.pending is None)
        self.publish_clock(110)
        self.until(lambda: len(self.commands) == 2)
        self.assertEqual((self.commands[1].request_id,
                          self.commands[1].command.command_id), (32, 22))

        new_epoch = "d" * 32
        self.state_pub.publish(self.state(new_epoch, 1, 60, 50))
        self.until(lambda: self.bridge.epoch == new_epoch)
        self.assertIsNone(self.bridge.pending)
        self.assertIsNone(self.bridge.next_drive_tick)
        self.assertEqual(self.bridge.adapter.trajectory_id, 0)
        self.info_pub.publish(self.accepted(self.EPOCH, 32, 22))
        for _ in range(3):
            self.executor.spin_once(timeout_sec=0.01)
        self.assertEqual(self.bridge.epoch, new_epoch)
        self.assertIsNone(self.bridge.fault_reason)
        self.assertIsNone(self.bridge.pending)
        self.spline_pub.publish(self.spline(1, 110))
        self.until(lambda: len(self.commands) == 3)
        third = self.commands[2]
        self.assertEqual(third.control_epoch, new_epoch)
        self.assertEqual((third.request_id, third.command.command_id), (61, 51))
