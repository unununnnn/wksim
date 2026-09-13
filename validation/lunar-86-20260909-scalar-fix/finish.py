"""Audit the completed run without changing its sealed evidence."""
import json
import shlex
from run import BASE, HERE, OUTPUT, RUN, call

preflight = json.loads((HERE/'preflight.stdout.log').read_text())
directory = OUTPUT + '/' + RUN
audit_path = '/mnt/c' + HERE.as_posix()[2:] + '/pid-audit.json'
setup = ''.join('source ' + shlex.quote(p) + '\n' for p in preflight['setup_files'])
call('audit', BASE + ['bash', '-lc', 'set -e\n' + setup + shlex.join([
    '/usr/bin/python3', '-B', 'tools/audit_pid_flight.py', '--run-dir', directory, '--output', audit_path])])
call('result', BASE + ['cat', directory + '/result.json'])
result = json.loads((HERE/'result.stdout.log').read_text())
probe = """import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); result=json.loads((root/'result.json').read_text())
owned={}
for name,child in result['children'].items():
 p=pathlib.Path('/proc')/str(child['pid'])/'stat'
 owned[name]={'pid':child['pid'],'pid_exists':p.exists(),'same_proc_stat':p.exists() and p.read_text()==child['proc_stat']}
hashes={}
for name in ('result.json','physics-1ms.jsonl','pid-trace.jsonl','pid-progress.json','pid-resolved-config.json','disturbance-event.json'):
 p=root/name
 if p.exists():
  h=hashlib.sha256()
  with p.open('rb') as f:
   for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
  hashes[name]=h.hexdigest()
print(json.dumps({'owned_processes':owned,'raw_sha256':hashes},indent=2))
"""
call('cleanup-and-hashes', BASE + ['/usr/bin/python3', '-c', probe, directory])
print(json.dumps({k:result.get(k) for k in ('status','error','safe_landing','stop_kind',
    'children_reaped','cleanup_errors','source_unchanged','candidate_unchanged')}, indent=2))
print((HERE/'audit.stdout.log').read_text())
