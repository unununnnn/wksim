"""Independent #115 acceptance; run once from the WSL repository root."""
import json
import hashlib
import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from tools import reexecute_model as r
from validation.test_model_reexecution import rewrite, encoded

EVIDENCE = Path(__file__).resolve().parent
BASE = Path('/root/wksim-reexecution-115-20260909-01')
SOURCE = Path('/root/wksim-reexecution-114-20260909-03/source')
LIBRARY = SOURCE.parent/'build/libwksim_configured.so'
PIN = '1ae747154a72ac46435c33cede8642b81224c12c20f0b13f02825750108d314f'
def hashes(folder):
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob('*')) if p.is_file()}
def save(path, value):
    r.write_json(path, value)

BASE.mkdir(exist_ok=False)
before = hashes(SOURCE)
assert before['manifest.json'] == PIN
m, config, inputs, expected, raw = r.load_bundle(SOURCE)
assert r.build_identity(LIBRARY, config) == m['build_identity']
capture = json.loads((SOURCE.parent/'capture.json').read_text())
capture_process = json.loads((SOURCE.parent/'capture-process.json').read_text())
assert capture_process['exit_code'] == 0
assert capture['outputs'] == [row['output120'] for row in expected]
assert capture['process']['pid'] == json.loads(raw['terminal.json'])['process']['pid']
assert (SOURCE.parent/'source-plan.json').read_bytes() == raw['plan.json']
archived = ROOT/'validation/lunar-114-astra-20260909-01/native/source'
assert hashes(archived) == before
save(BASE/'preflight.json', dict(manifest_sha256=PIN, source_hashes=before,
     source_capture_matches=True, archived_source_matches=True,
     build_identity=m['build_identity'], budget={'atol':0,'rtol':0,'dt_ns':1000000},
     source_capture_process=capture_process,
     execution_scope='static native library only; CLI exposes no FC/control destinations'))
commands = []
def cli(label, *args, code=0):
    argv = ['/usr/bin/python3', str(ROOT/'tools/reexecute_model.py'), *map(str,args)]
    result = subprocess.run(argv, capture_output=True, timeout=300)
    (BASE/(label+'.stdout.log')).write_bytes(result.stdout)
    (BASE/(label+'.stderr.log')).write_bytes(result.stderr)
    commands.append(dict(label=label, argv=argv, exit_code=result.returncode, expected_exit=code))
    save(BASE/(label+'.command.json'), commands[-1])
    assert result.returncode == code, (label,result.stderr,result.stdout)

cli('import','import','--source',SOURCE,'--output',BASE/'input')
cli('run','run','--input',BASE/'input','--library',LIBRARY,'--output',BASE/'run')
cli('audit','audit','--input',BASE/'input','--run',BASE/'run','--output',BASE/'audit.json')
actual = [json.loads(line) for line in (BASE/'run/actual.jsonl').read_text().splitlines()]
assert len(actual) == len(inputs) == len(expected) == 25
assert json.loads((BASE/'run/request.json').read_text())['pid'] != capture['process']['pid']
differences = []
for tick, (a,b) in enumerate(zip(actual,expected),1):
    assert a['tick'] == b['tick'] == tick
    assert a['before_ns'] == (tick-1)*1000000 and a['after_ns'] == tick*1000000
    assert a['output_phase'] == b['output_phase'] == 'post_step_api'
    assert len(a['output120']) == len(b['output120']) == 120
    for slot,(x,y) in enumerate(zip(a['output120'], b['output120'])):
        if x != y:
            differences.append(dict(tick=tick,slot=slot,actual=x,expected=y))
assert not differences
save(BASE/'independent-comparison.json', dict(ticks=25,comparisons=3000,failures=differences,
     dt_ns=1000000,atol=0,rtol=0,distinct_source_and_reexecution_pid=True))

for case in ('missing-tick','changed-input','foreign-model','changed-seed','missing-initial',
             'stale-event','missing-terminal','truncated','phase'):
    target = BASE/('negative-'+case)
    shutil.copytree(SOURCE,target)
    manifest = json.loads((target/'manifest.json').read_text())
    if case in ('missing-tick','changed-input','phase'):
        name = 'expected.jsonl' if case == 'phase' else 'inputs.jsonl'
        rows = [json.loads(line) for line in (target/name).read_text().splitlines()]
        if case == 'missing-tick': rows.pop(8)
        elif case == 'changed-input': rows[8]['inPWMs'][0] = .6
        else: rows[8]['output_phase'] = 'major_root'
        rewrite(target,name,b''.join(map(encoded,rows)))
    elif case == 'foreign-model':
        manifest['build_identity']['source']['archive_sha256'] = 'a'*64
        rewrite(target,'manifest.json',manifest)
    elif case == 'changed-seed':
        manifest['randomness']['seeds']['S246.Number'][0] = 0
        rewrite(target,'manifest.json',manifest)
    elif case == 'missing-initial':
        manifest['initialization'] = {}
        rewrite(target,'manifest.json',manifest)
    elif case == 'stale-event':
        rewrite(target,'events.jsonl',encoded(dict(event_seq=1,scene_epoch='foreign',kind='start')))
    elif case == 'missing-terminal':
        (target/'terminal.json').unlink()
    else:
        rewrite(target,'inputs.jsonl',(target/'inputs.jsonl').read_bytes()[:-1])
    output = BASE/('refused-'+case)
    cli(case,'run','--input',target,'--library',LIBRARY,'--output',output,code=2)
    assert not (output/'request.json').exists()
    assert not (output/'process.json').exists()

# Alter actual output only in an audit copy; reseal stream hash to test numerical comparison.
shutil.copytree(BASE/'run',BASE/'wrong-output-run')
mutated = json.loads(json.dumps(actual))
mutated[9]['output120'][10] += 1
stream = b''.join(map(encoded,mutated))
(BASE/'wrong-output-run/actual.jsonl').write_bytes(stream)
term = json.loads((BASE/'wrong-output-run/terminal.json').read_text())
term['actual_sha256'] = r.sha(stream)
(BASE/'wrong-output-run/terminal.json').write_bytes(encoded(term))
cli('numerical-negative','audit','--input',BASE/'input','--run',BASE/'wrong-output-run',
    '--output',BASE/'numerical-negative.json',code=1)
failure = json.loads((BASE/'numerical-negative.json').read_text())
assert failure['counts']['failures'] == 1
assert failure['first_mismatch']['tick'] == 10 and failure['first_mismatch']['slot'] == 10
assert hashes(SOURCE) == before
assert r.build_identity(LIBRARY, config) == m['build_identity']
save(BASE/'review.json', dict(status='passed',commands=commands,source_unchanged=True,
     build_unchanged=True,negative_admission_cases=9,numerical_negative_cases=1,
     source_files={str(p):r.sha(p.read_bytes()) for p in
       [ROOT/'tools/reexecute_model.py', ROOT/'validation/test_model_reexecution.py',
        ROOT/'docs/plan/46-reexecution-contract.md',Path(__file__)]},
     process_cleanup='all subprocess.run calls returned; no FC/ROS/UE launched'))
shutil.copytree(BASE,EVIDENCE/'native')
save(EVIDENCE/'archive-hashes.json',hashes(EVIDENCE/'native'))
print(json.dumps(dict(status='passed',ticks=25,comparisons=3000,negative_cases=10,output=str(BASE))))
