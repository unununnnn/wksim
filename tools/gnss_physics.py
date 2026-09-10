"""Actual GNSS sensor boundary with unchanged 1ms physical truth and original packets."""
import argparse
import hashlib
import importlib
import json
import math
import re
from pathlib import Path
import signal
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_core.model import Model
from Simulator.wksim_core.gnss_event import GnssEventController,GnssEventPlan
from Simulator.wksim_core.motor_efficiency_event import publish_plan,load_plan
from tools.pid_physics import capture_decoder


class Schedule:
    def __init__(self,directory,run_id,epoch,profile):
        if not all(isinstance(v,str) and re.fullmatch('[0-9a-f]{32}',v) for v in (run_id,epoch)):
            raise ValueError('GNSS physical identities must be hex32')
        self.directory=directory;self.run_id=run_id;self.epoch=epoch;self.profile=profile
        self.raw=None;self.plan=None;self.failed=False
        self.controller=GnssEventController(run_id,epoch,1,max_age_ticks=profile['max_gps_age_ticks'])

    def poll(self,tick):
        path=self.directory/'gnss-arm.json'
        if path.exists():
            raw=path.read_bytes()
            if self.raw is not None and raw!=self.raw:raise ValueError('Immutable GNSS arm request changed')
            if self.raw is None:
                request=load_plan(path)
                if (set(request)!={'run_id','scene_epoch','control_epoch','profile_sha256'}
                        or request['run_id']!=self.run_id or request['scene_epoch']!=self.epoch
                        or not isinstance(request['control_epoch'],str) or not re.fullmatch('[0-9a-f]{32}',request['control_epoch'])
                        or request['profile_sha256']!=hashlib.sha256((self.directory/'gnss-profile.json').read_bytes()).hexdigest()):
                    raise ValueError('Wrong GNSS request identity')
                start=((tick+self.profile['lead_ticks']+199)//200)*200
                if start+self.profile['outage_ticks']>self.profile['maximum_tick']:
                    raise ValueError('GNSS plan exceeds physical run budget')
                self.plan=dict(run_id=self.run_id,scene_epoch=self.epoch,control_epoch=request['control_epoch'],
                    vehicle_id=1,origin_tick=tick,start_tick=start,end_tick=start+self.profile['outage_ticks'],
                    profile_sha256=request['profile_sha256'])
                self.controller.schedule(GnssEventPlan(self.run_id,self.epoch,1,start,self.plan['end_tick']))
                publish_plan(self.directory/'gnss-plan.json',self.plan);self.raw=raw
        elif self.raw is not None:raise ValueError('GNSS request disappeared')


def observed_model(directory,schedule,context,stop):
    class Observed(Model):
        def __init__(self,library):
            super().__init__(library)
            self.raw=(directory/'physics-1ms.jsonl').open('x',buffering=1024*1024)
            self.raw.write(json.dumps(dict(kind='start',run_id=schedule.run_id,scene_epoch=schedule.epoch,
                library_sha256=hashlib.sha256(Path(library).read_bytes()).hexdigest(),initial_tick=0))+'\n')

        def step(self,commands,steps=1):
            for substep in range(steps):
                if stop['requested']:raise InterruptedError('Owned GNSS physics retired')
                stop['interval']=True
                try:
                    schedule.poll(self.ticks)
                    if self.ticks>=schedule.profile['maximum_tick']:raise TimeoutError('GNSS physical tick budget')
                    output=super().step(commands,1)
                    self.raw.write(json.dumps(dict(kind='step',tick=self.ticks,input16=list(commands),
                        raw_actuator_packet=context.get('latest'),output120=output,
                        observed_monotonic_ns=time.monotonic_ns()),allow_nan=False)+'\n')
                    if schedule.plan and not schedule.failed:
                        p=(output[7],output[6],-output[8]);cfg=schedule.profile
                        if (not cfg['minimum_height_m']<=p[2]<=cfg['maximum_height_m']
                                or math.dist(p,cfg['point_enu_m'])>cfg['maximum_distance_m']
                                or max(abs(output[9]),abs(output[10]))>math.radians(cfg['maximum_axis_tilt_deg'])):
                            schedule.failed=True
                            publish_plan(directory/'gnss-failure.json',dict(reason='physical_envelope',tick=self.ticks))
                finally:stop['interval']=False
                if stop['requested']:raise InterruptedError('Owned GNSS physics retired')
            if self.ticks%1000==0:self.raw.flush()
            return output

        def close(self):
            if not self.raw.closed:
                self.raw.write(json.dumps(dict(kind='end',ticks=self.ticks,failed=schedule.failed))+'\n');self.raw.close()
            super().close()
    return Observed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('library','run-id','scene-epoch','profile','trace'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--stack',choices=('px4','arducopter'),required=True);parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args();directory=Path(args.trace).parent
    from Simulator.wksim_runtime.gnss_task import load_profile
    profile=load_profile(args.profile)
    schedule=Schedule(directory,args.run_id,args.scene_epoch,profile);stop=dict(requested=False,interval=False)
    def retire(signum,frame):
        stop['requested']=True
        if not stop['interval']:raise InterruptedError('Owned GNSS physics retired')
    signal.signal(signal.SIGTERM,retire)
    module=importlib.import_module('Simulator.wksim_core.'+('ap_json' if args.stack=='arducopter' else 'px4_mavlink'))
    context={}
    with (directory/'physics-actuator-packets.jsonl').open('x',buffering=1) as packets, (directory/'gnss-wire.jsonl').open('x',buffering=1) as wire:
        capture_decoder(module,args.stack,context,packets)
        module.Model=observed_model(directory,schedule,context,stop)
        if args.stack=='arducopter':
            def sensor_message(state):
                tick=round(state[2]*1000)
                data=dict(wksim=f'{args.run_id}:{args.scene_epoch}:1:{tick}')
                if schedule.plan:data['gnss_plan']=f"{schedule.plan['start_tick']}:{schedule.plan['end_tick']}"
                data.update(module.sensor_fields(state))
                raw=('\n'+json.dumps(data,separators=(',',':'),allow_nan=False)+'\n').encode()
                wire.write(json.dumps(dict(tick=tick,hex=raw.hex()))+'\n')
                return raw
            module.sensor_message=sensor_message
            options={}
        else:
            gate=module.GnssSendGate(schedule.controller,lambda row:wire.write(json.dumps(row,allow_nan=False)+'\n'))
            options=dict(speedup=1,gnss_gate=gate,run_id=args.run_id,gnss_epoch=args.scene_epoch)
        try:module.serve(Path(args.library),args.port,Path(args.trace),duration=None,**options)
        except InterruptedError:pass


if __name__=='__main__':main()
