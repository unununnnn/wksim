"""Native-position efficiency task; reuse raw DDS observation, never RC execution."""
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from .rc_task import RCTask,physical
from .task import Task,grounded
from Simulator.wksim_core.motor_efficiency_event import publish_plan,load_plan

PROFILE_PATH=Path(__file__).with_name('efficiency-flight-v1.json')
PROFILE_SHA='f2ad9a91612dbda09150ee99bad581fce3dda50b072733a9aea6ee5bb379ec47'


def load_profile(path=PROFILE_PATH):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROFILE_SHA:raise ValueError('Frozen efficiency flight profile differs')
    return json.loads(raw)


class EfficiencyTask(RCTask):
    def __init__(self,directory,health,phase,flight_stack,*,case,**kwargs):
        if case not in ('baseline','fault'):raise ValueError('Select baseline or fault')
        self.directory=Path(directory);self.case=case;self.profile=load_profile()
        self._truth_stream=None;self._truth_cache=[];self.recovering=False
        super().__init__(directory,health,phase,flight_stack,scenario='movement',
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-',''),
            stream_id=uuid.uuid4().hex,truth_path=directory/'truth.jsonl',**kwargs)
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        self.raw_subs.append(self.raw_node.create_subscription(self.CommandRequest,self.topic_root+'v2/command',
            lambda _:None,QoSProfile(depth=500,reliability=ReliabilityPolicy.BEST_EFFORT)))

    def truth_rows(self):
        if self._truth_stream is None and Path(self.truth_path).exists():self._truth_stream=Path(self.truth_path).open()
        if self._truth_stream is not None:
            while True:
                offset=self._truth_stream.tell();line=self._truth_stream.readline()
                if not line.endswith('\n'):
                    self._truth_stream.seek(offset);break
                row=physical(json.loads(line))
                if self._truth_cache and row['time']<=self._truth_cache[-1]['time']:raise ValueError('Efficiency physical time regressed')
                self._truth_cache.append(row)
        return self._truth_cache

    def pump(self):
        super().pump()
        if not self.recovering and (self.directory/'efficiency-failure.json').exists():
            raise RuntimeError('Native efficiency envelope failed')

    def stable(self):
        rows=self.truth_rows()
        if not rows or not self.fresh():return False
        row=rows[-1];p=self.profile
        return (math.dist(row['position'],p['point_enu_m'])<=p['position_error_m']
                and math.hypot(*row['velocity'])<=p['speed_mps']
                and abs(math.remainder(row['yaw']-p['yaw_enu_rad'],2*math.pi))<=p['yaw_error_rad'])

    def execute(self):
        try:
            self.wait('public_control_ready',lambda:self.fresh() and self.epoch is not None
                      and self.setup_pub.get_subscription_count()==2 and self.command_pub.get_subscription_count()==2,55)
            if not grounded(self.state):raise RuntimeError('Efficiency requires disarmed ground start')
            self.active=True
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE,px4_mode='AUTO.LOITER'),'autonomous_hold_ready')
            if self.flight_stack=='px4':
                after=time.monotonic();self.wait('native_prearm_health_ready',lambda:self.arm_ready(after),55)
            self.send(self.Setup(cmd=self.Setup.ARMING,arming=True),'arming_completed')
            self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE,control_state='COMMAND_CONTROL'),'command_takeoff_completed',45)
            self.send(self.Cmd(agent_cmd=self.Cmd.MOVE,move_mode=self.Cmd.XYZ_POS,
                position_ref=self.profile['point_enu_m'],yaw_ref=self.profile['yaw_enu_rad'],command_id=1),'efficiency_point_accepted')
            self.wait('efficiency_point_reached',self.stable,30)
            stable_since=None
            def continuous_hold():
                nonlocal stable_since
                if not self.stable():
                    stable_since=None
                    return False
                now=self.truth_rows()[-1]['time']
                if stable_since is None:stable_since=now
                return now-stable_since>=self.profile['stable_seconds']
            # The six-second qualification starts again after a settling
            # excursion; no efficiency event has been authorized at this point.
            self.wait('efficiency_stable_six_seconds',continuous_hold,45)
            publish_plan(self.directory/'efficiency-arm.json',dict(run_id=self.run_id,control_epoch=self.epoch,
                         case=self.case,config_sha256=PROFILE_SHA))
            self.wait('physics_origin_committed',lambda:(self.directory/'efficiency-origin.json').exists(),5)
            origin=load_plan(self.directory/'efficiency-origin.json')
            if origin['run_id']!=self.run_id or origin['control_epoch']!=self.epoch:
                raise RuntimeError('Wrong physics-owned event origin')
            self.phase('efficiency_window_begin',origin=origin)
            self.wait('efficiency_window_completed',lambda:self.truth_rows()[-1]['time']*1000>=origin['recovery_deadline_tick'],30)
            if not self.stable():raise RuntimeError('Efficiency recovery endpoint not stable')
            self.phase('efficiency_recovery_observed')
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE,px4_mode='AUTO.LAND'),'land_mode_completed')
            self.wait('landed_disarmed_public',lambda:grounded(self.state),60)
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE,px4_mode='AUTO.LOITER'),'ground_hold_completed')
        except Exception:
            if not (self.directory/'efficiency-revoked.json').exists():
                publish_plan(self.directory/'efficiency-revoked.json',dict(reason='task_failed',run_id=self.run_id))
            self.recovering=True;self.active=False;self.error=None
            try:
                self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE,px4_mode='AUTO.LAND'),'failure_land_requested',10)
                self.wait('failure_landed',lambda:grounded(self.state),self.profile['failure_landing_timeout_s'])
            except Exception as error:
                self.log.write(json.dumps(dict(failure_landing_error=repr(error)))+'\n')
            raise

    def report(self):
        return dict(Task.report(self),efficiency=dict(case=self.case,profile=self.profile,phases=self.rc_phases,
                    observer_reuse='raw DDS only; no RC frames or RC scenario executed'))

    def close(self):
        if self._truth_stream is not None:self._truth_stream.close()
        super().close()
