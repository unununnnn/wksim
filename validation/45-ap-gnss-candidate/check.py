"""Run C++ contract fixtures; explicitly distinct from probe.py native AP evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys

here = Path(__file__).resolve().parent
out = Path(sys.argv[1]).resolve()
out.mkdir(exist_ok=False)
binary = out / 'header-test'
cmd = ['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', str(here / 'header_test.cpp'), '-o', str(binary)]
subprocess.run(cmd, check=True)
results = []
for mode, reason in [('boundaries', None), ('budget', None), ('warmup', None),
                     ('generation', None), ('late_generation', 'sensor_recreated_after_plan_start'),
                     ('warmup_repeat', 'stale_or_replayed_sample'), ('truth', 'truth_tick_mismatch'),
                     ('future', 'stale_or_replayed_sample'),
                     ('stale', 'stale_or_replayed_sample'), ('replay', 'stale_or_replayed_sample'),
                     ('hal', 'hal_phase_mismatch'), ('nofresh', 'write_without_fresh_sample'),
                     ('short', 'short_or_failed_serial_write')]:
    trace = out / (mode + '.tsv')
    result = subprocess.run([str(binary), mode], env=dict(os.environ, WKSIM_GNSS_TRACE=str(trace)))
    expected = 109 if reason else 0
    ok = result.returncode == expected and (reason is None or reason in trace.read_text())
    results.append(dict(mode=mode, exit=result.returncode, expected=expected, ok=ok))
(out / 'tests.json').write_text(json.dumps({'scope': 'C++ logic fixtures only', 'command': cmd, 'tests': results}, indent=2) + '\n')
print(json.dumps(results))
raise SystemExit(0 if all(r['ok'] for r in results) else 1)
