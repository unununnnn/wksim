"""Replay the archived PID-entry State through real ROS array storage."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prometheus_msgs.msg import UAVState
from Simulator.wksim_control.position_pid import PIDState

here = Path(__file__).resolve().parent
old = Path('/root/wksim-pid-flight-pid-px4-20260909-02-7e3ce147/pid-px4-20260909-02-7e3ce147/pid-progress.json')
raw = old.read_bytes()
entry = next(p['state'] for p in json.loads(raw)['phases'] if p['phase'] == 'pid_point_begin')
state = UAVState()
state.position, state.velocity = entry['position'], entry['velocity']
q = entry['attitude_q']
values = (tuple(state.position), tuple(state.velocity), tuple(q[k] for k in ('w', 'x', 'y', 'z')))
source = subprocess.check_output(['git', 'show', 'acf8c68:Simulator/wksim_control/position_pid.py'])
baseline = here/'baseline-position-pid.py'
with baseline.open('xb') as stream:
    stream.write(source)
spec = importlib.util.spec_from_file_location('pid_baseline', baseline)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
try:
    module.PIDState(*values)
except ValueError as error:
    failure = str(error)
else:
    raise AssertionError('Baseline must reproduce the archived failure')
assert failure == 'position_enu must be a finite number'
fixed = PIDState(*values)
assert list(fixed.position_enu) == entry['position']
assert list(fixed.velocity_enu) == entry['velocity']
print(json.dumps(dict(archived_source=str(old), archived_sha256=hashlib.sha256(raw).hexdigest(),
    baseline_sha256=hashlib.sha256(source).hexdigest(), scalar_type=str(type(state.position[0])),
    baseline_error=failure, fixed_position=fixed.position_enu, fixed_velocity=fixed.velocity_enu,
    values_unchanged=True), indent=2))
