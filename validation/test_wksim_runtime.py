"""No SITL/UE starts: contract, admission failure, public state and process ownership."""
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime import runtime
from Simulator.wksim_runtime.task import Task, grounded, valid_state


def config(stack='px4'):
    result = dict(schema_version=1, run_id='runtime-test', vehicle_id=1, stack=stack,
                  model_profile='quad_x', communication='native_dds', dds_workspace='/root/wksim-dds-VxM6Ni',
                  prometheus_workspace='/root/wksim-ros2-0viK3f', px4_root='/root/wksim-dependencies/px4-d6f12ad1')
    if stack == 'arducopter':
        result['ap_candidate'] = '/root/wksim-ap-dds-yaw-state-4Wr27s'
    return result


def state(**fields):
    return NS(**dict(dict(uav_id=1, connected=True, odom_valid=True, armed=False,
                         header=NS(frame_id='map', stamp=NS(sec=10, nanosec=0)),
                         position=[0, 0, 0], velocity=[0, 0, 0], attitude=[0, 0, 0]), **fields))


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        isolation_check = patch.object(runtime, 'check_isolation')
        isolation_check.start()
        self.addCleanup(isolation_check.stop)

    def test_launch_semantics_and_display_identity(self):
        for stack in ('px4', 'arducopter'):
            cfg = config(stack)
            plan = runtime.launch_spec(cfg, Path('/tmp/run'), Path('/tmp/model.so'))
            self.assertNotIn('--state-socket', plan['physics'])
            self.assertEqual(plan['control'][plan['control'].index('flight_stack:=' + stack)], 'flight_stack:=' + stack)
            self.assertFalse(any('validate_sitl' in arg for value in plan.values() if isinstance(value, list) for arg in value))
            cfg['display_socket'] = '/tmp/runtime-test/display.sock'
            plan = runtime.launch_spec(cfg, Path('/tmp/run'), Path('/tmp/model.so'))
            self.assertEqual(plan['physics'][-6:], ['--state-socket', cfg['display_socket'], '--run-id', cfg['run_id'], '--vehicle-id', '1'])
            if stack == 'px4':
                self.assertEqual(plan['fc_environment']['PX4_PARAM_UXRCE_DDS_SYNCT'], '0')
                self.assertTrue(plan['agent'][0].endswith('agent-install/bin/MicroXRCEAgent'))
            else:
                self.assertIn('4Wr27s/build/sitl/bin/arducopter', plan['fc'][0])
                self.assertIn('JSON:127.0.0.1', plan['fc'])

    def test_mission_physics_has_supervised_lifetime_not_a_hidden_pause_limit(self):
        for stack in ('px4', 'arducopter'):
            cfg = config(stack)
            normal = runtime.launch_spec(cfg, Path('/tmp/run'), Path('/tmp/model.so'))
            self.assertEqual(normal['physics'][-2:], ['--duration', '600'])
            mission = runtime.launch_spec(dict(cfg, mission={'waypoints': []}), Path('/tmp/run'), Path('/tmp/model.so'))
            self.assertIn('--run-until-stopped', mission['physics'])
            self.assertNotIn('--duration', mission['physics'])

    def test_telemetry_rate_profile_is_optional_and_only_changes_ap_stream_rates(self):
        cfg = config('arducopter')
        base = runtime.launch_spec(cfg, Path('/tmp/run'), Path('/tmp/model.so'))
        enabled = runtime.launch_spec(dict(cfg, telemetry_socket='/tmp/runtime-test/t.sock'),
                                      Path('/tmp/run'), Path('/tmp/model.so'))
        position = base['fc'].index('--defaults') + 1
        profile = REPO / 'Simulator/wksim_runtime/arducopter-telemetry.parm'
        parts = base['fc'][position].split(',')
        self.assertEqual(enabled['fc'][position], ','.join(parts[:-1] + [str(profile), parts[-1]]))
        self.assertTrue(enabled['fc'][position].endswith('/dds.parm'))
        enabled['fc'][position] = base['fc'][position]
        self.assertEqual(base, enabled)
        lines = [line for line in profile.read_text().splitlines() if line and not line.startswith('#')]
        self.assertEqual(lines, ['MAV1_POSITION 10', 'MAV1_EXTRA1 10', 'MAV1_EXTRA3 5'])

    def test_ground_requires_valid_disarmed_finite_state(self):
        self.assertTrue(grounded(state()))
        for fields in (dict(armed=True), dict(connected=False), dict(odom_valid=False),
                       dict(position=[0, 0, 3]), dict(position=[0, 0, float('nan')]), dict(uav_id=2)):
            self.assertFalse(grounded(state(**fields)))
        self.assertFalse(valid_state(None))

    def test_frozen_public_source_is_stale_even_with_new_receive(self):
        task = Task.__new__(Task)
        task.latest, task.received = {'state': state()}, {'state': 100}
        task.advanced_at = 90
        with patch('Simulator.wksim_runtime.task.time.monotonic', return_value=100):
            self.assertFalse(task.fresh())

    def test_preflight_rejection_creates_no_children_and_failed_result(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(runtime.sys, 'platform', 'linux'), \
                patch.object(runtime.os, 'readlink', side_effect=lambda p: 'private' if '/self/' in p else 'host'), \
                patch.dict(os.environ, ROS_DOMAIN_ID='77', ROS_LOCALHOST_ONLY='1', RMW_IMPLEMENTATION='rmw_fastrtps_cpp'), \
                patch.object(runtime, 'preflight', return_value=dict(ok=False, reasons=[dict(code='denied', message='test')])), \
                patch.object(runtime.subprocess, 'Popen') as spawn:
            result = runtime.run(config(), Path(folder))
            spawn.assert_not_called()
            self.assertEqual(result['status'], 'failed')
            self.assertFalse(result['safe_landing'])
            self.assertEqual(result['stop_kind'], 'unsuccessful_isolated_teardown')
            self.assertTrue((Path(folder) / 'runtime-test/result.json').is_file())
            with self.assertRaises(FileExistsError):
                runtime.run(config(), Path(folder))

    def test_shared_namespace_rejected_before_output(self):
        with patch.object(runtime.sys, 'platform', 'linux'), patch.object(runtime.os, 'readlink', return_value='host'):
            with self.assertRaisesRegex(RuntimeError, 'private Linux'):
                runtime.run(config(), Path('/unused'))

    def test_partial_start_failure_cleans_only_created_group(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = dict(config(), prometheus_workspace=folder, model_library='/tmp/verified.so')
            admission = dict(ok=True, config=cfg, identities=dict(model_library=dict(path='/tmp/verified.so'),
                              model_build={}, firmware_commit='test'))
            child = Mock(pid=345678, returncode=None)
            child.poll.return_value = None
            def reaped(timeout):
                child.poll.return_value = -15
            child.wait.side_effect = reaped
            calls = []
            def spawn(argv, **kwargs):
                calls.append(argv)
                if len(calls) == 2:
                    raise OSError('injected agent startup failure')
                kwargs['stdout'].write('{"ready": true}\n')
                kwargs['stdout'].flush()
                return child
            with patch.object(runtime.sys, 'platform', 'linux'), \
                    patch.object(runtime.os, 'readlink', side_effect=lambda p: 'private' if '/self/' in p else 'host'), \
                    patch.dict(os.environ, ROS_DOMAIN_ID='77', ROS_LOCALHOST_ONLY='1', RMW_IMPLEMENTATION='rmw_fastrtps_cpp'), \
                    patch.object(runtime, 'preflight', return_value=admission), \
                    patch.object(runtime, 'isolate_temporary_files', return_value={'scope':'unit filesystem boundary'}), \
                    patch.object(runtime.importlib.util, 'find_spec', return_value=NS(origin=folder + '/install/pkg/__init__.py')), \
                    patch.object(runtime, 'digest', return_value=runtime.PX4_SHA256), \
                    patch.object(runtime.socket, 'socket'), patch.object(runtime.subprocess, 'Popen', side_effect=spawn), \
                    patch.object(runtime.os, 'killpg', create=True) as kill:
                result = runtime.run(cfg, Path(folder))
            self.assertEqual(list(result['children']), ['physics'])
            self.assertEqual(result['status'], 'failed')
            self.assertIn('injected agent', result['error'])
            self.assertFalse(result['safe_landing'])
            self.assertTrue(result['children_reaped'])
            self.assertEqual([call.args[0] for call in kill.call_args_list], [345678, 345678])

    def test_task_sequence_is_same_six_public_inputs(self):
        class Setup(NS):
            ARMING, SET_PX4_MODE, SET_CONTROL_MODE = 0, 1, 3
        class Cmd(NS):
            LAND, MOVE, XYZ_POS = 3, 4, 0
        task = Task.__new__(Task)
        task.Setup, task.Cmd = Setup, Cmd
        task.flight_stack = 'arducopter'
        task.restart_control = None
        task.latest = {'state': state()}
        task.received = {'state': 0}
        task.setup_pub = task.command_pub = NS(get_subscription_count=lambda: 1)
        task.fresh = lambda: True
        sent, phases = [], []
        def send(msg, label, timeout=10):
            sent.append(vars(msg))
            if getattr(msg, 'cmd', None) == Setup.ARMING:
                task.state.armed = True
            if getattr(msg, 'cmd', None) == Setup.SET_CONTROL_MODE:
                task.state.position[2] = 3
            if getattr(msg, 'agent_cmd', None) == Cmd.MOVE:
                task.state.position = [2, 3, 3]
            if getattr(msg, 'agent_cmd', None) == Cmd.LAND:
                task.state.armed, task.state.position[2] = False, 0
        def wait(label, predicate, timeout=20):
            task.received['state'] = float('inf')  # a sample delivered after setup completion
            self.assertTrue(predicate(), label)
            phases.append(label)
        task.send, task.wait = send, wait
        task.dwell = lambda label, predicate, seconds: self.assertTrue(predicate(), label)
        task.execute()
        self.assertEqual(sent, [dict(cmd=1, px4_mode='AUTO.LOITER'), dict(cmd=0, arming=True),
            dict(cmd=3, control_state='COMMAND_CONTROL'), dict(agent_cmd=4, move_mode=0, command_id=1,
            position_ref=[2.0, 3.0, 3.0], yaw_ref=0.0), dict(agent_cmd=3, command_id=2),
            dict(cmd=1, px4_mode='AUTO.LOITER')])
        self.assertEqual(phases[-1], 'normal_stop_ready')

    def test_public_log_uses_full_topic_and_elapsed_wall(self):
        task = Task.__new__(Task)
        task.latest, task.received, task.events = {}, {}, []
        task.started, task.last_stamp, task.active = 100, None, False
        task.convert = lambda msg: dict(armed=msg.armed)
        task.log = io.StringIO()
        with patch('Simulator.wksim_runtime.task.time.monotonic', return_value=103):
            task.receive('state', state())
        record = json.loads(task.log.getvalue())
        self.assertEqual(record['topic'], '/uav1/prometheus/state')
        self.assertEqual(record['wall'], 3)

    def test_prearm_needs_fresh_native_health_for_current_mode(self):
        task = Task.__new__(Task)
        task.health_received, task.health_advanced = 101, 101
        task.native_health = NS(system_id=22, timestamp=123, pre_flight_checks_pass=True,
                                nav_state=4, NAVIGATION_STATE_AUTO_LOITER=4)
        with patch('Simulator.wksim_runtime.task.time.monotonic', return_value=102):
            self.assertTrue(task.arm_ready(100))
            self.assertFalse(task.arm_ready(101))
            task.native_health.pre_flight_checks_pass = False
            self.assertFalse(task.arm_ready(100))
            task.native_health.pre_flight_checks_pass = True
            task.native_health.nav_state = 0
            self.assertFalse(task.arm_ready(100))
            task.native_health.nav_state = 4
            task.health_advanced = 90
            self.assertFalse(task.arm_ready(100))

    def test_session_rejections_only_fail_the_matching_pending_request(self):
        task = Task.__new__(Task)
        task.protocol, task.run_id, task.epoch = 'session_v1', 'run', 'e' * 32
        task.pending_request_id = 3
        task.latest, task.received, task.events = {}, {}, []
        task.started, task.active, task.error = 0, True, None
        task.log, task.convert = io.StringIO(), lambda msg: vars(msg)
        base = dict(event='command_rejected', run_id='run', control_epoch=task.epoch, request_id=3)
        for fields in (dict(request_id=2), dict(requested_epoch='old'), dict(requested_run_id='other'),
                       dict(control_epoch='old'), dict(run_id='other')):
            task.receive('text_info', NS(message=json.dumps(dict(base, **fields))))
            self.assertIsNone(task.error)
        task.receive('text_info', NS(message=json.dumps(base)))
        self.assertIn('Product control failure', task.error)
        task.error, task.pending_request_id = None, None
        task.receive('text_info', NS(message=json.dumps(base)))
        self.assertIsNone(task.error)
        task.receive('text_info', NS(message=json.dumps(dict(base, event='control_revoked'))))
        self.assertIn('Product control failure', task.error)

    def test_ground_restart_config_requires_explicit_session_protocol(self):
        from Simulator.wksim_runtime.config import validate_config, ConfigError
        with self.assertRaises(ConfigError):
            validate_config(dict(config(), restart_control_on_ground=True))
        for value in ('true', 1, None):
            with self.assertRaises(ConfigError):
                validate_config(dict(config(), restart_control_on_ground=value, control_protocol='session_v1'))
        cfg = validate_config(dict(config(), restart_control_on_ground=True, control_protocol='session_v1'))
        self.assertTrue(cfg['restart_control_on_ground'])
        self.assertIn('run_id:=' + cfg['run_id'], runtime.launch_spec(cfg, Path('/tmp/run'), Path('/tmp/model.so'))['control'])

    def test_restart_retains_ground_evidence_until_supervisor_check(self):
        task = Task.__new__(Task)
        task.protocol, task.epoch = 'session_v1', 'old'
        task.latest, task.received = {'state': state()}, {'state': 10}
        task.active, task.retired_epochs, task.restarts = True, set(), []
        task.fresh = lambda: bool(task.latest)
        task.setup_pub = task.command_pub = NS(get_subscription_count=lambda: 1)
        def restart():
            self.assertTrue(task.fresh())
            self.assertTrue(grounded(task.state))
            self.assertFalse(task.active)
            return {'supervisor_checked': True}
        def ready(label, predicate, timeout):
            self.assertFalse(task.latest)
            self.assertIsNone(task.epoch)
            task.latest['state'], task.epoch = state(), 'new'
            self.assertTrue(predicate())
        task.restart_control, task.wait = restart, ready
        task.restart_on_ground()
        self.assertEqual(task.retired_epochs, {'old'})
        self.assertEqual(task.request_id, 0)
        self.assertEqual(task.restarts, [dict(supervisor_checked=True, old_epoch='old', new_epoch='new')])
        self.assertTrue(task.active)

    def test_truth_requires_real_records_and_ignores_incomplete_tail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'truth.jsonl'
            records = [dict(time=i, vehicle=[0] * 6 + p) for i, p in enumerate(([0, 0, 0], [3, 2, -3], [3, 2, 0]))]
            path.write_text(''.join(json.dumps(row) + '\n' for row in records) + '{')
            report = runtime.truth_summary(path)
            self.assertEqual(report['records'], 3)
            self.assertEqual(report['max_height_m'], 3)
            self.assertEqual(report['min_waypoint_error_m'], 0)
            self.assertEqual(report['final_height_m'], 0)
            path.write_text('')
            with self.assertRaisesRegex(RuntimeError, 'Missing physical truth'):
                runtime.truth_summary(path)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux process group ownership')
    def test_cleanup_terminates_owned_group_not_unrelated_process(self):
        owned = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        try:
            self.assertEqual(runtime.stop_children([('dummy', owned, io.StringIO())]), [])
            self.assertIsNotNone(owned.poll())
            self.assertIsNone(unrelated.poll())
        finally:
            for child in (owned, unrelated):
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
