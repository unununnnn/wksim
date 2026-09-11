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
  3. Only after the contract is fully provisioned and approved does the normal
     reference/native execution and strict parse/alignment become reachable. The
     execution description is validated before any evidence directory is created;
     the actual launcher is injectable for tests. No budget is invented to unblock
     it. The parser/alignment layer enforces 501 samples, the 1ms time grid, 120
     values per sample, finite values, a complete terminal record and identity match.

This module never fills budgets, never runs MATLAB or a build, never modifies the
frozen R1 contract, and never mutates git or issues.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import struct
import subprocess
import sys
import time
import uuid

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

# The single frozen comparison metric. Any other metric identifier is rejected, so a
# contract cannot silently switch the pass rule. Frozen in
# docs/plan/59-e0-same-source-command.md.
FROZEN_METRIC = 'abs_le_a_plus_r_absref_with_rms_cap_v1'

# Status vocabulary.  A declared_cases_pass result is still only a numerical result;
# it never upgrades physical_accuracy or G6 acceptance.
STATUS_BLOCKED = 'blocked'
# Retained as a historical vocabulary value for old evidence readers.  New runs
# return blocked, invalid_run, numerical_failed or declared_cases_pass.
STATUS_NOT_IMPLEMENTED = 'execution_not_implemented'
STATUS_INVALID_RUN = 'invalid_run'

# Aggregate outcomes of the pure offline comparison layer (compare_aligned). These are
# deliberate, evidence-backed labels only — never a G6 or physical-accuracy pass.
STATUS_NUMERICAL_FAILED = 'numerical_failed'
STATUS_DECLARED_CASES_PASS = 'declared_cases_pass'


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


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False,
                                     allow_nan=False) + '\n', encoding='utf-8')


def _read_json(path, label):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise Reject('%s is not valid JSON: %s' % (label, error))
    _require(isinstance(value, dict), '%s must be an object' % label)
    return value


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
        # The comparison metric must be exactly the one frozen formula identifier.
        if 'metric' in obs and obs.get('metric') != FROZEN_METRIC:
            reasons.append('%s (%s) metric is %r, must be the frozen %r'
                           % (label, name, obs.get('metric'), FROZEN_METRIC))
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


def _resolve_declared_path(value, base):
    _require(isinstance(value, str) and value.strip(), 'path must be a non-empty string')
    path = Path(value)
    return path if path.is_absolute() else (Path(base) / path).resolve()


def _read_input_csv(path):
    """Read the exact 501-row recorder input before any execution side effect."""
    path = Path(path)
    try:
        raw = path.read_bytes()
        text = raw.decode('ascii')
    except (OSError, UnicodeDecodeError) as error:
        raise Reject('input CSV cannot be read as ASCII: %s' % error)
    expected_header = ['k', 'time_s'] + [
        'inPWMs%d' % index for index in range(16)
    ] + ['TerrainIn15d%d' % index for index in range(15)]
    rows = list(csv.reader(io.StringIO(text)))
    _require(rows and rows[0] == expected_header, 'input CSV header mismatch')
    _require(len(rows) == SAMPLES + 1,
             'input CSV must contain exactly %d data rows' % SAMPLES)
    parsed = []
    for k, row in enumerate(rows[1:]):
        _require(len(row) == 33, 'input CSV row %d must contain 33 fields' % k)
        _require(row[0] == str(k), 'input CSV k sequence mismatch at k=%d' % k)
        try:
            values = [float(value) for value in row[1:]]
        except ValueError as error:
            raise Reject('input CSV row %d contains a non-numeric value: %s' % (k, error))
        _require(all(math.isfinite(value) for value in values),
                 'input CSV row %d contains a non-finite value' % k)
        _require(abs(values[0] - k * TIME_STEP_S) <= TIME_TOL_S,
                 'input CSV time grid mismatch at k=%d' % k)
        _require(all(0.0 <= value <= 1.0 for value in values[1:17]),
                 'input CSV PWM outside [0,1] at k=%d' % k)
        parsed.append({
            'time_s': values[0],
            'inPWMs': values[1:17],
            'TerrainIn15d': values[17:32],
        })
    return raw, parsed


def _validate_file_identity(item, label, base):
    _require(isinstance(item, dict), '%s must be an object' % label)
    path = _resolve_declared_path(item.get('path'), base)
    _require(path.is_file(), '%s file not found: %s' % (label, path))
    expected = item.get('sha256')
    _require(_is_sha256(expected), '%s.sha256 must be 64 lowercase hex chars' % label)
    actual = _sha256(path)
    _require(actual == expected, '%s SHA256 mismatch: %s' % (label, path))
    return {'path': path, 'sha256': actual}


def _validate_native_source(source, label='native source identity'):
    _require(isinstance(source, dict), '%s must be an object' % label)
    _require(all(field in source for field in NATIVE_SOURCE_REQUIRED_FIELDS),
             '%s is incomplete' % label)
    for field in ('builder_sha256', 'original_cpp_sha256', 'patched_cpp_sha256',
                  'header_sha256', 'rtwtypes_sha256', 'rtw_continuous_sha256',
                  'rtw_solver_sha256', 'driver_sha256'):
        _require(_is_sha256(source.get(field)),
                 '%s.%s must be 64 lowercase hex chars' % (label, field))
    _require(source.get('builder') == 'tools/build_generated_e0_major.py',
             '%s.builder is not the reviewed major builder' % label)
    _require(isinstance(source.get('generation_run_id'), str)
             and source['generation_run_id'], '%s.generation_run_id missing' % label)
    _require(isinstance(source.get('phase'), str) and source['phase'],
             '%s.phase missing' % label)
    _require(source.get('output_order') == ['Vehicle60', 'Sensor30', 'GPS30'],
             '%s.output_order mismatch' % label)
    _require(source.get('root_inputs') == ['inPWMs[16]', 'TerrainIn15d[15]'],
             '%s.root_inputs mismatch' % label)
    _require(type(source.get('insertion_line')) is int,
             '%s.insertion_line must be an integer' % label)
    return source


def validate_execution(contract_path, contract):
    """Validate all execution identities without creating files or launching a process.

    This is intentionally separate from ``validate_contract``: old parser fixtures
    remain useful, while ``run`` refuses to enter the execution stage unless this
    complete normal/native execution description is present.
    """
    contract_path = Path(contract_path).resolve()
    execution = contract.get('execution')
    _require(isinstance(execution, dict), 'execution block missing')
    case_id = execution.get('case_id')
    _require(isinstance(case_id, str) and case_id.strip(), 'execution.case_id missing')

    actual_contract_sha = _sha256(contract_path)
    declared_contract_sha = contract.get('contract_sha256')
    if declared_contract_sha is not None:
        _require(declared_contract_sha == actual_contract_sha,
                 'contract_sha256 does not match the contract file')

    input_item = _validate_file_identity(execution.get('input'), 'execution.input',
                                         contract_path.parent)
    input_raw, input_rows = _read_input_csv(input_item['path'])

    normal = execution.get('normal')
    _require(isinstance(normal, dict), 'execution.normal block missing')
    matlab_item = _validate_file_identity({
        'path': normal.get('matlab'),
        'sha256': normal.get('matlab_sha256'),
    }, 'execution.normal.matlab', contract_path.parent)
    export_item = _validate_file_identity(normal.get('export_script'),
                                          'execution.normal.export_script',
                                          contract_path.parent)
    stage_items = normal.get('stage_files')
    _require(isinstance(stage_items, list) and stage_items,
             'execution.normal.stage_files must be a non-empty list')
    stage_files = []
    seen_names = set()
    for position, item in enumerate(stage_items):
        label = 'execution.normal.stage_files[%d]' % position
        checked = _validate_file_identity(item, label, contract_path.parent)
        name = item.get('name')
        _require(isinstance(name, str) and name and Path(name).name == name,
                 '%s.name must be a plain staging filename' % label)
        _require(name not in seen_names, '%s.name is duplicated: %s' % (label, name))
        seen_names.add(name)
        stage_files.append({'name': name, **checked})
    required_names = {
        'Exp1_MinModelTemp.slx', 'Exp1_MinModelTemp_init.m',
        'parameter-bindings.json', 'readiness.json', 'dependencies.json',
    }
    _require(required_names.issubset(seen_names),
             'normal staging is missing %s' % sorted(required_names - seen_names))
    identity = contract.get('identity', {})
    for key, name in (('slx', 'Exp1_MinModelTemp.slx'),
                      ('init', 'Exp1_MinModelTemp_init.m')):
        item = identity.get(key, {})
        staged = next(row for row in stage_files if row['name'] == name)
        _require(item.get('path') == str(staged['path']) or
                 _sha256(staged['path']) == item.get('sha256'),
                 'normal %s does not match contract identity' % key)
    _require(export_item['path'].is_file(), 'normal export script is not readable')

    native = execution.get('native')
    _require(isinstance(native, dict), 'execution.native block missing')
    manifest_item = _validate_file_identity(native.get('manifest'),
                                            'execution.native.manifest',
                                            contract_path.parent)
    native_manifest = _read_json(manifest_item['path'], 'native build manifest')
    source = _validate_native_source(native_manifest.get('source_identity'))
    executable = native_manifest.get('executable')
    _require(isinstance(executable, dict), 'native build manifest executable missing')
    manifest_executable_sha = executable.get('sha256')
    _require(_is_sha256(manifest_executable_sha),
             'native build manifest executable.sha256 is invalid')
    _require(native.get('executable_sha256') == manifest_executable_sha,
             'native executable SHA does not match build manifest')
    manifest_executable_name = executable.get('filename')
    _require(isinstance(manifest_executable_name, str) and manifest_executable_name
             and PurePosixPath(manifest_executable_name).name == manifest_executable_name,
             'native build manifest executable.filename is invalid')
    manifest_executable_size = executable.get('size_bytes')
    _require(type(manifest_executable_size) is int and manifest_executable_size > 0,
             'native build manifest executable.size_bytes is invalid')
    wsl_executable = native.get('wsl_executable')
    _require(isinstance(wsl_executable, str) and wsl_executable.strip(),
             'execution.native.wsl_executable missing')
    _require(PurePosixPath(wsl_executable).name == manifest_executable_name,
             'native WSL executable filename does not match build manifest')
    distro = native.get('wsl_distro', 'Ubuntu-22.04')
    _require(isinstance(distro, str) and distro.strip(),
             'execution.native.wsl_distro must be a non-empty string')

    timeout = execution.get('timeout_seconds', 600.0)
    _require(_is_finite_number(timeout) and timeout > 0,\
             'execution.timeout_seconds must be positive and finite')
    return {
        'case_id': case_id,
        'contract_sha256': actual_contract_sha,
        'input': input_item,
        'input_raw': input_raw,
        'input_rows': input_rows,
        'normal': {
            'matlab': matlab_item,
            'export_script': export_item,
            'stage_files': stage_files,
        },
        'native': {
            'manifest': manifest_item,
            'manifest_data': native_manifest,
            'source_identity': source,
            'executable_sha256': manifest_executable_sha,
            'executable_size_bytes': manifest_executable_size,
            'executable_filename': manifest_executable_name,
            'wsl_executable': wsl_executable,
            'wsl_distro': distro,
        },
        'timeout_seconds': float(timeout),
    }


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
# Pure offline per-quantity comparison (NO execution of MATLAB/native).
# --------------------------------------------------------------------------- #
def compare_aligned(aligned, observables):
    """Apply the single frozen per-quantity budget to already-aligned scalar pairs.

    For each scalar the pointwise rule is exactly
        abs(x - r) <= A_i + R_i * abs(r)
    and, independently, the RMS of the errors must satisfy rms <= rms_budget.
    Pure: this never launches MATLAB or the native recorder and never reads engine
    outputs; it only consumes the aligned pairs produced by align().

    Strictly Rejects: an observable whose metric is not FROZEN_METRIC; a missing or
    non-finite/negative budget; a non-finite or boolean reference/native value; a
    wrong-length series; or a duplicate observable mapping.

    Returns a result dict with per-scalar stats and an aggregate status that is only
    ever STATUS_NUMERICAL_FAILED or STATUS_DECLARED_CASES_PASS. That aggregate is a
    numerical label only: it is NOT a G6 or physical-accuracy pass.
    """
    _require(isinstance(aligned, list), 'aligned must be a list')
    _require(isinstance(observables, list), 'observables must be a list')
    by_key = {}
    for obs in observables:
        _require(isinstance(obs, dict), 'observable must be an object')
        _require(obs.get('metric') == FROZEN_METRIC,
                 'observable metric %r is not the frozen %r' % (obs.get('metric'), FROZEN_METRIC))
        for budget in ('abs_budget', 'rel_budget', 'rms_budget'):
            value = obs.get(budget)
            _require(_is_finite_number(value) and value >= 0,
                     'observable %s budget %s must be a finite non-negative number'
                     % (obs.get('observable'), budget))
        array = obs.get('array')
        _require(array in ARRAY_LENGTHS and isinstance(obs.get('indices'), list),
                 'observable array/indices invalid')
        for index in obs['indices']:
            _require(type(index) is int and 0 <= index < ARRAY_LENGTHS[array],
                     'observable index out of range')
            key = (array, index)
            _require(key not in by_key, 'duplicate observable mapping for %s[%d]' % key)
            by_key[key] = obs
    _require(len(by_key) == TOTAL_SCALARS,
             'observable budget coverage is %d scalars, must be exactly %d'
             % (len(by_key), TOTAL_SCALARS))

    scalars = []
    seen_aligned = set()
    pointwise_failed_values = 0
    failed_conditions = 0
    for entry in aligned:
        _require(isinstance(entry, dict), 'aligned scalar must be an object')
        array = entry.get('array')
        index = entry.get('index')
        _require(array in ARRAY_LENGTHS and type(index) is int
                 and 0 <= index < ARRAY_LENGTHS[array],
                 'aligned scalar array/index invalid')
        key = (array, index)
        _require(key not in seen_aligned,
                 'duplicate aligned scalar for %s[%d]' % key)
        seen_aligned.add(key)
        obs = by_key.get(key)
        _require(obs is not None, 'aligned scalar %s[%d] has no observable budget' % key)
        _require(entry.get('observable') == obs.get('observable'),
                 'aligned scalar %s[%d] observable identity mismatch' % key)
        reference = entry.get('reference')
        native = entry.get('native')
        _require(isinstance(reference, (list, tuple))
                 and isinstance(native, (list, tuple)),
                 'aligned reference/native series must be arrays')
        _require(len(reference) == SAMPLES and len(native) == SAMPLES,
                 'aligned series length mismatch (%d vs %d, expected %d)'
                 % (len(reference), len(native), SAMPLES))
        abs_budget = obs['abs_budget']
        rel_budget = obs['rel_budget']
        rms_budget = obs['rms_budget']
        errors = []
        pointwise_failures = []
        for k in range(SAMPLES):
            r = reference[k]
            x = native[k]
            _require(_is_finite_number(r) and _is_finite_number(x),
                     'non-finite or boolean value at %s[%d] k=%d' % (key[0], key[1], k))
            error = abs(x - r)
            errors.append(error)
            if error > abs_budget + rel_budget * abs(r):
                pointwise_failures.append(k)
        # Independent RMS cap, computed in a numerically stable scaled form.
        maximum = max(errors)
        rms = (maximum * math.sqrt(math.fsum((e / maximum) ** 2 for e in errors) / SAMPLES)
               if maximum else 0.0)
        rms_failed = rms > rms_budget
        failed_count = len(pointwise_failures) + (1 if rms_failed else 0)
        pointwise_failed_values += len(pointwise_failures)
        failed_conditions += failed_count
        scalars.append(dict(
            observable=entry.get('observable'), array=key[0], index=key[1],
            sample_count=SAMPLES, max_abs_error=maximum, rms_error=rms,
            abs_budget=abs_budget, rel_budget=rel_budget, rms_budget=rms_budget,
            pointwise_failed_count=len(pointwise_failures),
            first_pointwise_failure_k=pointwise_failures[0] if pointwise_failures else None,
            rms_failed=rms_failed, failed_count=failed_count))

    _require(seen_aligned == set(by_key),
             'aligned scalar coverage does not exactly match observable budgets')
    _require(len(scalars) == TOTAL_SCALARS,
             'comparison covered %d scalars, must be exactly %d' % (len(scalars), TOTAL_SCALARS))
    status = STATUS_NUMERICAL_FAILED if failed_conditions else STATUS_DECLARED_CASES_PASS
    return {
        'status': status,
        'aggregate': status,
        'scalar_count': len(scalars),
        'comparisons': len(scalars) * SAMPLES,
        'failed_values': pointwise_failed_values,
        'failed_conditions': failed_conditions,
        'failed_scalars': sum(1 for s in scalars if s['failed_count'] > 0),
        'scalars': scalars,
        # Hard guardrails: this offline label is never a G6/physical verdict.
        'physical_accuracy': False,
        'g6_acceptance': False,
        'scope': ('Pure offline per-quantity budget comparison of pre-aligned pairs; '
                  'never executes MATLAB/native; aggregate is numerical only, never a '
                  'G6 or physical-accuracy pass.'),
    }


# --------------------------------------------------------------------------- #
# Execution stage: contract-first, then normal -> native, then offline compare.
# --------------------------------------------------------------------------- #
def _default_wsl_path(path, distro):
    command = ['wsl.exe', '-d', distro, '--exec', 'wslpath', '-a', '-u', str(path)]
    return subprocess.check_output(command, text=True).strip()


def _probe_wsl_executable(path, distro):
    """Return the executable identity measured inside the selected WSL distro."""
    _require(isinstance(path, str) and path.startswith('/')
             and not any(char in path for char in ('\x00', '\r', '\n')),
             'native WSL executable must be a safe absolute Linux path')
    prefix = ['wsl.exe', '-d', distro, '--exec']
    try:
        regular = subprocess.run(
            prefix + ['test', '-f', path], check=False, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=30)
        _require(regular.returncode == 0,
                 'native WSL executable is missing or not a regular file: %s' % path)
        executable = subprocess.run(
            prefix + ['test', '-x', path], check=False, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=30)
        _require(executable.returncode == 0,
                 'native WSL file is not executable: %s' % path)
        digest = subprocess.run(
            prefix + ['sha256sum', '--', path], check=False, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=30)
        _require(digest.returncode == 0,
                 'cannot hash native WSL executable: %s' % path)
        actual = digest.stdout.decode('ascii', errors='strict').split(None, 1)[0]
        stat = subprocess.run(
            prefix + ['stat', '-Lc', '%s\t%a', '--', path], check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        _require(stat.returncode == 0,
                 'cannot stat native WSL executable: %s' % path)
        size_text, mode = stat.stdout.decode('ascii', errors='strict').strip().split('\t')
        size_bytes = int(size_text)
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError, IndexError) as error:
        raise Reject('native WSL executable identity probe failed: %s' % error)
    _require(_is_sha256(actual), 'native WSL executable probe returned an invalid SHA256')
    _require(size_bytes > 0, 'native WSL executable is empty')
    try:
        mode_bits = int(mode, 8)
    except ValueError as error:
        raise Reject('native WSL executable probe returned an invalid mode: %s' % error)
    _require(bool(mode_bits & 0o111), 'native WSL executable mode has no execute bit')
    return {
        'path': path, 'sha256': actual, 'size_bytes': size_bytes,
        'mode': mode, 'regular_file': True, 'executable': True,
    }


def _verify_native_executable(execution, probe):
    observed = probe(
        execution['native']['wsl_executable'], execution['native']['wsl_distro'])
    _require(isinstance(observed, dict),
             'native executable identity probe did not return an object')
    _require(observed.get('path') == execution['native']['wsl_executable'],
             'native executable identity probe returned the wrong path')
    _require(observed.get('executable') is True,
             'native executable identity probe did not confirm executable access')
    _require(observed.get('regular_file') is True,
             'native executable identity probe did not confirm a regular file')
    _require(observed.get('sha256') == execution['native']['executable_sha256'],
             'native executable bytes do not match build manifest SHA256')
    _require(observed.get('size_bytes') == execution['native']['executable_size_bytes'],
             'native executable size does not match build manifest')
    return observed


def _terminate_process_tree(process):
    """Boundedly terminate the owned process tree after a timeout."""
    if os.name == 'nt':
        try:
            subprocess.run(
                ['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10)
        except (OSError, subprocess.SubprocessError):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
    try:
        return process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=5)


def _launch_process(*, side, argv, cwd, env, stdout_path, stderr_path, timeout_seconds):
    """Launch one owned child and retain deterministic process evidence.

    The callable is injectable in ``run`` so unit tests never need MATLAB, WSL or
    a generated executable.  A timeout is always invalid evidence.
    """
    status = {
        'side': side, 'argv': [str(value) for value in argv], 'cwd': str(cwd),
        'started_unix_ns': time.time_ns(), 'timeout': False,
    }
    group_options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
                     if os.name == 'nt' else {'start_new_session': True})
    with Path(stdout_path).open('wb') as stdout, Path(stderr_path).open('wb') as stderr:
        process = subprocess.Popen(argv, cwd=str(cwd), env=env, stdout=stdout, stderr=stderr,
                                   **group_options)
        status['pid'] = process.pid
        try:
            status['exit_code'] = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            status['timeout'] = True
            status['timeout_source'] = 'host_process_deadline'
            status['exit_code'] = _terminate_process_tree(process)
    status['ended_unix_ns'] = time.time_ns()
    return status


def _expected_input_f64(input_rows):
    raw = bytearray()
    for k, row in enumerate(input_rows):
        raw += struct.pack('<33d', float(k), row['time_s'], *row['inPWMs'],
                           *row['TerrainIn15d'])
    return bytes(raw)


def _validate_process_status(status, side):
    _require(isinstance(status, dict), '%s launcher did not return a status object' % side)
    _require(status.get('exit_code') == 0 and not status.get('timeout', False),
             '%s process did not complete successfully' % side)


def _prepare_execution(contract_path, execution, evidence_dir):
    """Build a complete evidence/staging tree and publish it with one rename."""
    if evidence_dir is None:
        evidence_dir = ROOT / 'validation' / (
            'e0-same-source-%s-%s' % (execution['case_id'], uuid.uuid4().hex))
    evidence_dir = Path(evidence_dir).resolve()
    _require(not evidence_dir.exists(),
             'evidence directory already exists; refusing to overwrite: %s' % evidence_dir)
    _require(evidence_dir.parent.is_dir(),
             'evidence parent directory does not exist: %s' % evidence_dir.parent)
    staging = evidence_dir.parent / ('.%s.staging-%s' % (evidence_dir.name, uuid.uuid4().hex))
    stage = staging / 'normal'

    def copy_checked(source, destination, expected_sha, label):
        shutil.copyfile(source, destination)
        _require(_sha256(destination) == expected_sha,
                 '%s changed during copy' % label)

    try:
        for directory in (staging, stage, staging / 'temp', staging / 'pref',
                          staging / 'cache', staging / 'codegen'):
            directory.mkdir(parents=False, exist_ok=False)

        contract_path = Path(contract_path).resolve()
        copy_checked(contract_path, staging / 'contract.json',
                     execution['contract_sha256'], 'staged contract')
        copy_checked(contract_path, stage / 'contract.json',
                     execution['contract_sha256'], 'normal staged contract')
        copy_checked(execution['input']['path'], staging / 'input.csv',
                     execution['input']['sha256'], 'staged input')
        copy_checked(execution['input']['path'], stage / 'input.csv',
                     execution['input']['sha256'], 'normal staged input')
        for item in execution['normal']['stage_files']:
            copy_checked(item['path'], stage / item['name'], item['sha256'],
                         'staged normal file %s' % item['name'])
        export_destination = stage / 'export_model_reference.m'
        copy_checked(execution['normal']['export_script']['path'], export_destination,
                     execution['normal']['export_script']['sha256'],
                     'staged normal export script')
        copy_checked(execution['native']['manifest']['path'],
                     staging / 'native-build-manifest.json',
                     execution['native']['manifest']['sha256'],
                     'staged native build manifest')

        manifest = {
            'schema_version': 1,
            'case': execution['case_id'],
            'epoch': uuid.uuid4().hex,
            'contract_sha256': execution['contract_sha256'],
            'input_sha256': execution['input']['sha256'],
            'normal': {
                'engine': 'MATLAB R2022b normal',
                'matlab_path': str(execution['normal']['matlab']['path']),
                'matlab_sha256': execution['normal']['matlab']['sha256'],
                'export_script_sha256': execution['normal']['export_script']['sha256'],
                'stage_files': {
                    item['name']: item['sha256']
                    for item in execution['normal']['stage_files']
                },
            },
            'native': {
                'wsl_executable': execution['native']['wsl_executable'],
                'executable_sha256': execution['native']['executable_sha256'],
                'observed_executable': execution['native']['observed_executable'],
                'source_identity': execution['native']['source_identity'],
            },
        }
        _write_json(staging / 'manifest.json', manifest)
        _write_json(stage / 'manifest.json', manifest)
        _require(not evidence_dir.exists(),
                 'evidence directory appeared during preparation: %s' % evidence_dir)
        staging.rename(evidence_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        'evidence_dir': evidence_dir,
        'stage': evidence_dir / 'normal',
        'manifest': manifest,
    }


def _validate_staged_normal_identity(prepared):
    stage = prepared['stage']
    manifest = prepared['manifest']
    _require(_sha256(stage / 'contract.json') == manifest['contract_sha256'],
             'normal staged contract changed during execution')
    _require(_sha256(stage / 'input.csv') == manifest['input_sha256'],
             'normal staged input changed during execution')
    normal = manifest['normal']
    _require(_sha256(stage / 'export_model_reference.m') == normal['export_script_sha256'],
             'normal export script changed during execution')
    for name, expected_sha in normal['stage_files'].items():
        _require(_sha256(stage / name) == expected_sha,
                 'normal staged file changed during execution: %s' % name)


def _validate_reference_outputs(prepared, execution):
    stage = prepared['stage']
    manifest = prepared['manifest']
    reference = _read_json(stage / 'reference.json', 'normal reference.json')
    _require(reference.get('status') == 'complete', 'normal reference status is not complete')
    for key in ('case', 'epoch', 'contract_sha256'):
        _require(reference.get(key) == manifest[key],
                  'normal reference identity mismatch: %s' % key)
    _validate_staged_normal_identity(prepared)
    expected_input = _expected_input_f64(execution['input_rows'])
    _require((stage / 'applied-input.f64').read_bytes() == expected_input,
             'normal applied-input.f64 does not match input CSV')
    channels = {}
    for array, width in ARRAY_LENGTHS.items():
        channels[array] = parse_reference_f64(stage / (array + '.f64'), array, width)
    return channels, reference


def _validate_native_inputs(record_path, input_rows, input_raw):
    lines = [line for line in Path(record_path).read_text(encoding='utf-8').splitlines()
             if line.strip()]
    _require(lines, 'native record is empty')
    try:
        records = [json.loads(line) for line in lines]
    except ValueError as error:
        raise Reject('native record JSON is invalid: %s' % error)
    _require(len(records) == SAMPLES + 2,
             'native record must contain start, %d samples and terminal' % SAMPLES)
    _require(isinstance(records[0], dict), 'native record start must be an object')
    start = records[0]
    input_csv = start.get('input_csv')
    _require(isinstance(input_csv, str), 'native start input_csv must be a string')
    _require(input_csv.encode('ascii') == input_raw,
             'native start input_csv does not match input CSV bytes')
    for k, row in enumerate(input_rows):
        sample = records[k + 1]
        _require(sample.get('inPWMs') == row['inPWMs'],
                 'native inPWMs mismatch at k=%d' % k)
        _require(sample.get('TerrainIn15d') == row['TerrainIn15d'],
                 'native TerrainIn15d mismatch at k=%d' % k)


def _execution_result(prepared, execution, normal_status, native_status, comparison):
    manifest = prepared['manifest']
    normal_result = dict(normal_status)
    normal_result['source_identity'] = manifest['normal']
    native_result = dict(native_status)
    native_result['executable_entity'] = execution['native']['launch_executable']
    native_result['source_identity'] = manifest['native']['source_identity']
    return {
        'status': comparison['status'],
        'case_id': manifest['case'],
        'epoch': manifest['epoch'],
        'contract_id': None,
        'contract_sha256': manifest['contract_sha256'],
        'input_sha256': manifest['input_sha256'],
        'execution_attempted': True,
        'matlab_launched': True,
        'native_launched': True,
        'normal': normal_result,
        'native': native_result,
        'sampling': {
            'fixed_step_s': TIME_STEP_S, 'k_first': 0, 'k_last': SAMPLES - 1,
            'array_lengths': dict(ARRAY_LENGTHS),
        },
        'comparison': comparison,
        'scalar_count': comparison['scalar_count'],
        'comparisons': comparison['comparisons'],
        'failed_values': comparison['failed_values'],
        'failed_conditions': comparison['failed_conditions'],
        'failed_scalars': comparison['failed_scalars'],
        'physical_accuracy': False,
        'g6_acceptance': False,
    }


def run(contract_path, *, evidence_dir=None, launcher=None, wsl_path_resolver=None,
        native_identity_probe=None):
    """Run normal MATLAB then native recorder after a complete fail-closed preflight.

    The launcher, WSL path resolver and native identity probe are injectable for tests. The
    real defaults are never reached when the contract or the 56 unbudgeted dynamic
    quantities leave the entry blocked.
    """
    try:
        contract, reasons = validate_contract(contract_path)
    except Reject as error:
        return _result(STATUS_BLOCKED, [str(error)], physical_accuracy=False)
    if reasons:
        return _result(STATUS_BLOCKED, reasons, physical_accuracy=False,
                       contract=contract)
    try:
        execution = validate_execution(contract_path, contract)
        if native_identity_probe is None:
            native_identity_probe = _probe_wsl_executable
        observed = _verify_native_executable(execution, native_identity_probe)
        execution['native']['observed_executable'] = observed
        prepared = _prepare_execution(contract_path, execution, evidence_dir)
    except Reject as error:
        # No directory is created by validation failures.  A preparation failure is
        # also reported blocked because no child has been started yet.
        return _result(STATUS_BLOCKED, [str(error)], physical_accuracy=False,
                       contract=contract)
    except (OSError, ValueError) as error:
        return _result(STATUS_BLOCKED, ['execution preparation failed: %s' % error],
                       physical_accuracy=False, contract=contract)

    launcher = _launch_process if launcher is None else launcher
    if wsl_path_resolver is None:
        wsl_path_resolver = _default_wsl_path
    evidence = prepared['evidence_dir']
    stage = prepared['stage']
    environment = os.environ.copy()
    environment.pop('MATLABPATH', None)
    environment.update({
        'TEMP': str(evidence / 'temp'), 'TMP': str(evidence / 'temp'),
        'MATLAB_PREFDIR': str(evidence / 'pref'),
    })
    normal_status = {
        'argv': [str(execution['normal']['matlab']['path']), '-wait', '-sd', str(stage),
                 '-batch', 'export_model_reference'],
        'cwd': str(stage), 'stdout_path': str(evidence / 'normal.stdout.log'),
        'stderr_path': str(evidence / 'normal.stderr.log'),
        'expected_executable': {
            'path': str(execution['normal']['matlab']['path']),
            'sha256': execution['normal']['matlab']['sha256'],
        },
        'pid': None, 'started_unix_ns': None, 'ended_unix_ns': None,
        'exit_code': None, 'timeout': False, 'timeout_source': None,
        'launch_skipped': True,
    }
    native_timeout = execution['timeout_seconds']
    native_status = {
        'argv': None, 'cwd': str(ROOT),
        'stdout_path': str(evidence / 'native.stdout.log'),
        'stderr_path': str(evidence / 'native.stderr.log'),
        'input_path_resolution': 'pending',
        'expected_executable': {
            'path': execution['native']['wsl_executable'],
            'filename': execution['native']['executable_filename'],
            'sha256': execution['native']['executable_sha256'],
            'size_bytes': execution['native']['executable_size_bytes'],
        },
        'preflight_executable': execution['native']['observed_executable'],
        'pid': None, 'started_unix_ns': None, 'ended_unix_ns': None,
        'exit_code': None, 'timeout': False, 'timeout_source': None,
        'launch_skipped': True,
    }
    try:
        wsl_input = wsl_path_resolver(
            evidence / 'input.csv', execution['native']['wsl_distro'])
        native_argv = [
            'wsl.exe', '-d', execution['native']['wsl_distro'], '--exec',
            'timeout', '--signal=TERM', '--kill-after=5s', '%ss' % native_timeout,
            execution['native']['wsl_executable'], '--record', wsl_input,
        ]
        native_status['argv'] = native_argv
        native_status['input_path_resolution'] = 'complete'
        native_status['wsl_input_path'] = wsl_input
        normal_launch_sha = _sha256(execution['normal']['matlab']['path'])
        _require(normal_launch_sha == execution['normal']['matlab']['sha256'],
                 'normal MATLAB executable bytes changed before launch')
        normal_status['prelaunch_executable'] = {
            'path': str(execution['normal']['matlab']['path']),
            'sha256': normal_launch_sha,
        }
        normal_status['launch_skipped'] = False
        normal_status.update(launcher(
            side='normal', argv=normal_status['argv'], cwd=stage, env=environment,
            stdout_path=evidence / 'normal.stdout.log',
            stderr_path=evidence / 'normal.stderr.log',
            timeout_seconds=execution['timeout_seconds']))
        _write_json(evidence / 'normal-process.json', normal_status)
        _validate_process_status(normal_status, 'normal')
        normal_values, reference = _validate_reference_outputs(prepared, execution)

        launch_observed = _verify_native_executable(execution, native_identity_probe)
        execution['native']['launch_executable'] = launch_observed
        native_status['prelaunch_executable'] = launch_observed
        _write_json(evidence / 'native-launch-identity.json', launch_observed)
        native_status['launch_skipped'] = False
        native_status.update(launcher(
            side='native', argv=native_argv, cwd=ROOT, env=os.environ.copy(),
            stdout_path=evidence / 'native.stdout.log',
            stderr_path=evidence / 'native.stderr.log',
            timeout_seconds=native_timeout + 10.0))
        if native_status.get('exit_code') in (124,137):
            native_status['timeout'] = True
            native_status['timeout_source'] = 'wsl_coreutils_timeout'
        _write_json(evidence / 'native-process.json', native_status)
        _validate_process_status(native_status, 'native')
        _validate_native_inputs(evidence / 'native.stdout.log', execution['input_rows'],
                                execution['input_raw'])
        native_values = parse_native_record(evidence / 'native.stdout.log',
                                            execution['native']['source_identity'])
        aligned = align(normal_values, native_values, contract['observables'])
        comparison = compare_aligned(aligned, contract['observables'])
        result = _execution_result(prepared, execution, normal_status, native_status,
                                   comparison)
        result['contract_id'] = contract.get('contract_id')
        result['normal']['reference_json'] = str(stage / 'reference.json')
        result['normal']['channels'] = {
            array: str(stage / (array + '.f64')) for array in ARRAY_LENGTHS
        }
        result['native']['record_jsonl'] = str(evidence / 'native.stdout.log')
    except (Reject, OSError, ValueError, subprocess.SubprocessError) as error:
        result = _result(STATUS_INVALID_RUN, [str(error)], physical_accuracy=False,
                         contract=contract)
        result.update({
            'case_id': prepared['manifest']['case'],
            'epoch': prepared['manifest']['epoch'],
            'contract_sha256': prepared['manifest']['contract_sha256'],
            'input_sha256': prepared['manifest']['input_sha256'],
            'execution_attempted': bool(normal_status.get('exit_code') is not None),
            'matlab_launched': bool(normal_status.get('exit_code') is not None),
            'native_launched': bool(native_status is not None
                                    and native_status.get('exit_code') is not None),
            'normal': {
                **normal_status,
                'source_identity': prepared['manifest']['normal'],
            },
            'native_executable_entity': execution['native'].get(
                'launch_executable', execution['native']['observed_executable']),
            'native_source_identity': execution['native']['source_identity'],
        })
        if native_status is not None:
            result['native'] = {
                **native_status,
                'executable_entity': execution['native'].get(
                    'launch_executable', execution['native']['observed_executable']),
                'source_identity': execution['native']['source_identity'],
            }
        result['error'] = str(error)
    _write_json(evidence / 'result.json', result)
    return result


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
    parser.add_argument('--evidence-dir', type=Path, default=None,
                        help='Fresh directory for staged inputs, logs and result.json')
    args = parser.parse_args()
    result = run(args.contract, evidence_dir=args.evidence_dir)
    text = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output is not None:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)
    if result['status'] == STATUS_DECLARED_CASES_PASS:
        return 0
    if result['status'] == STATUS_NUMERICAL_FAILED:
        return 1
    return 2


if __name__ == '__main__':
    sys.exit(main())
