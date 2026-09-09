"""One reviewed AP4.7 Hex live run; runtime/plan/config remain frozen."""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
repo = here.parents[1]
sys.path.insert(0,str(repo/'validation/lunar-86-20260909-scalar-fix'))
import run as recorder
recorder.HERE = here
raise SystemExit(recorder.call('ap47-coordinator', ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass',
    '-File',str(repo/'tools/run-hex-live.ps1'),'-Stack','arducopter','-RunId','hex-ap-live-ap47-20260909-02',
    '-OutputRoot','/root/wksim-hex-flight-ap-live-ap47-20260909-02',
    '-Output',str(repo/'validation/25-ap-live-ap47-20260909-02')]))
