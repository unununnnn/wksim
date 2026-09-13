"""One AP #87 attempt after #86 passed; no automatic flight retries."""
import json
from pathlib import Path
import shlex
import sys

here = Path(__file__).resolve().parent
repo = here.parents[2]
sys.path.insert(0, str(repo/'validation/lunar-86-20260909-scalar-fix'))
import run as recorder
recorder.HERE = here
run_id = 'pid-ap-native-backpressure-20260909-01'
output = '/root/wksim-pid-flight-' + run_id
root = output+'/'+run_id
# The runner itself performs actual admission before launching any child and
# retains both pre/post identities. A second separate preflight is unnecessary.
rc = recorder.call('flight', recorder.BASE+['bash','tools/run-pid-flight.sh',
    '--stack','arducopter','--run-id',run_id,'--config','Simulator/wksim_runtime/pid-flight-v1.json',
    '--output-root',output])
if recorder.call('result', recorder.BASE+['cat',root+'/result.json']):
    raise SystemExit(1)
result = json.loads((here/'result.stdout.log').read_text())
setup = '\n'.join('source '+shlex.quote(s) for s in result['admission']['setup_files'])
dest = '/mnt/c'+here.as_posix()[2:]+'/audit.json'
audit_rc = recorder.call('audit', recorder.BASE+['bash','-lc',setup+'\n'+shlex.join([
    '/usr/bin/python3','-B','tools/audit_pid_flight.py','--run-dir',root,'--output',dest])])
print(json.dumps({k:result.get(k) for k in ('status','error','safe_landing','children_reaped',
    'cleanup_errors','source_unchanged','candidate_unchanged','stop_kind')},indent=2))
print((here/'audit.stdout.log').read_text())
raise SystemExit(rc or audit_rc)
