#!/usr/bin/env python3
"""Fail-closed regression test for the worker cached-encoder preparation only.

Run:  python test_worker_candidate.py --archive <archived run dir>
Exit: 0 when every check passes.

Offline only: no production import, no child process, no native code, no
network. The candidate is never imported as a package.
"""
import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ARCHIVE = (r'\\wsl$\Ubuntu-22.04\root\wksim-release-acceptance-fe3\validation'
                   r'\joint-public-flight-rfw9nmbb')
EXPECTED_BASELINE = '0becd1f3214b53c6169fb61ae010a969fb57a4ccbe26fb3ed3c3652c26ef7fab'
EXPECTED_CANDIDATE = '38f34a8f68efe8353f99703ec3ce1a18749ec7798933587f349b480dd638060c'

CHECKS = []


def check(name, ok, detail=''):
    CHECKS.append(dict(name=name, ok=bool(ok), detail=str(detail)))
    return bool(ok)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', default=DEFAULT_ARCHIVE)
    args = parser.parse_args(argv)

    prep = load('prep_under_test', os.path.join(HERE, 'prepare_worker_candidate.py'))
    census = load('census_under_test', os.path.join(HERE, 'analyze_census.py'))

    try:
        sources = prep.read_pinned(args.archive)
        check('pinned_sources_match', True, '%d files' % len(sources))
    except Exception as error:  # noqa: BLE001
        check('pinned_sources_match', False, repr(error))
        sources = None

    if sources is None:
        return finish()

    worker = sources[prep.WORKER]
    check('baseline_sha_is_pinned_value', prep.sha256(worker) == EXPECTED_BASELINE,
          prep.sha256(worker))

    candidate = prep.build_worker_candidate(worker)
    check('candidate_sha_is_stable', prep.sha256(candidate) == EXPECTED_CANDIDATE,
          prep.sha256(candidate))
    check('candidate_differs_from_baseline', candidate != worker)
    candidate_text = candidate.decode('utf-8')
    check('exactly_two_edits', candidate_text.count(prep.CANDIDATE_CONSTANT) == 1
          and candidate_text.count(prep.CANDIDATE_FUNCTION) == 1)
    for label, anchor in (('encoded', prep.BASELINE_FUNCTION),
                          ('module_constants', prep.ANCHOR_HINT)):
        check('anchor_unique_' + label, worker.decode('utf-8').count(anchor) == 1)

    tampered = worker.replace(b'REQUEST_LIMIT = 4096', b'REQUEST_LIMIT = 4097')
    refused = False
    try:
        prep.build_worker_candidate(tampered)
    except ValueError as error:
        refused = 'pinned source mismatch' in str(error)
    check('tampered_source_refused_by_pin', refused)
    mislabelled = False
    try:
        prep.build_worker_candidate(worker, 'source__tools__group_work_timing.py.txt')
    except ValueError as error:
        mislabelled = 'pinned source mismatch' in str(error)
    check('mislabelled_source_refused', mislabelled)

    baseline = prep.load_worker(worker, 'baseline')
    patched = prep.load_worker(candidate, 'candidate')
    results = prep.equality_checks(baseline, patched)
    check('corpus_byte_identical', all(r['identical'] for r in results), '%d cases' % len(results))
    check('corpus_covers_value_cases', any(r['outcome'] == 'value' for r in results))
    check('corpus_covers_value_errors', any(r['outcome'] == 'ValueError' for r in results))
    check('corpus_covers_type_errors', any(r['outcome'] == 'TypeError' for r in results))
    check('candidate_calls_bound_encoder',
          patched.encoded.__code__.co_names == ('_ENCODER', 'encode'))
    check('baseline_calls_json_dumps',
          baseline.encoded.__code__.co_names == ('json', 'dumps'))
    compact = patched._ENCODER.encode({'a': 1, 'b': [1, 2]})
    check('encoder_settings_are_compact', compact == '{"a":1,"b":[1,2]}', compact)
    try:
        patched._ENCODER.encode(float('nan'))
        nan_raises = False
    except ValueError:
        nan_raises = True
    check('encoder_rejects_nan_like_baseline', nan_raises)
    check('public_api_unchanged', prep.module_api(worker) == prep.module_api(candidate))
    check('limits_unchanged', patched.REQUEST_LIMIT == 4096 and patched.RESPONSE_LIMIT == 65536)

    counts = prep.worker_call_counts(sources)
    check('parent_channels_two', counts['parent_channels'] == 2)
    check('one_batch_call_per_tick', counts['receive_workers_calls_per_tick'] == 1)
    check('parent_frames_per_tick', counts['parent_request_frames_per_tick'] == 2)
    check('child_calls_per_worker_per_tick', counts['child_calls_per_worker_per_tick'] == 2)
    check('whole_system_calls_per_tick', counts['whole_system_encoded_calls_per_tick'] == 6)
    check('cold_path_lines_excluded', counts['cold_path_lines'] == [27, 242, 243, 248])

    with open(os.path.join(args.archive, 'result.json'), encoding='utf-8') as handle:
        recorder_counts = json.load(handle)['group_work_timing']['counts']
    check('archived_reports_dropped_is_explicit', recorder_counts['reports_dropped'] == 2,
          recorder_counts)
    check('archived_drop_accounting_adds_up',
          recorder_counts['reports_dropped'] == (recorder_counts['over_budget_groups']
                                                - recorder_counts['reports_emitted']))
    records = census.load(os.path.join(args.archive, 'group-work-timing.jsonl'))
    check('census_records_match_emitted', len(records) == recorder_counts['reports_emitted'],
          len(records))
    check('census_rows_are_census_diagnostic_only',
          all(r['census'] is True and r['classification'] == 'diagnostic_only' for r in records))
    closure = []
    for record in records:
        decomposition = record['work_decomposition']
        closure.append(decomposition['prefix_ns'] + sum(decomposition['step_durations_ns'])
                       + sum(decomposition['step_gaps_ns']) + decomposition['suffix_ns']
                       == record['work_ns'])
    check('census_work_decomposition_closes', all(closure))

    report_path = os.path.join(HERE, 'patch-prep-report.json')
    with open(report_path, encoding='utf-8') as handle:
        report = json.load(handle)
    check('report_candidate_sha_matches', report['candidate_sha256'] == prep.sha256(candidate))
    check('report_edits_are_two', report['edits_applied'] == 2)
    check('report_declares_no_execution',
          report['executed_candidate'] is False and report['touched_production_files'] is False)
    check('report_states_no_performance_conclusion', report['performance']['conclusion'] is None)
    check('report_carries_idealised_drift_qualification',
          'previous_start + period' in report['performance']['qualification'])
    check('report_pins_all_sources', report['pinned_sha256'] == prep.PINNED)
    check('rejected_history_declared',
          'rejected' in report['reclaimed_history']['rejected'])
    return finish()


def finish():
    failed = [entry for entry in CHECKS if not entry['ok']]
    print(json.dumps(dict(checks=len(CHECKS), failed=len(failed),
                          failures=[entry['name'] for entry in failed],
                          detail={entry['name']: entry['detail'] for entry in failed}), indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
