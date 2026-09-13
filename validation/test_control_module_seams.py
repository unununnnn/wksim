"""Exercise real controller selection with the other algorithms unavailable."""
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
import unittest

from Simulator.wksim_control.position_contract import PositionState, PositionReference
from Simulator.wksim_control.controllers import controller_config, select_controller


class ControlModuleSeamTests(unittest.TestCase):
    def test_real_adapters_use_the_same_state_and_reference(self):
        # Common cold origin; NE binds its observer to that initial position.
        state = PositionState((0., 0., 0.), (0., 0., 0.), (1., 0., 0., 0.))
        reference = PositionReference((0., 0., 0.))
        for name in ('pid', 'ude', 'ne'):
            with self.subTest(controller=name):
                controller = select_controller(name, controller_config(name, 1.515, {}))
                output = controller.update(state, reference, dt_s=.02, external_control_active=True)
                self.assertEqual(output.controller, name)
                self.assertEqual(output.mass_kg, 1.515)
                self.assertAlmostEqual(output.projected_thrust_n, 1.515 * 9.8)

    def test_selected_algorithm_imports_without_any_peer_implementation(self):
        script = '''
import importlib.abc
import sys
selected = sys.argv[1]
class BlockPeers(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname.endswith('.position_' + name) for name in ('pid', 'ude', 'ne') if name != selected):
            raise AssertionError('unselected algorithm imported: ' + fullname)
sys.meta_path.insert(0, BlockPeers())
from Simulator.wksim_control.controllers import controller_config, select_controller
from Simulator.wksim_control.position_contract import PositionState, PositionReference
from Simulator.wksim_control.native_thrust import NativeThrustConfig
controller = select_controller(selected, controller_config(selected, 1.515, {}))
state = PositionState((0., 0., 0.), (0., 0., 0.), (1., 0., 0., 0.))
output = controller.update(state, PositionReference((0., 0., 0.)), dt_s=.02, external_control_active=True)
assert abs(NativeThrustConfig('px4', 'test-model', 1.515, .5).normalized_collective(output, model_identity='test-model') - .5) < 1e-10
'''
        for name in ('pid', 'ude', 'ne'):
            with self.subTest(controller=name):
                result = subprocess.run([sys.executable, '-c', script, name],
                    cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_existing_imports_preserve_type_identity_and_serialized_fields(self):
        from Simulator.wksim_control import PIDState, PIDReference, PIDConfig, PositionPID
        from Simulator.wksim_control.position_pid import PIDState as LegacyState
        self.assertIs(PIDState, PositionState)
        self.assertIs(PIDReference, PositionReference)
        self.assertIs(LegacyState, PositionState)
        self.assertIsInstance(select_controller('pid', PIDConfig(1.515)), PositionPID)
        self.assertEqual(asdict(PIDReference((1., 2., 3.))), dict(
            position_enu=(1., 2., 3.), velocity_enu=(0., 0., 0.),
            acceleration_enu=(0., 0., 0.), yaw_enu_rad=0.))

    def test_unknown_controller_and_mismatched_config_still_reject(self):
        with self.assertRaises(ValueError):
            controller_config('unknown', 1.515, {})
        with self.assertRaises(ValueError):
            select_controller('ude', controller_config('pid', 1.515, {}))
