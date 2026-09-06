"""Actual MissionTask with labelled public operator inputs, never native commands.

The timer supplies CLI pause/resume/cancel or one external public setup. It does
not replace execute/pump/send/pause/visit or physics. Read-only native samples and
physical truth independently corroborate output cessation and resumed dwell.
Not a QGroundControl UI test or an airborne DDS-loss policy acceptance.
"""
import argparse
from functools import partial
import hashlib
import json
import math
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
from Simulator.wksim_runtime.task import state_time
from validate_product_isolation import identity, group_members


class LifecycleProbe(MissionTask):
    def __init__(self, *args, scenario, **kwargs):
        self.scenario = scenario
        self.operator, self.native_outputs = [], []
        self.pause_sent = self.resume_sent = self.cancel_sent = self.old_rejected = False
        self.pause_token = None
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
        self.operator_timer = self.node.create_timer(.05, self.operate)

    def observe(self, msg):
        self.native_outputs.append(dict(received_monotonic_s=time.monotonic(), message=self.convert(msg)))

    def cli(self, action, *, token=None, expected=0):
        script = 'cancel-wksim.py' if action == 'cancel' else 'control-wksim-mission.py'
        argv = [sys.executable, str(REPO/'tools'/script), str(self.directory),
                '--run-id', self.run_id, '--mission-id', self.mission_id]
        if action != 'cancel':
            argv += ['--action', action, '--token', token or self.action_token]
        answer = subprocess.run(argv, capture_output=True, text=True, timeout=5)
        self.operator.append(dict(actor='labelled_test_operator', argv=argv, returncode=answer.returncode,
            stdout=answer.stdout, stderr=answer.stderr, expected=expected,
            received_monotonic_s=time.monotonic(), source_boot_s=state_time(self.state)))
        if answer.returncode != expected:
            raise RuntimeError('Operator CLI result differs from expected: '+answer.stderr)

    def operate(self):
        if time.monotonic()-self.started > 210:
            raise TimeoutError('Bounded validation operator deadline; not a product pause limit')
        if not self.pause_sent:
            if (not self.waypoints or self.waypoints[-1]['index'] != 3
                    or 'dwell_start_boot_s' not in self.waypoints[-1]
                    or state_time(self.state)-self.waypoints[-1]['dwell_start_boot_s'] < .7):
                return
            self.pause_sent, self.pause_token = True, self.action_token
            if self.scenario == 'external_resume':
                setup = self.Setup(cmd=self.Setup.SET_PX4_MODE,
                                   px4_mode='AUTO.LOITER' if self.flight_stack == 'px4' else 'BRAKE')
                setup.header.stamp = self.node.get_clock().now().to_msg()
                setup.header.frame_id = 'map'
                envelope = self.SetupRequest(version=1, run_id=self.run_id, control_epoch=self.epoch,
                                             request_id=self.request_id+1000, setup=setup)
                self.operator.append(dict(actor='labelled_test_operator', action='external public mode',
                    envelope=self.convert(envelope), received_monotonic_s=time.monotonic()))
                self.setup_pub.publish(envelope)
            else:
                self.cli('pause')
        elif self.mission_state == 'paused' and not self.resume_sent:
            elapsed = state_time(self.state)-self.pauses[-1]['start_boot_s']
            if elapsed >= 2 and not self.old_rejected:
                self.old_rejected = True
                self.cli('resume', token=self.pause_token, expected=1)
            if elapsed >= 3 and self.scenario == 'pause_cancel' and not self.cancel_sent:
                self.cancel_sent = True
                self.cli('cancel')
            if elapsed >= 6:
                self.resume_sent = True
                self.cli('resume')

    def report(self):
        result = super().report()
        result['lifecycle_probe'] = dict(scenario=self.scenario, operator=self.operator,
            native_outputs=self.native_outputs, native_commands_published_by_observer=0)
        return result


def audit(result):
    assert result['status'] in ('pass', 'cancelled') and result['safe_landing'], result.get('error')
    task, mission = result['task'], result['task']['mission']
    probe = task['lifecycle_probe']
    assert len(mission['pauses']) == 1
    pause = mission['pauses'][0]
    assert pause['publications_after'] == pause['publications_before'], 'Mission emitted during pause'
    assert pause['end_boot_s']-pause['start_boot_s'] >= 6
    assert pause['end_truth']['final_time']-pause['start_truth']['final_time'] >= 5.5
    # Let already queued native observations drain for 0.5 wall seconds; preserve
    # all samples and report this guard explicitly, never erase the transition.
    quiet = [r for r in probe['native_outputs'] if pause['start_monotonic_s']+.5
             <= r['received_monotonic_s'] < pause['end_monotonic_s']]
    assert pause['end_monotonic_s']-pause['start_monotonic_s'] > 1
    assert not quiet, 'Native position output continued while paused'
    rows = [json.loads(line) for line in (Path(result['run_dir'])/'truth.jsonl').read_text().splitlines()]
    window = rows[pause['start_truth']['records']:pause['end_truth']['records']]
    assert len(window) > 10 and min(-r['vehicle'][8] for r in window) > 2.5
    envelopes = task['request_envelopes']
    assert all(a['request_id'] < b['request_id'] for a, b in zip(envelopes, envelopes[1:]))
    point = mission['waypoints'][2]
    assert point['input']['frame'] == 'body_flu' and point['attempts'][0]['status'] == 'interrupted'
    interrupted = next(p for p in mission['progress'] if p.get('event') == 'waypoint_interrupted')
    assert interrupted['waypoint']['dwell_start_boot_s'] < pause['start_boot_s']
    setup = next(e for e in envelopes if e['request_id'] == pause['resume_setup_request_id'])
    assert setup['setup']['control_state'] == 'COMMAND_CONTROL'
    later = [e for e in envelopes if e['request_id'] > setup['request_id']]
    if probe['scenario'] == 'pause_cancel':
        assert result['status'] == 'cancelled' and len(point['attempts']) == 1
        assert not any('command' in e and e['command']['agent_cmd'] == 4 for e in later)
        assert later[0]['command']['agent_cmd'] == 3
    else:
        assert result['status'] == 'pass' and point['status'] == 'completed' and len(point['attempts']) == 2
        command = later[0]['command']
        assert command['move_mode'] == 0 and command['agent_cmd'] == 4
        assert math.dist(command['position_ref'], point['target_enu_m']) < 1e-5
        assert abs(math.remainder(command['yaw_ref']-point['yaw_enu_rad'], 2*math.pi)) < 1e-6
        assert point['attempts'][1]['command_id'] > point['attempts'][0]['command_id']
        assert point['dwell_start_boot_s'] >= pause['end_boot_s']
        assert point['dwell_end_boot_s']-point['dwell_start_boot_s'] >= point['dwell_s']
        assert result['mission_truth']['ok']
    if probe['scenario'] == 'external_resume':
        external = next(o['envelope'] for o in probe['operator'] if o.get('action') == 'external public mode')
        assert setup['request_id'] > external['request_id']
        assert pause['pause_request'] is None
    else:
        assert pause['pause_request']['action_token'] != pause['resume_request']['action_token']
    assert any(o.get('expected') == 1 and o['returncode'] == 1
               and json.loads(o['stderr']).get('submitted') is False
               and 'offer/action' in json.loads(o['stderr']).get('error', '') for o in probe['operator'])
    assert result['operator_wait_seconds'] >= pause['wait_wall_s'] > 0
    assert '--run-until-stopped' in result['children']['physics']['argv']
    return dict(status='pass', paused_boot_s=pause['end_boot_s']-pause['start_boot_s'],
        paused_physics_s=pause['end_truth']['final_time']-pause['start_truth']['final_time'],
        paused_wall_s=pause['wait_wall_s'], native_quiet_guard_wall_s=.5, native_outputs_in_quiet_window=len(quiet),
        minimum_paused_height_m=min(-r['vehicle'][8] for r in window),
        interrupted_waypoint=point['index'], attempts=len(point['attempts']),
        completed_physical_waypoints=result['mission_truth']['completed_waypoints'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stack', choices=('px4', 'arducopter'))
    parser.add_argument('scenario', choices=('pause_resume', 'external_resume', 'pause_cancel'))
    args = parser.parse_args()
    evidence = Path(tempfile.mkdtemp(prefix='mission-lifecycle-', dir=REPO/'validation'))
    print(str(evidence), flush=True)
    config = json.loads((REPO/f'Simulator/wksim_runtime/examples/{args.stack}-mission.json').read_text())
    config['run_id'] = 'lifecycle-'+args.stack+'-'+uuid.uuid4().hex[:10]
    report = dict(status='failed', stack=args.stack, scenario=args.scenario, original_before=identity(828),
                  validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    result = run(config, evidence/'runs', task_factory=partial(LifecycleProbe, scenario=args.scenario))
    report['runtime_result'] = result['run_dir']+'/result.json'
    report['original_after'] = identity(828)
    report['remaining_owned_processes'] = group_members({c['pgid'] for c in result['children'].values()})
    try:
        assert result['children_reaped'] and not result['cleanup_errors']
        assert not report['remaining_owned_processes'] and report['original_before'] == report['original_after']
        report.update(audit(result))
    except Exception as error:
        report['error'] = str(error) or type(error).__name__
    (evidence/'acceptance.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status=report['status'], evidence=str(evidence), error=report.get('error'))), flush=True)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
