"""Pure #35 candidate checks; no ROS node, native library or flight process."""
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from Simulator.wksim_control.position_pid import PIDState
from Simulator.wksim_core import ap_json
from Simulator.wksim_runtime.pid_task import (
    CONFIG_PATH, CONFIG_SHA256, PIDLoop, PIDTask, evaluate_rows, event_for, freeze_event, load_config, reference)
from tools.pid_physics import Disturbance, capture_decoder, observed_model
from tools import run_pid_flight as runner

REPO = Path(__file__).resolve().parents[1]


class FakeModel:
    """Only an input recorder for the observer test; never a flight oracle."""
    def __init__(self, library):
        self.ticks = 0

    def step(self, commands, steps):
        self.ticks += steps
        output = [0.] * 120
        output[2] = self.ticks*.001
        output[20:36] = commands
        return output

    def close(self):
        pass


class PIDCandidateTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(CONFIG_PATH)

    def test_configuration_rejects_every_non_pid_selection_and_budget_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'trial.json'
            for value in ('ude', 'ne', '', 'native', None):
                config = copy.deepcopy(self.config)
                config['controller'] = value
                path.write_text(json.dumps(config))
                with self.assertRaisesRegex(ValueError, 'frozen protocol'):
                    load_config(path)
            config = copy.deepcopy(self.config)
            config['point']['max_error_m'] = .31
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                load_config(path)
        self.assertEqual(hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(), CONFIG_SHA256)

    def test_native_timestamp_duplicate_skip_reset_and_discontinuities(self):
        state = PIDState((2., 3., 2.9), (0., 0., 0.), (1., 0., 0., 0.))
        target = reference(self.config, 'point', 0)
        loop = PIDLoop(self.config, 'arducopter', .32)
        self.assertIsNone(loop.update(1., state, target, active=True))
        self.assertIsNone(loop.update(1., state, target, active=True))
        row = loop.update(1.04, state, target, active=True)
        self.assertAlmostEqual(row['dt_s'], .04)
        self.assertAlmostEqual(row['output']['integral'][2], .004)
        self.assertEqual(row['controller'], 'pid')
        before = loop.pid.integral
        self.assertIsNone(loop.update(1.04, state, target, active=True))
        self.assertEqual(loop.pid.integral, before)
        for bad in (1.0, 2.0, math.nan):
            loop.reset('test', 1.04)
            with self.assertRaises((ValueError, RuntimeError)):
                loop.update(bad, state, target, active=True)
            self.assertEqual(loop.pid.integral, (0., 0., 0.))
        with self.assertRaisesRegex(RuntimeError, 'authority'):
            loop.update(3., state, target, active=False)

    def test_actual_force_projection_and_per_stack_thrust(self):
        angle = .2
        q = (math.cos(angle/2), math.sin(angle/2), 0., 0.)
        state = PIDState((2., 3., 3.), (0., 0., 0.), q)
        target = reference(self.config, 'point', 0)
        for stack, hover in [('arducopter', .32), ('px4', .53)]:
            loop = PIDLoop(self.config, stack, hover)
            loop.reset('test', 1.)
            row = loop.update(1.04, state, target, active=True)
            self.assertAlmostEqual(row['output']['projected_thrust_n'], 1.515*9.8*math.cos(angle))
            self.assertAlmostEqual(row['normalized_collective'], hover*math.cos(angle))
            self.assertEqual(row['native_thrust_convention'], [0., 0., -row['normalized_collective']]
                             if stack == 'px4' else row['normalized_collective'])

    def test_circle_reference_has_position_velocity_and_acceleration(self):
        first = reference(self.config, 'circle', 0.)
        final = reference(self.config, 'circle', 24.)
        self.assertLess(math.dist(first.position_enu, (2., 3., 3.)), 1e-12)
        self.assertLess(math.dist(final.position_enu, first.position_enu), 1e-12)
        t, delta = 1.3, 1e-4
        left, right = reference(self.config, 'circle', t-delta), reference(self.config, 'circle', t+delta)
        middle = reference(self.config, 'circle', t)
        for i in range(3):
            self.assertAlmostEqual((right.position_enu[i]-left.position_enu[i])/(2*delta), middle.velocity_enu[i], places=7)
            self.assertAlmostEqual((right.velocity_enu[i]-left.velocity_enu[i])/(2*delta), middle.acceleration_enu[i], places=7)

    def test_event_exact_interval_all_four_original_and_applied_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            library = directory/'not-a-native-library'
            library.write_bytes(b'fake input recorder only')
            config = copy.deepcopy(self.config)
            config['model']['library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
            packet = dict(protocol='test', packet_hex='1234')
            model = observed_model(directory/'raw.jsonl', directory, 'unit-run', config,
                                   {'latest': packet}, base_model=FakeModel)(library)
            event = event_for(config, 'unit-run', 0)
            checksum = freeze_event(directory, event)
            original = [.4, .5, .6, .7]+[.1]*12
            for _ in range(751):
                model.step(original, 4)
            model.close()
            rows = [json.loads(s) for s in (directory/'raw.jsonl').read_text().splitlines()]
            steps = rows[1:-1]
            active = [r for r in steps if r['disturbance_active']]
            self.assertEqual(len(active), 1000)
            self.assertEqual((active[0]['interval_tick'], active[-1]['interval_tick']), (2000, 2999))
            self.assertEqual(rows[-1]['disturbance_applied_ticks'], 1000)
            for row in steps:
                self.assertEqual(row['original_decoded_input16'], original)
                expected = [v*.97 if row['disturbance_active'] and i < 4 else v for i, v in enumerate(original)]
                self.assertEqual(row['applied_input16'], expected)
                self.assertEqual(row['output120'][20:36], expected)
                self.assertEqual(row['raw_actuator_packet'], packet)
                self.assertEqual(row['disturbance_event_sha256'], checksum)

    def test_event_wrong_run_late_load_mutation_restart_and_repeated_tick_fail(self):
        for variant in ('wrong_run', 'late', 'changed', 'reset', 'repeated'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                observer = Disturbance(directory, 'run', self.config)
                if variant == 'late':
                    observer.next_tick = 1001
                    freeze_event(directory, event_for(self.config, 'run', 0))
                    with self.assertRaisesRegex(RuntimeError, 'ahead'):
                        observer.apply([0.]*16, 1001)
                    continue
                event = event_for(self.config, 'other' if variant == 'wrong_run' else 'run', 0)
                freeze_event(directory, event)
                if variant == 'wrong_run':
                    with self.assertRaisesRegex(ValueError, 'run/protocol/window'):
                        observer.apply([0.]*16, 0)
                    continue
                observer.apply([0.]*16, 0)
                if variant == 'changed':
                    (directory/'disturbance-event.json').write_text('{}')
                    with self.assertRaisesRegex(RuntimeError, 'changed'):
                        observer.apply([0.]*16, 1)
                elif variant == 'reset':
                    with self.assertRaisesRegex(ValueError, 'empty disturbance'):
                        Disturbance(directory, 'new-run', self.config)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'discontinuity'):
                        observer.apply([0.]*16, 0)

    def test_event_revocation_immediately_stops_and_cannot_reenable(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            observer = Disturbance(directory, 'run', self.config)
            freeze_event(directory, event_for(self.config, 'run', 0))
            for tick in range(2001):
                applied, active = observer.apply([.5]*16, tick)
            self.assertTrue(active)
            (directory/'pid-disturbance-revoked.json').write_text('')
            applied, active = observer.apply([.5]*16, 2001)
            self.assertFalse(active)
            self.assertEqual(applied, [.5]*16)
            (directory/'pid-disturbance-revoked.json').unlink()
            self.assertFalse(observer.apply([.5]*16, 2002)[1])
            self.assertEqual(observer.applied_ticks, 1)

    def test_decoder_observation_retains_actual_ap_bytes_and_decoded_values(self):
        packet = struct.pack('<HHI16H', 18458, 1000, 12, *([1400, 1500, 1600, 1700]+[0]*12))
        module = NS(decode_servos=ap_json.decode_servos)
        context, stream = {}, io.StringIO()
        capture_decoder(module, 'arducopter', context, stream)
        result = module.decode_servos(packet)
        self.assertEqual(result, ap_json.decode_servos(packet))
        row = json.loads(stream.getvalue())
        self.assertEqual(bytes.fromhex(row['packet_hex']), packet)
        self.assertEqual(row['decoded_input16'], [.4, .5, .6, .7]+[0.]*12)
        self.assertEqual(context['latest'], row)

    def test_native_position_helper_is_forbidden_in_measured_stage(self):
        task = object.__new__(PIDTask)
        task.pid_measuring = True
        with self.assertRaisesRegex(RuntimeError, 'forbidden'):
            task.command('native', position=(2., 3., 3.))

    def test_actual_pid_offer_uses_public_attitude_envelope_and_waits_for_ack(self):
        class Message:
            MOVE, XYZ_ATT = 4, 5
            def __init__(self, **values):
                self.header = NS(stamp=None, frame_id='')
                self.__dict__.update(values)

        def convert(value):
            if isinstance(value, (Message, NS)):
                return {k: convert(v) for k, v in vars(value).items()}
            return value

        task = object.__new__(PIDTask)
        task.pid_config, task.flight_stack = self.config, 'arducopter'
        task.pid_loop = PIDLoop(self.config, 'arducopter', .32)
        task.pid_loop.reset('takeover', 1.)
        task.pid_origin, task.pid_kind = 1., 'point'
        task.pid_pending, task.pending_request_id = None, None
        task.pid_updates = task.pid_duplicate_states = 0
        task.command_number, task.request_id = 10, 20
        task.run_id, task.epoch, task.native_generation = 'run', 'a'*32, 7
        task.latest = {'state': NS(header=NS(stamp=NS(sec=1, nanosec=40000000)),
            position=(2., 3., 2.9), velocity=(0., 0., 0.), attitude_q=NS(w=1., x=0., y=0., z=0.))}
        task.Cmd, task.CommandRequest = Message, Message
        task.node = NS(get_clock=lambda: NS(now=lambda: NS(to_msg=lambda: 'wall-stamp')))
        task.convert, task.started = convert, 0.
        task.events, task.sent, task.envelopes = [], [], []
        task.pid_trace, task.log = io.StringIO(), io.StringIO()
        task.authority = lambda: True
        task.read_truth = lambda: {'time': 1.04}
        task.cursor = lambda: {'final_time': 1.04}
        task.record = lambda *args, **kwargs: None
        published = []
        task.command_pub = NS(publish=published.append)
        task.offer_pid()
        self.assertEqual(len(published), 1)
        outgoing = published[0]
        self.assertEqual((outgoing.request_id, outgoing.command.command_id, outgoing.command.move_mode), (21, 11, Message.XYZ_ATT))
        row = json.loads(task.pid_trace.getvalue())
        self.assertEqual(row['public_request_id'], 21)
        self.assertEqual(row['public_command_id'], 11)
        self.assertEqual(row['controller'], 'pid')
        self.assertEqual(outgoing.command.att_ref, [*row['output']['roll_pitch_yaw_enu_rad'], row['normalized_collective']])
        task.offer_pid()
        self.assertEqual(len(published), 1)
        task.events.append(dict(event='command_accepted', request_id=21, command_id=11))
        task.offer_pid()
        self.assertIsNone(task.pid_pending)
        self.assertEqual(len(published), 1)  # Identical source stamp cannot integrate again.
        task.latest['state'].header.stamp.nanosec = 80000000
        task.offer_pid()
        self.assertEqual(len(published), 2)
        self.assertEqual(published[-1].request_id, 22)

    def test_authority_rejects_native_position_flags_and_generation_change(self):
        task = object.__new__(PIDTask)
        task.flight_stack = 'px4'
        task.fresh = lambda: True
        task.epoch, task.native_generation = 'a'*32, 7
        task.pid_identity = (task.epoch, task.native_generation)
        task.latest = {'state': NS(armed=True, mode='OFFBOARD'),
            'control_state': NS(control_state=2, COMMAND_CONTROL=2)}
        from Simulator.wksim_runtime.attitude_task import MODE_TRUE, MODE_FALSE
        flags = dict.fromkeys(MODE_TRUE, True) | dict.fromkeys(MODE_FALSE, False)
        task.control_modes = [dict(physical_time=1., flags=flags)]
        task.read_truth = lambda: {'time': 1.04}
        self.assertTrue(task.authority())
        flags['flag_control_position_enabled'] = True
        self.assertFalse(task.authority())
        flags['flag_control_position_enabled'] = False
        task.native_generation = 8
        self.assertFalse(task.authority())

    def test_online_metrics_fail_an_excursion_and_require_final_return_dwell(self):
        rows = []
        event = event_for(self.config, 'run', 0)
        for tick in range(0, 11001, 20):
            v = [0.]*60
            v[6:9] = [3., 2., -3.]
            v[11] = math.pi/2
            rows.append(dict(time=tick/1000, vehicle=v))
        result = evaluate_rows(self.config, 'disturbance', rows, 0, event)
        self.assertTrue(result['online_ok'])
        rows[-1]['vehicle'][7] = 2.31
        self.assertFalse(evaluate_rows(self.config, 'disturbance', rows, 0, event)['online_ok'])
        rows[-1]['vehicle'][7] = 2.
        rows[50]['vehicle'][7] = 2.51
        self.assertFalse(evaluate_rows(self.config, 'disturbance', rows, 0, event)['online_ok'])

    def test_launch_plan_selects_private_pid_observer_and_attitude_outlet(self):
        for stack in ('px4', 'arducopter'):
            plan = dict(control=['control'], fc=['fc', '--speedup', '3', '--defaults', 'base,dds'], fc_environment={})
            with patch.object(runner, 'launch_spec', return_value=plan):
                actual = runner.launch_plan(dict(stack=stack, run_id='run'), Path('/root/run'), '/library')
            self.assertIn('native_attitude_profile:=attitude_thrust_v1', actual['control'])
            self.assertIn('enable_external_attitude:=true', actual['control'])
            self.assertTrue(any(x.endswith('pid_physics.py') for x in actual['physics']))
            self.assertIn('--config', actual['physics'])
            self.assertIn('--run-id', actual['physics'])

    def test_cli_requires_configuration_without_starting_admission(self):
        result = subprocess.run([sys.executable, '-B', str(REPO/'tools/run_pid_flight.py'),
            '--stack', 'px4', '--run-id', 'unit-run', '--preflight'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--config', result.stderr)


if __name__ == '__main__':
    unittest.main()
