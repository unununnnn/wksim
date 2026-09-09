"""One frozen PX4 cold-reset/live run from the strictly audited PX4-03 parent."""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
repo = here.parents[1]
sys.path.insert(0,str(repo/'validation/lunar-86-20260909-scalar-fix'))
import run as recorder
recorder.HERE = here
raise SystemExit(recorder.call('px4-reset-coordinator', ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass',
    '-File',str(repo/'tools/run-hex-live.ps1'),'-Stack','px4','-RunId','hex-px4-live-reset-20260909-01',
    '-OutputRoot','/root/wksim-hex-flight-px4-live-reset-20260909-01',
    '-Output',str(repo/'validation/25-px4-reset-live-20260909-01'),
    '-ColdResetFrom','/root/wksim-hex-flight-px4-03/hex-px4-03/result.json']))
