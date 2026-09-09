"""Actual read-only installed-resource admission for the selected UDE protocol."""
import json
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
repo = here.parents[1]
sys.path.insert(0,str(repo/'validation/lunar-86-20260909-scalar-fix'))
import run as recorder
recorder.HERE = here
stack = sys.argv[1]
assert stack in ('px4','arducopter')
rc = recorder.call(stack+'-preflight',recorder.BASE+['bash','tools/run-pid-flight.sh','--stack',stack,
    '--run-id','ude-'+stack+'-admission-20260909-01','--config','Simulator/wksim_runtime/ude-flight-v1.json','--preflight'])
if rc:
    raise SystemExit(rc)
value = json.loads((here/(stack+'-preflight.stdout.log')).read_text())
assert value['ok'] and value['external_ude']['configuration']['controller'] == 'ude'
assert value['external_ude']['implementation'] == 'Simulator.wksim_control.position_ude.PositionUDE'
print(stack,'UDE admission passed')
