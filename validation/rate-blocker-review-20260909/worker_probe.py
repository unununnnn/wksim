"""Actual worker function, fake prerecorded Model and in-memory pipes only."""
import contextlib
import difflib
import inspect
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT))
from Simulator.wksim_core import worker
EPOCH=ROOT/'validation/lunar-20-epoch-1/case/run/epochs/2a8d5df1dd4244c3868dc7f38e85a369'
row=json.loads(next((EPOCH/'arducopter-truth.jsonl').open()))
original=inspect.getsource(worker.model_worker)
old="log.write(encoded(dict(**response, commands=commands, input=line,\n                                       request=request)) + '\\n')"
new="response_json = encoded(response)\n                extras_json = encoded(dict(commands=commands, input=line, request=request))\n                log.write(response_json[:-1] + ',' + extras_json[1:] + '\\n')"
assert original.count(old)==1
candidate=original.replace(old,new).replace("output = encoded(response) + '\\n'",
    "output = (response_json if commands is not None else encoded(response)) + '\\n'")
full=(ROOT/'Simulator/wksim_core/worker.py').read_text()
proposed=full.replace(original,candidate)
assert proposed!=full
(OUT/'worker-response-reuse.patch').write_text(''.join(difflib.unified_diff(full.splitlines(True),proposed.splitlines(True),
    fromfile='a/Simulator/wksim_core/worker.py',tofile='b/Simulator/wksim_core/worker.py')))

class PrerecordedModel:
    def __init__(self,*args): self.ticks=0
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def step(self,commands):
        assert commands==row['commands']
        self.ticks+=1
        return row['state']

def run(source,name):
    namespace=dict(vars(worker))
    state_encodes=[]
    def counted(value):
        if isinstance(value,dict) and isinstance(value.get('state'),list):
            state_encodes.append(len(value['state']))
        return worker.encoded(value)
    output=io.StringIO()
    # Both a real retained step request and snapshot exercise the branches.
    snapshot=worker.encoded(dict(version=1,epoch=row['epoch'],snapshot=True))+'\n'
    namespace.update(Model=PrerecordedModel,_started=False,encoded=counted,
                     sys=SimpleNamespace(stdin=io.StringIO(row['input']+snapshot),stdout=output))
    exec(compile(source,'<offline-'+name+'>','exec'),namespace)
    with tempfile.TemporaryDirectory(dir=OUT) as temp:
        path=Path(temp)/'trace.jsonl'
        namespace['model_worker']('fake-not-a-native-library',path,row['epoch'])
        return dict(output=output.getvalue(),trace=path.read_text(),state_encodes=state_encodes)

before,after=run(original,'original'),run(candidate,'candidate')
assert before['output']==after['output'] and before['trace']==after['trace']
assert len(before['state_encodes'])==3 and len(after['state_encodes'])==2
result=dict(scope='Actual worker function with fake prerecorded state; no native model/socket/FC/ROS',
            response_and_trace_identical=True,original_state_encodes=len(before['state_encodes']),
            proposed_state_encodes=len(after['state_encodes']),
            workload='one accepted step plus one read-only snapshot',
            regression='one state encoding per worker response',old_regression_passed=False,new_regression_passed=True)
(OUT/'worker-probe-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
