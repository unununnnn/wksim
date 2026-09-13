"""One GNSS outage and explicit fresh task recovery on real native feedback."""
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from .rc_task import RCTask
from .efficiency_task import EfficiencyTask
from .task import Task,grounded
from Simulator.wksim_core.motor_efficiency_event import publish_plan,load_plan
from Simulator.wksim_control.gnss_recovery_frame import local_after_home_change

PROFILE_PATH=Path(__file__).with_name('gnss-flight-v3.json')
PROFILE_SHA='0f075f81a7ce9393d2108217c25afa1b1330293b22387d4de275cd62698c4a0a'


def load_profile(path=PROFILE_PATH):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROFILE_SHA:raise ValueError('Frozen GNSS profile differs')
    return json.loads(raw)


class GNSSTask(RCTask):
    truth_rows=EfficiencyTask.truth_rows

    def __init__(self,directory,health,phase,flight_stack,*,scene_epoch,**kwargs):
        self.directory=Path(directory);self.profile=load_profile();self.scene_epoch=scene_epoch
        self._truth_stream=None;self._truth_cache=[];self.native_rows={};self.native_received={};self.native_stamps={}
        self.loss_expected=False;self.withdrawal=None;self.failure_cleanup=False
        super().__init__(directory,health,phase,flight_stack,scenario='movement',
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-',''),
            stream_id=uuid.uuid4().hex,truth_path=directory/'truth.jsonl',**kwargs)
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        from prometheus_control.frames import topic
        qos=QoSProfile(depth=500,reliability=ReliabilityPolicy.BEST_EFFORT)
        self.raw_subs.append(self.raw_node.create_subscription(self.CommandRequest,self.topic_root+'v2/command',lambda _:None,qos))
        if flight_stack=='px4':
            from px4_msgs.msg import SensorGps,VehicleLocalPosition,EstimatorStatusFlags,VehicleLandDetected
            channels=[(key,topic('/wksim_px4_21','out',name,cls),cls) for key,name,cls in (
                ('gps','vehicle_gps_position',SensorGps),('position','vehicle_local_position',VehicleLocalPosition),
                ('estimator','estimator_status_flags',EstimatorStatusFlags),('land','vehicle_land_detected',VehicleLandDetected))]
        else:
            from ardupilot_msgs.msg import WksimState,Status
            channels=[('position','/ap/wksim/local_state_v1',WksimState),('land','/ap/status',Status)]
        existing={sub.topic_name for sub in self.raw_subs}
        for key,name,cls in channels:
            self.subscriptions.append(self.node.create_subscription(cls,name,lambda msg,key=key:self.native_receive(key,msg),qos))
            if name not in existing:self.raw_subs.append(self.raw_node.create_subscription(cls,name,lambda _:None,qos))

    def native_receive(self,key,msg):
        stamp=(msg.timestamp if self.flight_stack=='px4' else msg.time_boot_us if key=='position' else
               msg.header.stamp.sec*10**9+msg.header.stamp.nanosec)
        previous=self.native_stamps.get(key,0)
        if stamp<previous:self.error='Native GNSS observation clock regressed'
        if stamp<=previous:return
        self.native_rows[key]=msg;self.native_stamps[key]=stamp;self.native_received[key]=time.monotonic()

    def native_fresh(self,*keys):
        now=time.monotonic()
        return all(key in self.native_rows and 0<=now-self.native_received[key]<=2 for key in keys)

    def navigation_ready(self):
        if self.flight_stack=='px4':
            if not self.native_fresh('gps','position','estimator'):return False
            p,e,g=(self.native_rows[k] for k in ('position','estimator','gps'))
            return g.fix_type>=3 and p.xy_valid and p.z_valid and p.v_xy_valid and p.v_z_valid and p.heading_good_for_control and not p.dead_reckoning and e.cs_tilt_align and e.cs_yaw_align
        if not self.native_fresh('position'):return False
        p=self.native_rows['position']
        return p.gps_fix_type>=3 and p.position_valid and p.velocity_valid and p.attitude_valid and p.ahrs_healthy and p.home_valid

    def native_on_ground(self):
        if not self.native_fresh('land'):return None
        return bool(self.native_rows['land'].landed if self.flight_stack=='px4' else not self.native_rows['land'].flying)

    def home(self):
        if self.flight_stack!='arducopter':return None
        if not self.native_fresh('position') or not self.native_rows['position'].home_valid:
            raise RuntimeError('Fresh native home required')
        msg=self.native_rows['position']
        return dict(latitude_e7=msg.home_latitude_e7,longitude_e7=msg.home_longitude_e7,altitude_cm=msg.home_altitude_cm)

    def pump(self):
        super().pump()
        if self.loss_expected and not self.active:
            now=time.monotonic()
            if self.state is None or not self.state.connected or now-self.received.get('state',0)>2 or now-self.advanced_at>2:
                raise RuntimeError('GNSS observation lost the native transport/state clock')
        if not self.failure_cleanup and (self.directory/'gnss-failure.json').exists():raise RuntimeError('GNSS physical envelope failed')

    def receive(self,key,msg):
        count=len(self.events)
        super().receive(key,msg)
        if self.loss_expected and key=='text_info' and len(self.events)>count:
            event=self.events[-1]
            if event.get('event')=='control_revoked':self.on_control_revoked(event)
            elif event.get('event') in ('setup_rejected','command_rejected') and event.get('request_id')==self.pending_request_id:
                self.error='Explicit GNSS recovery request rejected: '+str(event)

    def on_control_revoked(self,event):
        if self.loss_expected and event.get('reason') in ('native_navigation_invalid_control_released',
                'native_failsafe_control_released','native_clock_or_origin_reset','external_mode_left_no_automatic_reacquisition'):
            if self.withdrawal is None:self.withdrawal=event
            self.active=False
            return
        super().on_control_revoked(event)

    def hold(self,label,point,seconds):
        since=None
        def ready():
            nonlocal since
            row=self.truth_rows()[-1];p=self.profile
            valid=self.fresh() and math.dist(row['position'],point)<=p['position_error_m'] and math.hypot(*row['velocity'])<=p['speed_mps'] and abs(math.remainder(row['yaw'],2*math.pi))<=p['yaw_error_rad']
            if not valid:since=None;return False
            if since is None:since=row['time']
            return row['time']-since>=seconds
        self.wait(label,ready,45)

    def move(self,point,number,label):
        self.send(self.Cmd(agent_cmd=self.Cmd.MOVE,move_mode=self.Cmd.XYZ_POS,position_ref=point,
                          yaw_ref=0.,command_id=number),label)

    def execute(self):
        try:
            self.wait('public_ready',lambda:self.fresh() and self.epoch is not None and self.setup_pub.get_subscription_count()==2 and self.command_pub.get_subscription_count()==2,55)
            keys=('gps','position','estimator','land') if self.flight_stack=='px4' else ('position','land')
            self.wait('native_observers_ready',lambda:self.native_fresh(*keys),10)
            if not grounded(self.state):raise RuntimeError('GNSS run requires initial disarmed ground state')
            self.active=True
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE,px4_mode='AUTO.LOITER'),'initial_native_hold')
            if self.flight_stack=='px4':
                after=time.monotonic();self.wait('native_prearm_ready',lambda:self.arm_ready(after),55)
            self.send(self.Setup(cmd=self.Setup.ARMING,arming=True),'initial_arm')
            self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE,control_state='COMMAND_CONTROL'),'initial_takeoff',45)
            initial_home=self.home()
            self.phase('initial_navigation_frame',home=initial_home)
            self.move(self.profile['point_enu_m'],1,'initial_point_accepted')
            self.hold('initial_stable_hold',self.profile['point_enu_m'],self.profile['stable_seconds'])
            self.loss_expected=True;self.active=False
            publish_plan(self.directory/'gnss-arm.json',dict(run_id=self.run_id,scene_epoch=self.scene_epoch,
                         control_epoch=self.epoch,profile_sha256=PROFILE_SHA))
            self.wait('gnss_plan_committed',lambda:(self.directory/'gnss-plan.json').exists(),5)
            plan=load_plan(self.directory/'gnss-plan.json')
            if plan['control_epoch']!=self.epoch or plan['scene_epoch']!=self.scene_epoch:raise RuntimeError('GNSS plan identity mismatch')
            self.phase('gnss_outage_planned',plan=plan)
            self.wait('gnss_control_withdrawn',lambda:self.withdrawal is not None,25)
            if self.flight_stack=='arducopter':
                self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE,px4_mode='AUTO.LAND'),'explicit_loss_land',10)
            self.wait('gnss_outage_finished',lambda:self.truth_rows()[-1]['time']*1000>=plan['end_tick'],25)
            self.wait('native_navigation_returned',self.navigation_ready,self.profile['recovery_timeout_s'])
            before=len(self.events);until=time.monotonic()+1.
            while time.monotonic()<until:
                self.pump()
                control=self.latest.get('control_state')
                if control is not None and control.control_state!=control.INIT:raise RuntimeError('Task control automatically reacquired')
            self.phase('no_automatic_reacquisition')
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE,px4_mode='AUTO.LOITER'),'explicit_recovery_hold')
            self.wait('recovery_public_ready',self.fresh,15)
            if self.native_on_ground() is True:
                self.wait('recovery_disarmed_ground',lambda:grounded(self.state),15)
                if self.flight_stack=='px4':
                    after=time.monotonic();self.wait('recovery_prearm_ready',lambda:self.arm_ready(after),30)
                self.send(self.Setup(cmd=self.Setup.ARMING,arming=True),'explicit_recovery_arm')
            self.loss_expected=False;self.active=True
            self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE,control_state='COMMAND_CONTROL'),'explicit_new_takeover',45)
            current_home=self.home()
            local=(local_after_home_change(self.profile['recovery_point_enu_m'],initial_home,current_home)
                   if initial_home is not None else self.profile['recovery_point_enu_m'])
            self.phase('recovery_navigation_frame',initial_home=initial_home,current_home=current_home,
                       world_point=self.profile['recovery_point_enu_m'],local_point=local)
            # Preserve the same goal while avoiding an abrupt multi-metre
            # position step after a landing/home change.
            initial=[float(v) for v in self.state.position];duration=max(1.,math.dist(initial,local)/self.profile['speed_mps'])
            started=self.task_time();number=2
            self.phase('recovery_reference_ramp',initial_local=initial,target_local=local,duration_s=duration)
            while self.task_time()-started<duration:
                fraction=min(1.,(self.task_time()-started)/duration)
                self.move([a+(b-a)*fraction for a,b in zip(initial,local)],number,'recovery_segment_'+str(number))
                number+=1;self.pump();time.sleep(.04)
            self.move(local,number,'new_point_accepted')
            self.hold('recovery_point_completed',self.profile['recovery_point_enu_m'],2.)
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE,px4_mode='AUTO.LAND'),'final_land')
            self.wait('landed_disarmed',lambda:grounded(self.state),45)
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE,px4_mode='AUTO.LOITER'),'ground_hold_completed')
        except Exception:
            self.failure_cleanup=True;self.loss_expected=False;self.active=False;self.error=None
            try:
                self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE,px4_mode='AUTO.LAND'),'failure_land',10)
                self.wait('failure_ground',lambda:grounded(self.state),30)
            except Exception as error:self.log.write(json.dumps(dict(failure_landing_error=repr(error)))+'\n')
            raise

    def report(self):
        return dict(Task.report(self),gnss=dict(scene_epoch=self.scene_epoch,profile=self.profile,
                    withdrawal=self.withdrawal,phases=self.rc_phases))

    def close(self):
        if self._truth_stream is not None:self._truth_stream.close()
        super().close()
