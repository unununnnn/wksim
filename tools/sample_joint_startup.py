"""Bounded nonblocking Python stack samples of one explicitly owned supervisor."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Simulator.wksim_runtime.evidence import json_identity


def sample(directory,executable,output):
    directory=Path(directory);executable=Path(executable);output=Path(output)
    if not re.fullmatch(r'/root/wksim-pyspy-[A-Za-z0-9]+/bin/py-spy',str(executable)):
        raise ValueError('Expected the explicit private sampler installation')
    output.mkdir(exist_ok=False)
    config=json.loads((directory/'config.json').read_text())
    report=dict(status='failed',run_id=config['run_id'],sampler=str(executable),
        sampler_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        mode='nonblocking stack sampling; may contain incomplete samples; no timing/flight acceptance')
    try:
        limit=time.monotonic()+180
        while time.monotonic()<limit:
            path=directory/'status.json'
            if path.exists():
                state=json.loads(path.read_text())
                if state['run_id']!=config['run_id']:raise ValueError('Foreign run status')
                if state['phase'] in ('stopped','failed','faulted'):raise RuntimeError('Run retired before sampler start')
                if state['authority']['tick']>=100:break
            time.sleep(.01)
        else:raise TimeoutError('Sampler start condition not reached')
        original=state['supervisor'];actual=json_identity(original['pid'])
        if actual!=original or actual['argv'][:4] != [sys.executable,'-B','-m','Simulator.wksim_runtime.joint_runtime']:
            # Python may have been invoked through the equivalent python3 path.
            if (actual is None or any(actual[k]!=original[k] for k in ('pid','pgid','start_ticks'))
                    or actual['argv'][1:4]!=['-B','-m','Simulator.wksim_runtime.joint_runtime']
                    or str(directory) not in actual['argv']):
                raise ValueError('Sampler target is not the owned joint supervisor')
        argv=[str(executable),'record','--pid',str(actual['pid']),'--duration','35','--rate','99',
              '--format','speedscope','--threads','--idle','--nonblocking',
              '--full-filenames','--output',str(output/'stacks.json')]
        report.update(target=actual,started_state=state,argv=argv,started_monotonic_ns=time.monotonic_ns())
        done=subprocess.run(argv,capture_output=True,text=True,timeout=45)
        (output/'sampler.stdout.log').write_text(done.stdout)
        (output/'sampler.stderr.log').write_text(done.stderr)
        report.update(returncode=done.returncode,status='sampled' if done.returncode==0 else 'failed')
        if (output/'stacks.json').is_file():
            report['stacks_sha256']=hashlib.sha256((output/'stacks.json').read_bytes()).hexdigest()
    except Exception as error:report['error']=repr(error)
    report['finished_monotonic_ns']=time.monotonic_ns()
    with (output/'result.json').open('x') as stream:json.dump(report,stream,indent=2,allow_nan=False)
    return {k:report.get(k) for k in ('status','error','returncode','stacks_sha256')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();value=sample(args.directory,args.executable,args.output)
    print(json.dumps(value));raise SystemExit(value['status']!='sampled')
