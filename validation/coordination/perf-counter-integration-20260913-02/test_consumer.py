import copy
import json
from pathlib import Path
import struct
import subprocess
import sys

root = Path(__file__).resolve().parent
coord = root.parent
fixture = coord/'ds-perf-stream-fixtures-20260913-01/fixtures/normal_two_pairs'
consumer = coord/'ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py'
raw = (fixture/'raw.bin').read_bytes()
base = json.loads((fixture/'metadata.json').read_bytes())
base['config']['read_format'] = 16
base.update(kernel_lost_read_ok=True, kernel_lost_read_bytes=16,
            kernel_lost_read_errno=0, kernel_lost_count=0)
cases = [('zero', base, raw, True, None)]
for name, key, value, reason in [
    ('lost', 'kernel_lost_count', 385, 'kernel_loss_counter_nonzero'),
    ('negative', 'kernel_lost_count', -1, 'kernel_loss_counter_value_invalid'),
    ('overflow', 'kernel_lost_count', 1 << 64, 'kernel_loss_counter_value_invalid'),
    ('bool', 'kernel_lost_count', False, 'kernel_loss_counter_value_invalid'),
    ('float', 'kernel_lost_count', 0.0, 'kernel_loss_counter_value_invalid'),
    ('null', 'kernel_lost_count', None, 'kernel_loss_counter_value_invalid'),
    ('unavailable', 'kernel_lost_read_ok', False, 'kernel_loss_counter_unavailable'),
    ('short', 'kernel_lost_read_bytes', 8, 'kernel_loss_counter_read_invalid'),
    ('bool_size', 'kernel_lost_read_bytes', True, 'kernel_loss_counter_read_invalid'),
    ('errno', 'kernel_lost_read_errno', 5, 'kernel_loss_counter_read_invalid'),
]:
    meta = copy.deepcopy(base)
    meta[key] = value
    cases.append((name, meta, raw, True, reason))
meta = copy.deepcopy(base)
del meta['kernel_lost_count']
cases.append(('missing_field', meta, raw, True, 'kernel_loss_counter_fields_missing'))
for value in (0, 16.0):
    meta = copy.deepcopy(base)
    meta['config']['read_format'] = value
    cases.append(('bad_format_'+str(value), meta, raw, True, 'kernel_loss_counter_format_invalid'))
legacy = json.loads((fixture/'metadata.json').read_bytes())
cases.append(('required_legacy', legacy, raw, True, 'kernel_loss_counter_required'))
cases.append(('inspect_legacy', legacy, raw, False, None))
meta = copy.deepcopy(base)
lost = struct.pack('<IHHQQIIQII', 2, 0, 48, 7, 1, base['owner_pid'],
                   base['owner_tid'], 3000000, 0, 0)
meta['captured_bytes'] += len(lost)
cases.append(('raw_lost_despite_zero', meta, raw+lost, True, 'record_lost_present'))
work = root/'counter-cases'
work.mkdir(exist_ok=False)
results = []
for name, meta, blob, required, reason in cases:
    case = work/name
    case.mkdir()
    (case/'raw.bin').write_bytes(blob)
    (case/'meta.json').write_bytes(json.dumps(meta).encode())
    argv = [sys.executable, '-B', str(consumer), '--raw', str(case/'raw.bin'),
            '--metadata', str(case/'meta.json'), '--output', str(case/'result.json')]
    if required:
        argv.append('--require-kernel-counter')
    run = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    if reason is None:
        report = json.loads((case/'result.json').read_bytes()) if run.returncode == 0 else {}
        expected_proof = name != 'inspect_legacy'
        passed = run.returncode == 0 and report.get('stream_completeness_proven') is expected_proof
        if expected_proof:
            passed &= report['window_completeness']['verified_until_ns'] == meta['disable_before_ns']
    else:
        err = json.loads(run.stderr) if run.stderr.strip() else {}
        passed = run.returncode == 3 and err.get('reason') == reason
    results.append(dict(case=name, passed=passed, expected_reason=reason,
                        exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr))
out = dict(synthetic=True, cases=len(results), failures=sum(not x['passed'] for x in results), results=results)
(root/'consumer-receipt.json').write_bytes((json.dumps(out, indent=2)+'\n').encode())
print(json.dumps({k: out[k] for k in ('cases', 'failures')}))
raise SystemExit(1 if out['failures'] else 0)
