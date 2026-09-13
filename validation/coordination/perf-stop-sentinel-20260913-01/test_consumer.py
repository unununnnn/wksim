import copy
import json
from pathlib import Path
import struct
import subprocess
import sys

root = Path(__file__).resolve().parent
coord = root.parent
fixture = coord/'ds-perf-stream-fixtures-20260913-01/fixtures/normal_two_pairs'
consumer = root/'sources/perf_stream_consumer.py'  # superseded strategy, pinned historical source
base = json.loads((fixture/'metadata.json').read_bytes())
prior = (fixture/'raw.bin').read_bytes()
windows = json.loads((fixture/'windows.json').read_bytes())
before = 6_000_000

def switch(misc, when):
    return struct.pack('<IHHIIQII', 14, misc, 32, base['owner_pid'],
                       base['owner_tid'], when, 0, 0)

raw = prior + switch(1 << 13, before + 1000) + switch(0, before + 2000)
base.update(captured_bytes=len(raw), sentinel_completed=True,
            sentinel_before_ns=before, sentinel_after_ns=before + 3000,
            drain_confirmed_free_bytes=base['ring_bytes'],
            verifiable_window_end_ns=before)
cases = [('valid', base, raw, windows, None)]

def changed(name, key, value, reason):
    meta = copy.deepcopy(base)
    meta[key] = value
    cases.append((name, meta, raw, None, reason))

changed('incomplete', 'sentinel_completed', False, 'sentinel_not_completed')
changed('bool_clock', 'sentinel_before_ns', True, 'sentinel_field_not_integer')
changed('float_clock', 'sentinel_after_ns', float(before + 3000), 'sentinel_field_not_integer')
changed('cutoff', 'verifiable_window_end_ns', before + 1, 'sentinel_cutoff_mismatch')
changed('small_headroom', 'drain_confirmed_free_bytes', 4095, 'sentinel_drain_headroom_invalid')
changed('impossible_headroom', 'drain_confirmed_free_bytes', base['ring_bytes'] + 1,
        'sentinel_drain_headroom_invalid')
changed('late_check', 'sentinel_after_ns', base['disable_after_ns'] + 1,
        'sentinel_bounds_invalid')
changed('partial_pair', 'sentinel_before_ns', before + 1500, 'sentinel_cutoff_mismatch')
meta = copy.deepcopy(base)
meta['sentinel_before_ns'] = meta['verifiable_window_end_ns'] = before + 1500
cases.append(('overlap_is_not_a_full_pair', meta, raw, None, 'sentinel_pair_missing'))
meta = copy.deepcopy(base)
del meta['sentinel_after_ns']
cases.append(('missing_field', meta, raw, None, 'sentinel_fields_missing'))
meta = copy.deepcopy(base)
meta['captured_bytes'] = len(prior)
cases.append(('no_actual_pair', meta, prior, None, 'sentinel_pair_missing'))
late = copy.deepcopy(windows)
late['windows'] = [dict(id='late', start_ns=before - 1, end_ns=before + 1)]
cases.append(('late_window', base, raw, late, 'window_after_stop_check'))
lost = struct.pack('<IHHQQIIQII', 2, 0, 48, 7, 1, base['owner_pid'],
                   base['owner_tid'], before - 1000, 0, 0)
meta = copy.deepcopy(base)
bad_raw = prior + lost + raw[len(prior):]
meta['captured_bytes'] = len(bad_raw)
cases.append(('lost_before_sentinel', meta, bad_raw, None, 'record_lost_present'))

work = root/'consumer-cases'
work.mkdir(exist_ok=False)
results = []
for name, meta, stream, ranges, reason in cases:
    case = work/name
    case.mkdir()
    (case/'raw.bin').write_bytes(stream)
    (case/'meta.json').write_bytes(json.dumps(meta).encode())
    argv = [sys.executable, '-B', str(consumer), '--raw', str(case/'raw.bin'),
            '--metadata', str(case/'meta.json'), '--output', str(case/'output.json')]
    if ranges is not None:
        (case/'windows.json').write_bytes(json.dumps(ranges).encode())
        argv += ['--windows', str(case/'windows.json')]
    run = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    if reason is None:
        report = json.loads((case/'output.json').read_bytes()) if run.returncode == 0 else {}
        passed = run.returncode == 0 and report['window_completeness']['verified_until_ns'] == before
        passed &= report.get('stream_completeness_proven') is False
        passed &= [w['intersection_total_ns'] for w in report.get('windows', [])] == [150000, 0, 100000]
    else:
        error = json.loads(run.stderr) if run.stderr.strip() else {}
        passed = run.returncode == 3 and error.get('reason') == reason
    results.append(dict(case=name, passed=passed, expected_reason=reason,
                        exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr))
receipt = dict(synthetic=True, cases=len(results),
               failures=sum(not r['passed'] for r in results), results=results)
(root/'consumer-receipt.json').write_bytes((json.dumps(receipt, indent=2)+'\n').encode())
print(json.dumps({k: receipt[k] for k in ('cases', 'failures')}))
raise SystemExit(1 if receipt['failures'] else 0)
