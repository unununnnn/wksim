"""Fail-closed entry seam for the #59 same-source e0 numerical comparison.

This is the NEXT seam after the source-consistent generation/build/recorder work
(#70/#71/#72 closed). It is the "SLX 11.8 normal versus same-source 11.8 native"
entry, NOT the old R1 cross-version re-run (tools/run_numerical_conformance.py is
hard-pinned to the 11.0 target build and the frozen numerical-conformance-v1.json
and is never reused here).

Ordering guarantee (fail-closed):
  1. The NEW contract (a separate file, never numerical-conformance-v1.json) is
     parsed and its schema, identity and per-observable budgets are validated FIRST.
  2. If ANY observable lacks an absolute/relative/RMS budget, or its approval is not
     exactly "approved", or any identity/schedule field is missing, the entry returns
     status "blocked" with physical_accuracy False and NEVER launches MATLAB or the
     native recorder, and NEVER reports pass.
  3. Only after the contract is fully provisioned and approved does the offline
     reference/candidate execution and the strict parse/alignment become reachable.
     Those stages are not implemented in this seam (no budget may be invented to
     unblock them); the pure parse/alignment layer below is independently testable
     and enforces: 501 samples, the 1ms time grid, 120 values per sample, finite,
     no booleans, a present complete terminal record, and identity match.

This module never fills budgets, never runs MATLAB or a build, never modifies the
frozen R1 contract, and never mutates git or issues.
"""
import argparse
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The new same-source contract must live in a NEW file. The frozen R1 contract is
# explicitly out of bounds for this seam.
FORBIDDEN_CONTRACT = ROOT / 'Simulator/wksim_core/numerical-conformance-v1.json'

ARRAY_LENGTHS = {'Vehicle60': 60, 'Sensor30': 30, 'GPS30': 30}
SAMPLES = 501                 # k = 0..500 inclusive
TIME_STEP_S = 0.001
TIME_TOL_S = 1e-12
TOTAL_SCALARS = 120           # 60 + 30 + 30
# Required per-observable fields for a fully-provisioned, approved budget.
OBSERVABLE_REQUIRED_FIELDS = (
    'observable', 'source_mapping', 'unit', 'frame', 'datum', 'sample_phase',
    'metric', 'abs_budget', 'rel_budget', 'rms_budget', 'derivation', 'domain',
    'approval', 'contract_sha256', 'array', 'indices',
)
OBSERVABLE_TEXT_FIELDS = (
    'observable', 'source_mapping', 'unit', 'frame', 'datum', 'sample_phase',
    'metric', 'derivation', 'domain',
)
NATIVE_SOURCE_REQUIRED_FIELDS = (
    'builder', 'builder_sha256', 'generation_run_id', 'original_cpp_sha256',
    'patched_cpp_sha256', 'header_sha256', 'rtwtypes_sha256',
    'rtw_continuous_sha256', 'rtw_solver_sha256', 'driver_sha256', 'phase',
    'output_order', 'root_inputs', 'insertion_line',
)

# Status vocabulary (never "pass" from this seam; the execution/compare stage that
# could yield declared_cases_pass is intentionally not implemented here).
STATUS_BLOCKED = 'blocked'
STATUS_NOT_IMPLEMENTED = 'execution_not_implemented'


class Reject(Exception):
    """A strict validation failure; always maps to a non-pass, no-execute result."""


def _require(condition, message):
    if not condition:
        raise Reject(message)


def _is_finite_number(value):
    return type(value) in (int, float) and not isinstance(value, bool) and math.isfinite(value)


def _is_sha256(value):
    return (isinstance(value, str) and len(value) == 64 and value == value.lower()
            and all(char in '0123456789abcdef' for char in value))


# --------------------------------------------------------------------------- #
# New-contract schema / identity / budget validation (runs BEFORE any launch).
# --------------------------------------------------------------------------- #
def validate_contract(contract_path):
    """Parse and fully validate the NEW same-source contract.

    Returns (contract_dict, blocking_reasons). blocking_reasons is empty only when
    every observable has a complete abs/rel/RMS budget and approval == 'approved'
    and the identity/schedule blocks are present and internally consistent.
    This function performs NO I/O beyond reading the contract file itself and never
    invokes MATLAB or the native recorder.
    """
    contract_path = Path(contract_path)
    _require(contract_path.is_file(), 'new contract file not found: %s' % contract_path)
    resolved = contract_path.resolve()
    _require(resolved != FORBIDDEN_CONTRACT.resolve(),
             'refusing to treat the frozen R1 contract as the new same-source contract')
    try:
        contract = json.loads(contract_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise Reject('new contract is not valid JSON: %s' % error)
    _require(isinstance(contract, dict), 'new contract root must be an object')

    reasons = []

    if type(contract.get('schema_version')) is not int or contract['schema_version'] != 1:
        reasons.append('schema_version must be 1')
    if contract.get('contract_id') == 'wksim-e0-fixed-reference-native-preservation-v1':
        reasons.append('contract_id collides with the frozen R1 contract id')
    if not isinstance(contract.get('contract_id'), str) or not contract.get('contract_id'):
        reasons.append('contract_id missing')
    if contract.get('status') != 'frozen':
        reasons.append('contract status must be frozen before any execution (got %r)'
                       % contract.get('status'))
    if 'contract_sha256' in contract:
        declared = contract['contract_sha256']
        if not _is_sha256(declared):
            reasons.append('declared contract_sha256 must be 64 lowercase hex chars')

    identity = contract.get('identity')
    if not isinstance(identity, dict):
        reasons.append('identity block missing')
    else:
        for key in ('reference_revision', 'target_revision', 'reference_engine',
                    'target_profile', 'slx', 'init'):
            if key not in identity:
                reasons.append('identity.%s missing' % key)
        for key in ('reference_revision', 'target_revision', 'reference_engine', 'target_profile'):
            if key in identity and (not isinstance(identity[key], str) or not identity[key].strip()):
                reasons.append('identity.%s must be a non-empty string' % key)
        for key in ('slx', 'init'):
            item = identity.get(key)
            if isinstance(item, dict):
                if not isinstance(item.get('path'), str) or not item['path'].strip():
                    reasons.append('identity.%s.path must be a non-empty string' % key)
                if not _is_sha256(item.get('sha256')):
                    reasons.append('identity.%s.sha256 must be 64 lowercase hex chars' % key)
            else:
                reasons.append('identity.%s must be an object' % key)

    sampling = contract.get('sampling')
    if not isinstance(sampling, dict):
        reasons.append('sampling block missing')
    else:
        if sampling.get('array_lengths') != ARRAY_LENGTHS:
            reasons.append('sampling.array_lengths must be exactly %r' % ARRAY_LENGTHS)
        if (not _is_finite_number(sampling.get('fixed_step_s'))
                or sampling['fixed_step_s'] != TIME_STEP_S):
            reasons.append('sampling.fixed_step_s must be 0.001')
        if (type(sampling.get('k_first')) is not int or sampling['k_first'] != 0
                or type(sampling.get('k_last')) is not int
                or sampling['k_last'] != SAMPLES - 1):
            reasons.append('sampling k range must be 0..500')

    observables = contract.get('observables')
    if not isinstance(observables, list) or not observables:
        reasons.append('observables must be a non-empty list')
        observables = []

    covered = set()
    for position, obs in enumerate(observables):
        label = 'observables[%d]' % position
        if not isinstance(obs, dict):
            reasons.append('%s must be an object' % label)
            continue
        name = obs.get('observable', label)
        for field in OBSERVABLE_REQUIRED_FIELDS:
            if field not in obs:
                reasons.append('%s (%s) missing field %s' % (label, name, field))
        for field in OBSERVABLE_TEXT_FIELDS:
            if field in obs and (not isinstance(obs[field], str) or not obs[field].strip()):
                reasons.append('%s (%s) %s must be a non-empty string'
                               % (label, name, field))
        if 'contract_sha256' in obs and not _is_sha256(obs['contract_sha256']):
            reasons.append('%s (%s) contract_sha256 must be 64 lowercase hex chars'
                           % (label, name))
        # Budgets must be present, finite, non-negative, and approved.
        for budget in ('abs_budget', 'rel_budget', 'rms_budget'):
            value = obs.get(budget)
            if budget in obs and not (_is_finite_number(value) and value >= 0):
                reasons.append('%s (%s) %s must be a finite non-negative number'
                               % (label, name, budget))
        if obs.get('approval') != 'approved':
            reasons.append('%s (%s) approval is %r, must be approved'
                           % (label, name, obs.get('approval')))
        # Coverage accounting so a missing scalar is itself blocking.
        array = obs.get('array')
        indices = obs.get('indices')
        if array not in ARRAY_LENGTHS:
            reasons.append('%s (%s) array %r is not one of %r'
                           % (label, name, array, tuple(ARRAY_LENGTHS)))
        elif isinstance(indices, list) and indices:
            for index in indices:
                if not (type(index) is int and 0 <= index < ARRAY_LENGTHS[array]):
                    reasons.append('%s (%s) index %r out of range for %s'
                                   % (label, name, index, array))
                elif (array, index) in covered:
                    reasons.append('%s (%s) duplicates scalar %s[%d]'
                                   % (label, name, array, index))
                else:
                    covered.add((array, index))
        else:
            reasons.append('%s (%s) indices must be a non-empty list' % (label, name))

    # Coverage gap is reported (not raised) so all blocking reasons surface together.
    if len(covered) != TOTAL_SCALARS:
        reasons.append('observable coverage is %d scalars, must be exactly %d (all 120)'
                       % (len(covered), TOTAL_SCALARS))

    return contract, reasons


# --------------------------------------------------------------------------- #
# Pure parse / alignment layer (independently testable; strict rejection).
# --------------------------------------------------------------------------- #
def parse_reference_f64(path, array, width):
    """Parse one normal-mode reference channel written by export_model_reference.m.

    Format: 501 rows of little-endian binary64, each row [time, v0..v{width-1}],
    written row-major (fwrite of the transposed rows matrix). Strictly enforces the
    exact byte length, the 1ms time grid, monotonic times, and finite non-bool values.
    Returns a list of 501 tuples of length width (values only, time stripped).
    """
    _require(array in ARRAY_LENGTHS and ARRAY_LENGTHS[array] == width,
             'reference array/width identity mismatch')
    raw = Path(path).read_bytes()
    columns = width + 1
    _require(len(raw) == SAMPLES * columns * 8,
             '%s: wrong byte length %d (expected %d) for %s'
             % (path, len(raw), SAMPLES * columns * 8, array))
    rows = list(struct.iter_unpack('<' + 'd' * columns, raw))
    _require(len(rows) == SAMPLES, '%s: expected %d rows' % (array, SAMPLES))
    values = []
    for k, row in enumerate(rows):
        time_s = row[0]
        _require(_is_finite_number(time_s) and abs(time_s - k * TIME_STEP_S) <= TIME_TOL_S,
                 '%s: time grid mismatch at k=%d (got %r)' % (array, k, time_s))
        if k:
            _require(row[0] > rows[k - 1][0], '%s: non-increasing time at k=%d' % (array, k))
        sample = row[1:]
        _require(all(_is_finite_number(v) for v in sample),
                 '%s: non-finite value at k=%d' % (array, k))
        values.append(tuple(sample))
    return values


def parse_native_record(path, expected_source=None):
    """Parse a native major-recorder record.jsonl and return major_root_outputs per k.

    Strictly enforces: exactly 503 records (start + 501 samples + terminal end),
    ordered complete samples with the 1ms engine/input clocks, 120 finite non-bool
    values per sample across the three arrays, and a present complete terminal record
    with the 501/0.500/0.501 schedule. Returns {array: [501 tuples]}.
    """
    lines = [line for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    _require(len(lines) == SAMPLES + 2,
             'record.jsonl: expected %d records, got %d' % (SAMPLES + 2, len(lines)))
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except ValueError as error:
            raise Reject('record.jsonl: invalid JSON line: %s' % error)
    _require(all(isinstance(record, dict) for record in records),
             'record.jsonl: every record must be an object')

    start = records[0]
    _require(start.get('kind') == 'major_recorder_start',
             'record.jsonl: first record must be major_recorder_start')
    _require(type(start.get('schema_version')) is int and start['schema_version'] == 1,
             'record.jsonl: start schema_version must be int 1')
    _require(type(start.get('expected_calls')) is int and start['expected_calls'] == SAMPLES,
             'record.jsonl: start expected_calls must be int 501')
    _require(_is_finite_number(start.get('comparison_end_s'))
             and abs(start['comparison_end_s'] - 0.5) <= TIME_TOL_S,
             'record.jsonl: start comparison_end_s must be 0.500')
    _require(_is_finite_number(start.get('expected_engine_end_s'))
             and abs(start['expected_engine_end_s'] - 0.501) <= TIME_TOL_S,
             'record.jsonl: start expected_engine_end_s must be 0.501')
    _require(isinstance(start.get('input_csv'), str) and start['input_csv'],
             'record.jsonl: start input_csv missing')
    source = start.get('source')
    _require(isinstance(source, dict), 'record.jsonl: start source identity missing')
    _require(all(field in source for field in NATIVE_SOURCE_REQUIRED_FIELDS),
             'record.jsonl: start source identity incomplete')
    for field in ('builder_sha256', 'original_cpp_sha256', 'patched_cpp_sha256',
                  'header_sha256', 'rtwtypes_sha256', 'rtw_continuous_sha256',
                  'rtw_solver_sha256', 'driver_sha256'):
        _require(_is_sha256(source.get(field)),
                 'record.jsonl: source.%s must be 64 lowercase hex chars' % field)
    _require(source.get('builder') == 'tools/build_generated_e0_major.py'
             and isinstance(source.get('generation_run_id'), str) and source['generation_run_id']
             and isinstance(source.get('phase'), str) and source['phase']
             and source.get('output_order') == ['Vehicle60', 'Sensor30', 'GPS30']
             and source.get('root_inputs') == ['inPWMs[16]', 'TerrainIn15d[15]']
             and type(source.get('insertion_line')) is int,
             'record.jsonl: source identity values invalid')
    if expected_source is not None:
        _require(source == expected_source, 'record.jsonl: source identity mismatch')
    end = records[-1]
    _require(end.get('kind') == 'major_recorder_end',
             'record.jsonl: missing terminal major_recorder_end record')
    _require(type(end.get('schema_version')) is int and end['schema_version'] == 1,
             'record.jsonl: terminal schema_version must be int 1')
    _require(end.get('status') == 'complete', 'record.jsonl: terminal status is not complete')
    for key in ('attempted_calls', 'returned_calls', 'emitted_samples'):
        _require(type(end.get(key)) is int and end[key] == SAMPLES,
                 'record.jsonl: terminal %s must be int %d' % (key, SAMPLES))
    _require(_is_finite_number(end.get('engine_end_s'))
             and abs(end['engine_end_s'] - (SAMPLES * TIME_STEP_S)) <= TIME_TOL_S,
             'record.jsonl: terminal engine_end_s must be 0.501')
    _require(_is_finite_number(end.get('comparison_end_s'))
             and abs(end['comparison_end_s'] - ((SAMPLES - 1) * TIME_STEP_S)) <= TIME_TOL_S,
             'record.jsonl: terminal comparison_end_s must be 0.500')

    out = {array: [] for array in ARRAY_LENGTHS}
    for k in range(SAMPLES):
        sample = records[k + 1]
        _require(sample.get('kind') == 'major_recorder_sample',
                  'record.jsonl: record %d must be major_recorder_sample' % (k + 1))
        _require(type(sample.get('schema_version')) is int and sample['schema_version'] == 1,
                 'record.jsonl: schema_version must be int 1 at k=%d' % k)
        _require(type(sample.get('k')) is int and sample['k'] == k,
                 'record.jsonl: sample order mismatch at k=%d' % k)
        _require(type(sample.get('call_number')) is int and sample['call_number'] == k + 1,
                 'record.jsonl: call_number mismatch at k=%d' % k)
        _require(sample.get('step_status') == 'complete',
                 'record.jsonl: step_status not complete at k=%d' % k)
        _require(_is_finite_number(sample.get('input_time_s'))
                 and abs(sample['input_time_s'] - k * TIME_STEP_S) <= TIME_TOL_S,
                 'record.jsonl: input_time_s mismatch at k=%d' % k)
        _require(_is_finite_number(sample.get('engine_before_s'))
                 and abs(sample['engine_before_s'] - k * TIME_STEP_S) <= TIME_TOL_S,
                 'record.jsonl: engine_before_s mismatch at k=%d' % k)
        _require(_is_finite_number(sample.get('engine_after_s'))
                 and abs(sample['engine_after_s'] - (k + 1) * TIME_STEP_S) <= TIME_TOL_S,
                 'record.jsonl: engine_after_s mismatch at k=%d' % k)
        _require(type(sample.get('major_capture_count')) is int
                 and sample['major_capture_count'] == 1,
                 'record.jsonl: major_capture_count must be int 1 at k=%d' % k)
        major = sample.get('major_root_outputs')
        _require(isinstance(major, dict), 'record.jsonl: missing major_root_outputs at k=%d' % k)
        for array, width in ARRAY_LENGTHS.items():
            values = major.get(array)
            _require(isinstance(values, list) and len(values) == width,
                     'record.jsonl: %s must have %d values at k=%d' % (array, width, k))
            for v in values:
                _require(_is_finite_number(v),
                         'record.jsonl: non-finite or boolean value in %s at k=%d' % (array, k))
            out[array].append(tuple(float(v) for v in values))
    return out


def align(reference_by_array, native_by_array, observables):
    """Build the per-scalar aligned (reference, native) value pairs for the given
    observables. Pure: no execution. Raises Reject on any coverage/shape mismatch.

    Returns a list of dicts: {observable, array, index, reference=[...], native=[...]}.
    """
    _require(set(reference_by_array) == set(ARRAY_LENGTHS), 'reference arrays incomplete')
    _require(set(native_by_array) == set(ARRAY_LENGTHS), 'native arrays incomplete')
    _require(isinstance(observables, list), 'observables must be a list')
    aligned = []
    covered = set()
    for obs in observables:
        _require(isinstance(obs, dict), 'observable mapping must be an object')
        array = obs.get('array')
        _require(array in ARRAY_LENGTHS and isinstance(obs.get('indices'), list),
                 'observable array/indices invalid')
        for index in obs['indices']:
            _require(type(index) is int and 0 <= index < ARRAY_LENGTHS[array]
                     and (array, index) not in covered,
                     'observable scalar coverage invalid')
            covered.add((array, index))
            ref = reference_by_array[array]
            nat = native_by_array[array]
            _require(len(ref) == SAMPLES and len(nat) == SAMPLES,
                      '%s: sample count mismatch (%d vs %d)' % (array, len(ref), len(nat)))
            _require(all(isinstance(row, (list, tuple)) and len(row) == ARRAY_LENGTHS[array]
                         for row in ref), '%s: reference row shape mismatch' % array)
            _require(all(isinstance(row, (list, tuple)) and len(row) == ARRAY_LENGTHS[array]
                         for row in nat), '%s: native row shape mismatch' % array)
            aligned.append(dict(
                observable=obs.get('observable'), array=array, index=index,
                reference=[row[index] for row in ref],
                native=[row[index] for row in nat]))
    _require(len(covered) == TOTAL_SCALARS,
             'observable coverage is %d scalars, must be exactly %d'
             % (len(covered), TOTAL_SCALARS))
    return aligned


# --------------------------------------------------------------------------- #
# Entry: contract-first, fail-closed. Never launches MATLAB/native when blocked.
# --------------------------------------------------------------------------- #
def run(contract_path):
    """Fail-closed seam entry. Returns a result dict; never raises for a blocked or
    unprovisioned contract, and never starts MATLAB or the native recorder."""
    try:
        contract, reasons = validate_contract(contract_path)
    except Reject as error:
        return _result(STATUS_BLOCKED, [str(error)], physical_accuracy=False)
    if reasons:
        # Budgets missing or unapproved (or identity/schema incomplete): blocked,
        # no execution, no pass.
        return _result(STATUS_BLOCKED, reasons, physical_accuracy=False,
                       contract=contract)
    # The contract is fully provisioned and approved. The offline reference/native
    # execution and per-scalar budget comparison belong to a later seam; this seam
    # deliberately does not implement them and never reports pass.
    return _result(STATUS_NOT_IMPLEMENTED,
                   ['contract fully provisioned and approved, but the reference/native '
                    'execution and budget comparison stage is not implemented in this seam'],
                   physical_accuracy=False, contract=contract)


def _result(status, reasons, physical_accuracy, contract=None):
    result = {
        'status': status,
        'physical_accuracy': bool(physical_accuracy),
        'g6_acceptance': False,
        'execution_attempted': False,
        'matlab_launched': False,
        'native_launched': False,
        'blocking_reasons': list(reasons),
        'scope': ('#59 same-source e0 SLX 11.8 normal vs same-source 11.8 native seam; '
                  'fail-closed. Not the R1 cross-version re-run; never fills budgets, '
                  'never modifies numerical-conformance-v1.json.'),
    }
    if contract is not None:
        result['contract_id'] = contract.get('contract_id')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contract', type=Path,
                        help='Path to the NEW same-source contract (never numerical-conformance-v1.json)')
    parser.add_argument('--output', type=Path, default=None,
                        help='Optional path to write the JSON result')
    args = parser.parse_args()
    result = run(args.contract)
    text = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output is not None:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)
    # No stage in this seam establishes physical success, so every status is nonzero.
    return 3 if result['status'] == STATUS_NOT_IMPLEMENTED else 2


if __name__ == '__main__':
    sys.exit(main())
