"""One source-corrected AP retry; preserve the first failed run unchanged."""
import json
from pathlib import Path
import shlex
import sys

here = Path(__file__).resolve().parent
repo = here.parents[2]
sys.path.insert(0, str(repo/'validation/lunar-86-20260909-scalar-fix'))
import run as recorder
recorder.HERE = here
run_id = 'pid-ap-shaped-feedback-20260909-02'
root = '/root/wksim-pid-flight-'+run_id+'/'+run_id
setup = 'source /opt/ros/humble/setup.bash; source /root/wksim-ros2-MUlZd0/install/local_setup.bash; '
if recorder.call('tests',recorder.BASE+['bash','-lc',setup+
        '/usr/bin/python3 -B -m unittest validation.test_pid_flight validation.test_position_pid validation.test_pid_flight_audit -v']):
    raise SystemExit(1)
rc = recorder.call('flight',recorder.BASE+['bash','tools/run-pid-flight.sh','--stack','arducopter',
    '--run-id',run_id,'--config','Simulator/wksim_runtime/pid-flight-v1.json',
    '--output-root','/root/wksim-pid-flight-'+run_id])
if recorder.call('result',recorder.BASE+['cat',root+'/result.json']):
    raise SystemExit(1)
result = json.loads((here/'result.stdout.log').read_text())
setup = '\n'.join('source '+shlex.quote(s) for s in result['admission']['setup_files'])
dest = '/mnt/c'+here.as_posix()[2:]+'/audit.json'
audit_rc = recorder.call('audit',recorder.BASE+['bash','-lc',setup+'\n'+shlex.join([
    '/usr/bin/python3','-B','tools/audit_pid_flight.py','--run-dir',root,'--output',dest])])
print(json.dumps({k:result.get(k) for k in ('status','error','safe_landing','children_reaped',
    'cleanup_errors','source_unchanged','candidate_unchanged','stop_kind')},indent=2))
print((here/'audit.stdout.log').read_text())
raise SystemExit(rc or audit_rc)
