"""Run one fresh UDE lifetime, retaining command and raw output independently."""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
repo = here.parents[1]
sys.path.insert(0, str(repo / 'validation/lunar-86-20260909-scalar-fix'))
import run as recorder

stack = sys.argv[1]
assert stack in ('px4', 'arducopter')
attempt = sys.argv[2] if len(sys.argv) > 2 else '01'
assert attempt in ('01', '02')
run_id = 'ude-' + stack + '-acceptance-20260909-' + attempt
recorder.HERE = here
label = stack + ('' if attempt == '01' else '-' + attempt)
raise SystemExit(recorder.call(label + '-flight-command', recorder.BASE + [
    'bash', 'tools/run-pid-flight.sh', '--stack', stack, '--run-id', run_id,
    '--config', 'Simulator/wksim_runtime/ude-flight-v1.json',
    '--output-root', '/root/wksim-pid-flight-' + run_id]))
