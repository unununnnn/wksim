"""Explicit pure-Python external PID candidate using the sealed #34 outlet.

The superclass supplies observation, parameter checks and preparation helpers,
not its attitude-step experiment. PID metrics remain pending independent audit.
"""
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import time

from Simulator.wksim_control.position_pid import (
    PIDConfig, PIDReference, PIDState, NativeThrustConfig, select_controller)
from .attitude_task import AttitudeTask, MODE_TRUE, MODE_FALSE, hover_median, within
from .evidence import write_json
from .task import Task, grounded, state_time

CONFIG_PATH = Path(__file__).with_name('pid-flight-v1.json')
CONFIG_SHA256 = '25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0'


def load_config(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONFIG_SHA256:
        raise ValueError('PID trial configuration differs from the pre-run frozen protocol')
    config = json.loads(raw)
    select_controller(config['controller'], PIDConfig(config['model']['mass_kg'], **config['pid']))
    return config


def reference(config, kind, elapsed):
    if kind != 'circle':
        return PIDReference(tuple(config['point']['position_enu_m']), yaw_enu_rad=config['point']['yaw_rad'])
    c = config['circle']
    omega = 2 * math.pi / c['period_s']
    angle, radius = omega * elapsed, c['radius_m']
    cs, sn = math.cos(angle), math.sin(angle)
    center = c['center_enu_m']
    return PIDReference((center[0]+radius*cs, center[1]+radius*sn, center[2]),
        (-radius*omega*sn, radius*omega*cs, 0.),
        (-radius*omega*omega*cs, -radius*omega*omega*sn, 0.), c['yaw_rad'])


class PIDLoop:
    """No ROS or physics imports needed to check the actual timestamp boundary."""
    def __init__(self, config, stack, hover):
        self.config = config
        self.pid = select_controller(config['controller'], PIDConfig(config['model']['mass_kg'], **config['pid']))
        self.thrust = NativeThrustConfig(stack, config['model']['identity'], config['model']['mass_kg'], hover)
        self.reset('selection')

    def reset(self, reason, stamp=None):
        self.pid.reset(reason)
        self.stamp = stamp

    def update(self, stamp, state, desired, *, active):
        if not active:
            self.reset('native_authority_lost')
            raise RuntimeError('PID requires verified native external-control authority')
        if not math.isfinite(stamp) or stamp <= 0:
            self.reset('invalid_native_time')
            raise ValueError('Invalid native State timestamp')
        if self.stamp is None:
            self.stamp = stamp
            return None
        dt = stamp-self.stamp
        if dt == 0:
            return None
        if not 0 < dt <= self.config['timing']['maximum_native_dt_s']:
            self.reset('native_time_discontinuity')
            raise RuntimeError('PID native State timestamp discontinuity')
        output = self.pid.update(state, desired, dt_s=dt, external_control_active=True)
        self.stamp = stamp
        collective = self.thrust.normalized_collective(output, model_identity=self.config['model']['identity'])
        return dict(native_state_stamp_s=stamp, dt_s=dt, controller='pid',
            state=asdict(state), reference=asdict(desired), output=asdict(output),
            normalized_collective=collective, native_thrust_convention=(
                [0., 0., -collective] if self.thrust.stack == 'px4' else collective))


def event_for(config, run_id, origin_tick):
    d = config['disturbance']
    start = origin_tick+d['lead_ticks']
    end = start+d['duration_ticks']
    return dict(schema='wksim.pid-disturbance.v1', run_id=run_id,
        protocol_sha256=CONFIG_SHA256, stage='pid_disturbance', declared_origin_tick=origin_tick,
        permitted_start_tick=origin_tick, permitted_end_tick=end+round(d['return_deadline_s']*1000),
        start_tick=start, end_tick=end, multiplier=d['multiplier'], channels=d['channels'],
        tick_semantics='zero-based integration interval [tick,tick+1); start inclusive, end exclusive')


def freeze_event(directory, event):
    """Atomic publication with exclusive hard-link creation; neither path is overwritten."""
    directory = Path(directory)
    raw = (json.dumps(event, sort_keys=True, separators=(',', ':'))+'\n').encode()
    prepared, target = directory/'disturbance-event.prepared.json', directory/'disturbance-event.json'
    with prepared.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(prepared, target)
    return hashlib.sha256(raw).hexdigest()


class PIDTask(AttitudeTask):
    def __init__(self, *args, pid_config, **kwargs):
        if pid_config != load_config(CONFIG_PATH):
            raise ValueError('PIDTask requires the exact frozen configuration')
        self.pid_config = pid_config
        self.pid_loop = None
        self.pid_measuring = False
        self.pid_pending = None
        self.pid_origin = None
        self.pid_kind = None
        self.pid_identity = None
        self.pid_updates = 0
        self.pid_duplicate_states = 0
        super().__init__(*args, **kwargs)
        # Reuse the observer's internal dictionary only. Never expose #34 step
        # completion or claim this task ran AttitudeTask.execute().
        self.attitude_result.update(controller='pid', status='not_started', protocol_sha256=CONFIG_SHA256,
            configuration=pid_config, scope=pid_config['scope'],
            observer_reuse='AttitudeTask observation/entry/preparation helpers; no attitude-step experiment',
            metrics=[], implementation='Simulator.wksim_control.position_pid.PositionPID')
        self.pid_trace = (self.directory/'pid-trace.jsonl').open('x', buffering=1)

    def mark(self, label, **data):
        row = dict(phase=label, measured_external_pid=self.pid_measuring,
            observed_monotonic_s=time.monotonic(), observed_unix_ns=time.time_ns(),
            native_boot_s=state_time(self.state) if self.state is not None else None,
            physical_cursor=self.cursor(), state=self.convert(self.state) if self.state is not None else None, **data)
        self.attitude_result['phases'].append(row)
        write_json(self.directory/'pid-progress.json', self.attitude_result)

    def command(self, label, **kwargs):
        if self.pid_measuring:
            raise RuntimeError('Preparation/native position helper is forbidden during PID measurement')
        return super().command(label, **kwargs)

    def authority(self):
        if (not self.fresh() or not self.state.armed
                or self.state.mode != ('GUIDED' if self.flight_stack == 'arducopter' else 'OFFBOARD')
                or (self.epoch, self.native_generation) != self.pid_identity):
            return False
        control = self.latest.get('control_state')
        if control is None or control.control_state != control.COMMAND_CONTROL:
            return False
        if self.flight_stack == 'px4':
            if not self.control_modes:
                return False
            mode = self.control_modes[-1]
            flags = mode['flags']
            return (self.read_truth()['time']-mode['physical_time'] <= .75
                and all(flags.get(k, False) for k in MODE_TRUE)
                and not any(flags.get(k, True) for k in MODE_FALSE))
        return True  # GUIDED plus verified GUID_OPTIONS bit 3 and native entry target.

    def check_pending(self):
        if self.pid_pending is None:
            return True
        request = self.pid_pending
        matches = [e for e in self.events[request['events_start']:]
                   if e.get('request_id') == request['request_id']
                   and e.get('command_id') == request['command_id']
                   and e.get('event') == 'command_accepted']
        if matches:
            self.record('pid_public_acknowledged', request_id=request['request_id'],
                        command_id=request['command_id'], event=matches[0], physical_cursor=self.cursor())
            self.pid_pending = None
            self.pending_request_id = None
            return True
        if (self.read_truth()['time']-request['physical_time'] > self.pid_config['timing']['ack_timeout_s']
                or time.monotonic()-request['wall'] > 2):
            raise TimeoutError('PID public request acknowledgement deadline')
        return False

    def offer_pid(self):
        if not self.authority():
            self.pid_loop.reset('native_authority_lost')
            raise RuntimeError('PID lost native external-control authority')
        if not self.check_pending():
            return
        stamp = state_time(self.state)
        q = self.state.attitude_q
        physical_time = self.read_truth()['time']
        desired = reference(self.pid_config, self.pid_kind, physical_time-self.pid_origin)
        row = self.pid_loop.update(stamp, PIDState(tuple(self.state.position), tuple(self.state.velocity),
            (q.w, q.x, q.y, q.z)), desired, active=True)
        if row is None:
            self.pid_duplicate_states += 1
            return
        self.command_number += 1
        msg = self.Cmd(agent_cmd=self.Cmd.MOVE, command_id=self.command_number, move_mode=self.Cmd.XYZ_ATT,
            att_ref=[*row['output']['roll_pitch_yaw_enu_rad'], row['normalized_collective']])
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.header.frame_id = 'map'
        self.request_id += 1
        outgoing = self.CommandRequest(version=1, run_id=self.run_id, control_epoch=self.epoch,
                                       request_id=self.request_id, command=msg)
        envelope = self.convert(outgoing)
        self.sent.append(self.convert(msg))
        self.envelopes.append(envelope)
        row.update(run_id=self.run_id, control_epoch=self.epoch, native_generation=self.native_generation,
            public_request_id=self.request_id, public_command_id=self.command_number,
            public_move_mode=int(msg.move_mode), public_envelope=envelope, stage=self.pid_kind,
            physical_time=physical_time, reference_origin_physical_s=self.pid_origin,
            model_identity=self.pid_config['model']['identity'], mass_kg=self.pid_config['model']['mass_kg'],
            protocol_sha256=CONFIG_SHA256, calibration=self.pid_loop.thrust.hover_thrust)
        self.pid_trace.write(json.dumps(row, allow_nan=False)+'\n')
        self.log.write(json.dumps(dict(wall=time.monotonic()-self.started, published='CommandRequest',
                                      message=envelope, request_envelope=True))+'\n')
        self.pending_request_id = self.request_id
        self.pid_pending = dict(request_id=self.request_id, command_id=self.command_number,
            events_start=len(self.events), physical_time=physical_time, wall=time.monotonic())
        self.command_pub.publish(outgoing)
        self.pid_updates += 1

    def stage(self, kind, settle, measure, *, disturbance=False):
        point = self.pid_config['point']
        hover = self.pid_loop.thrust.hover_thrust
        self.attitude_entry('pid_'+kind+'_entry', point['yaw_rad'], hover)
        # Also confirms actual AP attitude publication; PX4 was mode-gated above.
        self.command('pid_'+kind+'_neutral', attitude=(0., 0., point['yaw_rad'], hover))
        self.pid_identity = (self.epoch, self.native_generation)
        self.pid_kind, self.pid_origin = kind, self.read_truth()['time']
        self.pid_loop.reset('takeover_'+kind, state_time(self.state))
        self.pid_measuring = True
        self.mark('pid_'+kind+'_begin', physical_start=self.pid_origin, settle_s=settle,
                  measure_s=measure, reference_clock='model physical reception cursor')
        start_index = len(self.truth_rows)
        wall_end = time.monotonic()+max(30, (settle+measure)*3)
        event, event_sha = None, None
        try:
            while True:
                self.pump()
                self.offer_pid()
                value = self.read_truth()
                elapsed = value['time']-self.pid_origin
                if disturbance and event is None and elapsed >= settle:
                    origin_tick = math.ceil(value['time']*1000-1e-7)
                    event = event_for(self.pid_config, self.run_id, origin_tick)
                    event_sha = freeze_event(self.directory, event)
                    self.attitude_result['disturbance'] = dict(event=event, sha256=event_sha,
                        source='Actual model input command multiplier; not a motor-efficiency parameter')
                    self.mark('pid_disturbance_event_frozen', event=event, sha256=event_sha)
                end_time = (event['permitted_end_tick']/1000 if event else self.pid_origin+settle+measure)
                if value['time'] >= end_time:
                    break
                if time.monotonic() >= wall_end:
                    raise TimeoutError('PID '+kind+' physical duration deadline')
            while not self.check_pending():
                self.pump()
            rows = [r for r in self.truth_rows[start_index:]
                    if self.pid_origin+settle <= r['time'] <= end_time]
            metric = evaluate_rows(self.pid_config, kind, rows, self.pid_origin, event)
            self.attitude_result['metrics'].append(metric)
            self.mark('pid_'+kind+'_end', metric=metric, final_request_id=self.request_id)
            if not metric['online_ok']:
                raise RuntimeError('Frozen PID '+kind+' online physical budget failed')
        finally:
            self.pid_measuring = False
            self.pid_loop.reset('release_'+kind)

    def execute(self):
        self.attitude_result['status'] = 'running'
        point = tuple(self.pid_config['point']['position_enu_m'])
        yaw = self.pid_config['point']['yaw_rad']
        try:
            self.ground_parameters()
            self.wait('public_control_ready', lambda: self.fresh() and self.public_graph_ready(), 55)
            self.active = True
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'autonomous_hold_ready')
            if self.flight_stack == 'px4':
                completed = time.monotonic()
                self.wait('native_prearm_health_ready', lambda: self.arm_ready(completed), 55)
            self.send(self.Setup(cmd=self.Setup.ARMING, arming=True), 'arming_completed')
            self.wait('armed', lambda: self.state.armed)
            self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'), 'task_control_ready', 40)
            self.wait('takeoff_reached', lambda: self.state.position[2] >= 2.5, 25)
            self.command('native_position_preparation', position=point, yaw=yaw)
            self.wait('native_position_preparation_reached', lambda: self.fresh() and within(self.read_truth(), point, yaw,
                position=.25, speed=.15, tilt=2, heading=3), 30)
            self.envelope_anchor = point
            self.stable('native_hover_entry', point, yaw, timeout=15, dwell=2, position=.25, speed=.15, tilt=2, heading=3)
            start = self.read_truth()['time']
            self.duration('hover_observation', 3, lambda v: within(v, point, yaw, position=.25, speed=.15, tilt=2, heading=3))
            end = self.read_truth()['time']
            hover, samples = hover_median(self.native_samples, start, end)
            self.attitude_result['calibration'] = dict(stack=self.flight_stack, hover=hover,
                mass_kg=self.pid_config['model']['mass_kg'], model_identity=self.pid_config['model']['identity'],
                samples=samples, source='same-run native MAVLink ATTITUDE_TARGET collective',
                frozen_at_physical_time=end, status='frozen_pending_level_validation')
            self.mark('pid_hover_frozen')
            self.attitude_entry('pid_level_calibration_entry', yaw, hover)
            height = self.read_truth()['position'][2]
            start = self.command('pid_level_calibration', attitude=(0., 0., yaw, hover))
            self.duration('pid_level_calibration', 2, lambda v: abs(v['position'][2]-height) <= .3
                and abs(v['velocity'][2]) <= .2, start=start)
            self.attitude_result['calibration']['status'] = 'same_run_level_validated_frozen_before_PID'
            self.pid_loop = PIDLoop(self.pid_config, self.flight_stack, hover)
            write_json(self.directory/'pid-resolved-config.json', dict(configuration=self.pid_config,
                protocol_sha256=CONFIG_SHA256, calibration=self.attitude_result['calibration'],
                controller='pid', runtime_implementation='Simulator.wksim_control.position_pid.PositionPID'))
            self.recovery('native_calibration_recovery', point, yaw)
            self.stage('point', self.pid_config['point']['settle_s'], self.pid_config['point']['measure_s'])
            self.recovery('native_point_recovery', point, yaw)
            self.stage('circle', self.pid_config['circle']['settle_s'], self.pid_config['circle']['measure_s'])
            self.recovery('native_circle_recovery', point, yaw)
            d = self.pid_config['disturbance']
            self.stage('disturbance', d['settle_s'],
                       (d['lead_ticks']+d['duration_ticks'])*.001+d['return_deadline_s'], disturbance=True)
            self.recovery('native_disturbance_recovery', point, yaw)
            self.envelope_anchor = None
            self.command_number += 1
            self.send(self.Cmd(agent_cmd=self.Cmd.LAND, command_id=self.command_number), 'land_accepted')
            self.wait('landed_disarmed_public', lambda: grounded(self.state, self.uav_id), 30)
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'ground_hold_completed')
            self.attitude_result['status'] = 'completed_pending_raw_audit'
        except Exception as error:
            self.attitude_result.update(status='failed', error=str(error))
            self.pid_measuring = False
            if self.pid_loop is not None:
                self.pid_loop.reset('failure')
            with (self.directory/'pid-disturbance-revoked.json').open('x') as stream:
                json.dump(dict(run_id=self.run_id, reason=str(error)), stream)
            self.envelope_anchor = None
            if self.state is not None and self.state.armed:
                try:
                    self.command_number += 1
                    self.send(self.Cmd(agent_cmd=self.Cmd.LAND, command_id=self.command_number), 'failure_land_accepted')
                    self.wait('failure_landed', lambda: grounded(self.state, self.uav_id), 30)
                except Exception as cleanup:
                    self.attitude_result['landing_failure'] = str(cleanup)
            raise
        finally:
            self.attitude_result.update(pid_updates=self.pid_updates, duplicate_states_skipped=self.pid_duplicate_states)
            write_json(self.directory/'pid-progress.json', self.attitude_result)

    def report(self):
        return dict(Task.report(self), external_pid=self.attitude_result)

    def close(self):
        try:
            super().close()
        finally:
            if getattr(self, 'pid_trace', None) is not None:
                self.pid_trace.close()


def evaluate_rows(config, kind, rows, origin, event=None):
    """Sparse online gate only; full 1ms/native-wire independent audit is mandatory."""
    from .attitude_task import physical
    if not rows:
        raise RuntimeError('Missing PID physical measurement samples')
    values = [physical(row) for row in rows]
    errors = [math.dist(v['position'], reference(config, kind, v['time']-origin).position_enu) for v in values]
    speeds = [math.hypot(*v['velocity']) for v in values]
    yaw_errors = [abs(math.remainder(v['attitude'][2]-reference(config, kind, v['time']-origin).yaw_enu_rad,
                                     2*math.pi)) for v in values]
    budget = config[kind]
    result = dict(kind=kind, first_time=values[0]['time'], last_time=values[-1]['time'], samples=len(rows),
        max_position_error_m=max(errors), max_speed_mps=max(speeds), max_yaw_error_rad=max(yaw_errors),
        scope='20ms online truth samples; full 1ms and native command audit pending')
    ok = max(errors) <= budget['max_error_m']
    if kind == 'point':
        ok = ok and max(speeds) <= budget['max_speed_mps']
    if kind != 'disturbance':
        ok = ok and max(yaw_errors) <= budget['max_yaw_error_rad']
    else:
        if event is None:
            raise ValueError('Disturbance measurement needs a frozen event')
        # Require the final fixed dwell, not a transient crossing later lost.
        end = event['permitted_end_tick']/1000
        dwell = [i for i, v in enumerate(values) if end-budget['return_dwell_s'] <= v['time'] <= end]
        returned = (bool(dwell) and values[dwell[0]]['time'] <= end-budget['return_dwell_s']+.025
            and values[dwell[-1]]['time'] >= end-.025
            and all(errors[i] <= budget['return_error_m'] and speeds[i] <= budget['return_speed_mps']
                    and yaw_errors[i] <= budget['return_yaw_error_rad'] for i in dwell))
        result.update(returned_for_final_dwell=returned, return_deadline_physical_s=end)
        ok = ok and returned
    result['online_ok'] = bool(ok)
    return result
