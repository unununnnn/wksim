"""Read-only comparison of retained 11.8 native C0 and normal-mode C0 records."""
from pathlib import Path
import csv
import hashlib
import io
import json
import math
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from tools.run_e0_same_source_conformance import (
    ARRAY_LENGTHS, parse_native_record, parse_reference_f64,
)

native = ROOT / 'validation/e0-major-recorder-parent-final-01'
reference = ROOT / 'validation/numerical-conformance-u56ce17a/C0'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
build = json.loads((native / 'build-manifest.json').read_bytes())
summary = json.loads((native / 'summary.json').read_bytes())
assert summary['status'] == 'verified' and summary['parity_verified']
values = parse_native_record(native / 'record.jsonl', build['source_identity'])
records = [json.loads(line) for line in (native / 'record.jsonl').read_bytes().splitlines()]
input_raw = (reference / 'input.csv').read_bytes()
assert records[0]['input_csv'].encode('ascii') == input_raw
assert sha(reference / 'input.csv') == build['record_summary']['input_csv_sha256']
inputs = list(csv.reader(io.StringIO(input_raw.decode('ascii'))))[1:]
for k, sample in enumerate(records[1:-1]):
    row = list(map(float, inputs[k]))
    assert sample['inPWMs'] == row[2:18] and sample['TerrainIn15d'] == row[18:]
sources = json.loads((ROOT / 'validation/codegen-e0/short-cycle-codegen-01/source-manifest.json').read_bytes())
for source in sources:
    if source['filename'].endswith(('.slx', '.m')):
        assert sha(Path(source['staged_path'])) == source['sha256']
        assert source['sha256'] == sha(reference / 'staged-model' / source['filename'])
assert json.loads((reference / 'reference-process.json').read_bytes())['exit_code'] == 0

stats, differences = [], []
for array, width in ARRAY_LENGTHS.items():
    expected = parse_reference_f64(reference / (array + '.f64'), array, width)
    for index in range(width):
        errors, count = [], 0
        for k, (left, right) in enumerate(zip(expected, values[array])):
            delta = abs(left[index] - right[index])
            errors.append(delta)
            if left[index] != right[index]:
                count += 1
                differences.append(dict(array=array, index=index, k=k,
                    reference=left[index], native=right[index],
                    reference_hex=left[index].hex(), native_hex=right[index].hex(),
                    absolute_difference=delta))
        stats.append(dict(array=array, index=index, different_values=count,
            max_abs_difference=max(errors), rms_difference=math.hypot(*errors) / math.sqrt(501)))
paths = [native / 'record.jsonl', native / 'build-manifest.json', native / 'summary.json',
         reference / 'input.csv', reference / 'reference-process.json', reference / 'reference.json',
         ROOT / 'tools/run_e0_same_source_conformance.py', Path(__file__)]
paths += [reference / (array + '.f64') for array in ARRAY_LENGTHS]
result = dict(status='offline_diagnostic_only', case='C0', samples=501, scalar_count=120,
    comparisons=60120, different_values=len(differences),
    different_scalars=sum(row['different_values'] > 0 for row in stats),
    differences=differences, per_scalar=stats,
    identities={str(path.relative_to(ROOT)): sha(path) for path in paths},
    g6_acceptance=False, physical_accuracy='unverified',
    source_binding='Frozen SLX/init bytes match; generated native identity 11.8; exact same CSV and recorded 31 inputs',
    scope='Retained evidence compared offline; no new model execution, no budget assigned or changed, no official pass classification. Full new-contract provenance is not certified by this diagnostic.')
with (HERE / 'existing-c0-observation.json').open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps({key: value for key, value in result.items() if key not in ('per_scalar', 'identities')}))
