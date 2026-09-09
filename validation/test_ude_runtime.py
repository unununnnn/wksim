"""Finite UDE runtime/audit checks; synthetic evidence is not a flight proof."""
import copy
from dataclasses import asdict
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from Simulator.wksim_control.position_pid import PIDConfig, PIDState, PositionPID, select_controller
from Simulator.wksim_control.position_ude import PositionUDE, UDEConfig
from Simulator.wksim_runtime.pid_task import (CONFIG_PATH, UDE_CONFIG_PATH, PIDLoop, PIDTask,
    event_for, freeze_event, load_config, reference)
from tools import audit_pid_flight as shared, audit_ude_flight as audit, run_pid_flight as runner
from tools.pid_physics import Disturbance, observed_model
from validation.test_pid_flight import FakeModel
from validation.test_pid_flight_audit import physical_fixture, trace_fixture

CONFIG = load_config(UDE_CONFIG_PATH)


def ude_trace_fixture():
    rows, phases, result, data = trace_fixture()
    loop = PIDLoop(CONFIG, 'px4', .5)
    for row in rows:
        kind = row['stage']; origin = phases['pid_'+kind+'_begin']['native_boot_s']
        loop.reset('takeover_'+kind, origin)
        value = loop.update(row['native_state_stamp_s'], PIDState(**row['state']),
                            reference(CONFIG, kind, row['physical_time']-origin), active=True)
        row.update(json.loads(json.dumps(value)), protocol_sha256=audit.PROTOCOL)
        att = [*row['output']['roll_pitch_yaw_enu_rad'], row['normalized_collective']]
        row['public_envelope']['command']['att_ref'] = att
        data['/uav1/prometheus/v2/command'][row['public_request_id']-1][1]['command']['att_ref'] = att
        loop.reset('release_'+kind)
    return rows, phases, result, data


def ude_physics_fixture():
    rows, packets, _, _ = physical_fixture()
    event = event_for(CONFIG, 'fixture', 0)
    raw = (json.dumps(event, sort_keys=True, separators=(',', ':'))+'\n').encode()
    sha = shared.event_check(event, raw, 'fixture', controller='ude')
    rows[0].update(schema='wksim.ude.physics.v1', protocol_sha256=audit.PROTOCOL)
    for row in rows[1:]: row['disturbance_event_sha256'] = sha
    return rows, packets, event, sha


class UDERuntimeTests(unittest.TestCase):
    def test_selection_is_typed_fresh_and_no_fallback(self):
        selected = select_controller('ude', UDEConfig(1.515))
        self.assertIs(type(selected), PositionUDE)
        self.assertIs(type(select_controller('pid', PIDConfig(1.515))), PositionPID)
        for name, config in [('ude', PIDConfig(1.515)), ('pid', UDEConfig(1.515)),
                             ('ne', UDEConfig(1.515)), ('native', UDEConfig(1.515)),
                             ('', UDEConfig(1.515)), (None, UDEConfig(1.515))]:
            with self.subTest(name=name), self.assertRaises(ValueError): select_controller(name, config)
        self.assertEqual(selected.integral, (0., 0., 0.))
        self.assertIsNone(selected.last_output)
        self.assertIsNot(selected, select_controller('ude', UDEConfig(1.515)))

    def test_protocol_and_every_budget_remain_frozen(self):
        self.assertEqual(hashlib.sha256(UDE_CONFIG_PATH.read_bytes()).hexdigest(), audit.PROTOCOL)
        pid = load_config(CONFIG_PATH)
        for key in ('model', 'hover_calibration', 'timing', 'point', 'circle', 'disturbance', 'envelope'):
            self.assertEqual(CONFIG[key], pid[key])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.json'
            for key, value in [('controller', 'pid'), ('controller', 'ne'), ('timing', {'model_dt_s': .002})]:
                changed = copy.deepcopy(CONFIG); changed[key] = value
                path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, 'frozen protocol'): load_config(path)
            path.write_bytes(UDE_CONFIG_PATH.read_bytes()+b' ')
            with self.assertRaises(ValueError): load_config(path)

    def test_history_discontinuity_authority_and_lifecycle_reset(self):
        state = PIDState((1.9, 3., 2.9), (0., 0., 0.), (1., 0., 0., 0.))
        ref = reference(CONFIG, 'point', 0)
        loop = PIDLoop(CONFIG, 'px4', .5)
        self.assertIsNone(loop.update(1., state, ref, active=True))
        first = loop.update(1.02, state, ref, active=True)
        self.assertIsNone(loop.update(1.02, state, ref, active=True))
        self.assertEqual(loop.pid.integral, first['output']['integral'])
        second = loop.update(1.04, state, ref, active=True)
        self.assertNotEqual(first['output']['disturbance_acceleration_enu'], second['output']['disturbance_acceleration_enu'])
        for reason in ('selection', 'takeover', 'release', 'restart'):
            loop.reset(reason, 1.)
            self.assertIsNone(loop.pid.last_output)
            row = loop.update(1.02, state, ref, active=True)
            self.assertEqual(row['output'], first['output'])
            self.assertEqual(row['last_reset']['reason'], reason)
        for stamp in (1., 1.4, 0., float('nan'), float('inf')):
            loop.reset('before_bad_stamp', 1.02)
            with self.assertRaises((ValueError, RuntimeError)): loop.update(stamp, state, ref, active=True)
            self.assertEqual(loop.pid.integral, (0., 0., 0.)); self.assertIsNone(loop.pid.last_output)
        with self.assertRaises(RuntimeError): loop.update(2., state, ref, active=False)
        self.assertEqual(loop.pid.last_reset_reason, 'native_authority_lost')

    def test_two_stack_independent_equations_1200_samples(self):
        for stack, hover in [('px4', .53), ('arducopter', .32)]:
            loop = PIDLoop(CONFIG, stack, hover); loop.reset('takeover', 1.)
            integral = [0.]*3
            for i in range(1, 601):
                state = PIDState((2+.4*math.sin(i/17), 3+.4*math.cos(i/11), 3+.6*math.sin(i/13)),
                    (.1, -.2, .3), tuple(shared.wire.q_from_euler(.1, -.12, .3)))
                ref = reference(CONFIG, 'circle' if i % 5 == 0 else 'point', i*.02)
                row = loop.update(1+i*.02, state, ref, active=True)
                expected, thrust = audit.recompute(CONFIG, asdict(state), asdict(ref), row['dt_s'], integral, hover)
                for key, value in expected.items():
                    self.assertTrue(row['output'][key] == value if key == 'controller' else shared.near(row['output'][key], value))
                self.assertTrue(shared.near(row['normalized_collective'], thrust))
                self.assertEqual(row['native_thrust_convention'], [0., 0., -thrust] if stack == 'px4' else thrust)
                integral = expected['integral']

    def test_observer_uses_old_integral_and_moving_reference_retains_it(self):
        state = dict(position_enu=[1.9, 3., 3.], velocity_enu=[0., 0., 0.], attitude_flu_to_enu=[1., 0., 0., 0.])
        ref = shared.desired(CONFIG, 'point', 0); ref['velocity_enu'] = [.1, 0., 0.]
        out, _ = audit.recompute(CONFIG, state, ref, .02, [.4, 0., 0.], .5)
        self.assertTrue(shared.near(out['integral'], [.402, 0., 0.]))
        self.assertTrue(shared.near(out['disturbance_acceleration_enu'], [-.5, 0., 0.]))
        state['position_enu'][0] = 1.5
        out, _ = audit.recompute(CONFIG, state, ref, .02, [.4, 0., 0.], .5)
        self.assertEqual(out['integral'][0], 0.)
        self.assertEqual(out['disturbance_acceleration_enu'][0], -1.)

    def test_actual_offer_publishes_ude_xyz_att_and_waits(self):
        class Message:
            MOVE, XYZ_ATT = 4, 7
            def __init__(self, **values):
                self.header = NS(stamp=None, frame_id=''); self.__dict__.update(values)
        def convert(value):
            if isinstance(value, (Message, NS)): return {k: convert(v) for k,v in vars(value).items()}
            return value
        task = object.__new__(PIDTask)
        task.pid_config, task.flight_stack = CONFIG, 'px4'
        task.pid_loop = PIDLoop(CONFIG, 'px4', .53); task.pid_loop.reset('takeover_point', 1.)
        task.pid_origin, task.pid_kind = 1., 'point'; task.pid_pending = None
        task.pid_updates = task.pid_duplicate_states = task.command_number = task.request_id = 0
        task.run_id, task.epoch, task.native_generation = 'ude-fixture', 'epoch', 1
        task.latest = {'state': NS(header=NS(stamp=NS(sec=1, nanosec=20000000)), position=(1.9,3.,3.),
            velocity=(0.,0.,0.), attitude_q=NS(w=1.,x=0.,y=0.,z=0.))}
        task.Cmd = task.CommandRequest = Message
        task.node = NS(get_clock=lambda: NS(now=lambda: NS(to_msg=lambda: None)))
        task.convert, task.started = convert, 0.
        task.events, task.sent, task.envelopes, task.native_targets, task.native_samples = [], [], [], [], []
        task.pid_trace, task.log = io.StringIO(), io.StringIO()
        task.authority = lambda: True; task.read_truth = lambda: {'time': 1.02}
        published = []; task.command_pub = NS(publish=published.append)
        task.offer_pid(); task.offer_pid()
        self.assertEqual(len(published), 1)
        row = json.loads(task.pid_trace.getvalue())
        self.assertEqual((row['controller'], row['protocol_sha256']), ('ude', audit.PROTOCOL))
        self.assertEqual(published[0].command.move_mode, 7)
        self.assertEqual(published[0].command.att_ref, [*row['output']['roll_pitch_yaw_enu_rad'],row['normalized_collective']])
        self.assertNotEqual(row['output']['disturbance_acceleration_enu'][0], 0.)
        task.authority = lambda: False
        with self.assertRaises(RuntimeError): task.offer_pid()
        self.assertIsNone(task.pid_loop.pid.last_output)

    def test_actual_ros_message_accepts_frozen_numeric_preparation(self):
        try:
            from prometheus_msgs.msg import UAVCommand
            from rclpy.serialization import serialize_message, deserialize_message
        except ImportError:
            self.skipTest('Requires installed ROS messages/codecs; run in sourced WSL')
        task = object.__new__(PIDTask)
        task.pid_measuring = False; task.command_number = 0; task.Cmd = UAVCommand
        task.read_truth = lambda: {'time': 1.}
        task.mark = lambda *args, **kwargs: None
        task.convert = lambda value: value
        task.native_targets = []
        sent = []
        def send(message, label):
            encoded = serialize_message(message)
            self.assertEqual(deserialize_message(encoded, UAVCommand), message)
            sent.append(message)
            if message.move_mode == message.XYZ_ATT:
                task.native_targets.append(dict(thrust=.5, quaternion_xyzw=[0., 0., 0., 1.], physical_time=1.))
        task.send = send
        task.wait = lambda label, predicate, timeout: self.assertTrue(predicate())
        for config in (CONFIG, load_config(CONFIG_PATH)):
            point, yaw = config['point']['position_enu_m'], config['point']['yaw_rad']
            for kwargs in (dict(position=point, yaw=yaw), dict(position=[float(x) for x in point], yaw=yaw),
                           dict(position=point), dict(attitude=(0., 0., yaw, .5))):
                with self.subTest(controller=config['controller'], kwargs=kwargs):
                    task.command('frozen_numeric_preparation', **kwargs)
                    msg = sent[-1]
                    if 'attitude' in kwargs:
                        self.assertEqual(list(msg.att_ref), [0., 0., 0., .5])
                    else:
                        self.assertEqual(list(msg.position_ref), [2., 3., 3.])
                        self.assertIs(type(msg.yaw_ref), float)
        for invalid in (True, '2', float('nan'), float('inf')):
            with self.subTest(invalid=invalid), self.assertRaises((ValueError, AssertionError)):
                task.command('invalid_numeric', position=(invalid, 3., 3.), yaw=0.)

    def test_ude_event_physics_and_revocation_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); library = root/'fake-model'; library.write_bytes(b'input recorder')
            config = copy.deepcopy(CONFIG); config['model']['library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
            model = observed_model(root/'raw.jsonl', root, 'ude-test', config, {}, base_model=FakeModel)(library)
            freeze_event(root, event_for(config, 'ude-test', 0))
            for _ in range(300): model.step([.5]*4+[0.]*12, 10)
            model.close()
            rows = [json.loads(line) for line in (root/'raw.jsonl').read_text().splitlines()]
            self.assertEqual(rows[0]['schema'], 'wksim.ude.physics.v1')
            self.assertEqual(rows[0]['protocol_sha256'], audit.PROTOCOL)
            self.assertEqual(rows[-1]['disturbance_applied_ticks'], 1000)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); disturbance = Disturbance(root, 'test', CONFIG)
            freeze_event(root, event_for(load_config(CONFIG_PATH), 'test', 0))
            with self.assertRaises(ValueError): disturbance.apply([.5]*16, 0)


class UDEAuditTests(unittest.TestCase):
    def test_trace_independent_ude_and_wrong_controller_rejection(self):
        rows, phases, result, data = ude_trace_fixture()
        matched, counts = shared.trace_audit(CONFIG, rows, phases, result, .5, data, controller='ude')
        self.assertEqual(sum(counts.values()), 3)
        with self.assertRaises(ValueError): shared.trace_audit(CONFIG, rows, phases, result, .5, data)
        for mutate in (lambda r: r.update(controller='pid'), lambda r: r.update(reset_count=1),
                       lambda r: r['last_reset']['integral'].__setitem__(0, .1),
                       lambda r: r['output']['disturbance_acceleration_enu'].__setitem__(0, .1),
                       lambda r: r['output']['integral'].__setitem__(0, .1),
                       lambda r: r.update(protocol_sha256=shared.PROTOCOL)):
            altered = copy.deepcopy(rows); mutate(altered[0])
            with self.assertRaises(ValueError): shared.trace_audit(CONFIG, altered, phases, result, .5, data, controller='ude')

    def test_full_1ms_ude_identity_and_missing_tick_reject(self):
        rows, packets, event, sha = ude_physics_fixture()
        _, _, proof = shared.physics(rows, packets, event, sha, 'fixture', 'arducopter', controller='ude')
        self.assertEqual(proof['applied_ticks'], 1000)
        with self.assertRaises(ValueError): shared.physics(rows, packets, event, sha, 'fixture', 'arducopter')
        for mutate in (lambda r: r.pop(100), lambda r: r.pop(),
                       lambda r: r[2001]['applied_input16'].__setitem__(0, .5),
                       lambda r: r[0].update(protocol_sha256=shared.PROTOCOL)):
            altered = copy.deepcopy(rows); mutate(altered)
            with self.assertRaises(ValueError): shared.physics(altered, packets, event, sha, 'fixture', 'arducopter', controller='ude')

    def test_ude_native_px4_association_and_position_override(self):
        from Simulator.wksim_runtime.attitude_task import MODE_TRUE, MODE_FALSE
        rows, phases, result, data = ude_trace_fixture()
        matched, _ = shared.trace_audit(CONFIG, rows, phases, result, .5, data, controller='ude')
        targets = []; logged = []; modes = []; offboard = []; motors = []
        for row, raw, public in matched:
            t = round((row['native_state_stamp_s']+.01)*1e6)
            r,p,y,u = public['command']['att_ref']; q = shared.wire.native_q(shared.wire.q_from_euler(r,p,y))
            targets.append((dict(monotonic=raw['monotonic']+.01), dict(timestamp=t, q_d=q, thrust_body=[0.,0.,-u])))
            logged.append(dict(timestamp=t, q_d=q, **{'thrust_body[2]': -u}))
            modes.append(({}, dict(timestamp=t-1, **dict.fromkeys(MODE_TRUE,True), **dict.fromkeys(MODE_FALSE,False))))
            offboard.append(({},dict(timestamp=t,attitude=True,position=False,velocity=False,acceleration=False,
                                    body_rate=False,thrust_and_torque=False,direct_actuator=False)))
            motors.append(dict(timestamp=t,output=[1500]*4))
        data['/in/vehicle_attitude_setpoint'] = targets
        data['/in/offboard_control_mode'] = offboard
        data['/out/vehicle_control_mode'] = modes
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'synthetic.ulg').touch()
            with patch.object(shared.wire, 'ulog', return_value=(dict(vehicle_attitude_setpoint=logged,
                    actuator_outputs=motors), dict(dropout_durations_ms=[]))):
                report = shared.native_audit(root,result,data,matched,phases,[],[[.5]*4+[0.]*12]*72000)
                self.assertEqual(len(report['request_associations']), 3)
                modes[0][1]['flag_control_position_enabled'] = True
                with self.assertRaisesRegex(ValueError, 'loop override'):
                    shared.native_audit(root,result,data,matched,phases,[],[[.5]*4+[0.]*12]*72000)

    def test_preflight_selects_ude_without_launching(self):
        import sys
        fake = NS(admit=lambda stack, run_id: dict(ok=False, config=dict(stack=stack,run_id=run_id)))
        argv = ['run_pid_flight.py','--stack','px4','--run-id','ude-offline-preflight',
                '--config',str(UDE_CONFIG_PATH),'--preflight']
        with patch.dict(sys.modules, {'attitude_candidate': fake}), patch.object(sys,'argv',argv), \
             patch.object(runner,'run',side_effect=AssertionError('No flight')), patch('sys.stdout',new_callable=io.StringIO) as output:
            self.assertEqual(runner.main(), 2)
            admitted = json.loads(output.getvalue())
        self.assertEqual(admitted['external_ude']['protocol_sha256'], audit.PROTOCOL)
        self.assertEqual(admitted['external_ude']['implementation'], 'Simulator.wksim_control.position_ude.PositionUDE')
        self.assertNotIn('external_pid', admitted)

    def test_exact_end_recovery_requires_source_order_request_ack_and_target(self):
        # Frozen shape of real PX4 run02: native timestamp37.78 equals the
        # sparse physical end, while all recovery publications follow end.
        end = dict(physical_cursor=dict(final_time=37.78), observed_monotonic_s=165.989128546,
                   observed_unix_ns=1788966097446077056, final_request_id=176)
        command = dict(agent_cmd=4,move_mode=0,command_id=174,position_ref=[2.,3.,3.],yaw_ref=0.,yaw_rate_mode=False)
        phases = dict(pid_point_end=end,
            native_point_recovery_offered=dict(observed_monotonic_s=165.995378224,command_id=174,payload=command.copy()),
            native_point_recovery_accepted=dict(observed_monotonic_s=166.001352548))
        result = dict(run_id='fixture',task=dict(control_epoch='epoch'))
        request = dict(run_id='fixture',control_epoch='epoch',request_id=177,command=command)
        request_raw = dict(monotonic=166.000830148,source_timestamp=1788966097457176980)
        raw = dict(monotonic=166.011895230,source_timestamp=1788966097462272575,
                   received_timestamp=1788966097462307771)
        target = dict(timestamp=37780000,position=[3.,2.,-3.],velocity=[math.nan]*3,
            acceleration=[math.nan]*3,jerk=[math.nan]*3,yaw=math.pi/2,yawspeed=math.nan)
        event = dict(event='command_accepted',run_id='fixture',control_epoch='epoch',request_id=177,command_id=174)
        mode = dict(timestamp=37780000,position=True,velocity=False,acceleration=False,attitude=False,
                    body_rate=False,thrust_and_torque=False,direct_actuator=False)
        data = {'/uav1/prometheus/v2/command':[(request_raw,request)],
                '/uav1/prometheus/text_info':[(dict(monotonic=166.001),dict(message=json.dumps(event)))],
                '/in/offboard_control_mode':[(dict(monotonic=166.011836646,source_timestamp=1788966097462175340),mode)]}
        proof = shared.recovery_boundary(raw,target,'point',phases,result,data)
        self.assertEqual((proof['request_id'],proof['command_id']), (177,174))
        cases = {
            'inside_source_window': lambda r,t,p,d: t.update(timestamp=37779999),
            'received_during_stage': lambda r,t,p,d: r.update(monotonic=165.98),
            'delayed_old_publication': lambda r,t,p,d: r.update(source_timestamp=end['observed_unix_ns']),
            'missing_request': lambda r,t,p,d: d['/uav1/prometheus/v2/command'].clear(),
            'wrong_request_id': lambda r,t,p,d: d['/uav1/prometheus/v2/command'][0][1].update(request_id=176),
            'wrong_command_id': lambda r,t,p,d: d['/uav1/prometheus/v2/command'][0][1]['command'].update(command_id=175),
            'wrong_epoch': lambda r,t,p,d: d['/uav1/prometheus/v2/command'][0][1].update(control_epoch='other'),
            'missing_raw_ack': lambda r,t,p,d: d['/uav1/prometheus/text_info'].clear(),
            'wrong_position': lambda r,t,p,d: t['position'].__setitem__(0,3.1),
            'active_velocity': lambda r,t,p,d: t['velocity'].__setitem__(0,0.),
            'missing_mode': lambda r,t,p,d: d['/in/offboard_control_mode'].clear(),
            'wrong_mode_axis': lambda r,t,p,d: d['/in/offboard_control_mode'][0][1].update(attitude=True),
            'missing_recovery_phase': lambda r,t,p,d: p.pop('native_point_recovery_offered')}
        for name, change in cases.items():
            r,t,p,d = copy.deepcopy((raw,target,phases,data)); change(r,t,p,d)
            with self.subTest(case=name), self.assertRaises(ValueError):
                shared.recovery_boundary(r,t,'point',p,result,d)

    def test_event_and_audit_fail_closed(self):
        event = event_for(CONFIG, 'test', 0)
        raw = (json.dumps(event, sort_keys=True, separators=(',', ':'))+'\n').encode()
        self.assertEqual(shared.event_check(event, raw, 'test', controller='ude'), hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError): shared.event_check(event, raw, 'test')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'result.json').write_text(json.dumps(dict(status='observed', run_id='test', stack='px4', controller='ude')))
            result = audit.audit(root)
            self.assertEqual((result['status'], result['schema'], result['protocol_sha256']),
                             ('rejected', 'wksim.ude.audit.v1', audit.PROTOCOL))
            self.assertIn('shared_auditor_sha256', result)
        protocol, implementation, _ = shared.audit_profile('ne')
        self.assertEqual((protocol, implementation),
                         ('3b09761ad60976aa971f43e81edc0de9bb4ede7065a10b5d512c57c22a478e18',
                          'Simulator.wksim_control.position_ne.PositionNE'))


if __name__ == '__main__': unittest.main()
