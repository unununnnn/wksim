"""Two explicitly reviewed, sequential live attempts; no retry on failure."""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
repo = here.parents[1]
sys.path.insert(0,str(repo/'validation/lunar-86-20260909-scalar-fix'))
import run as recorder
recorder.HERE = here
base = ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(repo/'tools/run-hex-live.ps1')]
rc = recorder.call('px4-reset2-coordinator',base+['-Stack','px4','-RunId','hex-px4-live-reset-20260909-02',
    '-OutputRoot','/root/wksim-hex-flight-px4-live-reset-20260909-02',
    '-Output',str(repo/'validation/25-px4-reset-live-20260909-02'),
    '-ColdResetFrom','/root/wksim-hex-flight-px4-03/hex-px4-03/result.json'])
if rc not in (0,2):
    raise SystemExit(rc)
# Exit2 is explicitly only Actor/physical pass; parent still reviews real PNGs.
raise SystemExit(recorder.call('ap47v2-coordinator',base+['-Stack','arducopter',
    '-RunId','hex-ap-live-ap47v2-20260909-03',
    '-OutputRoot','/root/wksim-hex-flight-ap-live-ap47v2-20260909-03',
    '-Output',str(repo/'validation/25-ap-live-ap47v2-20260909-03')]))
