"""No ROS/FC/model: frozen clock, frame, calibration and recovery checks."""
import hashlib
import math
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Simulator.wksim_runtime.attitude_task import (AttitudeTask, BUDGET, BUDGET_SHA,
                                                  ENTRY_CONTRACT, MODE_TRUE, MODE_FALSE,
                                                  AP_PARAMETERS, require_ap_recovery_parameters,
                                                  hover_median, physical, within)


class AttitudeTaskTests(unittest.TestCase):
    def gate_task(self, *, mode_stamp=1000000, target_stamp=1.001, wrong_flag=None):
        task = AttitudeTask.__new__(AttitudeTask)
        task.flight_stack = 'px4'
        current = dict(time=0.)
        task.read_truth = lambda: current
        task.control_modes, task.native_samples = [], []
        task.control_mode_topic = '/mode'
        task.last_graph = {'/mode': [dict(node='px4', namespace='/', endpoint_gid='01')]}
        events = []
        task.mark = lambda label, **data: events.append((label, data))
        def command(label, *, attitude):
            events.append((label, attitude))
            task.last_command_target = dict(native_source_stamp=1000000)
        task.command = command
        flags = dict.fromkeys(MODE_TRUE, True) | dict.fromkeys(MODE_FALSE, False)
        if wrong_flag:
            flags[wrong_flag] = not flags[wrong_flag]
        def pump():
            current['time'] += .1
            if current['time'] > task.entry_deadline[0]:
                raise TimeoutError('fixture physical deadline')
            task.control_modes.append(dict(native_source_stamp=mode_stamp,
                                           physical_time=current['time'], flags=flags))
            task.native_samples.append(dict(native_boot_s=target_stamp, physical_time=current['time'],
                thrust=.4+1e-7, quaternion=[math.sqrt(.5), 0., 0., math.sqrt(.5)]))
        task.pump = pump
        return task, events

    def test_entry_neutral_first_and_strict_native_order(self):
        task, events = self.gate_task()
        task.attitude_entry('step', 0., .4)
        self.assertEqual(events[1], ('step_neutral', (0., 0., 0., .4)))
        self.assertEqual(events[-1][0], 'step_preconditioning_complete')
        self.assertIsNone(task.entry_deadline)
        for mode, target in ((999999, 1.1), (1000000, 1.), (1000000, .999)):
            task, events = self.gate_task(mode_stamp=mode, target_stamp=target)
            with self.assertRaises(TimeoutError):
                task.attitude_entry('step', 0., .4)
            self.assertNotIn('step_preconditioning_complete', [e[0] for e in events])
            self.assertIsNone(task.entry_deadline)

    def test_entry_rejects_every_wrong_mode_flag_and_wrong_neutral(self):
        for name in (*MODE_TRUE, *MODE_FALSE):
            task, _ = self.gate_task(wrong_flag=name)
            with self.subTest(flag=name), self.assertRaises(TimeoutError):
                task.attitude_entry('step', 0., .4)
        task, _ = self.gate_task()
        pump = task.pump
        def wrong_target():
            pump()
            task.native_samples[-1]['thrust'] = .43
        task.pump = wrong_target
        with self.assertRaises(TimeoutError):
            task.attitude_entry('step', 0., .4)

    def test_entry_no_cached_mode_and_ap_has_no_gate(self):
        task, events = self.gate_task()
        task.flight_stack = 'arducopter'
        task.attitude_entry('step', 0., .4)
        self.assertEqual(events, [])
        contract = json.loads(ENTRY_CONTRACT.read_text())
        self.assertEqual(contract['arducopter']['candidate_PSC_ANGLE_MAX'], 10)
        self.assertIn('PSC_ANGLE_MAX', AP_PARAMETERS)
        self.assertIn('ATC_ANGLE_MAX', AP_PARAMETERS)
        self.assertNotIn('ANGLE_MAX', AP_PARAMETERS)

    def test_ap_actual_candidate_readback_required(self):
        require_ap_recovery_parameters(dict(PSC_ANGLE_MAX=10, ATC_ANGLE_MAX=30))
        for values in ({}, dict(PSC_ANGLE_MAX=0, ATC_ANGLE_MAX=30),
                       dict(PSC_ANGLE_MAX=10, ATC_ANGLE_MAX=15)):
            with self.assertRaises(RuntimeError):
                require_ap_recovery_parameters(values)

    def test_entry_physical_and_wall_deadlines_apply_inside_pump(self):
        task, _ = self.gate_task()
        task.poll_dds = task.poll_native = lambda: None
        task.fresh = lambda: True
        task.envelope_anchor = None
        for physical_deadline, wall_deadline in ((-1., 101.), (1., 99.)):
            task.entry_deadline = (physical_deadline, wall_deadline)
            with patch('Simulator.wksim_runtime.task.Task.pump'), patch(
                    'Simulator.wksim_runtime.attitude_task.time.monotonic', return_value=100.):
                with self.assertRaises(TimeoutError):
                    AttitudeTask.pump(task)

    def test_frozen_budget_and_basis(self):
        self.assertEqual(hashlib.sha256(BUDGET.read_bytes()).hexdigest(), BUDGET_SHA)
        state = [0.]*60
        state[3:12] = [1., 2., -3., 4., 5., -6., .1, -.2, .3]
        result = physical(dict(time=7., vehicle=state))
        self.assertEqual(result['position'], (5., 4., 6.))
        self.assertEqual(result['velocity'], (2., 1., 3.))
        self.assertEqual(result['attitude'], (.1, .2, math.pi/2-.3))
        self.assertFalse(within(result, (5., 4., 6.), result['attitude'][2],
                                position=.4, speed=.3, tilt=3, heading=3))

    def test_native_hover_has_no_motor_average_or_tuned_fallback(self):
        samples = [dict(physical_time=i/20, thrust=.4 if i != 20 else .6) for i in range(61)]
        value, recorded = hover_median(samples, 0., 3.)
        self.assertEqual(value, .4)
        self.assertEqual(recorded, samples)
        for bad in (samples[10:], [dict(physical_time=i/20, thrust=.9) for i in range(61)],
                    [dict(physical_time=0., thrust=float('nan')), dict(physical_time=3., thrust=.4)]):
            with self.assertRaises((ValueError, RuntimeError)):
                hover_median(bad, 0., 3.)

    def test_stability_restarts_but_original_deadline_does_not(self):
        task = AttitudeTask.__new__(AttitudeTask)
        current = dict(time=0., position=(0., 0., 3.), velocity=(0., 0., 0.), attitude=(0., 0., 0.))
        task.read_truth = lambda: current
        task.mark = lambda *a, **k: None
        task.fresh = lambda: True
        samples = iter(((.5, .1), (1., .4), (2., .1), (3., .1), (3.5, .1)))
        def pump():
            current['time'], speed = next(samples)
            current['velocity'] = (speed, 0., 0.)
        task.pump = pump
        task.stable('recovery', (0., 0., 3.), 0., timeout=8., dwell=1.5,
                    position=.4, speed=.3, tilt=3, heading=3)
        self.assertEqual(current['time'], 3.5)
        current['time'] = 0.
        task.pump = lambda: current.update(time=8.01)
        with self.assertRaises(TimeoutError):
            task.stable('recovery', (0., 0., 3.), 0., timeout=8., dwell=1.5,
                        position=.4, speed=.3, tilt=3, heading=3)

    def test_recovery_counts_public_ack_latency(self):
        task = AttitudeTask.__new__(AttitudeTask)
        times = iter((10., 12.))
        task.read_truth = lambda: dict(time=next(times))
        task.command = lambda *a, **k: None
        seen = []
        task.stable = lambda *a, **k: seen.append(k)
        task.recovery('recovery', (0., 0., 3.), 0.)
        self.assertEqual(seen[0]['timeout'], 6.)
        self.assertEqual(seen[0]['dwell'], 1.5)

    def test_duration_uses_physical_time_and_checks_final_sample(self):
        task = AttitudeTask.__new__(AttitudeTask)
        current = dict(time=0.)
        task.read_truth = lambda: current
        task.mark = lambda *a, **k: None
        task.fresh = lambda: True
        task.pump = lambda: current.update(time=current['time']+.25)
        with patch('Simulator.wksim_runtime.attitude_task.time.monotonic', return_value=100.):
            task.duration('physical', 1., lambda v: v['time'] <= 1.)
            self.assertEqual(current['time'], 1.)
            with self.assertRaises(RuntimeError):
                task.duration('failed_final', .5, lambda v: v['time'] < 1.5)

    def test_observation_transport_rejects_motion_commands(self):
        task = AttitudeTask.__new__(AttitudeTask)
        task.peer = ('127.0.0.1', 12345)
        task.dialect = SimpleNamespace(MAV_CMD_SET_MESSAGE_INTERVAL=511)
        with self.assertRaises(ValueError):
            task.transmit_observation(SimpleNamespace(get_type=lambda: 'SET_ATTITUDE_TARGET'))
        with self.assertRaises(ValueError):
            task.transmit_observation(SimpleNamespace(get_type=lambda: 'COMMAND_LONG', command=400))


def ros_loopback():
    """Explicit real ROS loopback only; no FC/model and synthetic fixture truth."""
    import rclpy
    from rclpy.serialization import serialize_message, deserialize_message
    from wksim_msgs.msg import CommandRequest, SetupRequest
    from ardupilot_msgs.msg import WksimAttitudeTarget
    from px4_msgs.msg import VehicleAttitudeSetpoint, VehicleControlMode
    from prometheus_control.frames import topic
    import prometheus_control
    import ardupilot_msgs
    import px4_msgs
    root = Path(tempfile.mkdtemp(prefix='wksim-attitude-loopback-', dir='/root'))
    result = dict(scope='ROS loopback with synthetic fixture truth; no FC, model or flight evidence', cases=[],
        source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                       (Path(__file__), Path(sys.modules[AttitudeTask.__module__].__file__))},
        imports={m.__name__: str(Path(m.__file__).resolve()) for m in (prometheus_control, ardupilot_msgs, px4_msgs)})
    rclpy.init()
    try:
        for stack in ('arducopter', 'px4'):
            directory = root/stack
            directory.mkdir()
            state = [0.]*60
            state[8] = -3.
            (directory/'truth.jsonl').write_text(json.dumps(dict(time=1., vehicle=state))+'\n')
            task = AttitudeTask(directory, lambda: None, lambda label: None, stack,
                                run_id='attitude-loopback-'+stack, protocol='session_v1')
            fixture = rclpy.create_node('prometheus_native_control')
            fixture.create_subscription(SetupRequest, '/uav1/prometheus/v2/setup', lambda msg: None, 1)
            fixture.create_subscription(CommandRequest, '/uav1/prometheus/v2/command', lambda msg: None, 1)
            if stack == 'arducopter':
                cls, name = WksimAttitudeTarget, '/ap/wksim/attitude_target_v1'
                message = cls(normalized_thrust=.375)
                message.header.frame_id = 'map'
                message.header.stamp.sec = 1
                message.orientation.w = 1.
            else:
                cls = VehicleAttitudeSetpoint
                name = topic('/wksim_px4_21', 'in', 'vehicle_attitude_setpoint', cls)
                message = cls(timestamp=1000000, q_d=[math.sqrt(.5), 0., 0., math.sqrt(.5)],
                              thrust_body=[0., 0., -.375])
            publisher = fixture.create_publisher(cls, name, 10)
            mode_publisher = (fixture.create_publisher(VehicleControlMode, task.control_mode_topic, 10)
                              if stack == 'px4' else None)
            try:
                deadline = time.monotonic()+10
                while (not task.public_graph_ready() or publisher.get_subscription_count() != 1
                       or mode_publisher is not None and mode_publisher.get_subscription_count() != 1):
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Loopback discovery')
                    rclpy.spin_once(task.node, timeout_sec=.02)
                publisher.publish(message)
                if mode_publisher is not None:
                    mode_message = VehicleControlMode(timestamp=1000000, **dict.fromkeys(MODE_TRUE, True))
                    mode_publisher.publish(mode_message)
                deadline = time.monotonic()+5
                while not task.native_targets or mode_publisher is not None and not task.control_modes:
                    task.poll_dds()
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Loopback raw CDR')
                    time.sleep(.01)
                lines = [json.loads(line) for line in (directory/'attitude-native.jsonl').read_text().splitlines()]
                recorded = [row for row in lines if row['kind'] == 'dds' and row['topic'] == name]
                assert len(recorded) == 1 and recorded[0]['cdr_hex'] == serialize_message(message).hex()
                assert recorded[0]['per_message_publisher_gid_available'] is False and 'publisher_gid' not in recorded[0]
                assert isinstance(recorded[0]['source_timestamp'], int) and recorded[0]['source_timestamp'] > 0
                assert isinstance(recorded[0]['received_timestamp'], int) and recorded[0]['received_timestamp'] > 0
                assert math.dist(task.native_targets[0]['quaternion_xyzw'], (0., 0., 0., 1.)) < 1e-6
                if mode_publisher is not None:
                    mode_rows = [row for row in lines if row['kind'] == 'dds' and row['topic'] == task.control_mode_topic]
                    # CDR alignment padding is not semantic message data.
                    decoded_mode = deserialize_message(bytes.fromhex(mode_rows[0]['cdr_hex']), VehicleControlMode)
                    assert task.convert(decoded_mode) == task.convert(mode_message)
                    assert task.control_modes[0]['native_source_stamp'] == 1000000
                    assert all(task.control_modes[0]['flags'][key] for key in MODE_TRUE)
                result['cases'].append(dict(stack=stack, status='pass', raw_cdr_exact=True,
                    public_request_graph=task.attitude_result['public_request_graph'], native_targets=task.native_targets))
            finally:
                fixture.destroy_node()
                task.close()
    finally:
        rclpy.shutdown()
        (root/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(root=str(root), result=result)))


if __name__ == '__main__':
    if sys.argv[1:] == ['--ros-loopback']:
        ros_loopback()
    else:
        unittest.main()
