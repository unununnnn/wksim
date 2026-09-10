"""Compare real model RPC/trace bytes with synchronous and background evidence writes."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Simulator.wksim_core.worker import validate_response


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(library,output):
    output=Path(output);output.mkdir(exist_ok=False)
    native=Path(tempfile.mkdtemp(prefix='wksim-model-trace-',dir='/root'))
    epoch=uuid.uuid4().hex;inputs=[]
    for tick in range(1,1001):
        commands=([0.0]*4 if tick<=100 else [.45+.05*math.sin(tick*.03+axis*.2) for axis in range(4)])+[0.0]*12
        inputs.append(json.dumps(dict(version=1,epoch=epoch,tick=tick,commands=commands),separators=(',',':'))+'\n')
    payload=''.join(inputs);results={}
    for mode in ('sync','async'):
        trace=native/(mode+'.jsonl')
        command=[sys.executable,'-B','-m','Simulator.wksim_core.worker','--library',str(library),
                 '--trace',str(trace),'--epoch',epoch]+(['--async-evidence'] if mode=='async' else [])
        run=subprocess.run(command,input=payload,capture_output=True,text=True,cwd=ROOT,timeout=30)
        (output/(mode+'.stderr.log')).write_text(run.stderr)
        if run.returncode:raise RuntimeError(mode+' worker failed: '+run.stderr)
        lines=run.stdout.splitlines();assert len(lines)==1000
        for tick,line in enumerate(lines,1):validate_response(json.loads(line),epoch,tick)
        results[mode]=dict(command=command,returncode=run.returncode,trace_path=str(trace),
                           trace_sha256=digest(trace),response_sha256=hashlib.sha256(run.stdout.encode()).hexdigest())
    assert results['sync']['trace_sha256']==results['async']['trace_sha256']
    assert results['sync']['response_sha256']==results['async']['response_sha256']
    summary=json.loads(Path(results['async']['trace_path']+'.writer.json').read_text())
    assert summary['complete'] and not summary['alive'] and summary['written_bytes']==summary['submitted_bytes']
    assert summary['written_bytes']==Path(results['async']['trace_path']).stat().st_size
    report=dict(status='verified',scope='Same-build RPC and accepted-input trace equivalence; not a flight/G6 accuracy gate',
        samples=1000,epoch=epoch,library=str(library),library_sha256=digest(library),results=results,writer=summary,
        sources={name:digest(ROOT/name) for name in ('Simulator/wksim_core/worker.py',
            'Simulator/wksim_runtime/evidence_stream.py','tools/check_model_trace_stream.py')})
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();check(args.library,args.output)
