"""Explicit candidate public P+V task and passive raw DDS recorder; no admission."""
import json
import math
from pathlib import Path
import time
import uuid

from Simulator.wksim_runtime.evidence import write_json
from Simulator.wksim_runtime.task import Task, grounded

PROFILE = 'full_xyz_pv_yaw_v1'
DURATION = 12.0
DELTAS = ((1.5, 1.0, .4, .6), (-1.0, .5, -.2, -.3))


def reference(elapsed, position, yaw, leg):
    """Fixed minimum-jerk reference; acceleration is retained, not executed."""
    if leg not in (1, 2) or not math.isfinite(elapsed):
        raise ValueError('Invalid trajectory time or leg')
    s = max(0., min(1., elapsed / DURATION))
    q = 10*s**3 - 15*s**4 + 6*s**5
    dq = (30*s**2 - 60*s**3 + 30*s**4) / DURATION
    ddq = (60*s - 180*s**2 + 120*s**3) / DURATION**2
    delta = DELTAS[leg-1]
    return (tuple(p+d*q for p, d in zip(position, delta)),
            tuple(d*dq for d in delta[:3]), tuple(d*ddq for d in delta[:3]), yaw+delta[3]*q)


class PVTask(Task):
    def __init__(self, directory, *args, trajectory_epoch, **kwargs):
        super().__init__(directory, *args, **kwargs)
        self.directory = Path(directory)
        self.scene_epoch = trajectory_epoch
        self.pv_legs = []
        self.command_id = 0
        self.pv_request_graph = {}

    def request_graph_ready(self):
        """Exactly one controller plus this experiment's named passive recorder."""
        expected = {'wksim_joint_'+self.flight_stack+'_control', 'wksim_joint_flight_clock'}
        observations = {}
        for kind, publisher in (('setup', self.setup_pub), ('command', self.command_pub)):
            endpoints = self.node.get_subscriptions_info_by_topic(self.topic_root+'v2/'+kind)
            if (publisher.get_subscription_count() != 2 or len(endpoints) != 2
                    or {info.node_name for info in endpoints} != expected
                    or any(info.node_namespace != '/' for info in endpoints)):
                return False
            observations[kind] = [dict(node_name=info.node_name, node_namespace=info.node_namespace,
                                       endpoint_gid=bytes(info.endpoint_gid).hex()) for info in endpoints]
        self.pv_request_graph = observations
        return True

    def offer(self, label, **fields):
        self.command_id += 1
        self.send(self.Cmd(command_id=self.command_id, **fields), label)

    def tracked(self, position, velocity, yaw):
        return (self.fresh() and math.dist(self.state.position, position) <= .5
                and all(abs(a-b) <= .3 for a, b in zip(self.state.velocity, velocity))
                and abs((self.state.attitude[2]-yaw+math.pi) % (2*math.pi)-math.pi) <= .15)

    def execute(self):
        self.wait('public_control_ready', lambda: self.fresh() and self.request_graph_ready(), 55)
        if not grounded(self.state, self.uav_id):
            raise RuntimeError('Candidate task requires disarmed ground state')
        self.active = True
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'autonomous_hold_ready')
        if self.flight_stack == 'px4':
            completed = time.monotonic()
            self.wait('native_prearm_health_ready', lambda: self.arm_ready(completed), 55)
        self.send(self.Setup(cmd=self.Setup.ARMING, arming=True), 'arming_completed')
        self.wait('armed', lambda: self.state.armed)
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'), 'task_control_ready', 40)
        self.wait('takeoff_reached', lambda: self.state.position[2] >= 2.5, 25)
        self.dwell('hold_completed', lambda: abs(self.state.position[2]-3) <= .6
                   and max(abs(v) for v in self.state.attitude[:2]) <= .35, 5)
        self.offer('waypoint_accepted', agent_cmd=self.Cmd.MOVE, move_mode=self.Cmd.XYZ_POS,
                   position_ref=[2., 3., 3.], yaw_ref=0.)
        at_waypoint = lambda: (math.dist(self.state.position, [2, 3, 3]) <= .5
                              and math.hypot(*self.state.velocity) <= .5
                              and abs((self.state.attitude[2]+math.pi) % (2*math.pi)-math.pi) <= .15)
        self.wait('waypoint_reached', at_waypoint)
        self.dwell('waypoint_completed', at_waypoint, 2)
        for leg in (1, 2):
            self.fly_leg(leg)
        self.offer('land_accepted', agent_cmd=self.Cmd.LAND, control_level=self.Cmd.EXIT_ABSOLUTE_CONTROL)
        self.wait('landed_disarmed_public', lambda: grounded(self.state, self.uav_id), 30)
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'ground_hold_completed')
        completed = time.monotonic()
        self.wait('normal_stop_ready', lambda: self.fresh() and grounded(self.state, self.uav_id)
                  and self.received.get('state', 0) > completed)

    def fly_leg(self, leg):
        position = [2., 3., 3.] if leg == 1 else list(self.state.position)
        yaw = 0. if leg == 1 else float(self.state.attitude[2])
        ready = dict(version=1, profile=PROFILE, leg=leg, run_id=self.run_id,
            scene_epoch=self.scene_epoch, control_epoch=self.epoch, uav_id=self.uav_id,
            token=uuid.uuid4().hex, position=position, yaw=yaw)
        write_json(self.directory/f'pv-ready-{leg}.json', ready)
        path = self.directory.parent/f'pv-go-{leg}.json'
        self.wait(f'pv_{leg}_offer_ready', path.is_file, 40)
        go = json.loads(path.read_text())
        if (go['version'] != 1 or go['profile'] != PROFILE or go['run_id'] != self.run_id
                or go['scene_epoch'] != self.scene_epoch or go['leg'] != leg
                or go['tasks'][self.flight_stack] != ready
                or type(go['issued_tick']) is not int or go['issued_tick'] % 4
                or go['start_ns'] != (go['issued_tick']+1000)*1_000_000
                or type(go['start_ns']) is not int or go['start_ns'] <= self.task_time()*1e9):
            raise ValueError('Trajectory offer is stale or belongs to another task')
        start = go['start_ns']/1e9
        self.wait(f'pv_{leg}_started', lambda: self.task_time() >= start)
        record = dict(ready=ready, offer=go, samples=[], acceleration_executed=False)
        self.pv_legs.append(record)
        previous = None
        while True:
            elapsed = self.task_time()-start
            if previous is not None and elapsed-previous > .25:
                raise RuntimeError('Trajectory public sampling exceeded 250ms')
            p, v, a, heading = reference(elapsed, position, yaw, leg)
            level = self.Cmd.EXIT_ABSOLUTE_CONTROL if leg == 2 and previous is None else self.Cmd.DEFAULT_CONTROL
            record['samples'].append(dict(ros_time_s=self.task_time(), elapsed=elapsed,
                                         position=p, velocity=v, acceleration=a, yaw=heading))
            self.offer(f'pv_{leg}_reference', agent_cmd=self.Cmd.MOVE, move_mode=self.Cmd.TRAJECTORY,
                       position_ref=list(p), velocity_ref=list(v), acceleration_ref=list(a),
                       yaw_ref=heading, control_level=level)
            if elapsed >= DURATION:
                break
            previous = elapsed
            while self.task_time()-start < min(DURATION, elapsed+.1):
                self.pump()
                actual = reference(self.task_time()-start, position, yaw, leg)
                if not self.tracked(actual[0], actual[1], actual[3]):
                    raise RuntimeError('Trajectory tracking exceeded frozen bounds')
        p, v, _, heading = reference(DURATION, position, yaw, leg)
        self.dwell(f'pv_{leg}_endpoint_prepared', self.fresh, 2)
        self.dwell(f'pv_{leg}_endpoint_held', lambda: self.tracked(p, v, heading), 2)
        record['stop_anchor'] = list(self.state.position)
        record['stop_yaw'] = float(self.state.attitude[2])
        record['stop_requested_ros_s'] = self.task_time()
        self.offer(f'pv_{leg}_stop_accepted', agent_cmd=self.Cmd.CURRENT_POS_HOVER,
                   control_level=self.Cmd.ABSOLUTE_CONTROL)
        self.dwell(f'pv_{leg}_stop_prepared', self.fresh, 2)
        self.dwell(f'pv_{leg}_stop_held', lambda: self.fresh() and math.hypot(*self.state.velocity) <= .25
                   and math.dist(self.state.position, record['stop_anchor']) <= 1., 4)

    def report(self):
        return dict(super().report(), pv_profile=PROFILE, pv_legs=self.pv_legs, pv_request_graph=self.pv_request_graph)


class PVProbe:
    """Retain original middleware-delivered CDR without reserializing it."""
    def __init__(self, node, clock, directory, started):
        import rclpy
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from prometheus_control.frames import topic
        from prometheus_msgs.msg import TextInfo
        from wksim_msgs.msg import CommandRequest, SetupRequest, SessionState
        from std_msgs.msg import Bool
        from ardupilot_msgs.msg import GlobalPosition, WksimState
        from px4_msgs.msg import TrajectorySetpoint, OffboardControlMode, VehicleLocalPosition, VehicleStatus
        self.node, self.clock, self.started, self.ros = node, clock, started, rclpy
        self.log = (directory/'pv-dds.jsonl').open('x', buffering=65536)
        self.sequence, self.subscriptions = 0, []
        channels = [('/ap/cmd_gps_pose', GlobalPosition), ('/ap/wksim/local_state_v1', WksimState)]
        for uid in (1, 2):
            channels += [(f'/uav{uid}/prometheus/'+suffix, cls) for suffix, cls in
                (('v2/command', CommandRequest), ('v2/setup', SetupRequest), ('v2/state', SessionState),
                 ('text_info', TextInfo), ('stop_control_state', Bool))]
        for direction, name, cls in (('in', 'trajectory_setpoint', TrajectorySetpoint),
                ('in', 'offboard_control_mode', OffboardControlMode), ('out', 'vehicle_local_position', VehicleLocalPosition),
                ('out', 'vehicle_status', VehicleStatus)):
            channels.append((topic('/wksim_px4_21', direction, name, cls), cls))
        qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)
        for name, cls in channels:
            self.subscriptions.append(node.create_subscription(cls, name,
                lambda raw, name=name: self.receive(name, raw), qos, raw=True))

    def receive(self, topic, raw):
        self.sequence += 1
        self.log.write(json.dumps(dict(sequence=self.sequence, epoch=self.clock.epoch, tick=self.clock.tick,
            wall=time.monotonic()-self.started, topic=topic, cdr_hex=bytes(raw).hex()), separators=(',', ':'))+'\n')

    def pump(self):
        self.ros.spin_once(self.node, timeout_sec=0)

    def close(self):
        for subscription in self.subscriptions:
            self.node.destroy_subscription(subscription)
        self.log.close()
