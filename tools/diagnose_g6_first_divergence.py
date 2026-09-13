"""Offline locator for the first binary64 divergence in the frozen G6 R1 evidence.

Read-only and fail-closed: this tool never runs a model, MATLAB, a native
process, a ROS node, or a build, and it never changes the frozen contract,
thresholds, or any pinned evidence. It reads each of its input artifacts once,
re-derives and cross-checks their identities (contract hash vs run-index and vs
every failure row, failure count, case-manifest bytes vs run-index record, and
each row's decimal vs hex decoding), and *refuses* — rather than reporting a
localization — whenever any of those bindings is inconsistent.

When the evidence is intact it reports the earliest divergence (smallest sample
index k) with its input/model/unit/frame contract binding and reference/target
values, and frames the cause strictly as an *unproven hypothesis*: the frozen
data is consistent with a floating-point evaluation difference between the two
pinned engines; the exact cause requires first-step intra-step evidence that the
retained per-1ms outputs do not contain.

The comparison rule being analysed is R1's: for finite parsed binary64 reference
r and target x, require x == r (equal signed zeros pass), zero abs/rel budget.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys

REPO = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = REPO / 'validation' / 'numerical-conformance-gxxh6xhr'
DEFAULT_CONTRACT = REPO / 'Simulator' / 'wksim_core' / 'numerical-conformance-v1.json'
# The first localization wrote diagnosis.json (retained) and the integrity-hardened
# revision wrote v2/diagnosis.json (retained). New reports go to the v3 subdirectory.
DEFAULT_OUT = REPO / 'validation' / 'coordination' / 'g6-first-divergence-20260913' / 'v3'


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def hex_to_bits(text):
    """Parse a C99 hex float (e.g. '0x1.fb743384c5850p-98') to its binary64 bit pattern."""
    return struct.unpack('>Q', struct.pack('>d', float.fromhex(text)))[0]


def _ordered_key(bits):
    """Monotonic unsigned key for an IEEE-754 binary64 pattern.

    Maps most-negative -> 0 up to most-positive -> max, with -0.0 and +0.0
    adjacent (they compare equal under R1, so such a pair is never a failure).
    """
    if bits >> 63:  # sign bit set: negative value or -0.0
        return (~bits) & 0xFFFFFFFFFFFFFFFF
    return bits | 0x8000000000000000


def ulp_distance(hex_a, hex_b):
    """Absolute distance in ULPs between two C99 hex-float binary64 values."""
    return abs(_ordered_key(hex_to_bits(hex_a)) - _ordered_key(hex_to_bits(hex_b)))


def _decimal_matches_hex(decimal, hex_text):
    """A failure row's JSON decimal and C99 hex must decode to the same double."""
    return float(decimal) == float.fromhex(hex_text)


def load_failures(source):
    """Parse failure rows from a path, or from already-captured bytes."""
    if isinstance(source, (bytes, bytearray)):
        text = bytes(source).decode('utf-8')
    else:
        text = Path(source).read_bytes().decode('utf-8')
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _input_onset_k(case):
    """First sample index k at which the case applies any nonzero motor channel."""
    for event in sorted(case.get('events', []), key=lambda e: e['first_k']):
        if any(v != 0 for v in event.get('inPWMs0_to_3', [])):
            return event['first_k']
    return None


def _input_at_k(case, k):
    """The motor channels held over the step containing sample k (zero-order hold)."""
    for event in sorted(case.get('events', []), key=lambda e: e['first_k']):
        if event['first_k'] <= k <= event['last_k']:
            return {'first_k': event['first_k'], 'last_k': event['last_k'],
                    'inPWMs0_to_3': event.get('inPWMs0_to_3')}
    return None


def _artifact_sha(artifacts, case, suffix):
    needle = '/' + case + '/' + suffix
    for key, value in artifacts.items():
        if key.replace('\\', '/').endswith(needle):
            return value
    return None


def _artifact_path(artifacts, case, suffix, run_index_path):
    needle = '/' + case + '/' + suffix
    repo_root = Path(run_index_path).resolve().parents[2]
    for key in artifacts:
        if key.replace('\\', '/').endswith(needle):
            return repo_root / key.replace('\\', '/')
    return None


def _verified_manifest(artifacts, case, run_index_path):
    """Read the case manifest once and require its bytes to match the run-index record."""
    recorded = _artifact_sha(artifacts, case, 'manifest.json')
    if recorded is None:
        return None  # no manifest pinned for this case; executable/gen-cpp stay unrecorded
    path = _artifact_path(artifacts, case, 'manifest.json', run_index_path)
    _require(path is not None and path.is_file(),
             'recorded case manifest is missing: ' + case)
    manifest_bytes = path.read_bytes()
    _require(hashlib.sha256(manifest_bytes).hexdigest() == recorded,
             'case manifest bytes do not match run-index recorded sha256: ' + case)
    return json.loads(manifest_bytes)


def diagnose(failures_path, contract_path, run_index_path):
    """Locate the earliest binary64 divergence, refusing on any integrity mismatch."""
    failures_path = Path(failures_path)
    contract_path = Path(contract_path)
    run_index_path = Path(run_index_path)

    # Read each input once, then parse AND hash from the same captured bytes, so
    # the report can never desync from the data that was actually analysed.
    contract_bytes = contract_path.read_bytes()
    contract_sha = sha256_bytes(contract_bytes)
    contract = json.loads(contract_bytes)
    run_index_bytes = run_index_path.read_bytes()
    run_index = json.loads(run_index_bytes)
    failures_bytes = failures_path.read_bytes()
    failures = load_failures(failures_bytes)

    _require(run_index.get('contract_sha256') == contract_sha,
             'run-index contract_sha256 does not match the contract bytes')
    _require(len(failures) == run_index.get('failed_values'),
             'failure line count {} does not match run-index failed_values {}'.format(
                 len(failures), run_index.get('failed_values')))
    for row in failures:
        _require(row.get('contract_sha256') == contract_sha,
                 'failure row contract_sha256 does not match the contract bytes')
        _require(all(type(row[name]) in (int, float) and math.isfinite(row[name])
                     for name in ('reference', 'target')),
                 'failure row must contain finite JSON numbers')
        _require(_decimal_matches_hex(row['reference'], row['reference_hex']),
                 'failure row reference decimal does not decode to its hex')
        _require(_decimal_matches_hex(row['target'], row['target_hex']),
                 'failure row target decimal does not decode to its hex')
        _require(row['reference'] != row['target'],
                 'failure row is not a strict binary64 inequality (equal signed zeros pass R1)')

    observable = {}
    for obs in contract.get('observables', []):
        for index in obs['indices']:
            observable[(obs['array'], index)] = obs
    cases = {c['id']: c for c in contract.get('cases', [])}
    identity = contract.get('identity', {})

    for row in failures:
        a, b = row['reference'], row['target']
        row['ulp_distance'] = ulp_distance(row['reference_hex'], row['target_hex'])
        if a != 0:
            row['relative_error'] = abs(b - a) / abs(a)
        else:
            row['relative_error'] = math.inf if b != 0 else 0.0
        row['sign_flip'] = bool(a != 0 and b != 0 and (a < 0) != (b < 0))
        obs = observable.get((row['array'], row['index']), {})
        row['observable_id'] = obs.get('id')
        row['native_unit'] = obs.get('native_unit')
        row['semantic_status'] = obs.get('semantic_status')
        row['observable_source'] = obs.get('source')

    earliest_k = min(row['k'] for row in failures)
    co_earliest = sorted((row for row in failures if row['k'] == earliest_k),
                         key=lambda r: (r['case'], r['array'], r['index']))
    representative = co_earliest[0]

    # Determinism observation: is the representative axis's first divergence a
    # bit-identical value across the cases that excite it, at the first step
    # after each case's motor-input onset?
    rep_key = (representative['array'], representative['index'])
    first_by_case = {}
    for row in failures:
        if (row['array'], row['index']) == rep_key:
            case = row['case']
            if case not in first_by_case or row['k'] < first_by_case[case]['k']:
                first_by_case[case] = row
    onset = {cid: _input_onset_k(case) for cid, case in cases.items()}
    determinism = {
        'axis': {'array': rep_key[0], 'index': rep_key[1]},
        'first_failure_after_input_onset': {c: first_by_case[c]['k'] for c in sorted(first_by_case)},
        'input_onset_k': {c: onset[c] for c in sorted(first_by_case)},
        'same_value_bit_identical': len({(r['reference_hex'], r['target_hex'])
                                         for r in first_by_case.values()}) == 1,
        'onset_aligned': all(onset[c] is not None and first_by_case[c]['k'] == onset[c] + 1
                             for c in first_by_case),
    }

    # Factual observations only. A ~1-ULP ratio and no sign flips do NOT rule out
    # every coordinate/unit/timing contract issue; they are reported, not a proof.
    def _ratio_flag(row):
        a, b = row['reference'], row['target']
        if a == 0 or b == 0 or row['sign_flip']:
            return False
        ratio = b / a
        return not (0.5 < ratio < 2.0)

    finite_rel = [row['relative_error'] for row in failures
                  if row['reference'] != 0 and math.isfinite(row['relative_error'])]
    aggregate = {
        'per_case_failed_values': dict(sorted(Counter(row['case'] for row in failures).items())),
        'max_ulp_distance': max(row['ulp_distance'] for row in failures),
        'max_relative_error': max(finite_rel) if finite_rel else 0.0,
        'sign_flip_count': sum(1 for row in failures if row['sign_flip']),
        'ratio_outside_half_to_two_count': sum(1 for row in failures if _ratio_flag(row)),
        'reference_exact_zero_count': sum(1 for row in failures if row['reference'] == 0),
    }

    artifacts = run_index.get('artifacts', {})
    case_id = representative['case']
    case_contract = cases.get(case_id, {})
    input_info = case_contract.get('input', {})
    manifest = _verified_manifest(artifacts, case_id, run_index_path)
    executable_sha256 = None
    generated_cpp_sha256 = None
    if manifest is not None:
        for key, value in manifest.get('target_hashes', {}).items():
            norm = key.replace('\\', '/')
            if norm.endswith('/major_model_recorder'):
                executable_sha256 = value
            elif norm.endswith('/Exp1_MinModelTemp.cpp'):
                generated_cpp_sha256 = value
    representative['provenance'] = {
        'case': case_id,
        'epoch': representative['epoch'],
        'contract_sha256': contract_sha,
        'input_csv_path': input_info.get('path'),
        'input_csv_sha256': input_info.get('sha256'),
        'applied_input_f64_sha256': _artifact_sha(artifacts, case_id, 'applied-input.f64'),
        'build_sha256': _artifact_sha(artifacts, case_id, 'build.json'),
        'recorder_cpp_sha256': _artifact_sha(artifacts, case_id, 'major_model_recorder.cpp'),
        'reference_engine': identity.get('reference_engine'),
        'target_profile': identity.get('target_profile'),
        'executable_sha256': executable_sha256,
        'generated_cpp_sha256': generated_cpp_sha256,
    }
    representative['input_at_k'] = _input_at_k(case_contract, earliest_k)

    verdict = {
        'earliest_is_strict_binary64_inequality': True,
        'signed_zero_pair': False,
        'hypothesis': ('the frozen data is consistent with a floating-point evaluation '
                       'difference between the two pinned engines evaluating shared model '
                       'equations'),
        'hypothesis_status': 'unproven',
        'observation_limits': ('small relative error and zero sign flips do not rule out all '
                               'coordinate/unit/timing contract issues'),
        'exact_cause_requires': ('first-step (k=0->1) full-binary64 intra-step intermediates on '
                                 'both engines, which the retained per-1ms major outputs do not '
                                 'contain'),
    }

    return {
        'inputs_sha256': {
            'failures': sha256_bytes(failures_bytes),
            'contract': contract_sha,
            'run_index': sha256_bytes(run_index_bytes),
        },
        'contract_sha256': contract_sha,
        'integrity': {
            'contract_matches_run_index_and_every_failure': True,
            'failure_count_matches_run_index': True,
            'every_failure_decimal_matches_hex': True,
            'representative_manifest_matches_run_index': manifest is not None,
        },
        'total_failed_values': len(failures),
        'run_index_failed_values': run_index.get('failed_values'),
        'earliest_k': earliest_k,
        'co_earliest': co_earliest,
        'representative': representative,
        'determinism': determinism,
        'aggregate': aggregate,
        'verdict': verdict,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--failures', type=Path, default=DEFAULT_EVIDENCE / 'all-failures.jsonl')
    parser.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument('--run-index', type=Path, default=DEFAULT_EVIDENCE / 'run-index.json')
    parser.add_argument('--out-dir', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--no-write', action='store_true', help='print only; write no artifacts')
    args = parser.parse_args(argv)

    try:
        result = diagnose(args.failures, args.contract, args.run_index)
    except (ValueError, OSError, KeyError) as error:
        # Fail closed: inconsistent/corrupt/missing evidence is refused, and no
        # localization is printed as success or written.
        print('G6 first-divergence diagnosis refused: ' + str(error), file=sys.stderr)
        return 2

    rep = result['representative']
    det = result['determinism']
    agg = result['aggregate']
    verdict = result['verdict']
    print('G6 R1 first-divergence locator (offline, read-only, fail-closed)')
    print('  total failed values : {} (run-index {})'.format(
        result['total_failed_values'], result['run_index_failed_values']))
    print('  earliest divergence : case={} array={}[{}] k={}'.format(
        rep['case'], rep['array'], rep['index'], rep['k']))
    print('    observable        : {} unit={} semantic={}'.format(
        rep['observable_id'], rep['native_unit'], rep['semantic_status']))
    print('    reference (expect): {}  {}'.format(rep['reference'], rep['reference_hex']))
    print('    target    (actual): {}  {}'.format(rep['target'], rep['target_hex']))
    print('    ulp distance      : {}  abs_err={}'.format(rep['ulp_distance'], rep['absolute_error']))
    print('    input at k={}      : {}'.format(rep['k'], rep['input_at_k']))
    print('  co-earliest axes    : {}'.format(
        [(r['array'], r['index'], r['ulp_distance']) for r in result['co_earliest']]))
    print('  determinism (fact)  : bit_identical={} first_fail={} onset={} aligned={}'.format(
        det['same_value_bit_identical'], det['first_failure_after_input_onset'],
        det['input_onset_k'], det['onset_aligned']))
    print('  observations (fact) : max_ulp={} max_rel={:.3e} sign_flips={} ratio_flags={}'.format(
        agg['max_ulp_distance'], agg['max_relative_error'],
        agg['sign_flip_count'], agg['ratio_outside_half_to_two_count']))
    print('  provenance          : input_csv={}'.format(rep['provenance']['input_csv_sha256']))
    print('                        build={} exe={}'.format(
        rep['provenance']['build_sha256'], rep['provenance']['executable_sha256']))
    print('  hypothesis ({}): {}'.format(verdict['hypothesis_status'], verdict['hypothesis']))
    print('  exact cause needs   : {}'.format(verdict['exact_cause_requires']))

    if args.no_write:
        return 0
    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / 'diagnosis.json'
    # A retained report is evidence: refuse to clobber it (lexists is
    # dangling-symlink aware), then exclusively create so a check/write race
    # cannot overwrite either.
    if os.path.lexists(target):
        print('Diagnosis output already exists; refusing to overwrite retained report: '
              + str(target), file=sys.stderr)
        return 2
    try:
        with open(target, 'x') as handle:
            handle.write(json.dumps(result, indent=2) + '\n')
    except FileExistsError:
        print('Diagnosis output appeared during the run; refusing to overwrite retained report: '
              + str(target), file=sys.stderr)
        return 2
    print('  wrote               : {}'.format(target))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
