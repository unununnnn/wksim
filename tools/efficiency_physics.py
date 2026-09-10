"""Actual rotor efficiency in each native interval, with original actuator packets."""
import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import signal
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_core.motor_efficiency_model import EfficiencyModel
from Simulator.wksim_core.motor_efficiency_event import EfficiencyEvent,make_plan,publish_plan,load_plan,canonical
from tools.pid_physics import capture_decoder


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def observed_model(directory,run_id,profile,case,context,stop):
    class Observed(EfficiencyModel):
        def __init__(self,library):
            super().__init__(library)
            if self.library_sha256!=profile['library_sha256']:raise ValueError('Wrong efficiency physics library')
            self.raw=(directory/'physics-1ms.jsonl').open('x',buffering=1024*1024)
            self.event=None;self.origin=None;self.arm_raw=None;self.failure=None
            self.base_identity=dict(run_id=run_id,instance_id=1,model_identity='sha256:'+self.library_sha256,
                library_sha256=self.library_sha256,config_sha256=digest(directory/'efficiency-profile.json'),
                protocol_sha256=digest(REPO/'docs/plan/44-motor-efficiency-contract.md'),
                original_source_sha256=self.manifest['files_sha256']['original.cpp'],
                parameterized_source_sha256=self.manifest['files_sha256']['Exp1_MinModelTemp.cpp'],
                wrapper_sha256=self.manifest['files_sha256']['motor_efficiency_native.cpp'])
            self.raw.write(json.dumps(dict(kind='start',run_id=run_id,case=case,initial_tick=self.ticks,
                library_sha256=self.library_sha256,initial_eta=self.efficiency(),
                initial_random_state=self.initial_random_state,identity=self.base_identity))+'\n')

        def poll(self):
            path=directory/'efficiency-arm.json'
            if path.exists():
                raw=path.read_bytes()
                if self.arm_raw is not None and raw!=self.arm_raw:raise ValueError('Efficiency arm request changed')
                if self.arm_raw is None:
                    request=load_plan(path)
                    if (set(request)!={'run_id','control_epoch','case','config_sha256'}
                            or request['run_id']!=run_id or request['case']!=case
                            or request['config_sha256']!=self.base_identity['config_sha256']):
                        raise ValueError('Wrong efficiency arm identity')
                    identity=dict(self.base_identity,control_epoch=request['control_epoch'])
                    plan=make_plan(identity,self.ticks)
                    self.arm_raw=raw
                    self.origin=plan
                    if case=='fault':
                        publish_plan(directory/'efficiency-event.json',plan)
                        self.event=EfficiencyEvent(plan,identity,loaded_tick=self.ticks,path=directory/'efficiency-event.json')
                    publish_plan(directory/'efficiency-origin.json',dict(plan,event_enabled=case=='fault'))
            elif self.arm_raw is not None:
                raise ValueError('Efficiency arm request disappeared')

        def check_envelope(self,output):
            if self.origin is None or not self.origin['origin_tick']<=self.ticks<=self.origin['recovery_deadline_tick']:
                return
            p=(output[7],output[6],-output[8]); distance=math.dist(p,profile['point_enu_m'])
            if (not profile['minimum_height_m']<=p[2]<=profile['maximum_height_m']
                    or distance>profile['maximum_distance_m']
                    or max(abs(output[9]),abs(output[10]))>math.radians(profile['maximum_axis_tilt_deg'])
                    or self.origin['start_tick']<=self.ticks<=self.origin['end_tick'] and distance>profile['disturbance_error_m']):
                self.failure='physical_efficiency_envelope'
                publish_plan(directory/'efficiency-failure.json',dict(reason=self.failure,tick=self.ticks))
                publish_plan(directory/'efficiency-revoked.json',dict(reason=self.failure,tick=self.ticks))

        def step(self,commands,steps=1):
            if type(steps) is not int or not 1<=steps<=1000:raise ValueError('Invalid efficiency group size')
            for substep in range(steps):
                if stop['requested']:raise InterruptedError('Owned efficiency physics retired')
                stop['interval']=True
                try:
                    self.poll()
                    before=self.ticks
                    revoked=(directory/'efficiency-revoked.json').exists()
                    if self.event is None:
                        self.set_efficiency(1.)
                        output=super().step(commands,1)
                    else:
                        # EfficiencyEvent calls EfficiencyModel.step, avoiding a
                        # recursive call into this group/transport wrapper.
                        adapter=Interval(self)
                        output=self.event.step(adapter,commands,tick=before,revoke=revoked)
                    self.raw.write(json.dumps(dict(kind='step',interval_tick=before,tick=self.ticks,
                        group_steps=steps,substep=substep,input16=list(commands),applied_input16=list(commands),
                        raw_actuator_packet=context.get('latest'),output120=output,eta=self.efficiency(),
                        stages=self.stages,random_state=self.random_state(),origin=self.origin['origin_tick'] if self.origin else None,
                        event_state=self.event.state if self.event else 'baseline',revoked=revoked,
                        observed_monotonic_ns=time.monotonic_ns()),allow_nan=False)+'\n')
                    if self.failure is None:self.check_envelope(output)
                finally:
                    stop['interval']=False
                if stop['requested']:raise InterruptedError('Owned efficiency physics retired')
            if self.ticks%1000==0:self.raw.flush()
            return output

        def close(self):
            if not self.raw.closed:
                self.set_efficiency(1.)
                self.raw.write(json.dumps(dict(kind='end',ticks=self.ticks,final_eta=self.efficiency(),
                    final_random_state=self.random_state(),event_state=self.event.state if self.event else 'baseline',
                    failure=self.failure))+'\n')
                self.raw.close()
            super().close()

    class Interval:
        """One stable adapter delegates ownership attributes to the same native model."""
        def __init__(self,model):object.__setattr__(self,'model',model)
        def __getattr__(self,name):return getattr(self.model,name)
        def __setattr__(self,name,value):setattr(self.model,name,value)
        def step(self,commands,steps):return EfficiencyModel.step(self.model,commands,steps)
    return Observed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('stack','library','trace','profile','run-id','case'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--port',required=True,type=int)
    args=parser.parse_args()
    profile=json.loads(Path(args.profile).read_text())
    module=importlib.import_module('Simulator.wksim_core.'+('ap_json' if args.stack=='arducopter' else 'px4_mavlink'))
    directory=Path(args.trace).parent;context={};stop=dict(requested=False,interval=False)
    def retire(signum,frame):
        stop['requested']=True
        if not stop['interval']:raise InterruptedError('Owned efficiency physics retired')
    signal.signal(signal.SIGTERM,retire)
    with (directory/'physics-actuator-packets.jsonl').open('x',buffering=1) as packets:
        capture_decoder(module,args.stack,context,packets)
        module.Model=observed_model(directory,args.run_id,profile,args.case,context,stop)
        try:
            module.serve(Path(args.library),args.port,Path(args.trace),duration=None,
                         **({} if args.stack=='arducopter' else dict(speedup=1)))
        except InterruptedError:pass


if __name__=='__main__':main()
