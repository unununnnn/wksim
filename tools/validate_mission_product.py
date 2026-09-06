"""Real #15 scenarios: public mission cancellation / operator mode handoff.

The installed control node, native FC and independent physics are unchanged.
Normal flights use the plain formal entry, not this test-input task subclass.
The observer never publishes native control; a labelled simulated operator may
request AUTO.LOITER through the same public setup envelope as an operator UI.
"""
import argparse
from functools import partial
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.runtime import run
from Simulator.wksim_runtime.mission_task import MissionTask
from validate_product_isolation import identity, group_members


class MissionProbe(MissionTask):
    def __init__(self, *args, scenario, **kwargs):
        self.scenario, self.injected = scenario, False
        self.operator, self.native_observed = [], []
        self.operator_ack = False
        super().__init__(*args, **kwargs)
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)
        if self.flight_stack == 'px4':
            from px4_msgs.msg import TrajectorySetpoint
            from prometheus_control.frames import topic
            cls, endpoint = TrajectorySetpoint, topic('/wksim_px4_21', 'in', 'trajectory_setpoint', TrajectorySetpoint)
        else:
            from ardupilot_msgs.msg import GlobalPosition
            cls, endpoint = GlobalPosition, '/ap/cmd_gps_pose'
        self.subscriptions.append(self.node.create_subscription(cls, endpoint, self.observe, qos))

    def observe(self, msg):
        self.native_observed.append(dict(received_monotonic_s=time.monotonic(), message=self.convert(msg)))

    def progress(self, state=None, **fields):
        super().progress(state, **fields)
        event = fields.get('event')
        trigger = (event == 'mission_accepted' if self.scenario == 'cancel_ground' else
                   event == 'waypoint_running' and fields['waypoint']['index'] == 2)
        if self.injected or not trigger or self.scenario == 'invalid_body':
            return
        self.injected = True
        if self.scenario in ('cancel', 'cancel_ground'):
            argv = [sys.executable, str(REPO / 'tools/cancel-wksim.py'), str(self.directory),
                    '--run-id', self.run_id, '--mission-id', self.mission_id]
            answer = subprocess.run(argv, capture_output=True, text=True, timeout=10)
            self.operator.append(dict(actor='simulated_operator', action='CLI cancel', argv=argv,
                returncode=answer.returncode, stdout=answer.stdout, stderr=answer.stderr,
                received_monotonic_s=time.monotonic(), command_id=self.command_id))
            if answer.returncode:
                raise RuntimeError('Real cancellation CLI failed: ' + answer.stderr)
        elif self.scenario == 'external_mode':
            setup = self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER')
            setup.header.stamp = self.node.get_clock().now().to_msg()
            setup.header.frame_id = 'map'
            envelope = self.SetupRequest(version=1, run_id=self.run_id, control_epoch=self.epoch,
                request_id=self.request_id+1000, setup=setup)
            self.operator.append(dict(actor='simulated_operator', action='public AUTO.LOITER',
                envelope=self.convert(envelope), received_monotonic_s=time.monotonic(), command_id=self.command_id))
            self.setup_pub.publish(envelope)

    def report(self):
        if self.scenario == 'external_mode' and self.operator:
            # Failure is already terminal. Keep that failure intact while a
            # bounded read-only drain records the operator's actual mode result.
            # No mission step is resumed and no command is published here.
            deadline = time.monotonic()+3
            while time.monotonic() < deadline:
                self.ros.spin_once(self.node, timeout_sec=.02)
                self.operator_ack = any(e.get('event') == 'setup_completed' and
                    e.get('request_id') == self.operator[0]['envelope']['request_id'] for e in self.events)
                if self.operator_ack and self.state.mode == ('AUTO.LOITER' if self.flight_stack == 'px4' else 'LOITER'):
                    break
        result = super().report()
        result['mission_probe'] = dict(scenario=self.scenario, operator=self.operator,
            native_observed=self.native_observed, native_commands_published_by_observer=0,
            operator_mode_completed=self.operator_ack,
            post_failure_observation='up to 3s read-only drain; terminal failure not cleared or resumed')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stack', choices=('px4', 'arducopter'))
    parser.add_argument('scenario', choices=('cancel', 'cancel_ground', 'external_mode', 'invalid_body'))
    args = parser.parse_args()
    if args.scenario == 'external_mode':
        parser.error('Historical external_mode expected runtime teardown. Use run-mission-lifecycle.sh external_resume for the current pause/resume contract.')
    evidence = Path(tempfile.mkdtemp(prefix='product-mission-' + args.scenario + '-', dir=REPO / 'validation'))
    print(str(evidence), flush=True)
    config = json.loads((REPO / f'Simulator/wksim_runtime/examples/{args.stack}-mission.json').read_text())
    config['run_id'] = args.scenario.replace('_', '-') + '-' + args.stack + '-' + uuid.uuid4().hex[:10]
    if args.scenario == 'invalid_body':
        config['mission']['waypoints'][-1]['position_m'] = [10., 10., 10.]
    before = identity(828)
    report = dict(status='failed', original_before=before, validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    result = run(config, evidence / 'runs', task_factory=partial(MissionProbe, scenario=args.scenario))
    try:
        report['runtime_result'] = result['run_dir'] + '/result.json'
        assert result['children_reaped'] and not result['cleanup_errors']
        report['remaining_owned_processes'] = group_members({c['pgid'] for c in result['children'].values()})
        assert not report['remaining_owned_processes'] and identity(828) == before
        task, mission = result['task'], result['task']['mission']
        commands = [e['command'] for e in task['request_envelopes'] if 'command' in e]
        moves = [c for c in commands if c['agent_cmd'] == 4]
        ids = [e['request_id'] for e in task['request_envelopes']]
        assert all(a < b for a, b in zip(ids, ids[1:]))
        ids = [c['command_id'] for c in commands]
        assert all(a < b for a, b in zip(ids, ids[1:]))
        if args.scenario in ('cancel', 'cancel_ground'):
            assert result['status'] == 'cancelled' and result['safe_landing'], result.get('error')
            assert mission['state'] == 'cancelled' and mission['cancel_request']
            assert len(moves) == (0 if args.scenario == 'cancel_ground' else 2)
            assert len(result['mission_truth']['completed_waypoints']) == (0 if args.scenario == 'cancel_ground' else 1)
            if args.scenario == 'cancel_ground':
                assert not task['request_envelopes'], 'Ground cancellation armed or issued a flight command'
            else:
                assert commands[-1]['agent_cmd'] == 3 and len(commands) == 3
        else:
            assert result['status'] == 'failed' and not result['safe_landing'] and mission['state'] == 'failed'
            assert len(moves) == 2 and len(commands) == 2, 'Failure sent a later waypoint or attempted to regain control'
            if args.scenario == 'external_mode':
                assert 'lost task control' in result.get('error', ''), result.get('error')
                assert task['mission_probe']['operator_mode_completed']
                assert task['final']['state']['mode'] == ('AUTO.LOITER' if args.stack == 'px4' else 'LOITER')
            else:
                assert 'ENU position' in result.get('error', ''), result.get('error')
        report.update(status='pass', observed_runtime_status=result['status'], mission_id=mission['mission_id'],
                      actual_move_count=len(moves), completed_waypoints=sum(w['status']=='completed' for w in mission['waypoints']))
    except Exception as error:
        report['error'] = str(error)
    report['original_after'] = identity(828)
    (evidence / 'acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], evidence=str(evidence), error=report.get('error'))), flush=True)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
