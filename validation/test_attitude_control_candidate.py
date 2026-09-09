"""Installed #34 adapters and generated ROS codecs; recording transports, no ROS nodes."""
import ast
from copy import deepcopy
from dataclasses import replace
import importlib
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]


def candidate_suite(root):
    import prometheus_control
    from ardupilot_msgs.msg import GlobalPosition, WksimAttitudeTarget
    from prometheus_msgs.msg import UAVCommand as Cmd, UAVControlState as Control
    from prometheus_control.command import CommandProcessor
    from prometheus_control.frames import command_quaternion
    from prometheus_control.shaping import Setpoint, SetpointShaper
    from prometheus_control.native_arducopter import ArduCopterLink
    from prometheus_control.native_px4 import PX4Link
    from rclpy.serialization import serialize_message, deserialize_message
    from validation import test_prometheus_native as fixtures

    manifest = json.loads((root/'attitude-control-build.json').read_text())
    imports = {name: str(Path(importlib.import_module(name).__file__).resolve())
               for name in ('prometheus_control', 'ardupilot_msgs', 'px4_msgs', 'prometheus_msgs', 'wksim_msgs')}
    assert Path(imports['ardupilot_msgs']).is_relative_to(Path(manifest['messages_root'])/'install')
    expected = root/'install/prometheus_control/local/lib/python3.10/dist-packages/prometheus_control'
    assert Path(prometheus_control.__file__).resolve().parent == expected
    for name in ('command', 'frames', 'native_arducopter', 'native_px4', 'node', 'scene', 'session', 'shaping'):
        module = importlib.import_module('prometheus_control.'+name)
        assert Path(module.__file__).resolve().parent == expected

    class AttitudeTests(fixtures.NativeTests):
        def enabled(self, stack):
            if stack == 'ap':
                result = ArduCopterLink(fixtures.RecordingNode(), attitude_profile='attitude_thrust_v1',
                    clock=lambda: self.now)
                for key, value in self.ap.latest.items():
                    result.receive(key, deepcopy(value))
            else:
                result = PX4Link(fixtures.RecordingNode(), '', 22, attitude_profile='attitude_thrust_v1',
                    clock=lambda: self.now)
                for key, value in self.px.latest.items():
                    result.receive(key, deepcopy(value))
            return result

        def outputs(self, obj):
            publishers = list(obj.publishers.values()) if isinstance(obj, PX4Link) else [
                obj.position_pub, obj.velocity_pub] + ([obj.attitude_pub] if obj.attitude_pub else [])
            return [deepcopy(pub.messages) for pub in publishers]

        def test_default_closed_and_two_independent_optins(self):
            target = Setpoint('attitude', quaternion_xyzw=(0., 0., 0., 1.), thrust=.5)
            command = Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XYZ_ATT, command_id=1,
                          att_ref=[0., 0., 0., .5])
            self.assertIsNone(self.ap.attitude_pub)
            for obj in (self.ap, self.px):
                self.assertIsNotNone(obj.supports(command))
                with self.assertRaises(ValueError):
                    obj.send(target)
                self.assertTrue(all(not output for output in self.outputs(obj)))
            for cls, args in ((ArduCopterLink, ()), (PX4Link, ('', 22))):
                for invalid in (None, True, 'ATTITUDE_THRUST_V1', 'attitude_thrust'):
                    with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                        cls(fixtures.RecordingNode(), *args, attitude_profile=invalid)
            for stack in ('ap', 'px'):
                obj = self.enabled(stack)
                self.assertIsNone(obj.supports(command))
                for enabled in (False, True):
                    processor = CommandProcessor(enable_external_control=enabled)
                    processor.update_state(obj.state(1 if stack == 'ap' else 22))
                    self.assertTrue(processor.enter_control(Control.COMMAND_CONTROL).accepted)
                    accepted = processor.accept(command)
                    self.assertEqual(accepted.accepted, enabled)
                    if enabled:
                        obj.send(SetpointShaper().shape(processor.step(), processor.local_position()))

        def test_invalid_inputs_are_atomic_and_norm_boundary_is_strict(self):
            good = Setpoint('attitude', quaternion_xyzw=(0., 0., 0., 1.), thrust=.5)
            bad = [dict(quaternion_xyzw=q) for q in (None, (), (0., 0., 1.), (0.,)*4,
                    (0., 0., 0., 2.), (1e300, 0., 0., 1.))]
            for value in (math.nan, math.inf, -math.inf, 10**400):
                bad.append(dict(thrust=value))
                for axis in range(4):
                    q = list(good.quaternion_xyzw)
                    q[axis] = value
                    bad.append(dict(quaternion_xyzw=tuple(q)))
            bad += [dict(thrust=value) for value in (None, -.001, 1.001, -math.ulp(0.),
                                                         math.nextafter(1., math.inf))]
            # Adjacent representable inputs on either side of both squared-norm limits.
            boundary = [(0., 0., 0., math.nextafter(math.sqrt(squared), direction))
                        for squared in (.999, 1.001) for direction in (0., math.inf)]
            for q in boundary:
                if abs(q[3]*q[3]-1.) >= 1e-3:
                    bad.append(dict(quaternion_xyzw=q))
                else:
                    self.assertAlmostEqual(command_quaternion((q[3], 0., 0., 0.))[0], 1.)
            for stack in ('ap', 'px'):
                obj = self.enabled(stack)
                obj.send(good)
                before = self.outputs(obj)
                for change in bad:
                    with self.subTest(stack=stack, change=change), self.assertRaises(ValueError):
                        obj.send(replace(good, **change))
                    self.assertEqual(self.outputs(obj), before)

        def test_readiness_rejects_without_any_publication(self):
            target = Setpoint('attitude', quaternion_xyzw=(0., 0., 0., 1.), thrust=.5)
            for stack in ('ap', 'px'):
                for condition in ('subscriber', 'stale', 'clock') + (('odom', 'status') if stack == 'ap' else ()):
                    obj = self.enabled(stack)
                    pub = obj.attitude_pub if stack == 'ap' else obj.publishers['attitude']
                    if condition == 'stale':
                        obj.received['local' if stack == 'ap' else 'position'] -= 2.01
                    elif condition == 'clock':
                        obj.clock_invalid = True
                    elif condition == 'odom':
                        obj.latest['local'].home_valid = False
                    elif condition == 'status':
                        obj.latest.pop('status')
                    with patch.object(pub, 'get_subscription_count', return_value=0 if condition == 'subscriber' else 1):
                        with self.subTest(stack=stack, condition=condition), self.assertRaises(ValueError):
                            obj.send(target)
                    self.assertTrue(all(not output for output in self.outputs(obj)))

        def test_codec_thrust_endpoints_and_independent_basis_matrices(self):
            def matrix(q):
                w, x, y, z = q
                return ((1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)),
                        (2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)),
                        (2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)))
            for stack in ('ap', 'px'):
                obj = self.enabled(stack)
                for q in ((1., 0., 0., 0.), (.5, -.5, .5, .5),
                          (math.sqrt(.5), math.sqrt(.5), 0., 0.)):
                    for sign in (1, -1):
                        w, x, y, z = (v*sign for v in q)
                        for thrust in (0., .375, 1.):
                            obj.send(Setpoint('attitude', quaternion_xyzw=(x, y, z, w), thrust=thrust))
                            if stack == 'ap':
                                msg = obj.attitude_pub.messages[-1]
                                self.assertIsInstance(msg, WksimAttitudeTarget)
                                self.assertEqual((msg.header.frame_id, msg.header.stamp.sec, msg.header.stamp.nanosec),
                                                 ('map', 1, 0))
                                self.assertEqual(msg.normalized_thrust, thrust)
                                out = msg.orientation
                                self.assertEqual((out.w, out.x, out.y, out.z), (w, x, y, z))
                            else:
                                msg = obj.publishers['attitude'].messages[-1]
                                self.assertEqual(list(msg.thrust_body), [0., 0., -thrust])
                                mode = obj.publishers['offboard'].messages[-1]
                                self.assertTrue(mode.attitude)
                                for field in ('position', 'velocity', 'acceleration', 'body_rate', 'thrust_and_torque', 'direct_actuator'):
                                    self.assertFalse(getattr(mode, field))
                                self.assertEqual(deserialize_message(serialize_message(mode), type(mode)), mode)
                                original, actual = matrix((w, x, y, z)), matrix(msg.q_d)
                                expected_matrix = tuple(tuple(original[row][j]*row_sign*col_sign
                                    for j, col_sign in enumerate((1, -1, -1)))
                                    for row, row_sign in ((1, 1), (0, 1), (2, -1)))
                                self.assertLess(max(abs(actual[i][j]-expected_matrix[i][j])
                                                    for i in range(3) for j in range(3)), 2e-7)
                            self.assertEqual(deserialize_message(serialize_message(msg), type(msg)), msg)

    # Reuse the exact existing regression method bodies. Their source-run wrapper intentionally
    # asserts current-repository imports, so it is not called for this installed candidate.
    # The installed-path check above replaces no admission gate and does not claim repo equality.
    source = REPO/'validation/test_ap_pv_adapter.py'
    tree = ast.parse(source.read_text())
    cls = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == 'CandidateTests')
    selected = ('mixed_candidate', 'test_ap_mixed_wire_has_no_xy_position_and_preserves_pv_p_v',
        'test_ap_mixed_invalid_targets_never_publish', 'test_ap_mixed_readiness_is_required',
        'test_ap_mixed_body_once_capture_and_shaped_holds', 'test_ap_pv_native_wire_and_original_p_v_outputs',
        'test_ap_pv_invalid_targets_never_publish', 'test_ap_pv_preserves_readiness_checks')
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in selected]
    assert len(cls.body) == len(selected)
    scope = dict(vars(fixtures), fixtures=fixtures, replace=replace, GlobalPosition=GlobalPosition)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), 'exec'), scope)
    cases = [AttitudeTests(name) for name in AttitudeTests.__dict__ if name.startswith('test_')]
    # Exclude only the two existing methods that initialize real ROS nodes.
    cases += [fixtures.NativeTests(name) for name in fixtures.NativeTests.__dict__
              if name.startswith('test_') and name not in (
                  'test_node_rejection_does_not_falsify_connection_or_resume',
                  'test_native_takeoff_alignment_before_command_stream')]
    cases += [scope['CandidateTests'](name) for name in selected if name.startswith('test_')]
    suite = unittest.TestSuite(cases)
    suite.import_paths = imports
    return suite


if __name__ == '__main__':
    root = Path(sys.argv[1]).resolve(strict=True)
    assert root.parent == Path('/root') and root.name.startswith('wksim-attitude-control-')
    sys.path.insert(0, str(REPO))
    suite = candidate_suite(root)
    names, imports = [case.id() for case in suite], suite.import_paths
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    (root/'adapter-results.json').write_text(json.dumps(dict(tests=names, count=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), successful=result.wasSuccessful(), import_paths=imports,
        transport='recording; actual generated ROS messages and installed complete adapter modules',
        ros_nodes_started=False, sitl_started=False), indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
