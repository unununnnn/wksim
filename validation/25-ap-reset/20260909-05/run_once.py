"""One AP cold rebuild from the accepted AP04 result; no live-view changes."""
import json
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
repo = here.parents[2]
sys.path.insert(0,str(repo/'validation/lunar-86-20260909-scalar-fix'))
import run as recorder
recorder.HERE = here
parent = '/root/wksim-hex-flight-ap-live-observed-20260909-04/hex-ap-live-observed-20260909-04'
parent_sha = 'd29308997ac1c71d7d89ad30ea5a0a8431164a19a12988f44efe188747531c86'
audit = recorder.BASE+['bash','validation/lunar-65-astra-20260909-01/run-audit.sh','tools/audit_hex_flight.py']
dest = '/mnt/c'+here.as_posix()[2:]
if recorder.call('parent-audit-command',audit+['--run-dir',parent,'--output',dest+'/parent-audit-report.json']):
    raise SystemExit(1)
p = json.loads((here/'parent-audit-report.json').read_text())
assert p['passed'] and p['inputs_sha256']['result.json'] == parent_sha
run_id = 'hex-ap-reset-observed-20260909-05'
output = '/root/wksim-hex-flight-ap-reset-observed-20260909-05'
root = output+'/'+run_id
rc = recorder.call('flight',recorder.BASE+['bash','tools/run-hex-flight.sh','--stack','arducopter',
    '--run-id',run_id,'--output-root',output,'--cold-reset-from',parent+'/result.json'])
if recorder.call('result',recorder.BASE+['cat',root+'/result.json']):
    raise SystemExit(1)
result = json.loads((here/'result.stdout.log').read_text())
assert result['cold_reset_from']['sha256'] == parent_sha
audit_rc = recorder.call('strict-audit-command',audit+['--run-dir',root,'--require-cold-reset',
    '--output',dest+'/strict-audit-report.json'])
print(json.dumps({k:result.get(k) for k in ('status','error','safe_landing','children_reaped','cleanup_errors')},indent=2))
print((here/'strict-audit-command.stdout.log').read_text())
raise SystemExit(rc or audit_rc)
