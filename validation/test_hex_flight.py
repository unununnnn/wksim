"""Pure Hex launch, decoder, admission-boundary and cold-reset fixtures; no native loads."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools.hex_candidate import native_parameters, admit, plan_identity, PLAN_IDENTITY, AP47_PLAN_IDENTITY
from tools.hex_launch_plan import launch_plan as parameter_plan
from tools.run_hex_flight import launch_plan, prior_result, initial_model
from Simulator.wksim_runtime.hex_task import parameter_value, wire_payload, HexTask, PROTOCOL, PROTOCOL_SHA256, protocol_for


def config(stack):
    return dict(stack=stack, model_profile='hex_x', run_id='hex-fixture', dds_workspace='/dds', px4_root='/px4',
                ap_candidate='/ap', control_protocol='session_v1', hex_config='/hex/config.json')


def parameter(value, kind):
    raw = struct.pack('<i' if kind == 'INT32' else '<f', value)+b'\0'*21
    return dict(message=dict(param_type=6 if kind == 'INT32' else 9), payload_hex=raw.hex())


class HexFlightTests(unittest.TestCase):
    def test_ap47_contract_keeps_native_checks_and_px4_identity(self):
        legacy = parameter_plan()
        self.assertEqual(legacy, parameter_plan('px4'))
        self.assertEqual(legacy['plan_identity'], PLAN_IDENTITY)
        current = parameter_plan('arducopter')
        self.assertEqual(current['plan_identity'], AP47_PLAN_IDENTITY)
        self.assertEqual(native_parameters('arducopter')['ARMING_SKIPCHK'], 0)
        self.assertNotIn('ARMING_CHECK', native_parameters('arducopter'))
        self.assertEqual({k:v for k,v in native_parameters('arducopter').items() if k.startswith('MAV1_')},
                         {'MAV1_POSITION':10,'MAV1_EXTRA1':10,'MAV1_EXTRA3':5})
        self.assertFalse(any(k.startswith('SR0_') for k in native_parameters('arducopter')))
        self.assertEqual(current['px4_parameters'], legacy['px4_parameters'])
        self.assertEqual(current['px4_environment'], legacy['px4_environment'])
        ap_path, ap_sha = protocol_for('arducopter')
        self.assertEqual(hashlib.sha256(ap_path.read_bytes()).hexdigest(), ap_sha)
        ap_budget, px4_budget = json.loads(ap_path.read_text()), json.loads(PROTOCOL.read_text())
        self.assertEqual({k:v for k,v in ap_budget.items() if k not in ('schema','plan_identity')},
                         {k:v for k,v in px4_budget.items() if k not in ('schema','plan_identity')})
        self.assertEqual(ap_budget['plan_identity'], plan_identity('arducopter'))
        self.assertEqual(protocol_for('px4'), (PROTOCOL, PROTOCOL_SHA256))
    @unittest.skipUnless(sys.platform == 'linux', 'Exact generated native dialect is sealed in WSL')
    def test_actual_mavlink2_parameter_payload_excludes_header(self):
        from Simulator.wksim_runtime.telemetry_dialect import load_dialect
        dialect, _ = load_dialect('px4')
        encoder = dialect.MAVLink(None, srcSystem=22, srcComponent=1)
        original = dialect.MAVLink_param_value_message(b'MAV_TYPE',
            struct.unpack('<f', struct.pack('<i', 13))[0], 6, 883, 533)
        for mavlink1 in (False, True):
            raw = original.pack(encoder, force_mavlink1=mavlink1)
            decoded = dialect.MAVLink(None).parse_buffer(raw)[0]
            payload = wire_payload(decoded)
            self.assertEqual(len(payload), 25)
            self.assertEqual(parameter_value(dict(message=decoded.to_dict(),payload_hex=payload.hex()),'INT32',13),13)
            with self.assertRaises(ValueError):
                wire_payload(NS(get_msgbuf=lambda:raw[:-1]))

    def test_ap_defaults_replace_quad_keep_dds_last(self):
        plan = launch_plan(config('arducopter'), Path('/run'), Path('/hex/lib.so'))
        files = plan['fc'][plan['fc'].index('--defaults')+1].split(',')
        self.assertEqual(files, list(map(str, [Path('/ap/src/Tools/autotest/default_params/copter.parm'),
                                               Path('/run/hex.parm'), Path('/run/dds.parm')])))
        self.assertEqual(plan['fc'][plan['fc'].index('--speedup')+1], '1')
        self.assertNotIn('native_attitude_profile:=attitude_thrust_v1', plan['control'])

    def test_px4_exact_six_channel_and_no_unsupported_quad_override(self):
        plan = launch_plan(config('px4'), Path('/run'), Path('/hex/lib.so'))
        env = plan['fc_environment']
        self.assertEqual(env['PX4_SYS_AUTOSTART'], '10016')
        self.assertNotIn('PX4_PARAM_SIM_GZ_EN', env)
        self.assertEqual(env['PX4_PARAM_CA_ROTOR_COUNT'], '6')
        for n in range(1, 17):
            self.assertEqual(env['PX4_PARAM_PWM_MAIN_FUNC'+str(n)], str(100+n if n <= 6 else 0))
        self.assertEqual({k[10:]:v for k,v in env.items() if k.startswith('PX4_PARAM_')},
                         {k:str(v) for k,v in native_parameters('px4').items()})

    def test_quad_profile_rejected_before_launch(self):
        value = config('px4')
        value['model_profile'] = 'quad_x'
        with self.assertRaises(ValueError):
            launch_plan(value, Path('/run'), Path('/hex/lib.so'))

    def test_int32_bytewise_zero_positive_and_nan_bit_pattern(self):
        for value in (0, 6, 10016, -1, 2143289344):
            self.assertEqual(parameter_value(parameter(value, 'INT32'), 'INT32', value), value)

    def test_float32_storage_rounding_and_bad_wire_type(self):
        value = -.016555621653777514
        self.assertEqual(parameter_value(parameter(value, 'FLOAT'), 'FLOAT', value),
                         struct.unpack('<f', struct.pack('<f', value))[0])
        with self.assertRaises(ValueError):
            parameter_value(parameter(6, 'INT32'), 'FLOAT', 6)
        with self.assertRaises(ValueError):
            parameter_value(parameter(6, 'INT32'), 'INT32', 4)
        with self.assertRaises(ValueError):
            parameter_value(parameter(float('nan'), 'FLOAT'), 'FLOAT', 1)

    def test_frozen_protocol(self):
        self.assertEqual(hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(), PROTOCOL_SHA256)
        self.assertEqual(json.loads(PROTOCOL.read_text())['waypoint_enu_m'], [2, 3, 3])

    def test_parameter_failure_prevents_all_public_motion(self):
        task = HexTask.__new__(HexTask)
        task.budget = json.loads(PROTOCOL.read_text())
        task.hex_result = {}
        def reject():
            raise RuntimeError('bad native Hex geometry')
        task.ground_parameters = reject
        with patch.object(task, 'send') as send:
            with self.assertRaisesRegex(RuntimeError, 'bad native'):
                task.execute()
            send.assert_not_called()

    def test_qualified_public_graph_requires_two_distinct_known_endpoints(self):
        task = HexTask.__new__(HexTask)
        task.hex_result = {}
        task.recorder_node = NS(get_name=lambda: 'wksim_hex_raw_recorder')
        task.setup_pub = task.command_pub = NS(get_subscription_count=lambda: 2)
        endpoints = [NS(node_name=n, node_namespace='/', endpoint_gid=bytes([i])*16)
                     for i,n in enumerate(('prometheus_native_control', 'wksim_hex_raw_recorder'), 1)]
        task.node = NS(get_subscriptions_info_by_topic=lambda name: endpoints)
        self.assertTrue(task.public_graph_ready())
        endpoints[1].node_name = 'unrelated_observer'
        self.assertFalse(task.public_graph_ready())

    def test_initial_model_must_start_at_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'raw.jsonl'
            path.write_text('{"kind":"start","dt_s":0.001}\n{"kind":"initialized","initial_tick":0}\n')
            self.assertEqual(initial_model(path)['initial_tick'], 0)
            path.write_text(path.read_text().replace('"initial_tick":0', '"initial_tick":1'))
            with self.assertRaises(ValueError):
                initial_model(path)

    def test_cold_reset_refuses_live_prior_identity_and_keeps_original(self):
        admission = dict(configuration_identity='same', config=dict(run_id='new', stack='px4'))
        child = dict(pid=1234, returncode=0, identity=dict(boot_id='old-boot', starttime_ticks=100))
        previous = dict(model_profile='hex_x', status='observed', safe_landing=True, children_reaped=True,
            cleanup_errors=[], processes_absent_after_stop=True, admission=dict(configuration_identity='same'),
            run_id='old', children=dict(fc=child), task=dict(control_epoch='epoch-old'),
            protocol_sha256=PROTOCOL_SHA256, supervisor=dict(pid=999, boot_id='old-boot', starttime_ticks=99))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'result.json'
            path.write_text(json.dumps(previous))
            before = path.read_bytes()
            with patch('tools.run_hex_flight.process_identity', return_value=child['identity']):
                with self.assertRaisesRegex(ValueError, 'still alive'):
                    prior_result(path, admission)
            with patch('tools.run_hex_flight.process_identity', side_effect=FileNotFoundError):
                result = prior_result(path, admission)
                self.assertEqual(result['control_epoch'], 'epoch-old')
            self.assertEqual(path.read_bytes(), before)

    def test_bad_run_id_rejected_without_fixed_resource_probe(self):
        with patch('tools.hex_candidate.fixed_probe') as probe:
            self.assertFalse(admit('px4', '../wrong')['ok'])
            probe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
