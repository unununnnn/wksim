"""Read-only comparison under an explicit budget; never a G6 approval or runner."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def integer(value):
    return type(value) is int and value >= 0


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode(data):
    return json.loads(data, object_pairs_hook=unique_object,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('non-finite JSON: ' + x)))


def validate_contract(c):
    require(isinstance(c, dict) and c.get('schema') == 'model-trace-comparison-v1', 'unsupported contract schema')
    require(nonempty(c.get('case')) and integer(c.get('epoch')), 'case/epoch required')
    for side in ('reference', 'candidate'):
        identity = c.get(side)
        require(isinstance(identity, dict), side + ' identity required')
        require(set(identity) == {'model_sha256', 'configuration_sha256', 'execution_sha256'}, side + ' identity must contain exactly three hashes')
        for key in ('model_sha256', 'configuration_sha256', 'execution_sha256'):
            value = identity.get(key)
            require(isinstance(value, str) and len(value) == 64 and
                    all(ch in '0123456789abcdef' for ch in value), side + ' invalid ' + key)
    samples = c.get('samples')
    require(isinstance(samples, list) and samples, 'explicit nonempty samples required')
    previous_k, previous_time = -1, -math.inf
    for sample in samples:
        require(isinstance(sample, dict) and integer(sample.get('k')) and number(sample.get('time')), 'invalid sample k/time')
        require(sample['k'] == previous_k + 1 and sample['time'] > previous_time,
                'samples must cover consecutive k from zero with increasing model time')
        previous_k, previous_time = sample['k'], sample['time']
    quantities = c.get('quantities')
    require(isinstance(quantities, list) and quantities, 'explicit quantities required')
    names = set()
    for q in quantities:
        require(isinstance(q, dict) and nonempty(q.get('name')) and q['name'] not in names, 'unique quantity name required')
        names.add(q['name'])
        require(integer(q.get('reference_index')) and integer(q.get('candidate_index')), 'explicit zero-based indices required')
        require(nonempty(q.get('unit')), 'explicit unit required')
        require(q.get('comparison') in ('absolute', 'euler_wrap'), 'unsupported comparison (quaternion is not supported)')
        require(q['comparison'] != 'euler_wrap' or q['unit'] == 'rad', 'Euler wrapping requires rad')
        require(number(q.get('max_abs_error')) and q['max_abs_error'] >= 0, 'explicit finite nonnegative per-quantity budget required')


def read_trace(raw, side, contract, contract_hash):
    rows = []
    lines = raw.splitlines()
    require(len(lines) == len(contract['samples']), side + ': missing or extra samples')
    for line, expected in zip(lines, contract['samples']):
        row = decode(line)
        require(isinstance(row, dict), side + ': row must be object')
        for key, value in (('contract_sha256', contract_hash), ('case', contract['case']),
                           ('epoch', contract['epoch']), ('identity', contract[side])):
            require(type(row.get(key)) is type(value) and row[key] == value, side + ': wrong ' + key)
        require(integer(row.get('k')) and row['k'] == expected['k'], side + ': duplicate/missing/out-of-order k')
        require(number(row.get('time')) and row['time'] == expected['time'], side + ': model time mismatch')
        values, units = row.get('values'), row.get('units')
        require(isinstance(values, list) and values and all(number(x) for x in values), side + ': all values must be finite numbers')
        require(isinstance(units, list) and len(units) == len(values) and all(nonempty(u) for u in units), side + ': units must cover every value')
        require(not rows or units == rows[0]['units'], side + ': trace layout changed')
        for q in contract['quantities']:
            index = q[side + '_index']
            require(index < len(values), side + ': index out of bounds for ' + q['name'])
            require(units[index] == q['unit'], side + ': unit mismatch for ' + q['name'])
        rows.append(row)
    return rows


def compare(contract_path, reference_path, candidate_path):
    paths = {'contract': contract_path, 'reference': reference_path, 'candidate': candidate_path}
    result = {'status': 'fail', 'scope': 'Data comparison under supplied budgets only; not user approval or G6 acceptance.',
              'input_sha256': {}, 'quantities': [], 'failures': [], 'first_failure_k': None}
    try:
        raw = {}
        for name, path in paths.items():
            raw[name] = Path(path).read_bytes()
            result['input_sha256'][name] = hashlib.sha256(raw[name]).hexdigest()
        c = decode(raw['contract'])
        validate_contract(c)
        traces = {side: read_trace(raw[side], side, c, result['input_sha256']['contract'])
                  for side in ('reference', 'candidate')}
        for q in c['quantities']:
            errors = []
            failed = []
            for left, right in zip(traces['reference'], traces['candidate']):
                a, b = left['values'][q['reference_index']], right['values'][q['candidate_index']]
                # Reduce operands first: opposite finite extremes can overflow subtraction.
                if q['comparison'] == 'euler_wrap':
                    error = abs(math.remainder(math.remainder(a, math.tau) - math.remainder(b, math.tau), math.tau))
                else:
                    error = abs(a - b)
                require(math.isfinite(error), 'error arithmetic overflow for ' + q['name'])
                errors.append(error)
                if error > q['max_abs_error']:
                    failed.append(left['k'])
                    result['failures'].append({'quantity': q['name'], 'k': left['k'], 'time': left['time'],
                                               'reference': a, 'candidate': b, 'abs_error': error})
            maximum = max(errors)
            rms = maximum * math.sqrt(math.fsum((e / maximum) ** 2 for e in errors) / len(errors)) if maximum else 0.0
            result['quantities'].append({**q, 'max': maximum, 'rms': rms, 'first_failure_k': failed[0] if failed else None})
        result['first_failure_k'] = min((f['k'] for f in result['failures']), default=None)
        result['unverified_indices'] = {
            side: sorted(set(range(len(traces[side][0]['values']))) - {q[side + '_index'] for q in c['quantities']})
            for side in traces}
        result['status'] = 'fail' if result['failures'] else 'pass'
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        result['error'] = str(exc)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    args = parser.parse_args()
    result = compare(args.contract, args.reference, args.candidate)
    print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
