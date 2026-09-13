#!/usr/bin/env python3
"""Verify the repaired audit against the independent reviewer's own counterexamples.

Inputs are the reviewer's byte-pinned files under
``validation/coordination/claude-ds-audit-review-20260913-01/work/`` (read-only).
Nothing here writes into that directory, and the raw archive copy is never
modified: every input's sha256 is checked before and after the run.

What is exercised, exactly as the review named it:

* **report shortage 0 and 10** — ``reports-e5b.jsonl`` (empty) and a truncated
  10-report stream, each paired with result counters adjusted to the short
  stream, so only the ``min(over_budget, report_limit)`` law can catch them;
* **duplicated end** — ``rate-e2.jsonl``;
* **missing end** — ``rate-e1.jsonl``;
* **tick binding** — ``rate-e3.jsonl``;
* **globally reordered ends** — ``rate-e4.jsonl`` (all starts, then all ends),
  which satisfies "an end follows its own start" yet violates the one-open-group
  invariant;
* **the raw baseline must still pass** — ``rate.jsonl`` + ``rate-report.jsonl`` +
  ``result.json``, whose manifest shas match the archived flight.

Exit status: 0 when every expectation holds, 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT_PATH = os.path.join(HERE, 'ds_group_audit.py')
GAP_PATH = os.path.join(HERE, 'gap_map.py')

_spec = importlib.util.spec_from_file_location('ds_group_audit_verify', AUDIT_PATH)
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)
_gap_spec = importlib.util.spec_from_file_location('ds_group_map_verify', GAP_PATH)
gap_map = importlib.util.module_from_spec(_gap_spec)
_gap_spec.loader.exec_module(gap_map)

DEFAULT_WORK = ('C:/Users/PC/Documents/odid编译/wksim/validation/coordination/'
                'claude-ds-audit-review-20260913-01/work')

# Reviewer-pinned sha256 for every input this script reads.
PINNED = {
    'rate.jsonl': '7aa7e3f4624a5128d1301e6ca1f7d4baaa239357d920154a185546a496202d01',
    'rate-report.jsonl': '8f2d60a4adefdf0b96f5d3df19061a4f866bdede54267fcc39821be8e1e59c50',
    'result.json': '9e2caf5c58a7011642a3580341b999c21ac53bd52f0718b3cd8ed4e2a6dc4c27',
    'rate-e1.jsonl': 'c5237fef69accce79ec24fd84de0c141a68ff196d0d057c78ce0b5f73dc2d8ad',
    'rate-e2.jsonl': '17ba3ef49db94d7e422ec8ba2ba63bacc723418fc660a4a91322d681bfd75b98',
    'rate-e3.jsonl': 'b81c35cfdbaa1da1fe8d147784a50f835cf6cf948e84b9f5c8db970fad2a97b6',
    'rate-e4.jsonl': 'bb6c8fbcccb868b382e7f72ce3cd6c851d260fa307413c4b1513889e714496c2',
    'result-e1.json': '6d82c2b40fca1338fdff3d80209bce479cb1fdc9ccfcfe134e8881fc42a66130',
    'result-e2.json': '2659749f82be8babdf9aa0f275bb8e8ba9f2fecf9307ca8232dfba0355132c5c',
    'result-e3.json': '3f66afa291da32d15fa61c7fbe01e242cb49e9d62f2573b67cda1b0fd982320f',
    'result-e5a.json': '507e03ddd4ce4e03e2d38e57a1a78c099f84f4b48f5231e15e538a6bc31a57fc',
    'result-e5b.json': '5ab7983a416dc080a642efb997bad5e42509a9cda94bf1a33f56c09a3d6088d8',
    'reports-e5a.jsonl': '41c628ee9db45e730668bb2efbb5729b8d69185c57ee528e4606bd6d8185016f',
    'reports-e5b.jsonl': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'reports-e3.jsonl': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
}

EXPECTATIONS = [
    dict(name='baseline_raw', rate='rate.jsonl', reports='rate-report.jsonl',
         result='result.json', want='pass', codes=[],
         note='the archived raw flight must still pass with no finding'),
    dict(name='e1_missing_end', rate='rate-e1.jsonl', reports='rate-report.jsonl',
         result='result-e1.json', want='fail',
         codes=['rate-orphan-start', 'rate-stream-unbalanced'],
         note='final rate_group_end deleted; stream shows starts > ends'),
    dict(name='e2_duplicated_end', rate='rate-e2.jsonl', reports='rate-report.jsonl',
         result='result-e2.json', want='fail',
         codes=['rate-duplicate-end'],
         note='last end row duplicated and appended after the unmet row'),
    dict(name='e3_tick_binding', rate='rate-e3.jsonl', reports='reports-e3.jsonl',
         result='result-e3.json', want='fail',
         codes=['rate-'],
         note='single-group stream; row ticks are 77/88 while boundaries are 0/4'),
    dict(name='e4_globally_reordered_ends', rate='rate-e4.jsonl',
         reports='rate-report.jsonl', result='result.json', want='fail',
         codes=['rate-group-overlap', 'rate-open-group-reconciliation'],
         note='all starts then all ends: every end follows its own start, only the '
              'one-open-group invariant and the event-order reconciliation catch it'),
    dict(name='e5a_short_report_stream', rate='rate.jsonl', reports='reports-e5a.jsonl',
         result='result-e5a.json', want='fail',
         codes=['report-cap-minimum'],
         note='10 reports against 18 over-budget groups with a declared limit of 16'),
    dict(name='e5b_empty_report_stream', rate='rate.jsonl', reports='reports-e5b.jsonl',
         result='result-e5b.json', want='fail',
         codes=['report-cap-minimum'],
         note='zero reports against 18 over-budget groups'),
]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def run_audit(work, entry, out_dir):
    rate = os.path.join(work, entry['rate'])
    reports = os.path.join(work, entry['reports'])
    result = os.path.join(work, entry['result'])
    out = os.path.join(out_dir, 'audit-%s.json' % entry['name'])
    code = audit.main(['--rate', rate, '--group-work-timing', reports,
                       '--result', result, '--out', out, '--label', entry['name']])
    with open(out, 'r', encoding='utf-8') as handle:
        report = json.load(handle)
    return code, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--work', default=DEFAULT_WORK)
    parser.add_argument('--out', default=os.path.join(HERE, 'evidence',
                                                     'verification-v2.json'))
    args = parser.parse_args(argv)
    work = args.work
    out_dir = tempfile.mkdtemp(prefix='ds-audit-verify-')

    before = {name: sha256_file(os.path.join(work, name)) for name in PINNED}
    findings = []
    results = []
    for entry in EXPECTATIONS:
        code, report = run_audit(work, entry, out_dir)
        # use the complete per-code tally: the retained finding list is capped
        code_counts = report.get('finding_code_counts', {})
        codes = sorted(code_counts)
        # a wanted entry is either an exact code or a code prefix (e.g. 'rate-')
        matches = [any(actual == wanted or actual.startswith(wanted) for actual in code_counts)
                   for wanted in entry['codes']]
        if entry['want'] == 'pass':
            ok = report['verdict'] == 'pass' and report['finding_counts']['error'] == 0
        else:
            # every named defect must be reported; additional findings are fine
            ok = report['verdict'] == 'fail' and all(matches)
        results.append({
            'case': entry['name'],
            'note': entry['note'],
            'inputs': {'rate': entry['rate'], 'reports': entry['reports'],
                       'result': entry['result']},
            'expected_verdict': entry['want'],
            'actual_verdict': report['verdict'],
            'exit_code': code,
            'finding_codes': codes,
            'expected_codes': entry['codes'],
            'expectation_met': bool(ok),
            'declared_vs_recomputed': (
                report['counts']['declared'] == report['counts']['recomputed']
                if isinstance(report.get('counts'), dict) else None),
            'over_budget_groups': report.get('rate', {}).get('over_budget_groups'),
            'reports_emitted': len(report.get('reports', [])),
        })
        if not ok:
            findings.append('case %s: expected %s got %s (codes %s)'
                            % (entry['name'], entry['want'], report['verdict'], codes))

    after = {name: sha256_file(os.path.join(work, name)) for name in PINNED}
    unchanged = before == after
    for name, digest in before.items():
        if digest != PINNED[name]:
            findings.append('input %s sha256 differs from the reviewer pin' % name)
    if not unchanged:
        findings.append('an input file changed while the verification ran')

    # Gap categorisation: all 48 retained gaps are intra-group (4-step relation).
    # Derived from the audit artifact's own duration/gap fields, because the
    # reviewer work directory has no joint-wire.jsonl for clock alignment.
    gap_checks = []
    try:
        with open(os.path.join(HERE, 'evidence',
                               'joint-public-flight-rfw9nmbb-audit.json'),
                  'r', encoding='utf-8') as handle:
            audit_artifact = json.load(handle)
        gaps = gap_map.gaps_from_audit(audit_artifact)
        intra = [gap for gap in gaps if gap['within_group_span']]
        crossing = [gap for gap in gaps if gap['crosses_rate_boundary']]
        four_step_ok = all(
            gap['to_tick'] - gap['from_tick'] == 1
            and gap['from_tick'] == gap['group_start_tick'] + 1 + gap['index']
            and gap['to_tick'] <= gap['group_start_tick'] + 4
            for gap in gaps)
        gap_checks.append({
            'gaps_total': len(gaps),
            'gaps_intra_group': len(intra),
            'gaps_crossing_rate_boundary': len(crossing),
            'four_step_relation_holds': four_step_ok,
            'audit_artifact': 'evidence/joint-public-flight-rfw9nmbb-audit.json',
        })
        if (len(gaps), len(intra), len(crossing)) != (48, 48, 0):
            findings.append('gap categorisation is not 48 intra / 0 boundary')
        if not four_step_ok:
            findings.append('a retained gap does not join consecutive steps of P+1..P+4')
    except Exception as error:  # noqa: BLE001 - reported, not raised
        findings.append('gap verification failed: %s: %s' % (type(error).__name__, error))

    report = {
        'tool': 'ds_group_audit_verification',
        'purpose': 'verify the repaired audit against the independent reviewer counterexamples',
        'work_dir': work,
        'input_sha256_before': before,
        'input_sha256_after': after,
        'inputs_unchanged': unchanged,
        'cases': results,
        'cases_passed': sum(1 for item in results if item['expectation_met']),
        'cases_total': len(results),
        'gap_categorisation': gap_checks,
        'verdict': 'pass' if not findings else 'fail',
        'findings': findings,
    }
    if args.out:
        directory = os.path.dirname(os.path.abspath(args.out))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(args.out, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
    print(json.dumps({'verdict': report['verdict'],
                      'cases_passed': report['cases_passed'],
                      'cases_total': report['cases_total'],
                      'inputs_unchanged': unchanged,
                      'out': args.out}, sort_keys=True))
    for item in findings:
        print('  finding: %s' % item)
    return 0 if not findings else 1


if __name__ == '__main__':
    sys.exit(main())
