"""Schedule one reviewed AP Hex live attempt, preserving coordinator output."""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
repo = here.parents[1]
sys.path.insert(0,str(repo/'validation/lunar-86-20260909-scalar-fix'))
import run as recorder
recorder.HERE = here
raise SystemExit(recorder.call('coordinator', ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass',
    '-File',str(repo/'tools/run-hex-live.ps1'),'-Stack','arducopter','-RunId','hex-ap-live-20260909-01',
    '-OutputRoot','/root/wksim-hex-flight-ap-live-20260909-01',
    '-Output',str(repo/'validation/25-ap-live-20260909-01')]))
