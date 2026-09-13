"""Offline NE runtime/independent-equation checks; no native process launch."""

from dataclasses import asdict
import hashlib
import math
import unittest

from Simulator.wksim_control.position_ne import NEConfig, PositionNE
from Simulator.wksim_control.position_pid import PIDConfig, PIDReference, PIDState, select_controller
from Simulator.wksim_runtime.pid_task import NE_CONFIG_PATH, PIDLoop, load_config, reference
from tools import audit_ne_flight as audit


CONFIG = load_config(NE_CONFIG_PATH)


class NERuntimeTests(unittest.TestCase):
    def test_frozen_config_and_explicit_selector(self):
        self.assertEqual(hashlib.sha256(NE_CONFIG_PATH.read_bytes()).hexdigest(), audit.PROTOCOL)
        selected = select_controller('ne', NEConfig(1.515))
        self.assertIsInstance(selected, PositionNE)
        with self.assertRaises(ValueError): select_controller('ne', object())
        with self.assertRaises(ValueError): select_controller('ne', PIDConfig(1.515))

    def test_pid_loop_binds_initial_position_and_recomputes_independently(self):
        loop = PIDLoop(CONFIG, 'px4', .5, initial_position=(2., 3., 3.))
        loop.reset('takeover_point', 1., initial_position=(2., 3., 3.))
        state = PIDState((2.01, 3., 3.), (.02, -.01, .03), (1., 0., 0., 0.))
        ref = reference(CONFIG, 'point', 0.)
        actual = loop.update(1.02, state, ref, active=True)
        memory = dict(integral=[0., 0., 0.], velocity_integral=[0., 0., 0.], lpf=[0., 0., 0.],
                      hpf=[0., 0., 0.], hpf_input=[0., 0., 0.], llf=[0., 0., 0.],
                      llf_input=[0., 0., 0.], initial_position_enu=[2., 3., 3.])
        expected, collective = audit.recompute(CONFIG, asdict(state), asdict(ref), .02, memory, .5)
        self.assertTrue(all(audit.near(actual['output'][key], value) for key, value in expected.items()
                            if key not in ('controller', '_initial_position_enu')))
        self.assertTrue(audit.near(actual['normalized_collective'], collective))
        self.assertEqual(actual['last_reset']['initial_position_enu'], [2., 3., 3.])

    def test_ne_memory_reset_is_cold_and_invalid_cycles_do_not_publish(self):
        controller = PositionNE(NEConfig(1.515))
        state = PIDState((1., 2., 3.), (0., 0., 0.), (1., 0., 0., 0.))
        ref = PIDReference((2., 2., 3.))
        first = controller.update(state, ref, dt_s=.02, external_control_active=True)
        self.assertNotEqual(first.memory.integral, (0., 0., 0.))
        controller.reset('release', initial_position_enu=(9., 8., 7.))
        self.assertEqual(controller.memory.integral, (0., 0., 0.))
        self.assertEqual(controller.initial_position_enu, (9., 8., 7.))
        with self.assertRaises(ValueError):
            controller.update(state, ref, dt_s=0., external_control_active=True)
        self.assertEqual(controller.memory.integral, (0., 0., 0.))

    def test_ne_loop_handles_duplicate_native_state_without_update(self):
        loop = PIDLoop(CONFIG, 'arducopter', .5, initial_position=(2., 3., 3.))
        state = PIDState((2., 3., 3.), (0., 0., 0.), (1., 0., 0., 0.))
        ref = reference(CONFIG, 'point', 0.)
        self.assertIsNone(loop.update(2., state, ref, active=True))
        self.assertIsNone(loop.update(2., state, ref, active=True))
        with self.assertRaises(RuntimeError): loop.update(1.7, state, ref, active=True)
        self.assertEqual(loop.pid.memory.integral, (0., 0., 0.))


if __name__ == '__main__': unittest.main()
