import base64
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
precheck = (root/'precheck.py').read_text()
checks = []
for distro in ('Ubuntu-22.04', 'RflySim-20.04'):
    run = subprocess.run(['wsl.exe', '-d', distro, '-u', 'root', '--', 'python3', '-'],
                         input=precheck, capture_output=True, text=True, timeout=45)
    assert run.returncode == 0, run.stderr
    result = json.loads([x for x in run.stdout.splitlines() if x.startswith('{')][-1])
    assert not result['found'], result
    checks.append(result)
(root/'linux-prechecks.json').write_bytes((json.dumps(checks, indent=2)+'\n').encode())
encoded = base64.b64encode(json.dumps(checks).encode()).decode()
script = 'import base64,json\nchecks=json.loads(base64.b64decode('+repr(encoded)+'))\n'
script += '''
import hashlib,os,pathlib,signal,subprocess,time
repo=pathlib.Path('/mnt/c/Users/PC/Documents/odid编译/wksim')
boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert all(c['boot_id']==boot and 0<=time.time()-c['checked_unix']<=60 and not c['found'] for c in checks)
ancestor=subprocess.run(['git','merge-base','--is-ancestor','f333316e6efa6b299b4288a9d91fb2bccedfb9d6','HEAD'],cwd=repo)
assert ancestor.returncode==0
files=['Simulator/wksim_core/ackermann.py','Simulator/wksim_runtime/experiment_bundle.py','tools/run_experiment.py','Simulator/wksim_runtime/replay.py','validation/test_ackermann_response_bounds.py','validation/test_experiment_input_identity.py','validation/test_replay_read_limits.py']
hashes={n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in files}
mods=['validation.test_ackermann_response_bounds','validation.test_vehicle_models','validation.test_experiment_input_identity','validation.test_experiment_bundle','validation.test_control_module_seams','validation.test_replay_read_limits','validation.test_wksim_replay']
argv=['python3','-m','unittest',*mods]
p=subprocess.Popen(argv,cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
try:stdout,stderr=p.communicate(timeout=45)
except subprocess.TimeoutExpired:
 os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate()
out={'cwd':str(repo),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'architecture_ancestor_exit_code':0,'argv':argv,'pid':p.pid,'exit_code':p.returncode,'stdout':stdout,'stderr':stderr,'boot_id':boot,'source_sha256':hashes}
try:os.killpg(p.pid,0);out['pgid_empty']=False
except ProcessLookupError:out['pgid_empty']=True
out['sources_unchanged']=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in hashes.items())
out['boot_after']=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
print(json.dumps(out))
'''
run = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '-u', 'root', '--', 'python3', '-'],
                     input=script, capture_output=True, text=True, timeout=60)
assert run.returncode == 0, (run.stdout, run.stderr)
result = json.loads([x for x in run.stdout.splitlines() if x.startswith('{')][-1])
(root/'linux-receipt.json').write_bytes((json.dumps(result, indent=2)+'\n').encode())
print(json.dumps({k: result[k] for k in ('exit_code', 'stderr', 'pgid_empty', 'sources_unchanged')}))
