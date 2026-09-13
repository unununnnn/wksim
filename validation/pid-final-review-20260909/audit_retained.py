"""Regenerate a full audit with distinct report/command-record paths."""
import json
from pathlib import Path
import shlex
import sys

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'validation/lunar-86-20260909-scalar-fix'))
import run as recorder
case = (repo/sys.argv[1]).resolve()
if not case.is_relative_to(repo/'validation'):
    raise ValueError('Evidence directory must be inside project validation')
recorder.HERE = case
result = json.loads((case/'result.stdout.log').read_text())
setup = '\n'.join('source '+shlex.quote(s) for s in result['admission']['setup_files'])
dest = '/mnt/c'+case.as_posix()[2:]+'/strict-audit-report.json'
code = "import sys,runpy;sys.path.insert(0,'/root/wksim-attitude-audit-deps-g_2y8olg');runpy.run_path('tools/audit_pid_flight.py',run_name='__main__')"
rc = recorder.call('strict-audit-command',recorder.BASE+['bash','-lc',setup+'\n'+shlex.join([
    '/usr/bin/python3','-B','-c',code,'--run-dir',result['run_dir'],'--output',dest])])
report = json.loads((case/'strict-audit-report.json').read_text())
assert report['schema'] == 'wksim.pid.audit.v1'
assert report['run_id'] == result['run_id']
print(json.dumps(dict(status=report['status'],failure=report.get('failure'),
    checks=list(report['checks'])),indent=2))
raise SystemExit(rc)
