"""Main-only adapter admission against the pinned shared-library build."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
repo = root.parents[2]
assert not (root / 'run-receipt.json').exists()
tree = ast.parse((root.parent / 'perf-counter-integration-20260913-01/run_checks.py').read_text())
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
(root / 'run-prechecks.json').write_text(json.dumps(checks, indent=2) + '\n')
paths = {'perf_capture.py': repo / 'Simulator/wksim_runtime/perf_capture.py',
         'consumer.py': root.parent / 'ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py'}
payload = dict(checks=checks, build=json.loads((root / 'build-receipt.json').read_text()),
               sources={n: base64.b64encode(p.read_bytes()).decode() for n, p in paths.items()})
linux = r'''
import base64,hashlib,json,os,pathlib,signal,subprocess,tempfile,time
boot_path=pathlib.Path('/proc/sys/kernel/random/boot_id');boot=boot_path.read_text().strip()
assert all(c['boot_id']==boot and not c['found'] and
           0<=time.time()-c['checked_unix']<=60 for c in payload['checks'])
build=payload['build'];library=pathlib.Path(build['directory'])/'libwksim_perf_stream.so'
assert hashlib.sha256(library.read_bytes()).hexdigest()==build['library_sha256']
out=pathlib.Path(tempfile.mkdtemp(prefix='adapter-run-',dir=build['directory']))
for name,encoded in payload['sources'].items():(out/name).write_bytes(base64.b64decode(encoded))
receipt={'boot_id':boot,'directory':str(out),'library_sha256':build['library_sha256'],
 'source_sha256':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in payload['sources']},
 'commands':[],'full_acceptance':False,'architecture_acceptance':False}
driver=r"""
import json,os,pathlib,sys,threading,time
from perf_capture import PerfCaptureError,PerfStreamCapture
root=pathlib.Path(sys.argv[1]);library=sys.argv[2];sha=sys.argv[3];rows=[]
for name in ['normal','wrong-owner','existing-output']:
 directory=root/name;directory.mkdir()
 cap=PerfStreamCapture(library,sha,directory/'switch.raw',directory/'switch.meta.json')
 row={'case':name,'owner_pid':cap.owner_pid,'owner_tid':cap.owner_tid}
 try:
  cap.start()
  if name=='normal':
   for _ in range(6):time.sleep(.05)
  elif name=='wrong-owner':
   errors=[]
   def other():
    try:cap.stop()
    except PerfCaptureError as e:errors.append(str(e))
   thread=threading.Thread(target=other);thread.start();thread.join(timeout=2)
   assert not thread.is_alive() and len(errors)==1 and cap.owns_handle
   row['wrong_owner_rejected']=True;time.sleep(.02)
  else:(directory/'switch.raw').write_bytes(b'preserve original')
  try:
   cap.stop();row['stop_error']=None
  except PerfCaptureError as e:row['stop_error']=str(e)
  row.update(owns_handle=cap.owns_handle,stop_completed=cap.stop_completed)
  assert not cap.owns_handle
  if name=='existing-output':
   assert row['stop_error'] and not cap.stop_completed
   assert (directory/'switch.raw').read_bytes()==b'preserve original'
  else:assert row['stop_error'] is None and cap.stop_completed
 finally:
  if cap.owns_handle:cap.stop()
 rows.append(row)
print(json.dumps(rows))
"""
(out/'driver.py').write_text(driver)
def execute(argv,cwd=out,timeout=20):
 p=subprocess.Popen(argv,cwd=cwd,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 timed_out=False
 try:stdout,stderr=p.communicate(timeout=timeout)
 except subprocess.TimeoutExpired:
  timed_out=True
  if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
  stdout,stderr=p.communicate()
 try:os.killpg(p.pid,0);empty=False
 except ProcessLookupError:empty=True
 row={'argv':argv,'pid':p.pid,'exit_code':p.returncode,'stdout':stdout,'stderr':stderr,
      'timed_out':timed_out,'pgid_empty':empty}
 receipt['commands'].append(row)
 (out/'run-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 assert p.returncode==0 and empty and not timed_out,row
 return row
workspace=pathlib.Path('/mnt/c/Users/PC/Documents/odid编译/wksim')
execute(['python3','-m','unittest','validation.test_perf_capture','-v'],cwd=workspace)
cases=execute(['python3',str(out/'driver.py'),str(out),str(library),build['library_sha256']])
receipt['cases']=json.loads(cases['stdout'])
for name in ('normal','wrong-owner'):
 d=out/name
 execute(['python3',str(out/'consumer.py'),'--raw',str(d/'switch.raw'),'--metadata',str(d/'switch.meta.json'),
          '--output',str(d/'decoded.json'),'--require-kernel-counter'])
 result=json.loads((d/'decoded.json').read_text());meta=json.loads((d/'switch.meta.json').read_text())
 assert result['stream_completeness_proven'] is True and meta['boot_id']==boot
 assert meta['owner_pid']==meta['owner_tid']==receipt['cases'][0]['owner_pid']
receipt['boot_after']=boot_path.read_text().strip()
assert receipt['boot_after']==boot
receipt['files']={p.relative_to(out).as_posix():base64.b64encode(p.read_bytes()).decode()
 for p in out.rglob('*') if p.is_file() and p.suffix in ('.json','.raw') and p.name!='run-receipt.json'}
(out/'run-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
'''
script = 'payload=' + repr(payload) + '\n' + linux
result = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '-u', 'root', '--', 'python3', '-'],
                        input=script, capture_output=True, text=True, timeout=55)
(root / 'run-stdout.txt').write_text(result.stdout)
(root / 'run-stderr.txt').write_text(result.stderr)
assert result.returncode == 0, (result.stdout, result.stderr)
receipt = json.loads([s for s in result.stdout.splitlines() if s.startswith('{')][-1])
(root / 'run-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
for name, encoded in receipt['files'].items():
    target = root / 'capture' / name
    assert target.resolve().is_relative_to((root / 'capture').resolve())
    target.parent.mkdir(exist_ok=True, parents=True)
    with target.open('xb') as stream:
        stream.write(base64.b64decode(encoded))
for name, path in paths.items():
    assert hashlib.sha256(path.read_bytes()).hexdigest() == receipt['source_sha256'][name]
print(json.dumps({k: v for k, v in receipt.items() if k != 'files'}))
