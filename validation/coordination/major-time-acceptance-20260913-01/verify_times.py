"""Independent checks of retained 11.8 major time fields; no model execution."""
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PINS = {
    'Vehicle60': 'fcbfb3439f2595d459463d61b1b9b5830290e4993b46ef8614e788880ebc8ceb',
    'Sensor30': '066a5561a82737d8ea0fccfd81c60efe82f1eb06156a460e67ba73fe545e8b90',
    'GPS30': '459dd65a702e64b28f701f79318250be56127470df2579fecbaa607845cc4074',
}


def bits(value):
    return struct.pack('<d', value)


def verify():
    raw = (ROOT / 'validation/e0-major-recorder-parent-final-01/record.jsonl').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '8ce61b3338d42f964dbb704bcebe25a7c0b728926eae974970fe3cb6a58ff354'
    records = [json.loads(line) for line in raw.splitlines()]
    assert records[0]['source']['original_cpp_sha256'] == '2c25b3fa08c996c8f2ed1a7feae5558062cd722ae5d350cc8a25caf2be10b274'
    assert records[0]['source']['insertion_line'] == 7919
    samples = [r for r in records if r['kind'] == 'major_recorder_sample']
    assert len(samples) == 501 and [r['k'] for r in samples] == list(range(501))
    reference_root = ROOT / 'validation/numerical-conformance-u56ce17a/C0'
    contract = json.loads((reference_root / 'contract.json').read_text())
    assert contract['identity']['reference_revision'] == 'SLX model 11.8'
    result = {}
    for array, width, index, gain in [('Vehicle60', 60, 2, 1), ('Sensor30', 30, 0, 1000000), ('GPS30', 30, 0, 1000000)]:
        reference_bytes = (reference_root / (array + '.f64')).read_bytes()
        assert hashlib.sha256(reference_bytes).hexdigest() == PINS[array]
        assert len(reference_bytes) == 501 * (width + 1) * 8
        reference = list(struct.iter_unpack('<' + 'd' * (width + 1), reference_bytes))
        native = [r['major_root_outputs'][array][index] for r in samples]
        expected = [(k * .001) * gain for k in range(501)]
        assert all(bits(a) == bits(b) == bits(c[index + 1]) for a, b, c in zip(native, expected, reference))
        row_time_division_matches = sum(bits(r[0]) == bits(k / 1000) for k, r in enumerate(reference))
        row_time_product_matches = sum(bits(r[0]) == bits(k * .001) for k, r in enumerate(reference))
        shifted = list(native)
        shifted[17] = ((17 + 1) * .001) * gain
        assert sum(bits(a) != bits(b) for a, b in zip(shifted, expected)) == 1
        result[array] = dict(rows=501, slot=index, unit='s' if gain == 1 else 'us',
            both_sides_match_product_then_gain=True,
            differs_from_division_then_gain=sum(bits(v) != bits((k / 1000) * gain) for k, v in enumerate(native)),
            shifted_row_rejected=True, reference_row_width=width + 1,
            reference_row_time_division_matches=row_time_division_matches,
            reference_row_time_product_matches=row_time_product_matches)
    return dict(source=records[0]['source'], reference_revision='SLX model 11.8',
                results=result, phase='major outputs before update',
                runtime_index_relation='zero-based call i returns runtime tick i+1; major row i precedes that update',
                budget_approved=False, g6_acceptance=False)


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
