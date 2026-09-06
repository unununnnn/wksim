"""Bounded Windows unit seams of real MissionTask; no ROS or flight evidence.

Fake publishers/spins supply observations only. Production pump/send/visit/cancel
are exercised directly; execute outcome tests explicitly stub flight operations.
"""
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import numpy as np
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Simulator.wksim_runtime.mission_task import MissionTask, MissionCancelled, MissionPaused


class Message(NS):
    def __init__(self, **fields):
        super().__init__(header=NS(stamp=None, frame_id=''), **fields)


class Setup(Message):
    ARMING, SET_PX4_MODE, SET_CONTROL_MODE = 0, 1, 3


class Command(Message):
    LAND, MOVE, XYZ_POS, XYZ_POS_BODY = 3, 4, 0, 1


def plain(value):
    if isinstance(value, NS):
        return {key: plain(item) for key, item in vars(value).items()}
    return value


class MissionTaskTests(unittest.TestCase):
    def setUp(self):
        clock = patch('time.monotonic', return_value=100.0)
        clock.start()
        self.addCleanup(clock.stop)
        task = self.task = MissionTask.__new__(MissionTask)
        task.latest = {'state': NS(uav_id=1, connected=True, odom_valid=True,
            header=NS(frame_id='map', stamp=NS(sec=10, nanosec=0)),
            position=[0., 0., 3.], velocity=[0., 0., 0.], attitude=[0., 0., 0.],
            armed=True, mode='OFFBOARD'),
            'control_state': NS(uav_id=1, control_state=2, COMMAND_CONTROL=2, failsafe=False)}
        task.received, task.advanced_at = {'state': 100.}, 100.
        task.active, task.error = True, None
        task.flight_stack, task.protocol = 'px4', 'session_v1'
        task.run_id, task.epoch = 'unit-run', 'e' * 32
        task.native_generation = task.control_generation = 1
        task.session_sequence, task.retired_epochs, task.last_stamp = 0, set(), None
        task.action_token, task.release_event = 'a' * 32, None
        task.actions = NS(poll=Mock(return_value=None), rejections=[])
        task.pauses, task._operator_wait_total, task._operator_wait_started = [], 0., None
        task.request_id, task.command_id, task.pending_request_id = 0, 0, None
        task.events, task.sent, task.envelopes = [], [], []
        task.started, task.log = 100., io.StringIO()
        task.Setup, task.Cmd = Setup, Command
        task.SetupRequest = task.CommandRequest = NS
        task.convert, task.health, task.phase = plain, Mock(), Mock()
        task.node = NS(get_clock=lambda: NS(now=lambda: NS(to_msg=lambda: NS(sec=10))))
        task.interruptible = task.control_required = task.control_taken = True
        task.cancel_request = None
        task.mailbox = NS(poll=Mock(return_value=None), rejections=[])
        task.progress_records, task.waypoints, task.mission_state = [], [], 'accepted'
        def progress(state=None, **fields):
            if state is not None:
                task.mission_state = state
            task.progress_records.append(dict(state=task.mission_state, **fields))
        task.progress = progress  # Persistence is outside these control seams.
        self.published, self.spins = [], 0
        self.on_spin = lambda: None
        def spin(*args, **kwargs):
            self.spins += 1
            if self.spins > 12:
                raise AssertionError('Unit seam exceeded 12 spins')
            self.on_spin()
        task.ros = NS(spin_once=spin)
        task.setup_pub = task.command_pub = NS(publish=self.published.append,
                                               get_subscription_count=lambda: 1)
        task.truth_cursor = Mock(side_effect=[{'record': 1}, {'record': 2}])

    def ack(self):
        envelope = self.published[-1]
        if hasattr(envelope, 'setup'):
            event = dict(event='setup_completed')
        else:
            event = dict(event='command_accepted', command_id=envelope.command.command_id)
        self.task.events.append(dict(event, request_id=envelope.request_id))

    def test_cancel_before_move_dispatch_sends_nothing(self):
        self.task.mailbox.poll.return_value = {'id': 'cancel'}
        with self.assertRaises(MissionCancelled):
            self.task.send(self.task.command(agent_cmd=Command.MOVE), 'move')
        self.assertEqual(self.published, [])

    def test_send_latches_cancel_until_matching_ack_then_suppresses_next_move(self):
        task = self.task
        observations = []
        def spin():
            if not self.published:
                return
            task.mailbox.poll.return_value = {'id': 'cancel'}
            observations.append((task.interruptible, task.pending_request_id))
            if len(observations) == 1:
                task.events.append(dict(event='command_accepted', command_id=1, request_id=999))
            else:
                self.assertIsNotNone(task.cancel_request)
                self.ack()
        self.on_spin = spin
        task.send(task.command(agent_cmd=Command.MOVE), 'move')
        self.assertEqual(observations, [(False, 1), (False, 1)])
        self.assertTrue(task.interruptible)
        self.assertIsNone(task.pending_request_id)
        self.assertEqual(task.mission_state, 'accepted')
        with self.assertRaises(MissionCancelled):
            task.send(task.command(agent_cmd=Command.MOVE), 'next')
        self.assertEqual(len(self.published), 1)
        self.assertEqual(sum(r.get('event') == 'cancel_received' for r in task.progress_records), 1)

    def test_session_high_water_does_not_change_inflight_ack_identity(self):
        task = self.task
        def spin():
            if not self.published:
                return
            task.receive_session(NS(version=1, run_id=task.run_id, control_epoch=task.epoch,
                sequence=task.session_sequence+1, last_request_id=1000, native_generation=1,
                published_monotonic_s=100., source_received_valid=True, source_received_monotonic_s=100.,
                state=task.state, control=task.latest['control_state']))
            self.ack()
        self.on_spin = spin
        task.send(task.command(agent_cmd=Command.MOVE), 'first')
        self.assertEqual(task.request_id, 1000)
        task.send(task.command(agent_cmd=Command.MOVE), 'second')
        self.assertEqual([e.request_id for e in self.published], [1, 1001])

    def test_pause_request_waits_for_ack_before_interrupting(self):
        task = self.task
        task.mission_state = 'running'
        request = dict(action='pause')
        def spin():
            if self.published:
                task.actions.poll.return_value = request
                self.ack()
        self.on_spin = spin
        task.send(task.command(agent_cmd=Command.MOVE), 'first')
        self.assertEqual(len(self.published), 1)
        with self.assertRaises(MissionPaused) as caught:
            task.send(task.command(agent_cmd=Command.MOVE), 'second')
        self.assertEqual(caught.exception.request, request)
        self.assertEqual(len(self.published), 1)

    def test_real_pause_resume_releases_then_waits_without_output(self):
        task = self.task
        task.mission_state = 'running'
        task.actions.poll.side_effect = [None, dict(action='resume', request_id='new')]
        paused_samples = []
        def spin():
            if not self.published:
                return
            setup = self.published[-1].setup
            if setup.cmd == Setup.SET_PX4_MODE:
                self.assertEqual(setup.px4_mode, 'AUTO.LOITER')
                task.state.mode, task.latest['control_state'].control_state = 'AUTO.LOITER', 0
            else:
                task.state.mode, task.latest['control_state'].control_state = 'OFFBOARD', 2
            self.ack()
            if task.mission_state == 'paused':
                paused_samples.append(len(self.published))
                task.state.header.stamp.sec += 1
        self.on_spin = spin
        task.pause_and_resume(MissionPaused('unit explicit pause', dict(action='pause')))
        self.assertEqual(paused_samples, [1, 1])
        self.assertEqual(len(self.published), 2)
        self.assertTrue(task.owns_control())
        self.assertEqual(task.mission_state, 'running')
        entry = task.pauses[0]
        self.assertEqual(entry['publications_before'], entry['publications_after'])
        self.assertEqual(entry['end_boot_s'] - entry['start_boot_s'], 2)
        self.assertEqual(entry['resume_setup_request_id'], 2)

    def test_external_pause_does_not_send_hold_and_cancel_waits_for_ground(self):
        task = self.task
        task.mission_state = 'running'
        task.state.mode, task.latest['control_state'].control_state = 'AUTO.LOITER', 0
        task.cancel_request = dict(action='cancel')
        observations = []
        def spin():
            observations.append(len(self.published))
            if len(observations) == 2:
                task.state.armed, task.state.position[2] = False, 0.
        self.on_spin = spin
        with self.assertRaises(MissionCancelled):
            task.pause_and_resume(MissionPaused('external operator release'))
        task.cancel()
        self.assertEqual(self.published, [])
        self.assertEqual(observations, [0, 0])
        self.assertEqual(task.mission_state, 'cancelled')

    def test_pause_native_generation_change_cannot_resume(self):
        task = self.task
        task.state.mode, task.latest['control_state'].control_state = 'AUTO.LOITER', 0
        self.on_spin = lambda: setattr(task, 'native_generation', 2)
        with self.assertRaisesRegex(RuntimeError, 'Native generation changed'):
            task.pause_and_resume(MissionPaused('external operator release'))
        self.assertEqual(self.published, [])
        task.actions.poll.assert_not_called()

    def test_only_explicit_external_release_event_is_nonfatal(self):
        task = self.task
        for reason in ('native_state_stale', 'native_clock_or_origin_reset', 'native_failsafe_control_released'):
            task.error = None
            task.on_control_revoked(dict(reason=reason))
            self.assertIsNotNone(task.error)
        task.error = None
        task.on_control_revoked(dict(reason='external_mode_left_no_automatic_reacquisition'))
        self.assertIsNone(task.error)
        task.state.mode, task.latest['control_state'].failsafe = 'AUTO.LOITER', True
        with self.assertRaises(MissionPaused):
            task.pump()

    def test_operator_wait_excludes_only_the_paused_wall_interval(self):
        task = self.task
        task._operator_wait_total, task._operator_wait_started = 3., 95.
        self.assertEqual(task.operator_wait_seconds, 8.)
        task._operator_wait_started = None
        self.assertEqual(task.operator_wait_seconds, 3.)

    def test_send_timeout_is_not_cancelled_and_restores_interruptibility(self):
        task = self.task
        def spin():
            if self.published:
                task.mailbox.poll.return_value = {'id': 'cancel'}
        self.on_spin = spin
        with self.assertRaises(TimeoutError):
            task.send(task.command(agent_cmd=Command.MOVE), 'unacknowledged', timeout=0)
        self.assertIsNotNone(task.cancel_request)
        self.assertTrue(task.interruptible)
        self.assertIsNone(task.pending_request_id)
        self.assertNotEqual(task.mission_state, 'cancelled')

    def test_public_invalid_stale_and_error_win_over_cancel(self):
        task = self.task
        for fault in ('invalid', 'receive_stale', 'clock_stale', 'error'):
            with self.subTest(fault=fault):
                task.state.odom_valid = fault != 'invalid'
                task.received['state'] = 90 if fault == 'receive_stale' else 100
                task.advanced_at = 90 if fault == 'clock_stale' else 100
                task.error = 'explicit failure' if fault == 'error' else None
                task.cancel_request = {'id': 'cancel'}
                with self.assertRaisesRegex(RuntimeError, 'Public state|explicit failure'):
                    task.pump()
        self.assertEqual(self.published, [])

    def test_external_mode_control_state_and_failsafe_revoke_without_text(self):
        task = self.task
        for stack, mode in [('px4', 'OFFBOARD'), ('arducopter', 'GUIDED')]:
            for fault in ('mode', 'control', 'failsafe', 'missing_control'):
                with self.subTest(stack=stack, fault=fault):
                    task.flight_stack = stack
                    task.state.mode = 'AUTO.LOITER' if fault == 'mode' else mode
                    task.latest['control_state'] = NS(control_state=0 if fault == 'control' else 2,
                        COMMAND_CONTROL=2, failsafe=fault == 'failsafe')
                    if fault == 'missing_control':
                        del task.latest['control_state']
                    task.cancel_request = {'id': 'cancel'}
                    expected = MissionPaused if fault in ('mode', 'control') else RuntimeError
                    with self.assertRaisesRegex(expected, 'no automatic reacquisition') as caught:
                        task.pump()
                    self.assertIs(type(caught.exception), expected)
        self.assertEqual(task.events, [])
        self.assertEqual(self.published, [])

    def test_cancel_disarmed_ground_issues_zero_commands(self):
        task = self.task
        task.state.armed, task.state.position[2] = False, 0
        task.cancel()
        self.assertEqual(task.mission_state, 'cancelled')
        self.assertEqual(self.published, [])

    def test_cancel_armed_ground_uses_only_ordinary_disarm(self):
        task = self.task
        task.control_taken = task.control_required = False
        task.state.position[2] = 0
        def spin():
            task.state.armed = False
            self.ack()
        self.on_spin = spin
        task.cancel()
        self.assertEqual(task.mission_state, 'cancelled')
        self.assertEqual(len(self.published), 1)
        self.assertEqual(vars(self.published[0].setup).keys(), {'header', 'cmd', 'arming'})
        self.assertEqual(self.published[0].setup.cmd, Setup.ARMING)
        self.assertIs(self.published[0].setup.arming, False)

    def test_cancel_disarm_rejection_does_not_force_or_reacquire(self):
        task = self.task
        task.control_taken = task.control_required = False
        task.state.position[2] = 0
        self.on_spin = lambda: setattr(task, 'error', 'ordinary disarm rejected')
        with self.assertRaisesRegex(RuntimeError, 'ordinary disarm rejected'):
            task.cancel()
        self.assertEqual(len(self.published), 1)
        self.assertIs(self.published[0].setup.arming, False)
        self.assertNotEqual(task.mission_state, 'cancelled')

    def test_cancel_airborne_without_ownership_or_stale_cannot_claim_success(self):
        task = self.task
        task.control_taken = False
        with self.assertRaisesRegex(RuntimeError, 'no safe authorized disposition'):
            task.cancel()
        task.control_taken = True
        task.state.mode = 'AUTO.LOITER'
        with self.assertRaisesRegex(RuntimeError, 'lost task control'):
            task.cancel()
        task.received['state'] = 90
        with self.assertRaisesRegex(RuntimeError, 'stale state'):
            task.cancel()
        self.assertEqual(self.published, [])
        self.assertNotEqual(task.mission_state, 'cancelled')

    def test_visit_preserves_native_body_payload_and_estimates_snapshot(self):
        task = self.task
        task.state.position, task.state.attitude[2] = [2., 3., 3.], math.pi/2
        self.on_spin = lambda: self.ack() if self.published else None
        real_wait = task.wait
        def wait(label, predicate, timeout=20):
            if label.endswith('_reached'):
                task.state.position = [2., 4., 3.]
            real_wait(label, predicate, timeout)
        task.wait = wait
        def dwell(record, predicate):
            self.assertEqual(record['dwell_s'], 2)
            self.assertTrue(predicate())
            record['dwell_start_boot_s'] = 10
            record['dwell_start_truth'] = task.truth_cursor()
            task.state.header.stamp.sec += 2
            record['dwell_end_boot_s'] = 12
            record['dwell_end_truth'] = task.truth_cursor()
        task.dwell_waypoint = dwell
        task.visit(1, dict(frame='body_flu', position_m=[1, 0, 0], yaw_rad=0, dwell_s=2))
        command = self.published[0].command
        self.assertEqual(command.move_mode, Command.XYZ_POS_BODY)
        self.assertEqual(command.position_ref, [1, 0, 0])
        self.assertEqual(command.yaw_ref, 0)
        record = task.waypoints[0]
        self.assertEqual(record['target_enu_m'], [2, 4, 3])
        self.assertEqual(record['anchor']['position'], [2, 3, 3])
        self.assertEqual(record['status'], 'completed')
        self.assertEqual(record['dwell_end_boot_s'] - record['dwell_start_boot_s'], 2)
        self.assertEqual(task.truth_cursor.call_count, 2)

    def test_body_resume_keeps_recorded_enu_goal_and_restarts_whole_dwell(self):
        task = self.task
        task.state.position, task.state.attitude[2] = [2., 3., 3.], math.pi/2
        self.on_spin = lambda: self.ack() if self.published else None
        real_wait = task.wait
        def wait(label, predicate, timeout=20):
            if label.endswith('_reached'):
                task.state.position, task.state.attitude[2] = [2., 4., 3.], math.pi/2
            real_wait(label, predicate, timeout)
        task.wait = wait
        def pause(reason):
            self.assertNotIn('dwell_start_boot_s', task.waypoints[0])
            task.state.position, task.state.attitude[2] = [5., 6., 3.], 0.
        task.pause_and_resume = pause
        def dwell(record, predicate):
            self.assertTrue(predicate())
            if len(record['attempts']) == 1:
                record.update(dwell_start_boot_s=10., dwell_start_truth={'record': 1})
                raise MissionPaused('external mode')
            self.assertEqual(record['dwell_s'], 2.)
            record.update(dwell_start_boot_s=20., dwell_end_boot_s=22.)
        task.dwell_waypoint = dwell
        task.visit(1, dict(frame='body_flu', position_m=[1., 0., 0.], yaw_rad=0., dwell_s=2.))
        first, resumed = [e.command for e in self.published]
        self.assertEqual(first.move_mode, Command.XYZ_POS_BODY)
        self.assertEqual(resumed.move_mode, Command.XYZ_POS)
        self.assertEqual(resumed.position_ref, [2., 4., 3.])
        self.assertAlmostEqual(resumed.yaw_ref, math.pi/2)
        self.assertGreater(resumed.command_id, first.command_id)
        record = task.waypoints[0]
        self.assertEqual([a['status'] for a in record['attempts']], ['interrupted', 'completed'])
        self.assertEqual(record['dwell_end_boot_s']-record['dwell_start_boot_s'], 2.)

    def test_visit_cancel_after_ack_never_completes_waypoint(self):
        task = self.task
        def spin():
            if self.published:
                self.ack()
                task.mailbox.poll.return_value = {'id': 'cancel'}
        self.on_spin = spin
        point = dict(frame='enu', position_m=[0, 0, 3], yaw_rad=0, dwell_s=2)
        with self.assertRaises(MissionCancelled):
            task.visit(1, point)
        with self.assertRaises(MissionCancelled):
            task.visit(2, point)
        self.assertEqual(len(self.published), 1)
        self.assertEqual(task.waypoints[0]['status'], 'running')
        task.truth_cursor.assert_not_called()

    def test_cancel_owned_airborne_lands_then_observes_ground(self):
        task = self.task
        task.cancel_request = {'id': 'cancel'}
        def spin():
            if not self.published:
                return
            self.ack()
            envelope = self.published[-1]
            if hasattr(envelope, 'command'):
                self.assertEqual(envelope.command.agent_cmd, Command.LAND)
                task.state.armed, task.state.position[2] = False, 0
            else:
                task.received['state'] = 100.1
        self.on_spin = spin
        task.cancel()
        self.assertEqual(task.mission_state, 'cancelled')
        self.assertEqual(len(self.published), 2)
        self.assertEqual(self.published[1].setup.cmd, Setup.SET_PX4_MODE)
        self.assertEqual(self.published[1].setup.px4_mode, 'AUTO.LOITER')
        self.assertEqual([record.get('event') for record in task.progress_records],
                         ['mission_cancelling', 'landing_requested', 'mission_cancelled'])
        self.assertIn(unittest.mock.call('normal_stop_ready'), task.phase.call_args_list)

    def test_visit_resolved_out_of_bounds_sends_nothing(self):
        self.task.state.position = [20, 0, 3]
        with self.assertRaises(ValueError):
            self.task.visit(1, dict(frame='body_flu', position_m=[1, 0, 0], yaw_rad=0, dwell_s=2))
        self.assertEqual(self.published, [])
        self.assertEqual(self.task.waypoints, [])

    def test_visit_dwell_rejects_bad_position_speed_or_yaw(self):
        task = self.task
        self.on_spin = lambda: self.ack() if self.published else None
        point = dict(frame='enu', position_m=[0, 0, 3], yaw_rad=0, dwell_s=2)
        def dwell(record, predicate):
            for field, value in [('position', [1, 0, 3]), ('velocity', [0.6, 0, 0]),
                                 ('attitude', [0, 0, 0.2])]:
                old = getattr(task.state, field)
                setattr(task.state, field, value)
                self.assertFalse(predicate(), field)
                setattr(task.state, field, old)
            raise RuntimeError('injected dwell threshold failure')
        task.dwell_waypoint = dwell
        with self.assertRaisesRegex(RuntimeError, 'dwell threshold'):
            task.visit(1, point)
        self.assertEqual(task.waypoints[0]['status'], 'running')
        self.assertNotIn('dwell_end_truth', task.waypoints[0])

    def real_progress_files(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        task = self.task
        task.directory, task.mission_id = Path(folder.name), 'unit-mission'
        task.mission_log = (task.directory / 'mission.jsonl').open('w', encoding='utf-8', buffering=1)
        self.addCleanup(task.mission_log.close)
        del task.progress  # Exercise production JSON encoding and status replacement.

    def test_numpy_float32_visit_progress_serializes_real_files(self):
        self.real_progress_files()
        task = self.task
        self.on_spin = lambda: self.ack() if self.published else None
        real_wait = task.wait
        def wait(label, predicate, timeout=20):
            if label.endswith('_reached'):
                task.state.position = np.array(task.waypoints[-1]['target_enu_m'], dtype=np.float32)
            real_wait(label, predicate, timeout)
        task.wait = wait
        def dwell(record, predicate):
            self.assertTrue(predicate())
        task.dwell_waypoint = dwell
        for index, frame in enumerate(('enu', 'body_flu'), 1):
            task.state.position = np.array([2, 3, 3], dtype=np.float32)
            task.state.velocity = np.zeros(3, dtype=np.float32)
            task.state.attitude = np.array([0, 0, math.pi/2], dtype=np.float32)
            self.assertIsInstance(task.state.position[0], np.float32)
            # Reproduce the original failure without modifying production code.
            with self.assertRaises(TypeError):
                json.dumps(list(task.state.position))
            point = dict(frame=frame, position_m=[2, 3, 3] if frame == 'enu' else [1, 0, 0],
                         yaw_rad=float(task.state.attitude[2]) if frame == 'enu' else 0, dwell_s=2)
            task.visit(index, point)
            anchor = task.waypoints[-1]['anchor']
            self.assertTrue(all(type(x) is float for x in anchor['position']))
            self.assertIs(type(anchor['yaw']), float)
        rows = [json.loads(line) for line in (task.directory / 'mission.jsonl').read_text().splitlines()]
        self.assertEqual(rows, task.progress_records)
        self.assertEqual([r['update_sequence'] for r in rows], [1, 2, 3, 4])
        self.assertEqual(json.loads((task.directory / 'mission-status.json').read_text()), rows[-1])
        self.assertEqual(rows[-1]['event'], 'waypoint_completed')
        json.dumps(task.waypoints, allow_nan=False)

    def test_progress_serialization_failure_does_not_poison_records_or_files(self):
        self.real_progress_files()
        task = self.task
        task.progress(event='baseline')
        before = (task.directory / 'mission.jsonl').read_bytes()
        status = (task.directory / 'mission-status.json').read_bytes()
        with self.assertRaises(TypeError):
            task.progress(event='bad_scalar', value=np.float32(1))
        self.assertEqual(len(task.progress_records), 1)
        self.assertEqual((task.directory / 'mission.jsonl').read_bytes(), before)
        self.assertEqual((task.directory / 'mission-status.json').read_bytes(), status)
        task.fail('serialization rejected')
        self.assertEqual(task.progress_records[-1]['update_sequence'], 2)
        self.assertEqual(json.loads((task.directory / 'mission-status.json').read_text())['state'], 'failed')

    def test_dwell_false_resets_entire_window_without_accumulating_fragments(self):
        task = self.task
        samples = iter([(10, True), (11, True), (12, False),
                        (13, True), (14, True), (15, True)])
        observed = []
        def pump():
            stamp, good = next(samples)
            task.state.header.stamp.sec = stamp
            observed.append((stamp, good))
        task.pump = pump
        task.truth_cursor = Mock(side_effect=[{'record': 10}, {'record': 13}, {'record': 15}])
        record = dict(index=1, dwell_s=2)
        task.dwell_waypoint(record, lambda: observed[-1][1])
        self.assertEqual(len(observed), 6)  # Must not finish at 13 or 14.
        self.assertEqual(record['dwell_start_boot_s'], 13)
        self.assertEqual(record['dwell_end_boot_s'], 15)
        self.assertEqual(record['dwell_start_truth'], {'record': 13})
        self.assertEqual(record['dwell_end_truth'], {'record': 15})
        self.assertEqual([r['event'] for r in task.progress_records],
                         ['waypoint_dwell_started', 'waypoint_dwell_reset', 'waypoint_dwell_started'])
        self.assertEqual(task.progress_records[1]['invalidated_start_boot_s'], 10)

    def test_dwell_never_settles_hits_wall_deadline(self):
        task = self.task
        task.pump = Mock()
        with patch('time.monotonic', side_effect=[100, 114, 115]):
            with self.assertRaisesRegex(TimeoutError, 'continuous boot-clock dwell timeout'):
                task.dwell_waypoint(dict(index=1, dwell_s=2), lambda: False)
        self.assertEqual(task.pump.call_count, 2)
        task.truth_cursor.assert_not_called()

    def test_dwell_stale_is_fatal_but_operator_release_interrupts(self):
        task = self.task
        for fault in ('stale', 'ownership'):
            with self.subTest(fault=fault):
                task.received['state'] = 90 if fault == 'stale' else 100
                task.state.mode = 'OFFBOARD' if fault == 'stale' else 'AUTO.LOITER'
                predicate = Mock(return_value=True)
                expected = RuntimeError if fault == 'stale' else MissionPaused
                with self.assertRaisesRegex(expected, 'Public state|lost task control') as caught:
                    task.dwell_waypoint(dict(index=1, dwell_s=2), predicate)
                self.assertIs(type(caught.exception), expected)
                predicate.assert_not_called()
        task.truth_cursor.assert_not_called()

    def test_execute_cancel_resolution_failure_is_failed(self):
        task = self.task
        task.state.armed, task.state.position[2] = False, 0
        task.wait = Mock()
        task.check_cancel = Mock(side_effect=MissionCancelled())
        task.cancel = Mock(side_effect=RuntimeError('landing rejected'))
        with self.assertRaisesRegex(RuntimeError, 'landing rejected'):
            task.execute()
        self.assertEqual(task.mission_state, 'failed')
        self.assertEqual(self.published, [])

    def test_execute_cancel_release_race_waits_for_explicit_resume(self):
        task = self.task
        task.state.armed, task.state.position[2] = False, 0
        task.wait = Mock()
        task.check_cancel = Mock(side_effect=MissionCancelled())
        task.cancel = Mock(side_effect=[MissionPaused('concurrent operator release'), None])
        task.pause_and_resume = Mock(side_effect=MissionCancelled())
        task.execute()
        self.assertEqual(task.cancel.call_count, 2)
        self.assertEqual(task.pause_and_resume.call_count, 1)
        self.assertNotEqual(task.mission_state, 'failed')

    def test_takeoff_can_be_paused_again_before_resumed_target_dispatch(self):
        task = self.task
        task.state.armed, task.state.position[2] = False, 0
        task.flight_stack, task.plan = 'arducopter', {'waypoints': []}
        task.events = [dict(event='takeover_reference', position_enu_m=[0., 0., 3.], yaw_enu_rad=0.)]
        def wait(label, predicate, timeout=20):
            if label == 'takeoff_reached' and task.pause_and_resume.call_count == 0:
                raise MissionPaused('first pause during takeoff')
        def send(msg, label, timeout=10):
            if label == 'takeoff_resume_target_accepted' and task.pause_and_resume.call_count == 1:
                raise MissionPaused('second pause before resumed target')
        task.wait, task.send = wait, send
        task.pause_and_resume, task.check_cancel = Mock(), Mock()
        task.dwell, task.land = Mock(), Mock()
        task.execute()
        self.assertEqual(task.pause_and_resume.call_count, 2)
        self.assertEqual(task.mission_state, 'completed')

    def test_execute_terminal_outcomes_are_distinct(self):
        # Deliberately stub flight operations; test real execute exception routing.
        task = self.task
        task.flight_stack = 'arducopter'
        task.state.armed, task.state.position[2] = False, 0
        task.plan = {'waypoints': []}
        task.wait = Mock()
        task.send = Mock()
        task.dwell = Mock()
        task.land = Mock()
        task.check_cancel = Mock()
        task.execute()
        self.assertEqual(task.mission_state, 'completed')
        task.check_cancel.side_effect = MissionCancelled()
        task.execute()
        self.assertEqual(task.mission_state, 'cancelled')
        task.check_cancel.side_effect = RuntimeError('state failure')
        with self.assertRaisesRegex(RuntimeError, 'state failure'):
            task.execute()
        self.assertEqual(task.mission_state, 'failed')
        self.assertFalse(task.interruptible)
        self.assertFalse(task.control_required)


if __name__ == '__main__':
    unittest.main()
