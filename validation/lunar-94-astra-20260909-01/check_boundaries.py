"""Read-only reproduction of the #94 selection gap; no runtime processes."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Simulator.wksim_control.position_pid import PIDConfig, select_controller
from Simulator.wksim_runtime.pid_task import load_config, CONFIG_PATH

config = load_config(CONFIG_PATH)
assert config['controller'] == 'pid'
try:
    select_controller('ne', PIDConfig(config['model']['mass_kg']))
except ValueError as error:
    rejection = str(error)
else:
    raise AssertionError('NE unexpectedly selectable: reassess scope')
paths = ['Simulator/wksim_control/position_ne.py',
         'Simulator/wksim_control/position_pid.py',
         'Simulator/wksim_runtime/pid_task.py',
         'Simulator/wksim_runtime/pid-flight-v1.json',
         'tools/run_pid_flight.py', 'tools/pid_physics.py',
         'tools/audit_pid_flight.py',
         'validation/lunar-93-ne-20260909-02/result.json']
print(json.dumps(dict(ne_selection_rejected=rejection,
    hashes={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}), indent=2))
