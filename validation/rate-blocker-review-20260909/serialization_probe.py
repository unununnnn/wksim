"""Bounded in-memory encoding probe using 256 actual records; no worker/model run."""
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import sys
import time

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT))
from Simulator.wksim_core.worker import encoded
EPOCH=ROOT/'validation/lunar-20-epoch-1/case/run/epochs/2a8d5df1dd4244c3868dc7f38e85a369'
samples=[]
for name in ('arducopter-truth.jsonl','px4-truth.jsonl'):
    with (EPOCH/name).open() as stream:
        for line in itertools.islice(stream,128):
            row=json.loads(line)
            response={k:row[k] for k in ('version','epoch','tick','state')}
            extras={k:row[k] for k in ('commands','input','request')}
            samples.append((response,extras,line))

def original(response,extras):
    return encoded(dict(**response,**extras))+'\n', encoded(response)+'\n'

def candidate(response,extras):
    # Same JSON field order/representation, state encoded once rather than twice.
    response_json=encoded(response)
    return response_json[:-1]+','+encoded(extras)[1:]+'\n', response_json+'\n'

for response,extras,line in samples:
    assert original(response,extras)==candidate(response,extras)
    assert candidate(response,extras)[0]==line
times={'original':[],'candidate':[]}
for turn in range(6):
    order=[('original',original),('candidate',candidate)]
    if turn%2: order.reverse()
    for name,function in order:
        began=time.perf_counter_ns()
        for response,extras,_ in samples:
            function(response,extras)
        times[name].append(time.perf_counter_ns()-began)
median={name:statistics.median(values) for name,values in times.items()}
result=dict(scope='In-memory CPython encoding only; 256 actual ground records, no model/socket/file-write hot path',
    python=sys.version,samples=len(samples),all_record_and_response_bytes_equal=True,
    elapsed_wall_ns=times,median_wall_ns=median,
    median_wall_saved_fraction=1-median['candidate']/median['original'],
    clock='perf_counter_ns; initial Windows thread_time sampling was too coarse and retained separately',
    current_worker_sha256=hashlib.sha256((ROOT/'Simulator/wksim_core/worker.py').read_bytes()).hexdigest(),
    archived_worker_sha256=hashlib.sha256((EPOCH/'source/Simulator/wksim_core/worker.py').read_bytes()).hexdigest(),
    boundary='Not proof that serialization caused captured scheduling tails or that1x acceptance will pass')
(OUT/'serialization-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
