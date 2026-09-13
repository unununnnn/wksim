"""Read-only re-check for audit.json in this directory.

Verifies, without executing MATLAB/native/ROS/FC/UE/build:
  1. every cited material exists and still hashes to the recorded value;
  2. the frozen R1 contract still hashes to 23d72e26...;
  3. the same-source entry still refuses the frozen R1 contract and blocks;
  4. the retained R1 failure rows still total 5684 over 180360 comparisons;
  5. the same-source C0 full-series diagnostic still re-derives to 2 different
     values in Sensor30[10] over 60120 comparisons.

Exit 0 means every check reproduced. Any drift exits non-zero.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from tools.run_e0_same_source_conformance import (  # noqa: E402
    ARRAY_LENGTHS, Reject, parse_native_record, parse_reference_f64, validate_contract,
)

failures = []


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def check(condition, message):
    print(('PASS  ' if condition else 'FAIL  ') + message)
    if not condition:
        failures.append(message)


def main():
    audit = json.loads((HERE / 'audit.json').read_text(encoding='utf-8'))

    # 1. cited materials
    for item in audit['identity']['materials']:
        path = ROOT / item['path']
        if not item['exists']:
            check(not path.exists(), 'absent as recorded: %s' % item['path'])
            continue
        check(path.is_file() and sha256(path) == item['sha256'],
              'identity unchanged: %s' % item['path'])

    # 2. frozen R1 contract
    r1 = audit['identity']['r1_contract']
    check(sha256(ROOT / r1['path']) == r1['sha256'],
          'frozen R1 contract sha256 unchanged (%s)' % r1['sha256'])

    # 3. entry refuses R1 and blocks
    try:
        validate_contract(ROOT / r1['path'])
        check(False, 'entry refused the frozen R1 contract')
    except Reject as error:
        check('refusing to treat the frozen R1 contract' in str(error),
              'entry refuses the frozen R1 contract: %s' % error)

    # 4. retained R1 failures
    run_index = json.loads((ROOT / 'validation/numerical-conformance-gxxh6xhr/run-index.json')
                           .read_text(encoding='utf-8'))
    check(run_index['failed_values'] == audit['summary']['r1_cross_version_failed_values'] == 5684,
          'R1 failed_values still 5684')
    check(run_index['total_comparisons'] == audit['summary']['r1_cross_version_comparisons'] == 180360,
          'R1 total_comparisons still 180360')
    check(run_index['failed_case_scalars'] == audit['summary']['r1_cross_version_failed_case_scalars'] == 49,
          'R1 failed_case_scalars still 49')
    rows = [line for line in (ROOT / 'validation/numerical-conformance-gxxh6xhr/all-failures.jsonl')
            .read_text(encoding='utf-8').splitlines() if line.strip()]
    check(len(rows) == 5684, 'retained failure rows still 5684 (found %d)' % len(rows))

    # 5. same-source C0 diagnostic re-derived
    build = json.loads((ROOT / 'validation/e0-major-recorder-parent-final-01/build-manifest.json')
                       .read_text(encoding='utf-8'))
    native = parse_native_record(ROOT / 'validation/e0-major-recorder-parent-final-01/record.jsonl',
                                 build['source_identity'])
    compared = 0
    different = 0
    slots = []
    ref_dir = ROOT / 'validation/numerical-conformance-u56ce17a/C0'
    for array, width in ARRAY_LENGTHS.items():
        reference = parse_reference_f64(ref_dir / (array + '.f64'), array, width)
        for index in range(width):
            count = sum(1 for k in range(501)
                        if reference[k][index] != native[array][k][index])
            compared += 501
            different += count
            if count:
                slots.append('%s[%d]' % (array, index))
    check(compared == 60120, 'same-source C0 comparisons still 60120 (found %d)' % compared)
    check(different == 2, 'same-source C0 different_values still 2 (found %d)' % different)
    check(slots == ['Sensor30[10]'],
          'same-source C0 different slot still Sensor30[10] (found %r)' % slots)
    check(sha256(ROOT / 'validation/e0-major-recorder-parent-final-01/record.jsonl')
          == '8ce61b3338d42f964dbb704bcebe25a7c0b728926eae974970fe3cb6a58ff354',
          'retained C0 native record sha256 unchanged')

    # 6. no slot has an approved epsilon anywhere in the audit
    check(all(q['operator_matrix']['approval'].startswith('not_applicable')
              for q in audit['quantities']),
          'no audited slot declares an approved epsilon')
    check(audit['summary']['slots_with_any_approved_epsilon'] == 0,
          'summary still records 0 approved epsilons')

    print()
    if failures:
        print('RESULT: %d check(s) failed' % len(failures))
        return 1
    print('RESULT: all checks reproduced')
    return 0


if __name__ == '__main__':
    sys.exit(main())
