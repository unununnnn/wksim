"""Reproducible #85 evidence collection; refuses existing generated outputs."""
import copy
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
from tools import audit_pid_flight as audit
from validation.test_pid_flight_audit import physical_fixture, trace_fixture, CONFIG


def save(name, value):
    with (HERE/name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')


commands = []
def run(label, argv, expected=0):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result = subprocess.run(argv, cwd=REPO, capture_output=True, timeout=120)
    for suffix, content in (('stdout', result.stdout), ('stderr', result.stderr)):
        with (HERE/(label+'.'+suffix+'.log')).open('xb') as stream: stream.write(content)
    commands.append(dict(label=label, argv=argv, cwd=str(REPO), started_utc=started,
                         returncode=result.returncode, expected_returncode=expected))
    if result.returncode != expected:
        save('commands-failed.json', commands)
        raise RuntimeError(label+' exit '+str(result.returncode))


modules = ['validation.test_pid_flight_audit','validation.test_pid_flight','validation.test_position_pid']
run('windows-tests', [sys.executable,'-B','-m','unittest',*modules,'-v'])
run('wsl-tests', ['wsl','-d','Ubuntu-22.04','-u','root','--','python3','-B','-m','unittest',*modules,'-v'])
run('cli-help', [sys.executable,'-B','tools/audit_pid_flight.py','--help'])
run('git-whitespace', ['git','diff','--check','--','tools/audit_pid_flight.py','validation/test_pid_flight_audit.py'])
run('head', ['git','rev-parse','HEAD'])
rows, packets, event, sha = physical_fixture()
save('event.synthetic.json',event)
save('trace.synthetic.json',trace_fixture()[0])
with (HERE/'physics.synthetic.jsonl.gz').open('xb') as file:
    with gzip.GzipFile(fileobj=file, mode='wb', mtime=0) as stream:
        for row in rows: stream.write((json.dumps(row)+'\n').encode())
with (HERE/'packets.synthetic.jsonl.gz').open('xb') as file:
    with gzip.GzipFile(fileobj=file, mode='wb', mtime=0) as stream:
        for packet in packets: stream.write((json.dumps(packet)+'\n').encode())
_, _, positive = audit.physics(rows, packets, event, sha, 'fixture', 'arducopter')
save('physics-positive.synthetic.json',positive)
negative = []
for name in ('deleted_tick','missing_terminal','wrong_run','missing_input','false_disturbance','wrong_event_hash'):
    changed = copy.deepcopy(rows)
    if name == 'deleted_tick': changed.pop(100)
    if name == 'missing_terminal': changed.pop()
    if name == 'wrong_run': changed[100]['run_id']='other'
    if name == 'missing_input': changed[100]['raw_actuator_packet']=None
    if name == 'false_disturbance': changed[2001]['applied_input16']=[.5]*4+[0.]*12
    if name == 'wrong_event_hash': changed[100]['disturbance_event_sha256']='0'*64
    try:
        audit.physics(changed,packets,event,sha,'fixture','arducopter')
        raise AssertionError('Negative passed: '+name)
    except ValueError as error:
        negative.append(dict(case=name,status='rejected',failure=str(error)))
save('negative-results.json',negative)
fake = HERE/'observed-only.synthetic'; fake.mkdir()
save('observed-only.synthetic/result.json',dict(status='observed',online_ok=True,run_id='synthetic-only',stack='px4'))
run('cli-observed-rejection', [sys.executable,'-B','tools/audit_pid_flight.py','--run-dir',str(fake),
                              '--output',str(HERE/'observed-rejection.json')], expected=1)
save('commands.json',commands)
paths = ['tools/audit_pid_flight.py','validation/test_pid_flight_audit.py','tools/audit_attitude_flight.py',
         'tools/run_pid_flight.py','tools/run-pid-flight.sh','tools/pid_physics.py',
         'Simulator/wksim_runtime/pid_task.py','Simulator/wksim_runtime/pid-flight-v1.json',
         'Simulator/wksim_control/position_pid.py']
save('source-sha256.json',{name:audit.digest(REPO/name) for name in paths})
save('artifact-sha256.json',{str(p.relative_to(HERE)):audit.digest(p) for p in HERE.rglob('*') if p.is_file()})
print(json.dumps(dict(windows_tests=42,wsl_tests=42,skipped=0,negative_cases=len(negative),
                      scope='Synthetic audit validation, no actual PID flight',evidence=str(HERE))))
