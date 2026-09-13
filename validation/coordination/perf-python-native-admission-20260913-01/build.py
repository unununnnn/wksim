"""Main-only native shared-library build, with fresh two-WSL checks."""
import ast
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
assert not (root / 'build-receipt.json').exists()
prior = root.parent / 'perf-counter-integration-20260913-01/run_checks.py'
tree = ast.parse(prior.read_text())
pre = next(ast.literal_eval(n.value) for n in tree.body
           if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
           and n.targets[0].id == 'pre')
checks = []
for distro in ('Ubuntu-22.04', 'RflySim-20.04'):
    result = subprocess.run(['wsl.exe', '-d', distro, '-u', 'root', '--', 'python3', '-'],
                            input=pre, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    check = json.loads([s for s in result.stdout.splitlines() if s.startswith('{')][-1])
    assert not check['found'], check
    checks.append(check)
(root / 'build-prechecks.json').write_text(json.dumps(checks, indent=2) + '\n')
linux = r'''
import hashlib,json,os,pathlib,platform,signal,subprocess,tempfile,time
boot_path=pathlib.Path('/proc/sys/kernel/random/boot_id')
boot=boot_path.read_text().strip()
assert all(c['boot_id']==boot and not c['found'] and
           0<=time.time()-c['checked_unix']<=60 for c in checks)
assert platform.release()=='6.6.87.2-microsoft-standard-WSL2'
repo=pathlib.Path('/root/wksim-architecture-acceptance-20260913')
ancestor=subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',
 'f333316e6efa6b299b4288a9d91fb2bccedfb9d6','HEAD'])
assert ancestor.returncode==0
head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
assert not subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip()
source=repo/'validation/coordination/ds-perf-stream-recorder-20260913-01'
pins={'wksim_perf_stream.c':'aa807f3baaafcd64ed6174a49f8010b49798a74d139ead2d4eb69eafa503c1d2',
      'wksim_perf_stream.h':'ef1eabf247107098dc59a314d99b8fc82d4c54dbddd58d645bcec35141a12823'}
out=pathlib.Path(tempfile.mkdtemp(prefix='wksim-perf-python-admission-',dir='/root'))
for name,sha in pins.items():
 data=(source/name).read_bytes()
 assert hashlib.sha256(data).hexdigest()==sha
 (out/name).write_bytes(data)
argv=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread','-shared','-fPIC',
      '-o',str(out/'libwksim_perf_stream.so'),str(out/'wksim_perf_stream.c')]
process=subprocess.Popen(argv,cwd=out,start_new_session=True,stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,text=True)
timed_out=False
try:stdout,stderr=process.communicate(timeout=30)
except subprocess.TimeoutExpired:
 timed_out=True
 if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
 stdout,stderr=process.communicate()
try:os.killpg(process.pid,0);empty=False
except ProcessLookupError:empty=True
result={'cwd':str(repo),'head':head,'architecture_ancestor_exit_code':ancestor.returncode,
 'work_class':'new-architecture-acceptance preparation; independent perf library',
 'kernel':platform.release(),'boot_id':boot,'directory':str(out),'source_sha256':pins,
 'command':argv,'pid':process.pid,'exit_code':process.returncode,'timed_out':timed_out,
 'stdout':stdout,'stderr':stderr,'pgid_empty':empty,'capture_executed':False,
 'architecture_acceptance':False,'full_acceptance':False}
if process.returncode==0 and empty:
 result['library_sha256']=hashlib.sha256((out/'libwksim_perf_stream.so').read_bytes()).hexdigest()
 symbols=subprocess.run(['nm','-D','--defined-only',str(out/'libwksim_perf_stream.so')],
                        capture_output=True,text=True,timeout=10)
 result['export_check']={'exit_code':symbols.returncode,'stdout':symbols.stdout,'stderr':symbols.stderr}
 assert symbols.returncode==0
 names={s.split()[-1] for s in symbols.stdout.splitlines()}
 assert {'wksim_perf_start','wksim_perf_stop','wksim_perf_last_error'}<=names
result['boot_after']=boot_path.read_text().strip()
(out/'build-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
'''
result = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '-u', 'root', '--', 'python3', '-'],
                        input='checks=' + repr(checks) + '\n' + linux,
                        capture_output=True, text=True, timeout=45)
(root / 'build-stdout.txt').write_text(result.stdout)
(root / 'build-stderr.txt').write_text(result.stderr)
assert result.returncode == 0, (result.stdout, result.stderr)
receipt = json.loads([s for s in result.stdout.splitlines() if s.startswith('{')][-1])
(root / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
assert receipt['exit_code'] == 0 and receipt['pgid_empty'] and not receipt['timed_out']
assert receipt['boot_id'] == receipt['boot_after']
print(json.dumps(receipt))
