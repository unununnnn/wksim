"""Isolate EEXIST after a valid switch pair; never overwrite earlier captures."""
import ast
import base64
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
assert not (root / 'collision-receipt.json').exists()
tree = ast.parse((root.parent / 'perf-counter-integration-20260913-01/run_checks.py').read_text())
pre = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
           and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'pre')
checks = []
for distro in ('Ubuntu-22.04', 'RflySim-20.04'):
    result = subprocess.run(['wsl.exe', '-d', distro, '-u', 'root', '--', 'python3', '-'],
                            input=pre, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    check = json.loads([s for s in result.stdout.splitlines() if s.startswith('{')][-1])
    assert not check['found'], check
    checks.append(check)
(root / 'collision-prechecks.json').write_text(json.dumps(checks, indent=2) + '\n')
payload = dict(checks=checks, build=json.loads((root / 'build-receipt.json').read_text()),
               adapter=base64.b64encode((root.parents[2] / 'Simulator/wksim_runtime/perf_capture.py').read_bytes()).decode())
linux = r'''
import base64,hashlib,json,os,pathlib,signal,subprocess,tempfile,time
boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert all(c['boot_id']==boot and not c['found'] and 0<=time.time()-c['checked_unix']<=60 for c in payload['checks'])
b=payload['build'];lib=pathlib.Path(b['directory'])/'libwksim_perf_stream.so'
assert hashlib.sha256(lib.read_bytes()).hexdigest()==b['library_sha256']
out=pathlib.Path(tempfile.mkdtemp(prefix='collision-',dir=b['directory']))
(out/'perf_capture.py').write_bytes(base64.b64decode(payload['adapter']))
driver=r"""
import errno,json,pathlib,sys,time
from perf_capture import PerfCaptureError,PerfStreamCapture
out=pathlib.Path(sys.argv[1]);cap=PerfStreamCapture(sys.argv[2],sys.argv[3],out/'switch.raw',out/'switch.meta.json')
cap.start()
try:
 time.sleep(.03);time.sleep(.03)
 (out/'switch.raw').write_bytes(b'preserve original')
 try:cap.stop();raise AssertionError('stop unexpectedly succeeded')
 except PerfCaptureError as e:failure=str(e)
 assert not cap.owns_handle and not cap.stop_completed
finally:
 if cap.owns_handle:cap.stop()
meta=json.loads((out/'switch.meta.json').read_text())
assert meta['complete_pairs']>=2 and meta['kernel_lost_count']==0
assert meta['collector_errors'] and all(e['saved_errno']==errno.EEXIST for e in meta['collector_errors'])
assert all(meta['lifecycle'][k] for k in ('disable_ok','reader_joined','munmap_ok','close_ok'))
assert (out/'switch.raw').read_bytes()==b'preserve original'
print(json.dumps({'failure':failure,'retained':cap.owns_handle,'stop_completed':cap.stop_completed,'meta':meta}))
"""
(out/'driver.py').write_text(driver)
argv=['python3',str(out/'driver.py'),str(out),str(lib),b['library_sha256']]
p=subprocess.Popen(argv,cwd=out,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
timed_out=False
try:stdout,stderr=p.communicate(timeout=15)
except subprocess.TimeoutExpired:
 timed_out=True
 if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
 stdout,stderr=p.communicate()
try:os.killpg(p.pid,0);empty=False
except ProcessLookupError:empty=True
r={'directory':str(out),'boot_id':boot,'argv':argv,'pid':p.pid,'exit_code':p.returncode,
 'timed_out':timed_out,'pgid_empty':empty,'stdout':stdout,'stderr':stderr,
 'adapter_sha256':hashlib.sha256((out/'perf_capture.py').read_bytes()).hexdigest(),
 'library_sha256':b['library_sha256'],'boot_after':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
if p.returncode==0:r['case']=json.loads(stdout)
print(json.dumps(r))
'''
result = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '-u', 'root', '--', 'python3', '-'],
                        input='payload=' + repr(payload) + '\n' + linux,
                        capture_output=True, text=True, timeout=30)
assert result.returncode == 0, (result.stdout, result.stderr)
receipt = json.loads([s for s in result.stdout.splitlines() if s.startswith('{')][-1])
(root / 'collision-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
assert receipt['exit_code'] == 0 and receipt['pgid_empty'] and not receipt['timed_out']
assert receipt['boot_id'] == receipt['boot_after']
print(json.dumps(receipt))
