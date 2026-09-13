"""Independently audit one sealed UDE flight; never overwrite prior evidence."""
import json
from pathlib import Path
import shlex
import sys

here = Path(__file__).resolve().parent
repo = here.parents[1]
sys.path.insert(0, str(repo / 'validation/lunar-86-20260909-scalar-fix'))
import run as recorder

stack = sys.argv[1]
assert stack in ('px4', 'arducopter')
attempt = sys.argv[2] if len(sys.argv) > 2 else '01'
assert attempt in ('01', '02')
label = stack + ('' if attempt == '01' else '-' + attempt)
if len(sys.argv) > 3:
    revision = sys.argv[3]
    assert revision.isalnum()
    label += '-' + revision
run_id = 'ude-' + stack + '-acceptance-20260909-' + attempt
root = '/root/wksim-pid-flight-' + run_id + '/' + run_id
result = json.loads(Path('//wsl.localhost/Ubuntu-22.04' + root + '/result.json').read_text())
setup = '\n'.join('source ' + shlex.quote(p) for p in result['admission']['setup_files'])
destination = '/mnt/c' + here.as_posix()[2:] + '/' + label + '-strict-audit-report.json'
command = ['/usr/bin/python3', '-B', '-c',
    "import sys,runpy;sys.path.insert(0,'/root/wksim-attitude-audit-deps-g_2y8olg');runpy.run_path('tools/audit_ude_flight.py',run_name='__main__')",
    '--run-dir', root, '--output', destination]
recorder.HERE = here
raise SystemExit(recorder.call(label + '-strict-audit-command', recorder.BASE + [
    'bash', '--noprofile', '--norc', '-c', setup + '\n' + shlex.join(command)]))
