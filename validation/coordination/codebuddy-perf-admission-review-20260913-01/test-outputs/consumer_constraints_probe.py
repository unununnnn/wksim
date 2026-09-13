#!/usr/bin/env python3
"""Independent read-only probe of the strict perf-stream consumer contract.

Pure Python only: no native code, no build, no ROS, no flight controller, no
model, no UE and no MATLAB. Reuses the committed synthetic fixture
(``ds-perf-stream-fixtures-20260913-01/fixtures/normal_two_pairs``) read-only
and writes every output into a throwaway directory next to itself.

It exercises the exact flag/output/windows constraints the review asked about:
``--require-kernel-counter``, ``--windows`` and ``--output`` (refuse overwrite),
plus the never-self-certify-Full claim (classification/full_acceptance/
flight_conclusion).
"""
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
FIXTURE = REPO / 'validation/coordination/ds-perf-stream-fixtures-20260913-01/fixtures/normal_two_pairs'
CONSUMER = REPO / 'validation/coordination/ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py'

CASES = []


def check(name, ok, detail=''):
    CASES.append(dict(name=name, ok=bool(ok), detail=str(detail)))


def load_consumer():
    spec = importlib.util.spec_from_file_location('perf_stream_consumer', str(CONSUMER))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(module, argv):
    stderr, stdout = io.StringIO(), io.StringIO()
    with redirect_stderr(stderr), redirect_stdout(stdout):
        try:
            code = module.main(argv)
        except SystemExit as error:
            code = error.code
    text = stderr.getvalue().strip() or stdout.getvalue().strip()
    payload = None
    if text:
        try:
            payload = json.loads(text.splitlines()[-1])
        except ValueError:
            payload = None
    return code, payload


module = load_consumer()
raw_bytes = (FIXTURE / 'raw.bin').read_bytes()
base_meta = json.loads((FIXTURE / 'metadata.json').read_text())
work = Path(tempfile.mkdtemp(prefix='chain-consumer-', dir=str(HERE)))
try:
    def fixture(name, meta=None, raw=None):
        directory = work / name
        directory.mkdir()
        blob = raw_bytes if raw is None else raw
        (directory / 'raw.bin').write_bytes(blob)
        document = copy.deepcopy(base_meta) if meta is None else meta
        (directory / 'meta.json').write_text(json.dumps(document))
        return directory

    def argv(directory, output='out.json', require=False, windows=None):
        values = ['--raw', str(directory / 'raw.bin'), '--metadata', str(directory / 'meta.json'),
                  '--output', str(directory / output)]
        if require:
            values.append('--require-kernel-counter')
        if windows is not None:
            (directory / 'windows.json').write_text(json.dumps(windows))
            values += ['--windows', str(directory / 'windows.json')]
        return values

    # A. Legacy metadata (no counter) without the flag: decodes, but never proves
    #    completeness and never self-certifies Full.
    legacy = fixture('legacy')
    code, payload = run(module, argv(legacy))
    report = json.loads((legacy / 'out.json').read_text())
    check('legacy_decodes_without_flag', code == 0, payload)
    check('legacy_completeness_unproven', report['stream_completeness_proven'] is False)
    check('legacy_no_self_full',
          report['classification'] == 'diagnostic_only'
          and report['full_acceptance'] is False
          and report['flight_conclusion'] is None,
          {k: report[k] for k in ('classification', 'full_acceptance', 'flight_conclusion')})
    check('raw_bytes_bound_by_sha',
          report['inputs']['raw_sha256'] == hashlib.sha256(raw_bytes).hexdigest())
    check('windows_absent_is_null', report['windows'] is None)

    # B. The same legacy metadata under --require-kernel-counter must be rejected
    #    (exit 3) and must not leave an output.
    legacy2 = fixture('legacy_required')
    code, payload = run(module, argv(legacy2, require=True))
    check('legacy_rejected_when_required',
          code == 3 and payload and payload.get('reason') == 'kernel_loss_counter_required',
          payload)
    check('rejected_legacy_wrote_no_output', not (legacy2 / 'out.json').exists())

    # C. A valid zero post-disable counter proves stream completeness.
    proved = copy.deepcopy(base_meta)
    proved['config']['read_format'] = 16
    proved.update(kernel_lost_read_ok=True, kernel_lost_read_bytes=16,
                  kernel_lost_read_errno=0, kernel_lost_count=0)
    directory = fixture('proved', meta=proved)
    code, payload = run(module, argv(directory, require=True))
    report = json.loads((directory / 'out.json').read_text())
    check('zero_counter_proves_completeness',
          code == 0 and report['stream_completeness_proven'] is True,
          {k: report.get(k) for k in ('stream_completeness_proven',)})

    # D. A non-zero counter is a hard rejection under the flag.
    lost = copy.deepcopy(proved)
    lost['kernel_lost_count'] = 385
    directory = fixture('lost', meta=lost)
    code, payload = run(module, argv(directory, require=True))
    check('nonzero_counter_rejected',
          code == 3 and payload and payload.get('reason') == 'kernel_loss_counter_nonzero',
          payload)

    # E. --output must be a new file.
    existing = fixture('overwrite', meta=proved)
    (existing / 'out.json').write_text('{}')
    code, payload = run(module, argv(existing, require=True))
    check('refuses_to_overwrite_output',
          code == 3 and payload and payload.get('reason') == 'output_exists_refusing_overwrite',
          payload)

    # F. --windows is optional; when supplied it must lie inside the inner span.
    good_windows = dict(schema='wksim.perf_windows.v1', boot_id=base_meta['boot_id'],
                        owner_pid=base_meta['owner_pid'], owner_tid=base_meta['owner_tid'],
                        clock_id='CLOCK_MONOTONIC',
                        windows=[dict(id='w1', start_ns=1_000_000, end_ns=1_100_000)])
    directory = fixture('windows_ok', meta=proved)
    code, payload = run(module, argv(directory, require=True, windows=good_windows))
    report = json.loads((directory / 'out.json').read_text())
    check('windows_optional_and_intersected',
          code == 0 and report['windows'] and report['windows'][0]['id'] == 'w1', payload)

    outside_windows = dict(good_windows,
                           windows=[dict(id='w1', start_ns=900_000, end_ns=1_000_000)])
    directory = fixture('windows_outside', meta=proved)
    code, payload = run(module, argv(directory, require=True, windows=outside_windows))
    check('windows_outside_inner_rejected',
          code == 3 and payload and payload.get('reason') == 'windows_outside_capture_bounds',
          payload)

    receipt = dict(
        tool='codebuddy-perf-admission-review consumer_constraints_probe',
        mode='read-only pure Python; commit fixture read-only',
        consumer_sha256=hashlib.sha256(CONSUMER.read_bytes()).hexdigest(),
        fixture='ds-perf-stream-fixtures-20260913-01/fixtures/normal_two_pairs',
        cases=len(CASES), failures=sum(1 for row in CASES if not row['ok']), results=CASES,
    )
    (HERE / 'consumer_constraints.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(cases=receipt['cases'], failures=receipt['failures'])))
finally:
    shutil.rmtree(work, ignore_errors=True)

raise SystemExit(1 if any(not row['ok'] for row in CASES) else 0)
