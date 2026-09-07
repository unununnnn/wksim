"""Pure public-message contract tests; these do not launch or validate a flight controller."""
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from Simulator.wksim_runtime.task import Task
from validation.test_task_identity import task, session, state
from validation.test_task_scene_pause import scene_task


class Setup(NS):
    SET_CONTROL_MODE, SET_PX4_MODE, ARMING = 1, 2, 3

    def __init__(self, **fields):
        super().__init__(header=NS(), **fields)


class Command(NS):
    LAND = 3

    def __init__(self, **fields):
        super().__init__(header=NS(), **fields)


class Harness:
    def __init__(self, stack='px4'):
        self.t = t = task()
        self.wall, self.ros_time, self.sequence = 100., 10., 0
        self.high_water, self.pending, self.published, self.phases = 700, [], [], []
        self.bad_state, self.reject, self.old_only = None, False, False
        t.use_sim_time, t.flight_stack = True, stack
        t.Setup, t.Cmd, t.SetupRequest, t.CommandRequest = Setup, Command, NS, NS
        t.sent, t.envelopes, t.events = [], [], []
        t.pending_request_id, t._last_ros_ns = None, None
        t.node = NS(get_clock=lambda: NS(now=lambda: NS(
            nanoseconds=round(self.ros_time*1e9), to_msg=lambda: NS())))
        t.setup_pub = NS(publish=self.publish, get_subscription_count=lambda: 1)
        t.command_pub = NS(publish=self.publish, get_subscription_count=lambda: 1)
        t.phase = lambda label: self.phases.append((label, t.task_time()))
        t.pump = self.pump
        self.aircraft = state()
        self.aircraft.armed, self.aircraft.position, self.aircraft.mode = True, [1., 2., 3.], 'AUTO.LOITER'
        self.control = NS(uav_id=1, control_state=0, COMMAND_CONTROL=2, failsafe=False)

    def publish(self, message):
        self.published.append(message)
        self.pending.append(message)

    def event(self, **fields):
        self.t.receive('text_info', NS(message=json.dumps(dict(
            run_id='run', control_epoch='e'*32, **fields))))

    def pump(self):
        self.wall += .1
        self.ros_time += .1
        self.sequence += 1
        if self.pending:
            message = self.pending.pop(0)
            self.high_water = message.request_id
            # A new Task must neither fail on retired-task events nor accept its ACK.
            self.event(event='control_revoked', request_id=700)
            self.event(event='setup_rejected', request_id=700)
            self.event(event='setup_completed', request_id=700)
            if self.reject:
                self.event(event='setup_rejected', request_id=message.request_id)
            elif not self.old_only:
                if hasattr(message, 'setup'):
                    if message.setup.cmd == Setup.SET_CONTROL_MODE:
                        self.control.control_state = 2
                        self.aircraft.mode = 'OFFBOARD' if self.t.flight_stack == 'px4' else 'GUIDED'
                    elif message.setup.cmd == Setup.SET_PX4_MODE:
                        self.aircraft.mode = message.setup.px4_mode
                        self.aircraft.odom_valid = True
                    self.event(event='setup_completed', request_id=message.request_id)
                else:
                    self.aircraft.armed, self.aircraft.position[2] = False, 0.
                    self.event(event='command_accepted', request_id=message.request_id,
                               command_id=message.command.command_id)
        self.aircraft.header.stamp = NS(sec=int(self.ros_time), nanosec=round(self.ros_time%1*1e9))
        msg = session(sequence=self.sequence, last_request_id=self.high_water,
                      published_monotonic_s=self.wall, source_received_monotonic_s=self.wall,
                      state=self.aircraft, control=self.control)
        if self.bad_state:
            self.bad_state(msg)
        self.t.receive_session(msg)
        if self.t.error:
            raise RuntimeError(self.t.error)
        if self.t.active and not self.t.fresh():
            raise RuntimeError('Public state invalid, disconnected, or stale')

    def run(self, **kwargs):
        with patch('Simulator.wksim_runtime.task.time.monotonic', side_effect=lambda: self.wall):
            self.t.recover_then_land(**kwargs)


class AirborneRecoveryTests(unittest.TestCase):
    def test_explicit_native_hold_is_not_skipped_for_a_temporarily_healthy_snapshot(self):
        h=Harness('px4')
        self.assertTrue(h.aircraft.odom_valid)
        h.run(allow_native_hold=True)
        self.assertEqual([message.request_id for message in h.published],[701,702,703,704])
        self.assertEqual(h.published[0].setup.px4_mode,'AUTO.LOITER')
        self.assertEqual(h.published[1].setup.control_state,'COMMAND_CONTROL')

    def test_native_hold_reserves_the_land_command_id_before_any_public_request(self):
        h=Harness('px4')
        h.high_water=2**32-3
        with self.assertRaisesRegex(RuntimeError,'high-water mark'):
            h.run(allow_native_hold=True)
        self.assertEqual(h.published,[])

    def test_only_explicit_native_hold_offer_can_request_mode_before_position_control(self):
        h=Harness('px4')
        h.aircraft.odom_valid=False
        h.run(allow_native_hold=True)
        self.assertEqual([message.request_id for message in h.published],[701,702,703,704])
        self.assertEqual(h.published[0].setup.px4_mode,'AUTO.LOITER')
        self.assertEqual(h.published[1].setup.control_state,'COMMAND_CONTROL')
        self.assertEqual(h.published[2].command.agent_cmd,Command.LAND)

    def test_new_requests_hold_land_both_stacks(self):
        for stack in ('px4', 'arducopter'):
            h = Harness(stack)
            h.run()
            self.assertEqual([x.request_id for x in h.published], [701, 702, 703])
            self.assertEqual(h.published[0].setup.control_state, 'COMMAND_CONTROL')
            self.assertEqual(h.published[1].command.agent_cmd, Command.LAND)
            self.assertEqual(h.published[1].command.command_id, 702)
            self.assertEqual(h.published[2].setup.px4_mode, 'AUTO.LOITER')
            phases = dict(h.phases)
            self.assertGreaterEqual(phases['airborne_recovery_hold_completed']-
                                    phases['airborne_recovery_state_confirmed'], 2.)
            self.assertIn('normal_stop_ready', phases)
            self.assertFalse(h.t.state.armed)
            with self.assertRaisesRegex(RuntimeError, 'new session task'):
                h.run()

    def test_no_admission_on_ground_invalid_stale_or_duplicate_session(self):
        mutations = [lambda m: setattr(m.state, 'armed', False),
                     lambda m: m.state.position.__setitem__(2, .3),
                     lambda m: setattr(m.state, 'odom_valid', False),
                     lambda m: setattr(m.state, 'connected', False),
                     lambda m: setattr(m, 'source_received_monotonic_s', 90.),
                     lambda m: setattr(m, 'sequence', 0)]
        for mutate in mutations:
            h = Harness()
            h.bad_state = mutate
            with self.assertRaises(TimeoutError):
                h.run()
            self.assertFalse(h.t.active)
            self.assertEqual(h.published, [])

    def test_requires_exactly_one_control_subscriber(self):
        for count in (0, 2):
            h = Harness()
            h.t.command_pub.get_subscription_count = lambda: count
            with self.assertRaises(TimeoutError):
                h.run()
            self.assertEqual(h.published, [])

    def test_rejection_and_retired_ack_never_retry(self):
        for flag, error in (('reject', RuntimeError), ('old_only', TimeoutError)):
            h = Harness()
            setattr(h, flag, True)
            with self.assertRaises(error):
                h.run()
            self.assertEqual(len(h.published), 1)
            with self.assertRaises(RuntimeError):
                h.run()
            self.assertEqual(len(h.published), 1)

    def test_confirmation_requires_current_control_mode_and_no_failsafe(self):
        for mutate in (lambda m: setattr(m.control, 'control_state', 0),
                       lambda m: setattr(m.control, 'failsafe', True),
                       lambda m: setattr(m.state, 'mode', 'AUTO.LOITER')):
            h = Harness()
            h.bad_state = mutate
            with self.assertRaises(TimeoutError):
                h.run()
            self.assertEqual(len(h.published), 1)

    def test_new_revocation_invalid_state_and_hold_drift_fail_without_land(self):
        for failure in ('revoked', 'unscoped_revocation', 'invalid', 'drift'):
            h = Harness()
            def mutate(msg):
                if h.ros_time < 10.6:
                    return
                if failure == 'revoked':
                    h.event(event='control_revoked', request_id=701)
                elif failure == 'unscoped_revocation':
                    h.event(event='control_revoked', request_id=0)
                elif failure == 'invalid':
                    msg.state.odom_valid = False
                else:
                    msg.state.position[0] += 1.
            h.bad_state = mutate
            with self.assertRaises(RuntimeError):
                h.run()
            self.assertEqual(len(h.published), 1)

    def test_old_failed_task_and_legacy_or_wall_clock_are_not_recoverable(self):
        for key, value in (('error', 'old task failed'), ('active', True),
                           ('sent', [{}]), ('envelopes', [{}]),
                           ('protocol', 'legacy_v1'), ('use_sim_time', False)):
            h = Harness()
            setattr(h.t, key, value)
            with self.assertRaises(RuntimeError):
                h.run()
            self.assertEqual(h.published, [])

    def test_exhausted_high_water_rejected_before_takeover(self):
        h = Harness()
        h.high_water = 2**32-2
        with self.assertRaisesRegex(RuntimeError, 'high-water'):
            h.run()
        self.assertEqual(h.published, [])

    def test_default_execute_still_requires_ground(self):
        h = Harness()
        with patch('Simulator.wksim_runtime.task.time.monotonic', side_effect=lambda: h.wall):
            with self.assertRaisesRegex(RuntimeError, 'initial disarmed ground'):
                h.t.execute()
        self.assertEqual(h.published, [])

    @patch('Simulator.wksim_runtime.task.time.monotonic', return_value=100.)
    def test_recovering_waits_inactive_with_no_source_age_exemption(self, clock):
        t = scene_task()
        t.active = False
        t.scene_lease.status.update(phase='recovering', sequence=2)
        t.scene_status()
        clock.return_value = 104.
        t.receive_session(session(sequence=2, published_monotonic_s=104.))
        self.assertFalse(t.fresh())
        self.assertFalse(t.active)
        self.assertIsNone(t.error)
        phases = iter(('recovering', 'running'))
        spins = []
        def spin(*args, **kwargs):
            phase = next(phases)
            spins.append(phase)
            t.scene_lease.status.update(phase=phase, sequence=3+len(spins))
            msg = session(sequence=3+len(spins), published_monotonic_s=104.,
                          source_received_monotonic_s=104.)
            # Beyond the recovering heartbeat tick: moving physics is allowed.
            msg.state.header.stamp.sec = 11+len(spins)
            t.receive_session(msg)
            self.assertFalse(t.active)
        t.health = lambda: None
        t.ros = NS(spin_once=spin)
        t.pump()
        self.assertEqual(spins, ['recovering', 'running'])
        self.assertTrue(t.fresh())
        self.assertIsNone(t._scene_frozen_stamp)


if __name__ == '__main__':
    unittest.main()
