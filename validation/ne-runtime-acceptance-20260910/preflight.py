"""Record real installed-resource NE admission for both stacks."""
import json
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
repo = here.parents[1]
sys.path.insert(0, str(repo / 'validation/lunar-86-20260909-scalar-fix'))
import run as recorder

stack = sys.argv[1]
assert stack in ('px4', 'arducopter')
recorder.HERE = here
raise SystemExit(recorder.call(stack + '-preflight', recorder.BASE + [
    'bash', 'tools/run-pid-flight.sh', '--stack', stack,
    '--run-id', 'ne-' + stack + '-admission-20260910-01',
    '--config', 'Simulator/wksim_runtime/ne-flight-v1.json', '--preflight']))
