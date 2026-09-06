"""Real dual-stack #14 gate using the product runtime and public-input test seam.

The installed control node, FC and physics are not replaced. A Task subclass
injects only explicitly labelled invalid public inputs and one recorded PX4 ACK.
The latter is a response replay, never a native flight-control command.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.runtime import run, truth_summary
from Simulator.wksim_runtime.task import Task, grounded
from validate_product_isolation import identity, group_members


class RestartProbe(Task):
    def __init__(self, directory, *args, **kwargs):
        super().__init__(directory, *args, **kwargs)
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        self.directory = directory
        self.checks, self.native_outputs, self.native_commands, self.native_acks = [], [], [], []
        self.expected_rejection = None
        self.probe_log = (directory / 'epoch-probe.jsonl').open('x', buffering=1)
        qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)
        if self.flight_stack == 'px4':
            from px4_msgs.msg import TrajectorySetpoint, VehicleCommand, VehicleCommandAck
            from prometheus_control.frames import topic
            for key, cls, direction, name in (
                    ('position', TrajectorySetpoint, 'in', 'trajectory_setpoint'),
                    ('command', VehicleCommand, 'in', 'vehicle_command'),
                    ('ack', VehicleCommandAck, 'out', 'vehicle_command_ack')):
                endpoint = topic('/wksim_px4_21', direction, name, cls)
                self.subscriptions.append(self.node.create_subscription(cls, endpoint,
                    lambda msg, key=key: self.observe(key, msg), qos))
            self.ack_pub = self.node.create_publisher(VehicleCommandAck,
                topic('/wksim_px4_21', 'out', 'vehicle_command_ack', VehicleCommandAck), 10)
        else:
            from ardupilot_msgs.msg import GlobalPosition
            self.subscriptions.append(self.node.create_subscription(GlobalPosition,
                '/ap/cmd_gps_pose', lambda msg: self.observe('position', msg), qos))
        self.legacy_pub = self.node.create_publisher(self.Setup, '/uav1/prometheus/setup', 1)

    def observe(self, key, msg):
        record = dict(kind=key, wall=time.monotonic()-self.started, message=self.convert(msg))
        self.probe_log.write(json.dumps(record) + '\n')
        if key == 'position':
            target = (list(msg.position) + [msg.yaw] if self.flight_stack == 'px4'
                      else [msg.latitude, msg.longitude, msg.altitude, msg.yaw])
            self.native_outputs.append(target)
        elif key == 'command':
            self.native_commands.append(self.convert(msg))
        else:
            self.native_acks.append(deepcopy(msg))

    def settle(self, seconds=0.3):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.pump()

    def envelope(self, payload, *, epoch=None, run_id=None, number=None):
        payload.header.stamp = self.node.get_clock().now().to_msg()
        payload.header.frame_id = 'map'
        setup = isinstance(payload, self.Setup)
        cls = self.SetupRequest if setup else self.CommandRequest
        return cls(version=1, run_id=run_id or self.run_id, control_epoch=epoch or self.epoch,
                   request_id=self.request_id if number is None else number,
                   **{('setup' if setup else 'command'): payload})

    def rejected(self, message, reason, label, *, legacy=False, holding=False):
        self.settle()
        before = len(self.native_outputs), len(self.native_commands)
        old_target = self.native_outputs[-1] if holding else None
        start = len(self.events)
        setup = legacy or isinstance(message, self.SetupRequest)
        number = 0 if legacy else message.request_id
        self.expected_rejection = ('setup_rejected' if setup else 'command_rejected', reason, number)
        self.probe_log.write(json.dumps(dict(injected=type(message).__name__, label=label,
                                             message=self.convert(message))) + '\n')
        try:
            (self.legacy_pub if legacy else self.setup_pub if setup else self.command_pub).publish(message)
            self.wait(label, lambda: any((e.get('event'), e.get('reason'), e.get('request_id')) == self.expected_rejection
                                        for e in self.events[start:]), 5)
            self.settle()
        finally:
            self.expected_rejection = None
        new_targets = self.native_outputs[before[0]:]
        if holding:
            if not new_targets or any(target != old_target for target in new_targets):
                raise RuntimeError(label + ': rejected MOVE changed the accepted native target or stopped valid hold')
        elif new_targets or not grounded(self.state):
            raise RuntimeError(label + ': unsolicited setpoint or arming after ground rejection')
        if len(self.native_commands) != before[1]:
            raise RuntimeError(label + ': rejected input emitted a native command')
        if any(e.get('event') in ('setup_received', 'setup_completed', 'command_accepted')
               for e in self.events[start:]):
            raise RuntimeError(label + ': negative input was accepted')
        self.checks.append(dict(label=label, status='pass', reason=reason,
            new_native_commands=0, new_native_targets=0, existing_hold_samples=len(new_targets)))

    def restart_on_ground(self):
        self.settle()
        old_epoch = self.epoch
        old_ack = deepcopy(self.native_acks[-1]) if self.native_acks else None
        super().restart_on_ground()
        self.settle()
        after = truth_summary(self.directory / 'truth.jsonl')['final_time']
        self.restarts[-1]['model_time_after'] = after
        if after <= self.restarts[-1]['model_time_before'] or not grounded(self.state):
            raise RuntimeError('Same physics did not advance during ground control restart')
        self.checks.append(dict(label='same_fc_physics_new_control_epoch', status='pass'))
        self.rejected(self.envelope(self.Setup(cmd=self.Setup.ARMING, arming=True),
                      epoch=old_epoch, number=2**63), 'wrong_run_or_control_epoch', 'old_epoch_arm_rejected')
        self.rejected(self.envelope(self.Cmd(agent_cmd=self.Cmd.MOVE, move_mode=self.Cmd.XYZ_POS,
                      command_id=99, position_ref=[8., 8., 3.]), epoch=old_epoch, number=2**63),
                      'wrong_run_or_control_epoch', 'old_epoch_move_rejected')
        self.rejected(self.envelope(self.Setup(cmd=self.Setup.ARMING, arming=True),
                      run_id=self.run_id + '-other', number=2**63), 'wrong_run_or_control_epoch', 'other_run_rejected')
        legacy = self.Setup(cmd=self.Setup.ARMING, arming=True)
        legacy.header.stamp = self.node.get_clock().now().to_msg()
        self.rejected(legacy, 'legacy_input_requires_session', 'legacy_arming_rejected', legacy=True)
        if self.flight_stack == 'px4':
            if old_ack is None:
                raise RuntimeError('Missing actual first-epoch native ACK')
            start, before = len(self.events), len(self.native_commands)
            self.probe_log.write(json.dumps(dict(injected='recorded_old_PX4_ACK', message=self.convert(old_ack))) + '\n')
            self.ack_pub.publish(old_ack)
            self.wait('old_native_ack_rejected', lambda: any(e.get('event') == 'native_input_rejected'
                and e.get('source') == 'ack' and e.get('reason') == 'unmatched_ack' for e in self.events[start:]), 5)
            if len(self.native_commands) != before or any(e.get('event') == 'native_ack' for e in self.events[start:]):
                raise RuntimeError('Old ACK completed or initiated a new operation')
            self.checks.append(dict(label='recorded_old_PX4_ACK_rejected', status='pass',
                scope='real ACK replay after process restart; pending-request correlation also has separate boundary tests'))

    def send(self, msg, label, timeout=10):
        if label == 'land_accepted':
            duplicate = self.Cmd(agent_cmd=self.Cmd.MOVE, move_mode=self.Cmd.XYZ_POS,
                                 command_id=1, position_ref=[8., 8., 3.])
            self.rejected(self.envelope(deepcopy(duplicate)), 'request_id_not_increasing',
                          'duplicate_envelope_rejected', holding=True)
            self.request_id += 1
            self.rejected(self.envelope(duplicate), 'command_id_not_increasing',
                          'duplicate_move_id_rejected', holding=True)
        super().send(msg, label, timeout)

    def report(self):
        result = super().report()
        result['epoch_probe'] = dict(checks=self.checks, native_commands=self.native_commands,
            scope='public negative inputs; native output observation; recorded PX4 ACK replay only, no native command injection')
        return result

    def close(self):
        self.probe_log.close()
        super().close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stack', choices=('px4', 'arducopter'))
    parser.add_argument('workspace')
    args = parser.parse_args()
    evidence = Path(tempfile.mkdtemp(prefix='product-epoch-', dir=REPO / 'validation'))
    config = json.loads((REPO / f'Simulator/wksim_runtime/examples/{args.stack}.json').read_text())
    config.update(run_id='epoch-' + args.stack + '-' + uuid.uuid4().hex[:10],
                  prometheus_workspace=args.workspace, control_protocol='session_v1', restart_control_on_ground=True)
    before = identity(828)
    report = dict(status='failed', original_before=before,
                  validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    print(str(evidence), flush=True)
    result = run(config, evidence / 'runs', task_factory=RestartProbe)
    try:
        report['runtime_result'] = result['run_dir'] + '/result.json'
        assert result['status'] == 'pass' and result['safe_landing'] and result['children_reaped'], result.get('error')
        assert not result['cleanup_errors']
        checks = result['task']['epoch_probe']['checks']
        assert len(checks) == (8 if args.stack == 'px4' else 7) and all(c['status'] == 'pass' for c in checks)
        report['remaining_owned_processes'] = group_members({c['pgid'] for c in result['children'].values()})
        assert not report['remaining_owned_processes']
        assert identity(828) == before
        if args.stack == 'px4':
            commands = result['task']['epoch_probe']['native_commands']
            pairs = [(c['source_system'], c['source_component']) for c in commands]
            assert len(pairs) >= 5 and len(pairs) == len(set(pairs)), 'Native ACK identity reused'
            report['native_request_identities'] = pairs
        report['checks'], report['status'] = checks, 'pass'
    except Exception as error:
        report['error'] = str(error)
    report['original_after'] = identity(828)
    (evidence / 'acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], evidence=str(evidence), error=report.get('error'))), flush=True)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
