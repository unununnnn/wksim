"""Offline native parameter guard: AP4.7 names, unavailable and disabled checks."""
from pathlib import Path
import sys
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Simulator.wksim_runtime.hex_task import HexTask
from tools.hex_candidate import native_parameters


class AP47Parameters(unittest.TestCase):
    def check(self, response, expected=None):
        task = object.__new__(HexTask)
        task.flight_stack = 'arducopter'
        task.epoch, task.native_generation, task.peer = 'offline', 4, ('127.0.0.1', 1)
        task.budget = dict(parameter_total_timeout_s=dict(arducopter=45), parameter_read_timeout_s=10)
        task.parameters = expected if expected is not None else {'ARMING_SKIPCHK':native_parameters('arducopter')['ARMING_SKIPCHK']}
        task.hex_result = dict(parameter_readback={})
        task.ground_current = task.public_graph_ready = lambda: True
        task.record = lambda *args, **kwargs: None
        task.convert = lambda value: {}
        task.mark = lambda label: None
        task.wait = lambda label, predicate, *args: self.assertTrue(predicate(), label)
        requested = []
        def call(request):
            requested.extend(request.names)
            value = response(request.names[0]) if callable(response) else response
            return N(done=lambda:True, result=lambda:N(values=[N(**value)]))
        client = N(service_is_ready=lambda:True, call_async=call)
        task.node = N(create_client=lambda *args:client, destroy_client=lambda value:None)
        modules = {'rcl_interfaces':N(), 'rcl_interfaces.srv':N(GetParameters=N(Request=lambda **k:N(**k))),
                   'rclpy':N(), 'rclpy.serialization':N(serialize_message=lambda value:b'offline')}
        with patch.dict(sys.modules,modules):
            task.ground_parameters()
        return requested, task.hex_result['parameter_readback']

    def test_requests_no_checks_skipped(self):
        names, values = self.check(dict(type=2,integer_value=0,double_value=0.))
        self.assertEqual(names, ['ARMING_SKIPCHK'])
        self.assertEqual(values, {'ARMING_SKIPCHK':0})

    def test_retained_unavailable_response_never_uses_stale_numeric_storage(self):
        # Actual failing DDS response has NOT_SET with integer_value=1000 left over.
        with self.assertRaisesRegex(RuntimeError, 'Native parameter unavailable: ARMING_CHECK'):
            self.check(dict(type=0,integer_value=1000,double_value=0.), {'ARMING_CHECK':1})
        with self.assertRaisesRegex(RuntimeError, 'Native parameter unavailable: ARMING_SKIPCHK'):
            self.check(dict(type=0,integer_value=1000,double_value=0.))

    def test_any_skipped_checks_are_rejected(self):
        for value in (-1, 1, 2, 1024):
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, 'Native AP parameter differs'):
                self.check(dict(type=2,integer_value=value,double_value=0.))

    def test_all_33_source_supported_names_are_requested(self):
        # Full native PARM census of the retained AP47 run supports these names.
        available = {'FRAME_CLASS','FRAME_TYPE','MOT_PWM_MIN','MOT_PWM_MAX','MOT_BAT_VOLT_MIN',
            'MOT_BAT_VOLT_MAX','SIM_RATE_HZ','ARMING_SKIPCHK','MAV1_POSITION','MAV1_EXTRA1',
            'MAV1_EXTRA3','DDS_ENABLE','DDS_UDP_PORT','DDS_DOMAIN_ID','LOG_DISARMED'}
        available |= {f'SERVO{i}_{field}' for i in range(1,7) for field in ('FUNCTION','MIN','MAX')}
        parameters = native_parameters('arducopter')
        def response(name):
            return dict(type=2 if name in available else 0,integer_value=parameters[name],double_value=0.)
        requested, values = self.check(response, parameters)
        self.assertEqual(set(requested),available)
        self.assertEqual(len(requested),33)
        self.assertEqual(values,parameters)

    def test_renamed_streams_must_be_available_and_match_rate(self):
        for name, rate in [('MAV1_POSITION',10),('MAV1_EXTRA1',10),('MAV1_EXTRA3',5)]:
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError,'Native parameter unavailable'):
                self.check(dict(type=0,integer_value=rate,double_value=0.),{name:rate})
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError,'Native AP parameter differs'):
                self.check(dict(type=2,integer_value=0,double_value=0.),{name:rate})


if __name__ == '__main__':
    unittest.main()
