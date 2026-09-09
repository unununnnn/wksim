"""Fresh-process native equivalence for the explicit 1 ms attitude observer."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_core.model import Model
from tools.attitude_physics import observed_model

LIBRARY=Path('/root/wksim-private-tmp-bhi18a3s/artifacts/wksim-model-qhdy93lm/libwksim_model.so')
LIBRARY_SHA='cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3'


def child(mode, output):
    assert hashlib.sha256(LIBRARY.read_bytes()).hexdigest()==LIBRARY_SHA
    cls=Model if mode=='original' else observed_model(output.with_suffix('.raw.jsonl'))
    with cls(LIBRARY) as model, output.open('x') as stream:
        for group in range(200):
            commands=([0.]*4 if group<30 else [.65+.05*math.sin(group*.03+i*.2) for i in range(4)])+[0.]*12
            stream.write(json.dumps(dict(group=group,input=commands,output=model.step(commands,4)),allow_nan=False)+'\n')


def verify(output):
    output.mkdir(exist_ok=False)
    protocol=dict(groups=200,steps_per_group=4,comparison='All group-final 120 binary64 Python values exactly equal',
        commands='zero first 30 groups, then .65+.05*sin(group*.03+motor*.2) for motors0..3; 4..15 zero',
        library=str(LIBRARY),library_sha256=LIBRARY_SHA,observer_sha256=hashlib.sha256((REPO/'tools/attitude_physics.py').read_bytes()).hexdigest())
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    for mode in ('original','observed'):
        subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--child',mode,str(output/(mode+'.jsonl'))],check=True)
    old,new=([json.loads(x) for x in (output/(mode+'.jsonl')).read_text().splitlines()] for mode in ('original','observed'))
    assert len(old)==len(new)==200 and old==new
    raw=[json.loads(x) for x in (output/'observed.raw.jsonl').read_text().splitlines()]
    assert len(raw)==802 and raw[0]['kind']=='start' and raw[-1]['kind']=='end' and raw[-1]['ticks']==800
    for tick,row in enumerate(raw[1:-1],1):
        group=(tick-1)//4
        assert row['tick']==tick and row['group']==group+1 and row['group_steps']==4
        assert row['input16']==old[group]['input'] and row['substep']==(tick-1)%4
        if tick%4==0: assert row['output120']==old[group]['output']
    summary=dict(result='pass',groups=200,exact_group_final_values=24000,raw_steps=800,
        files_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()})
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child',choices=('original','observed'))
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.child: child(args.child,args.output)
    else: verify(args.output)
