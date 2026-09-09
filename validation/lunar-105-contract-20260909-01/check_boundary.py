"""Read-only #105 source boundary evidence, not an efficiency/flight test."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Simulator.wksim_core.model_parameters import RAW_HASHES, make_config, validate

paths = ['Simulator/wksim_core/model.cpp', 'Simulator/wksim_core/model.py',
         'Simulator/wksim_core/model_parameters.py', 'tools/pid_physics.py',
         'Simulator/wksim_runtime/task.py', 'Simulator/wksim_runtime/pid_task.py',
         'Simulator/wksim_runtime/pid-flight-v1.json']
hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}
archive = Path(sys.argv[1])
archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
assert archive_hash == 'd528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed'
with zipfile.ZipFile(archive) as z:
    raw = z.read('e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.cpp')
assert hashlib.sha256(raw).hexdigest() == RAW_HASHES['Exp1_MinModelTemp.cpp']
config = make_config()
config['motor_efficiency'] = [0.97, 1, 1, 1]
try:
    validate(config)
except ValueError as error:
    rejection = str(error)
else:
    raise AssertionError('Current mass-only API unexpectedly accepts efficiency')
wrapper = (ROOT / paths[0]).read_text()
exports = [line.strip() for line in wrapper.splitlines()
           if line.startswith(('void* wk_', 'void wk_', 'int wk_'))]
assert len(exports) == 3, exports
assert all('efficiency' not in line for line in exports)
pid = json.loads((ROOT / paths[-1]).read_text())
assert pid['disturbance']['channels'] == [0, 1, 2, 3]
assert pid['disturbance']['multiplier'] == 0.97
assert hashes[paths[-1]] == '25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0'
print(json.dumps(dict(scope='read-only source boundary; no native execution or flight',
    archive_sha256=archive_hash, generated_cpp_sha256=hashlib.sha256(raw).hexdigest(),
    source_sha256=hashes, actual_wrapper_exports=exports,
    efficiency_config_rejection=rejection, pid_disturbance=pid['disturbance'],
    conclusion='native efficiency seam and runnable/auditable experiment absent; needs-triage'), indent=2))
