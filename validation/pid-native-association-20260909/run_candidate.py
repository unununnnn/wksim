"""One post-backpressure PX4 run using the unchanged frozen flight protocol."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent/'lunar-86-20260909-scalar-fix'))
import run as recorder

recorder.HERE = HERE
RUN = 'pid-px4-native-backpressure-20260909-01'
OUTPUT = '/root/wksim-pid-flight-' + RUN
sources = ['Simulator/wksim_runtime/pid_task.py', 'Simulator/wksim_runtime/pid-flight-v1.json',
           'Simulator/wksim_control/position_pid.py', 'tools/audit_pid_flight.py',
           'validation/test_pid_flight.py', 'validation/test_pid_flight_audit.py']
with (HERE/'source-sha256.json').open('x') as f:
    json.dump({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}, f, indent=2)
setup = 'source /opt/ros/humble/setup.bash; source /root/wksim-ros2-MUlZd0/install/local_setup.bash; '
if recorder.call('tests', recorder.BASE + ['bash','-lc', setup +
        '/usr/bin/python3 -B -m unittest validation.test_pid_flight validation.test_position_pid validation.test_pid_flight_audit -v']):
    raise SystemExit(1)
flight = recorder.BASE + ['bash', 'tools/run-pid-flight.sh', '--stack', 'px4', '--run-id', RUN,
    '--config', 'Simulator/wksim_runtime/pid-flight-v1.json', '--output-root', OUTPUT]
if recorder.call('preflight', flight + ['--preflight']):
    raise SystemExit(1)
raise SystemExit(recorder.call('flight', flight))
