"""An explicit one-motor command disturbance around the existing physics adapters.

The multiplier is applied at individual 1 ms model intervals, not wall time.
It is a command disturbance, not a claim of calibrated motor efficiency.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_core.model import Model


def publish_event(path,event):
    """Expose a complete immutable event name with one exclusive hard link."""
    path=Path(path);prepared=path.with_name(path.stem+'.prepared.json')
    raw=(json.dumps(event,sort_keys=True)+'\n').encode()
    with prepared.open('xb') as stream:stream.write(raw)
    os.link(prepared,path)
    return hashlib.sha256(raw).hexdigest()


class ScheduledFault:
    def __init__(self,path):
        self.path=Path(path);self.event=None;self.sha256=None;self.applied=0

    def apply(self,commands,tick):
        if tick%20==0 and self.path.exists():
            raw=self.path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
            if self.sha256 is not None and digest!=self.sha256:raise ValueError('Actuator event changed after publication')
            if self.event is None:
                event=json.loads(raw)
                if (set(event)!={'schema','channel','start_tick','end_tick','multiplier'}
                        or event['schema']!='wksim.rate-actuator-fault.v1' or type(event['channel']) is not int or event['channel']!=0
                        or type(event['start_tick']) is not int or type(event['end_tick']) is not int
                        or event['start_tick']<tick or event['end_tick']-event['start_tick']!=1000
                        or type(event['multiplier']) is not float or event['multiplier']!=.97):
                    raise ValueError('Invalid or late frozen actuator event')
                self.event=event;self.sha256=digest
        applied=list(commands)
        active=self.event is not None and self.event['start_tick']<=tick<self.event['end_tick']
        if active:applied[0]*=.97;self.applied+=1
        return applied,active


def fault_model(event,trace):
    class FaultModel(Model):
        def __init__(self,library):
            super().__init__(library)
            self.fault=ScheduledFault(event)
            self.record=Path(trace).open('x',buffering=65536)
        def step(self,commands,steps=1,*,terrain=None):
            for _ in range(steps):
                tick=self.ticks;applied,active=self.fault.apply(commands,tick)
                output=super().step(applied,1,terrain=terrain)
                self.record.write(json.dumps(dict(kind='step',tick=tick,original=commands,applied=applied,
                    active=active,event_sha256=self.fault.sha256),allow_nan=False)+'\n')
            return output
        def close(self):
            try:super().close()
            finally:
                if hasattr(self,'record') and not self.record.closed:
                    self.record.write(json.dumps(dict(kind='end',ticks=self.ticks,applied_ticks=self.fault.applied,
                        event_sha256=self.fault.sha256))+'\n');self.record.close()
    return FaultModel


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack',choices=['px4','arducopter'],required=True)
    parser.add_argument('--library',type=Path,required=True);parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--trace',type=Path,required=True);parser.add_argument('--event',type=Path,required=True)
    parser.add_argument('--input-trace',type=Path,required=True);parser.add_argument('--duration',type=float,default=180)
    args=parser.parse_args()
    if not 1024<=args.port<=65535 or not 0<args.duration<=180:parser.error('Invalid bounded physics profile')
    def stop(*_):raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    if args.stack=='px4':from Simulator.wksim_core import px4_mavlink as adapter
    else:from Simulator.wksim_core import ap_json as adapter
    adapter.Model=fault_model(args.event,args.input_trace)
    adapter.serve(args.library,args.port,args.trace,duration=args.duration)


if __name__=='__main__':main()
