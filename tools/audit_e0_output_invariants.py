"""Offline invariant auditor for #59 e0 outputs.

Validates public/retained record.jsonl outputs against proven structural and value invariants:
1. Exact vector lengths for both major_root_outputs and post_step_api:
   - Vehicle60: 60
   - Sensor30: 30
   - GPS30: 30
2. Finite numeric non-bool values across all channels.
3. The 59 truly reserved numeric-zero slots:
   - Vehicle60[33:60] (27 slots)
   - Sensor30[15:30] (15 slots)
   - GPS30[13:30] (17 slots)
   Numeric zero may be either sign (+0.0 or -0.0); report signed-zero counts instead of rejecting -0.0.
4. The 5 exact interface metadata constants:
   - Vehicle60[0:2] == [1.0, 3.0]
   - Sensor30[14] == 8191.0
   - GPS30[11:13] == [3.0, 10.0]
5. Usable samples (>0) and a valid terminal record (major_recorder_end with status='complete',
   matching sample counts, and finite timestamps).

Emits deterministic JSON containing input path/SHA256, sample counts, invariant groups,
signed-zero counts, and pass/fail diagnostics.

BOUNDARY:
This tool produces diagnostic evidence only. It does NOT claim G6 acceptance or physical completion.
"""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

# Ensure repo root is available on sys.path for direct invocations.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_e0_same_source_conformance import ARRAY_LENGTHS, _is_finite_number


AUDIT_VERSION = 1
BRANCHES = ('major_root_outputs', 'post_step_api')

# The 59 truly reserved numeric-zero slots
RESERVED_ZERO_SLOTS = {
    'Vehicle60': list(range(33, 60)),  # 27 slots: 33..59
    'Sensor30': list(range(15, 30)),   # 15 slots: 15..29
    'GPS30': list(range(13, 30)),      # 17 slots: 13..29
}
TOTAL_RESERVED_ZERO_SLOTS = sum(len(slots) for slots in RESERVED_ZERO_SLOTS.values())  # 59

# The 5 exact interface metadata constants
INTERFACE_METADATA_CONSTANTS = {
    'Vehicle60': {0: 1.0, 1: 3.0},
    'Sensor30': {14: 8191.0},
    'GPS30': {11: 3.0, 12: 10.0},
}
TOTAL_INTERFACE_CONSTANTS = sum(len(c) for c in INTERFACE_METADATA_CONSTANTS.values())  # 5

MAX_RECORDED_VIOLATIONS = 200


def is_negative_zero(value):
    """Detect negative zero (-0.0) vs positive zero (+0.0)."""
    return value == 0.0 and math.copysign(1.0, value) < 0.0


def compute_file_sha256(path):
    """Compute sha256 hex digest of file."""
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def audit_record(path):
    """Audit a single record.jsonl file against e0 output invariants."""
    file_path = Path(path).resolve()
    result = {
        'input_path': str(file_path).replace('\\', '/'),
        'sha256': None,
        'passed': False,
        'sample_counts': {
            'total_lines': 0,
            'usable_samples': 0,
            'terminal_emitted_samples': None,
        },
        'terminal_status': {
            'kind': None,
            'status': None,
            'valid': False,
        },
        'signed_zero_counts': {
            'positive_zeros': 0,
            'negative_zeros': 0,
        },
        'invariant_groups': {
            'vector_lengths': {
                'status': 'pass',
                'expected_lengths': dict(ARRAY_LENGTHS),
                'violations': 0,
            },
            'finite_numeric_non_bool': {
                'status': 'pass',
                'violations': 0,
            },
            'reserved_numeric_zeros': {
                'status': 'pass',
                'total_slots_per_sample_branch': TOTAL_RESERVED_ZERO_SLOTS,
                'slots': {
                    'Vehicle60': '33:60',
                    'Sensor30': '15:30',
                    'GPS30': '13:30',
                },
                'violations': 0,
            },
            'interface_metadata_constants': {
                'status': 'pass',
                'total_slots_per_sample_branch': TOTAL_INTERFACE_CONSTANTS,
                'constants': {
                    'Vehicle60[0:2]': [1.0, 3.0],
                    'Sensor30[14]': 8191.0,
                    'GPS30[11:13]': [3.0, 10.0],
                },
                'violations': 0,
            },
            'terminal_record': {
                'status': 'pass',
                'violations': 0,
            },
            'usable_samples': {
                'status': 'pass',
                'violations': 0,
            },
        },
        'violations': [],
    }

    if not file_path.is_file():
        result['violations'].append(f'File not found: {file_path}')
        return result

    result['sha256'] = compute_file_sha256(file_path)

    try:
        raw_text = file_path.read_text(encoding='utf-8')
    except Exception as err:
        result['violations'].append(f'Failed to read file: {err}')
        return result

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    result['sample_counts']['total_lines'] = len(lines)

    if not lines:
        result['violations'].append('File is empty or contains only whitespace')
        result['invariant_groups']['usable_samples']['status'] = 'fail'
        result['invariant_groups']['usable_samples']['violations'] += 1
        return result

    records = []
    for line_idx, line in enumerate(lines):
        try:
            record = json.loads(line)
        except ValueError as err:
            result['violations'].append(f'Line {line_idx + 1}: invalid JSON: {err}')
            return result
        if not isinstance(record, dict):
            result['violations'].append(f'Line {line_idx + 1}: record is not a JSON object')
            return result
        records.append(record)

    if len(records) < 2:
        result['violations'].append(
            f'Insufficient records: expected start, samples, and terminal record, got {len(records)}'
        )
        result['invariant_groups']['terminal_record']['status'] = 'fail'
        result['invariant_groups']['terminal_record']['violations'] += 1
        result['invariant_groups']['usable_samples']['status'] = 'fail'
        result['invariant_groups']['usable_samples']['violations'] += 1
        return result

    # Identify terminal and sample records
    terminal = records[-1]
    result['terminal_status']['kind'] = terminal.get('kind')
    result['terminal_status']['status'] = terminal.get('status')

    # Validate terminal record
    terminal_valid = True
    terminal_reasons = []
    if terminal.get('kind') != 'major_recorder_end':
        terminal_valid = False
        terminal_reasons.append(f"terminal kind is {terminal.get('kind')!r}, expected 'major_recorder_end'")
    if terminal.get('schema_version') != 1 or type(terminal.get('schema_version')) is not int:
        terminal_valid = False
        terminal_reasons.append(f"terminal schema_version is {terminal.get('schema_version')!r}, expected int 1")
    if terminal.get('status') != 'complete':
        terminal_valid = False
        terminal_reasons.append(f"terminal status is {terminal.get('status')!r}, expected 'complete'")

    emitted = terminal.get('emitted_samples')
    result['sample_counts']['terminal_emitted_samples'] = emitted
    if type(emitted) is not int or emitted <= 0:
        terminal_valid = False
        terminal_reasons.append(f"terminal emitted_samples is {emitted!r}, expected positive integer")

    for call_field in ('attempted_calls', 'returned_calls'):
        val = terminal.get(call_field)
        if type(val) is not int or val != emitted:
            terminal_valid = False
            terminal_reasons.append(f"terminal {call_field} is {val!r}, expected {emitted}")

    for time_field in ('comparison_end_s', 'engine_end_s'):
        val = terminal.get(time_field)
        if not _is_finite_number(val):
            terminal_valid = False
            terminal_reasons.append(f"terminal {time_field} is {val!r}, expected finite numeric time")

    result['terminal_status']['valid'] = terminal_valid
    if not terminal_valid:
        result['invariant_groups']['terminal_record']['status'] = 'fail'
        result['invariant_groups']['terminal_record']['violations'] += len(terminal_reasons)
        result['violations'].extend(terminal_reasons)

    # Collect usable samples (records between start and terminal with kind == 'major_recorder_sample')
    samples = []
    start_offset = 1 if records[0].get('kind') == 'major_recorder_start' else 0
    candidate_samples = records[start_offset:-1]

    for idx, rec in enumerate(candidate_samples):
        if rec.get('kind') == 'major_recorder_sample':
            samples.append(rec)
        else:
            result['violations'].append(
                f"Candidate sample record at line {start_offset + idx + 1} has kind {rec.get('kind')!r}"
            )

    result['sample_counts']['usable_samples'] = len(samples)

    if not samples:
        result['violations'].append('No usable major_recorder_sample records found')
        result['invariant_groups']['usable_samples']['status'] = 'fail'
        result['invariant_groups']['usable_samples']['violations'] += 1
        return result

    if terminal_valid and emitted is not None and len(samples) != emitted:
        result['violations'].append(
            f'Usable sample count ({len(samples)}) does not match terminal emitted_samples ({emitted})'
        )
        result['invariant_groups']['usable_samples']['status'] = 'fail'
        result['invariant_groups']['usable_samples']['violations'] += 1

    # Validate each sample against all invariants on both branches
    pos_zeros = 0
    neg_zeros = 0

    def add_violation(group_name, message):
        result['invariant_groups'][group_name]['status'] = 'fail'
        result['invariant_groups'][group_name]['violations'] += 1
        if len(result['violations']) < MAX_RECORDED_VIOLATIONS:
            result['violations'].append(message)
        elif len(result['violations']) == MAX_RECORDED_VIOLATIONS:
            result['violations'].append('... [additional violations truncated for brevity]')

    for sample_idx, sample in enumerate(samples):
        k = sample.get('k', sample_idx)

        # Check step_status
        if sample.get('step_status') != 'complete':
            add_violation('usable_samples', f"k={k}: step_status is {sample.get('step_status')!r}, expected 'complete'")

        for branch in BRANCHES:
            branch_data = sample.get(branch)
            if not isinstance(branch_data, dict):
                add_violation('vector_lengths', f"k={k}: branch {branch} is missing or not an object")
                continue

            for array_name, expected_len in ARRAY_LENGTHS.items():
                values = branch_data.get(array_name)
                if not isinstance(values, list):
                    add_violation('vector_lengths', f"k={k}: {branch}.{array_name} is missing or not a list")
                    continue

                # 1. Exact vector length check
                if len(values) != expected_len:
                    add_violation(
                        'vector_lengths',
                        f"k={k}: {branch}.{array_name} length {len(values)} != {expected_len}"
                    )
                    continue

                # 2. Finite numeric non-bool check
                for slot_idx, val in enumerate(values):
                    if not _is_finite_number(val):
                        add_violation(
                            'finite_numeric_non_bool',
                            f"k={k}: {branch}.{array_name}[{slot_idx}] is not finite numeric non-bool: {val!r} (type={type(val).__name__})"
                        )

                # 3. The 59 truly reserved numeric-zero slots
                zero_slots = RESERVED_ZERO_SLOTS.get(array_name, [])
                for slot_idx in zero_slots:
                    val = values[slot_idx]
                    if _is_finite_number(val):
                        if val == 0.0:
                            if is_negative_zero(val):
                                neg_zeros += 1
                            else:
                                pos_zeros += 1
                        else:
                            add_violation(
                                'reserved_numeric_zeros',
                                f"k={k}: {branch}.{array_name}[{slot_idx}] = {val!r} != 0.0 (reserved zero violation)"
                            )

                # 4. The 5 exact interface metadata constants
                constant_slots = INTERFACE_METADATA_CONSTANTS.get(array_name, {})
                for slot_idx, expected_val in constant_slots.items():
                    val = values[slot_idx]
                    if not _is_finite_number(val) or val != expected_val:
                        add_violation(
                            'interface_metadata_constants',
                            f"k={k}: {branch}.{array_name}[{slot_idx}] = {val!r} != {expected_val} (interface constant mismatch)"
                        )

    result['signed_zero_counts']['positive_zeros'] = pos_zeros
    result['signed_zero_counts']['negative_zeros'] = neg_zeros

    all_groups_pass = all(
        group['status'] == 'pass' for group in result['invariant_groups'].values()
    )
    result['passed'] = all_groups_pass and not result['violations']
    return result


def audit_records(paths):
    """Audit one or more record.jsonl files and return a deterministic report dict."""
    results = [audit_record(p) for p in paths]
    total = len(results)
    passed = sum(1 for r in results if r['passed'])
    failed = total - passed

    report = {
        'audit_version': AUDIT_VERSION,
        'scope': 'offline_invariant_diagnostics_only',
        'g6_acceptance': False,
        'physical_completion': False,
        'summary': {
            'total_inputs': total,
            'passed_inputs': passed,
            'failed_inputs': failed,
            'all_passed': (failed == 0 and total > 0),
        },
        'results': results,
    }
    return report


def format_audit_json(report):
    """Format report into deterministic sorted JSON."""
    return json.dumps(report, indent=2, sort_keys=True)


def main(argv=None):
    """CLI entry point for offline output invariant auditor."""
    parser = argparse.ArgumentParser(
        description='Offline invariant auditor for #59 e0 outputs (diagnostic evidence only).'
    )
    parser.add_argument(
        'inputs',
        nargs='+',
        help='One or more record.jsonl files to audit.',
    )
    parser.add_argument(
        '--output',
        '-o',
        type=str,
        default=None,
        help='Optional path to write the deterministic JSON report.',
    )
    args = parser.parse_args(argv)

    report = audit_records(args.inputs)
    json_text = format_audit_json(report)

    if args.output:
        Path(args.output).write_text(json_text, encoding='utf-8')

    print(json_text)
    return 0 if report['summary']['all_passed'] else 2


if __name__ == '__main__':
    sys.exit(main())
