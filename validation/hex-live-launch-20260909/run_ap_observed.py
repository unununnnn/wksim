"""One AP Hex run with reviewed native target/landed observation requests."""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
repo = here.parents[1]
sys.path.insert(0,str(repo/'validation/lunar-86-20260909-scalar-fix'))
import run as recorder
recorder.HERE = here
raise SystemExit(recorder.call('ap-observed-coordinator', ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass',
    '-File',str(repo/'tools/run-hex-live.ps1'),'-Stack','arducopter',
    '-RunId','hex-ap-live-observed-20260909-04',
    '-OutputRoot','/root/wksim-hex-flight-ap-live-observed-20260909-04',
    '-Output',str(repo/'validation/25-ap-live-observed-20260909-04')]))
