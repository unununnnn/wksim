"""Real node takeover gate through the public Task interface and formal runtime.

This labelled operator-input scenario is NOT a MissionTask pause/resume feature
or QGC acceptance. Native DDS observers never publish flight commands. The FC,
installed product node and independent physics are the real pinned processes.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.runtime import run, truth_summary
from Simulator.wksim_runtime.task import Task, grounded, state_time
from validate_product_isolation import identity, group_members


class TakeoverProbe(Task):
    def __init__(self, directory, *args, **kwargs):
        super().__init__(directory, *args, **kwargs)
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        self.directory = directory
        self.probe_log = (directory / 'takeover-probe.jsonl').open('x', buffering=1)
        self.outputs, self.checks, self.injections, self.holds = [], [], [], []
        self.ap_home = None
        self.release_mode = 'AUTO.LOITER' if self.flight_stack == 'px4' else 'BRAKE'
        qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)
        if self.flight_stack == 'px4':
            from px4_msgs.msg import TrajectorySetpoint
            from prometheus_control.frames import topic
            cls = TrajectorySetpoint
            endpoint = topic('/wksim_px4_21', 'in', 'trajectory_setpoint', cls)
        else:
            from ardupilot_msgs.msg import GlobalPosition, WksimState
            cls, endpoint = GlobalPosition, '/ap/cmd_gps_pose'
            self.subscriptions.append(self.node.create_subscription(WksimState, '/ap/wksim/local_state_v1',
                lambda msg: setattr(self, 'ap_home', msg), qos))
        self.subscriptions.append(self.node.create_subscription(cls, endpoint, self.observe, qos))

    def observe(self, message):
        row = dict(received_monotonic_s=time.monotonic(), message=self.convert(message))
        self.outputs.append(row)
        self.probe_log.write(json.dumps(dict(observed_native_position=row)) + '\n')

    def settle(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.pump()

    def snapshot(self):
        return dict(public=self.convert(self.state), source_boot_s=state_time(self.state),
                    truth=truth_summary(self.directory / 'truth.jsonl'),
                    received_monotonic_s=time.monotonic())

    def loitering(self):
        control = self.latest.get('control_state')
        return (self.fresh() and self.state.armed and self.state.mode ==
                self.release_mode
                and control is not None and control.control_state == control.INIT)

    def owns_control(self):
        control = self.latest.get('control_state')
        return (self.fresh() and self.state.armed and self.state.mode ==
                ('OFFBOARD' if self.flight_stack == 'px4' else 'GUIDED')
                and control is not None and control.control_state == control.COMMAND_CONTROL
                and not control.failsafe)

    def at(self, position, yaw):
        return (self.owns_control() and math.dist(self.state.position, position) <= .5
                and math.hypot(*self.state.velocity) <= .5
                and abs(math.remainder(float(self.state.attitude[2])-yaw, 2*math.pi)) <= .15)

    def negative(self, envelope, reason):
        before, count = len(self.events), len(self.outputs)
        row = dict(message=self.convert(envelope), reason=reason, received_monotonic_s=time.monotonic())
        self.injections.append(row)
        self.probe_log.write(json.dumps(dict(injected_public_envelope=row)) + '\n')
        publisher = self.setup_pub if isinstance(envelope, self.SetupRequest) else self.command_pub
        publisher.publish(envelope)
        self.wait('rejected_' + reason, lambda: any(e.get('reason') == reason and
            e.get('request_id') == envelope.request_id and e.get('event') in
            ('setup_rejected', 'command_rejected') for e in self.events[before:]), 5)
        self.settle(.2)
        if len(self.outputs) != count or not self.loitering():
            raise RuntimeError('Rejected request changed native output/control')
        self.checks.append(dict(label=reason, status='pass', new_native_outputs=0))

    def fresh_envelope(self, recorded):
        payload = 'setup' if 'setup' in recorded else 'command'
        fields = deepcopy(recorded[payload])
        fields.pop('header')
        message = (self.Setup if payload == 'setup' else self.Cmd)(**fields)
        message.header.stamp = self.node.get_clock().now().to_msg()
        message.header.frame_id = 'map'
        cls = self.SetupRequest if payload == 'setup' else self.CommandRequest
        return cls(version=1, run_id=self.run_id, control_epoch=self.epoch,
                   request_id=recorded['request_id'], **{payload: message})

    def verify_hold_outputs(self, reference, rows):
        if len(rows) < 10:
            raise RuntimeError('Insufficient actual native hold samples')
        position, yaw = reference['position_enu_m'], reference['yaw_enu_rad']
        if self.flight_stack == 'px4':
            expected = [position[1], position[0], -position[2]]
            expected_yaw = math.remainder(math.pi/2-yaw, 2*math.pi)
            for row in rows:
                message = row['message']
                if (math.dist(message['position'], expected) > 1e-5 or
                        abs(math.remainder(message['yaw']-expected_yaw, 2*math.pi)) > 1e-6):
                    raise RuntimeError('PX4 warmup/active reference moved away from captured pose')
        else:
            if self.ap_home is None or not self.ap_home.home_valid:
                raise RuntimeError('Missing observed native AP home for reference audit')
            home_lat, home_lon = self.ap_home.home_latitude_e7, self.ap_home.home_longitude_e7
            for row in rows:
                message = row['message']
                # Invert observed wire coordinates independently; AP integer E7
                # truncation is bounded to 0.012m on each horizontal axis.
                north = (message['latitude']*1e7-home_lat)*.011131884502145034
                midpoint = (message['latitude']+home_lat/1e7)/2
                east = (message['longitude']*1e7-home_lon)*.011131884502145034*math.cos(math.radians(midpoint))
                if (abs(north-position[1]) > .012 or abs(east-position[0]) > .012 or
                        abs(message['altitude']-position[2]) > 1e-5 or
                        abs(math.remainder(message['yaw']-yaw, 2*math.pi)) > 1e-6):
                    raise RuntimeError('AP active reference differs from captured pose')

    def execute(self):
        self.wait('public_control_ready', lambda: self.fresh() and self.setup_pub.get_subscription_count()
                  and self.command_pub.get_subscription_count(), 55)
        if not grounded(self.state):
            raise RuntimeError('Probe must start disarmed on ground')
        self.active = True
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'hold_completed')
        if self.flight_stack == 'px4':
            after = time.monotonic()
            self.wait('native_prearm_ready', lambda: self.arm_ready(after), 25)
        self.send(self.Setup(cmd=self.Setup.ARMING, arming=True), 'arm_completed')
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'),
                  'takeoff_control_completed', 45)
        old_setup = deepcopy(self.envelopes[-1])
        self.wait('takeoff_reached', lambda: self.owns_control() and self.state.position[2] >= 2.5, 30)
        self.dwell('initial_hold', lambda: abs(self.state.position[2]-3) <= .6, 5)
        first_position, first_yaw = [2., 3., 3.], -.9
        self.send(self.Cmd(agent_cmd=self.Cmd.MOVE, move_mode=self.Cmd.XYZ_POS, command_id=1,
                          position_ref=first_position, yaw_ref=first_yaw), 'first_move_accepted')
        old_move = deepcopy(self.envelopes[-1])
        self.wait('off_home_waypoint_reached', lambda: self.at(first_position, first_yaw), 30)
        self.dwell('off_home_waypoint_dwell', lambda: self.at(first_position, first_yaw), 2)
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode=self.release_mode), 'yield_mode_completed')
        self.wait('public_control_released', self.loitering, 10)
        self.settle(.3)  # Drain delivery already queued before the observed release.
        before, count = self.snapshot(), len(self.outputs)
        self.settle(2.)
        after = self.snapshot()
        if (not self.loitering() or len(self.outputs) != count or
                min(before['truth']['final_height_m'], after['truth']['final_height_m']) < 2 or
                after['truth']['final_time'] <= before['truth']['final_time']+2):
            raise RuntimeError('Yield did not leave native mode and advancing physics with zero output')
        self.checks.append(dict(label='released_no_output_physics_continues', status='pass',
                                before=before, after=after, new_native_outputs=0))
        self.negative(self.fresh_envelope(old_setup), 'request_id_not_increasing')
        self.negative(self.fresh_envelope(old_move), 'request_id_not_increasing')
        wrong = self.fresh_envelope(old_setup)
        wrong.control_epoch, wrong.request_id = '0'*32, self.request_id+1
        self.negative(wrong, 'wrong_run_or_control_epoch')
        self.settle(.2)
        before, count, events = self.snapshot(), len(self.outputs), len(self.events)
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'),
                  'fresh_airborne_takeover_completed', 15)
        self.wait('fresh_airborne_control_observed', self.owns_control, 10)
        references = [e for e in self.events[events:] if e.get('event') == 'takeover_reference']
        if len(references) != 1 or not references[0]['airborne']:
            raise RuntimeError('Missing unique airborne reference event')
        reference = references[0]
        if math.hypot(*reference['position_enu_m'][:2]) < 2 or abs(reference['yaw_enu_rad']) < .5:
            raise RuntimeError('Test never established a distinct off-home/nonzero-yaw takeover')
        self.wait('captured_hold_settled', lambda: self.at(reference['position_enu_m'], reference['yaw_enu_rad']), 15)
        self.dwell('captured_hold_dwell', lambda: self.at(reference['position_enu_m'], reference['yaw_enu_rad']), 2)
        rows = self.outputs[count:]
        self.verify_hold_outputs(reference, rows)
        self.holds.append(dict(before=before, after=self.snapshot(), reference=reference,
                               native_output_start=count, native_output_end=len(self.outputs),
                               samples=len(rows), status='pass'))
        self.send(self.Cmd(agent_cmd=self.Cmd.MOVE, move_mode=self.Cmd.XYZ_POS, command_id=2,
                          position_ref=[-1., 1., 3.], yaw_ref=.6), 'new_move_accepted')
        self.wait('new_move_reached', lambda: self.at([-1., 1., 3.], .6), 30)
        self.dwell('new_move_dwell', lambda: self.at([-1., 1., 3.], .6), 2)
        self.send(self.Cmd(agent_cmd=self.Cmd.LAND, command_id=3), 'land_accepted')
        self.wait('landed_and_disarmed', lambda: grounded(self.state), 40)
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'ground_hold_completed')
        self.wait('normal_stop_ready', lambda: self.fresh() and grounded(self.state))

    def report(self):
        result = super().report()
        result['takeover_probe'] = dict(checks=self.checks, holds=self.holds, injections=self.injections,
            native_outputs=self.outputs, native_commands_published_by_observers=0,
            scope='explicit public operator inputs; node transition only, not MissionTask resume or QGC')
        return result

    def close(self):
        self.probe_log.close()
        super().close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stack', choices=('px4', 'arducopter'))
    parser.add_argument('workspace')
    args = parser.parse_args()
    evidence = Path(tempfile.mkdtemp(prefix='airborne-takeover-', dir=REPO / 'validation'))
    config = json.loads((REPO / f'Simulator/wksim_runtime/examples/{args.stack}-session.json').read_text())
    config.update(run_id='takeover-'+args.stack+'-'+uuid.uuid4().hex[:10], prometheus_workspace=args.workspace)
    report = dict(status='failed', original_before=identity(828),
                  validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    print(str(evidence), flush=True)
    result = run(config, evidence / 'runs', task_factory=TakeoverProbe)
    try:
        report['runtime_result'] = result['run_dir']+'/result.json'
        assert result['status'] == 'pass' and result['safe_landing'], result.get('error')
        assert result['children_reaped'] and not result['cleanup_errors']
        report['remaining_owned_processes'] = group_members({c['pgid'] for c in result['children'].values()})
        assert not report['remaining_owned_processes']
        probe = result['task']['takeover_probe']
        assert len(probe['checks']) == 4 and len(probe['holds']) == 1
        assert all(c['status'] == 'pass' for c in probe['checks']+probe['holds'])
        assert identity(828) == report['original_before']
        report.update(status='pass', checks=probe['checks'], holds=probe['holds'])
    except Exception as error:
        report['error'] = str(error)
    report['original_after'] = identity(828)
    (evidence / 'acceptance.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status=report['status'], evidence=str(evidence), error=report.get('error'))), flush=True)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
