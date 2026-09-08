"""Frozen public mixed-axis candidate task; reference capture is not native ACK."""
import math
import time
from tools.pv_trajectory_task import PVTask
from Simulator.wksim_runtime.task import Task

PROFILE = 'xy_velocity_z_position_yaw_v1'


class MixedTask(PVTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mixed_segments = []

    def mixed(self, name, velocity, altitude, yaw=0., *, body=False, exit_absolute=False):
        self.offer(name+'_accepted', agent_cmd=self.Cmd.MOVE,
            move_mode=self.Cmd.XY_VEL_Z_POS_BODY if body else self.Cmd.XY_VEL_Z_POS,
            position_ref=[0., 0., float(altitude)], velocity_ref=[*map(float, velocity), 0.], yaw_ref=float(yaw),
            control_level=self.Cmd.EXIT_ABSOLUTE_CONTROL if exit_absolute else self.Cmd.DEFAULT_CONTROL)
        if body:
            request_id, command_id = self.request_id, self.command_id
            def captured():
                return next((event for event in self.events if event['event'] == 'mixed_body_reference_captured'
                    and event.get('request_id') == request_id and event.get('command_id') == command_id), None)
            self.wait(name+'_capture_ready', lambda: captured() is not None, 10)
            capture = captured()
            return dict(velocity=capture['reference_velocity'][:2], altitude=capture['reference_position'][2],
                        yaw=capture['reference_yaw'], body_capture=capture)
        message = self.sent[-1]
        return dict(velocity=message['velocity_ref'][:2], altitude=message['position_ref'][2], yaw=float(yaw))

    def tracking(self, reference):
        return (self.fresh() and all(abs(a-b) <= .3 for a, b in zip(self.state.velocity[:2], reference['velocity']))
                and abs(self.state.position[2]-reference['altitude']) <= .5
                and abs(math.remainder(self.state.attitude[2]-reference['yaw'], 2*math.pi)) <= .15)

    def window(self, name, predicate, seconds, reference, **extra):
        self.phase(name+'_started')
        item = dict(name=name, command_id=self.command_id, request_id=self.request_id, reference=reference,
                    start_ns=self.node.get_clock().now().nanoseconds, start_state=self.convert(self.state),
                    status='running', **extra)
        self.mixed_segments.append(item)
        self.dwell(name+'_completed', predicate, seconds)
        item.update(end_ns=self.node.get_clock().now().nanoseconds, end_state=self.convert(self.state), status='pass')

    def moving(self, name, velocity, altitude, yaw=0., *, body=False):
        reference = self.mixed(name, velocity, altitude, yaw, body=body)
        self.wait(name+'_ready', lambda: self.tracking(reference), 20)
        self.window(name, lambda: self.tracking(reference), 3, reference)

    def zero(self, name, altitude, *, body=False):
        anchor = [float(v) for v in self.state.position]
        reference = self.mixed(name, (0., 0.), altitude, body=body)
        if body:
            anchor = list(reference['body_capture']['shaped_position'])
        self.dwell(name+'_prepared', self.fresh, 2)
        held = lambda: (self.tracking(reference) and math.hypot(*self.state.velocity) <= .25
                        and math.dist(self.state.position, anchor) <= 1.)
        settling = self.stable_hold(name, held)
        self.window(name, held, 4, reference, anchor=anchor, hold_settling=settling)
        return reference, anchor

    def stable_hold(self, name, predicate):
        began, stable_since = time.monotonic(), None
        record = dict(started_monotonic_s=began, wall_limit_s=12., stable_minimum_s=1.5)
        def stable():
            nonlocal stable_since
            wall, now = time.monotonic(), self.task_time()
            if wall-began > 12:
                raise TimeoutError(name+': stable hold preparation exceeded 12 wall seconds')
            if not predicate():
                stable_since = None
                return False
            if stable_since is None:
                stable_since = now
            if now-stable_since < 1.5:
                return False
            record.update(stable_from_s=stable_since, ready_s=now, ready_monotonic_s=wall)
            return True
        self.wait(name+'_stable', stable, 20)
        return record

    def absolute_stop(self, name):
        anchor = [float(v) for v in self.state.position]
        yaw = float(self.state.attitude[2])
        self.offer(name+'_accepted', agent_cmd=self.Cmd.CURRENT_POS_HOVER, control_level=self.Cmd.ABSOLUTE_CONTROL)
        self.dwell(name+'_prepared', self.fresh, 2)
        held = lambda: (self.fresh() and math.hypot(*self.state.velocity) <= .25
                        and math.dist(self.state.position, anchor) <= 1.
                        and abs(math.remainder(self.state.attitude[2]-yaw, 2*math.pi)) <= .15)
        settling = self.stable_hold(name, held)
        self.window(name, held, 4, dict(altitude=anchor[2], yaw=yaw), anchor=anchor, hold_settling=settling)

    def fly_leg(self, leg):
        if leg == 1:
            self.moving('world_step', (.8, .4), 4.)
            self.moving('world_reverse', (-.4, .6), 3.)
            anchor = [float(v) for v in self.state.position]
            reference = self.mixed('world_one_axis', (0., .6), 3.)
            self.dwell('world_one_axis_prepared', self.fresh, 2)
            self.window('world_one_axis', lambda: self.tracking(reference) and abs(self.state.velocity[0]) <= .25
                        and abs(self.state.position[0]-anchor[0]) <= 1., 4, reference, anchor=anchor)
            reference, anchor = self.zero('world_zero', 3.)
            if self.flight_stack == 'arducopter':
                self.command_id += 1
                self.offer_rejected(self.Cmd(agent_cmd=self.Cmd.MOVE, move_mode=self.Cmd.XY_VEL_Z_POS,
                    command_id=self.command_id, position_ref=[0., 0., 3.], velocity_ref=[1., 0., 0.],
                    yaw_rate_mode=True, yaw_rate_ref=.5), 'arducopter_mixed_requires_yaw_angle',
                    'invalid_world_yaw_rate_rejected')
                self.window('invalid_world_yaw_rate', lambda: self.tracking(reference)
                    and math.hypot(*self.state.velocity) <= .25 and math.dist(self.state.position, anchor) <= 1.,
                    2, reference, anchor=anchor)
            self.moving('world_reentry', (.4, -.3), 3.6)
            self.absolute_stop('world_absolute_stop')
        else:
            position = [float(v) for v in self.state.position]
            self.offer('body_heading_accepted', agent_cmd=self.Cmd.MOVE, move_mode=self.Cmd.XYZ_POS,
                position_ref=position, yaw_ref=.6, control_level=self.Cmd.EXIT_ABSOLUTE_CONTROL)
            at_heading = lambda: (self.fresh() and math.dist(self.state.position, position) <= .5
                and math.hypot(*self.state.velocity) <= .5
                and abs(math.remainder(self.state.attitude[2]-.6, 2*math.pi)) <= .15)
            self.wait('body_heading_ready', at_heading, 20)
            self.window('body_heading', at_heading, 2, dict(position=position, yaw=.6))
            self.moving('body_step', (.8, .4), 1., .3, body=True)
            self.zero('body_zero', 0., body=True)
            self.absolute_stop('body_absolute_stop')

    def report(self):
        return dict(Task.report(self), mixed_profile=PROFILE, mixed_segments=self.mixed_segments,
                    mixed_request_graph=self.pv_request_graph)
