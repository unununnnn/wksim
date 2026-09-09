"""Strict offline audit of the new completed candidate; originals stay sealed."""
import json
from pathlib import Path
import shlex
import sys

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parent/'lunar-86-20260909-scalar-fix'))
import run as recorder
recorder.HERE = here
root = '/root/wksim-pid-flight-pid-px4-native-backpressure-20260909-01/pid-px4-native-backpressure-20260909-01'
preflight = json.loads((here/'preflight.stdout.log').read_text())
setup = '\n'.join('source '+shlex.quote(s) for s in preflight['setup_files'])
code = "import sys,runpy;sys.path.insert(0,'/root/wksim-attitude-audit-deps-g_2y8olg');runpy.run_path('tools/audit_pid_flight.py',run_name='__main__')"
dest = '/mnt/c'+here.as_posix()[2:]+'/audit.json'
rc = recorder.call('strict-audit', recorder.BASE+['bash','-lc',setup+'\n'+shlex.join([
    '/usr/bin/python3','-B','-c',code,'--run-dir',root,'--output',dest])])
recorder.call('result', recorder.BASE+['cat',root+'/result.json'])
result = json.loads((here/'result.stdout.log').read_text())
print(json.dumps({k:result.get(k) for k in ('status','error','safe_landing','children_reaped',
    'cleanup_errors','source_unchanged','candidate_unchanged','stop_kind')},indent=2))
print((here/'strict-audit.stdout.log').read_text())
raise SystemExit(rc)
