"""Decode sampled native wait intervals; association with the sealed epoch remains required."""
import argparse
import hashlib
import json
from pathlib import Path

PREFIXES={'WKSIM_PX4_SEND ':'send','WKSIM_PX4_COMPONENT ':'component','WKSIM_PX4_REGISTER ':'register'}
STAGES=('poll_ns','prepare_ns','component_ns','send_ns')


def require(value,message):
    if not value:raise ValueError(message)


def parse(line,number):
    found=[(line.find(prefix),prefix,kind) for prefix,kind in PREFIXES.items() if prefix in line]
    if not found:return None
    require(len(found)==1,'Multiple diagnostic prefixes on one line')
    at,prefix,kind=found[0];row=json.loads(line[at+len(prefix):])
    require(isinstance(row,dict),'Diagnostic must be an object')
    if kind=='register':
        require(set(row)=={'component','tid','task'},'Registration fields differ')
        require(type(row['component']) is int and row['component']>0
                and row['component']&(row['component']-1)==0,'Invalid component bit')
        require(type(row['tid']) is int and row['tid']>0 and isinstance(row['task'],str),'Invalid registration identity')
    else:
        fields=({'start_mono_ns','end_mono_ns',*STAGES,'pret','revents','hrt_us'} if kind=='send' else
                {'start_mono_ns','end_mono_ns','wait_ns','used','progress','missing',
                 'observed_release_component','observed_release_mono_ns'})
        require(set(row)==fields and all(type(value) is int for value in row.values()),'Timing fields/types differ')
        require(0<row['start_mono_ns']<=row['end_mono_ns'],'Invalid real monotonic interval')
        if kind=='send':
            require(all(row[key]>=0 for key in STAGES),'Negative stage duration')
            require(sum(row[key] for key in STAGES)==row['end_mono_ns']-row['start_mono_ns'],'Stage sum differs')
            require(0<=row['hrt_us']<10**12,'Invalid simulation microseconds')
            if row['pret']<=0:require(all(row[key]==0 for key in STAGES[1:]),'Timeout includes unsent stages')
            else:require(row['revents']&1,'Successful record lacks POLLIN')
        else:
            require(row['wait_ns']==row['end_mono_ns']-row['start_mono_ns'],'Wait duration differs')
            require(all(row[key]>=0 for key in ('used','progress','missing','observed_release_component','observed_release_mono_ns')),
                    'Negative barrier observation')
            require(row['missing']==row['used']&~row['progress'],'Missing mask differs')
    return dict(kind=kind,line=number,**row)


def analyze(path):
    path=Path(path);records=[]
    with path.open(encoding='utf-8') as f:
        for number,line in enumerate(f,1):
            row=parse(line,number)
            if row is not None:records.append(row)
    sends=[row for row in records if row['kind']=='send']
    barriers=[row for row in records if row['kind']=='component']
    registrations=[row for row in records if row['kind']=='register']
    examples=[]
    for row in sorted(sends,key=lambda r:r['end_mono_ns']-r['start_mono_ns'],reverse=True)[:12]:
        begin=row['start_mono_ns']+row['poll_ns']+row['prepare_ns']
        end=begin+row['component_ns']
        contained=[b for b in barriers if begin<=b['start_mono_ns'] and b['end_mono_ns']<=end]
        examples.append(dict(row,contained_component_observations=contained))
    return dict(status='observed' if sends or barriers else 'no_timing_samples',scope=__doc__,
        counts=dict(send=len(sends),component=len(barriers),register=len(registrations)),
        maximum_stage_ns={key:max((row[key] for row in sends),default=None) for key in STAGES},
        largest_sender_intervals=examples,registrations=registrations,
        limitations=['Only slow intervals are emitted; absence is not proof of zero delay.',
          'Poll includes normal waiting for the supervisor to send sensors.',
          'Component stage includes the barrier diagnostic output cost; inner wait_ns excludes it.',
          'Release component/time are separate atomic observations, not a coherent pair or a causal verdict.'],
        log_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    try:r=analyze(a.log)
    except Exception as error:r=dict(status='failed',error=str(error))
    with a.output.open('x') as f:json.dump(r,f,indent=2,allow_nan=False)
    print(json.dumps({key:r.get(key) for key in ('status','counts','maximum_stage_ns','error')}))
    raise SystemExit(r['status']=='failed')
