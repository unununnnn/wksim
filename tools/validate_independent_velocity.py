"""Formal independent position baseline, velocity/hold/yaw profile and landing."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

from Simulator.wksim_runtime.config import load_config,validate_config
from Simulator.wksim_runtime.independent_profile import select_config
from Simulator.wksim_runtime.runtime import run,truth_summary
from Simulator.wksim_runtime.task import Task,state_time


class IndependentVelocityTask(Task):
    def __init__(self,directory,health,phase,*args,**kwargs):
        self.directory=directory
        self.velocity_phases=[]
        def record(label):
            row=dict(phase=label,observed_monotonic_s=time.monotonic(),
                observed_unix_ns=self.node.get_clock().now().nanoseconds,
                native_boot_s=state_time(self.state),state=self.convert(self.state),
                physical_cursor=truth_summary(directory/'truth.jsonl'))
            self.velocity_phases.append(row)
            (directory/'velocity-phases.json').write_text(json.dumps(self.velocity_phases,indent=2)+'\n')
            phase(label)
        super().__init__(directory,health,record,*args,**kwargs)

    def send(self,message,label,timeout=10):
        # One actual position baseline precedes the frozen velocity profile.
        if isinstance(message,self.Cmd):
            if label=='land_accepted':
                self.extra_profiles()
                message.command_id=9
            elif not label.startswith('position_baseline'):
                message.command_id+=1
        return super().send(message,label,timeout)

    def extra_profiles(self):
        def send(velocity,command_id,label,*,body=False,angle=None):
            message=self.Cmd(agent_cmd=self.Cmd.MOVE,
                move_mode=self.Cmd.XYZ_VEL_BODY if body else self.Cmd.XYZ_VEL,
                velocity_ref=list(velocity),yaw_rate_mode=angle is None,
                yaw_rate_ref=0.,yaw_ref=0. if angle is None else angle,command_id=command_id)
            Task.send(self,message,label)
        def tracking(body=False,angle=None):
            velocity=self.state.velocity
            yaw=self.state.attitude[2]
            if body:
                c,s=math.cos(yaw),math.sin(yaw)
                velocity=(c*velocity[0]+s*velocity[1],-s*velocity[0]+c*velocity[1],velocity[2])
            return (self.fresh() and all(abs(a-b)<=.3 for a,b in zip(velocity,(.8,.4,0.)))
                    and (angle is None or abs(math.remainder(yaw-angle,2*math.pi))<=.15))
        if self.flight_stack=='px4':
            send((.8,.4,0.),5,'angle_velocity_accepted',angle=.6)
            self.dwell('angle_velocity_settled',self.fresh,2)
            self.dwell('angle_velocity_tracking',lambda:tracking(angle=.6),3)
            anchor=tuple(self.state.position)
            send((0.,0.,0.),6,'angle_hold_accepted',angle=.6)
            def zero_angle():
                return (self.fresh() and math.hypot(*self.state.velocity)<=.25
                        and math.dist(self.state.position,anchor)<=1.
                        and abs(math.remainder(self.state.attitude[2]-.6,2*math.pi))<=.15)
            settled_since=None
            def settled():
                nonlocal settled_since
                if not zero_angle():
                    settled_since=None
                    return False
                now=state_time(self.state)
                if settled_since is None:settled_since=now
                return now-settled_since>=1.5
            self.wait('angle_hold_settled',settled,12)
            self.dwell('angle_zero_hold',zero_angle,4)
        send((.8,.4,0.),7,'body_velocity_accepted',body=True)
        self.dwell('body_velocity_settled',self.fresh,2)
        self.dwell('body_velocity_tracking',lambda:tracking(body=True),3)
        anchor=tuple(self.state.position)
        send((0.,0.,0.),8,'body_hold_accepted',body=True)
        self.dwell('body_hold_settled',self.fresh,2)
        self.dwell('body_zero_hold',lambda:self.fresh() and math.hypot(*self.state.velocity)<=.25
                   and math.dist(self.state.position,anchor)<=1.,4)

    def offer_rejected(self,message,*args,**kwargs):
        message.command_id+=1
        return super().offer_rejected(message,*args,**kwargs)

    def dwell(self,label,predicate,seconds):
        # Pre-run observation margin; the audit still requires the full frozen
        # 3/4/2-second physical windows, with no tolerance relaxed.
        super().dwell(label,predicate,seconds+.5)
        if label=='hold_completed':
            target=(2.,3.,3.)
            self.send(self.Cmd(agent_cmd=self.Cmd.MOVE,move_mode=self.Cmd.XYZ_POS,
                              position_ref=list(target),command_id=1),'position_baseline_accepted')
            def reached():
                return (self.fresh() and math.dist(self.state.position,target)<=.5
                        and math.hypot(*self.state.velocity)<=.5 and abs(self.state.attitude[2])<=.15)
            self.wait('position_baseline_reached',reached,30)
            super().dwell('position_baseline_dwell',reached,2.5)

    def execute(self):
        self.execute_velocity_yaw()

    def report(self):
        return dict(super().report(),independent_velocity=dict(phases=self.velocity_phases,
            source_clock='native boot dwell; independent physical cursors, not a joint scene grid',
            observation_margin_s=.5,position_baseline=(2.,3.,3.)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--prepared',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    config=validate_config(dict(load_config(args.config),run_id=args.run_id))
    if (config.get('runtime_profile')!='independent_quad_dds_v1' or config.get('control_protocol')!='session_v1'
            or any(k in config for k in ('mission','display_socket','telemetry_socket','gcs_udp_forward',
                                        'restart_control_on_ground','promotion_flight'))):
        raise ValueError('Requires the admitted plain independent session profile')
    config,profile=select_config(config)
    if not args.prepared:
        script='''set -eo pipefail
count=$1
shift
for ((i=0; i<count; i++)); do source "$1"; shift; done
export LD_LIBRARY_PATH="$1/agent-install/lib:${LD_LIBRARY_PATH:-}"
shift
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
exec python3 -B -m tools.validate_independent_velocity --prepared "$@"
'''
        os.execvp('bash',['bash','-c',script,'independent-velocity',str(len(profile['setup_files'])),
            *profile['setup_files'],profile['dds_workspace'],'--config',str(args.config.resolve()),
            '--run-id',args.run_id,'--output-root',str(args.output_root.absolute())])
    output=args.output_root.absolute()
    if output.parent!=Path('/root') or not output.name.startswith('wksim-') or output.resolve()!=output or output.exists():
        raise ValueError('Use a new /root/wksim-* output root')
    output.mkdir(mode=0o700)
    sources=[Path(__file__),Path(__file__).with_name('run-independent-velocity.sh')]
    report=dict(status='running',scope=__doc__,config=config,
                sources_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    path=output/'independent-velocity.json'
    path.write_text(json.dumps(report,indent=2)+'\n')
    report['runtime_result']=run(config,output,task_factory=IndependentVelocityTask)
    report['status']=report['runtime_result']['status']
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],report=str(path))),flush=True)
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
