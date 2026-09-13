"""Offline scope/prerequisite evidence, not a runtime integration test."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Simulator.wksim_control.position_ude import PositionUDE, UDEConfig
from Simulator.wksim_control.position_pid import PIDState, PIDReference, NativeThrustConfig
from Simulator.wksim_runtime.pid_task import load_config

candidate = ROOT / 'Simulator/wksim_runtime/ude-flight-v1.json'
config = json.loads(candidate.read_bytes())
baseline = load_config(ROOT / 'Simulator/wksim_runtime/pid-flight-v1.json')
for key in ('model', 'hover_calibration', 'timing', 'point', 'circle', 'disturbance', 'envelope'):
    assert config[key] == baseline[key], key
algorithm = PositionUDE(UDEConfig(config['model']['mass_kg'], **config['ude']))
state = PIDState((0., 0., 0.), (0., 0., 0.), (1., 0., 0., 0.))
output = algorithm.update(state, PIDReference((.1, 0., 0.)), dt_s=.005, external_control_active=True)
assert output.controller == 'ude' and output.disturbance_acceleration_enu[0] != 0
for stack in ('px4', 'arducopter'):
    # Synthetic mapping input only; never a measured hover calibration.
    mapping = NativeThrustConfig(stack, config['model']['identity'], config['model']['mass_kg'], .5)
    assert .1 <= mapping.normalized_collective(output, model_identity=config['model']['identity']) <= 1
algorithm.reset('selection')
assert algorithm.integral == (0., 0., 0.) and algorithm.last_output is None
try:
    load_config(candidate)
except ValueError as error:
    rejection = str(error)
else:
    raise AssertionError('Existing PID loader unexpectedly admitted UDE')
paths = ['Simulator/wksim_runtime/ude-flight-v1.json', 'Simulator/wksim_runtime/pid-flight-v1.json',
         'Simulator/wksim_control/position_ude.py', 'Simulator/wksim_control/position_pid.py',
         'Simulator/wksim_runtime/pid_task.py', 'tools/run_pid_flight.py', 'tools/pid_physics.py',
         'tools/audit_pid_flight.py', 'validation/lunar-89-astra-20260909-02/summary.md']
print(json.dumps({'scope': 'offline candidate and current rejection only', 'runtime_integrated': False,
    'flight_pass': False, 'pid_loader_rejection': rejection,
    'sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}}, indent=2))
result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'validation.test_position_ude',
    'validation.test_position_pid', 'validation.test_pid_flight', '-v'], cwd=ROOT)
raise SystemExit(result.returncode)
