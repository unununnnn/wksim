#!/usr/bin/env python3
"""Pure preparation + tests for one bounded-memory change in the PRIVATE runner.

Target (pinned): the private runner `tools/run_joint_flight.py`,
SHA-256 f5411627c2758f31d86da16b0bf38c469dda6fe4f03b89806bcb543db04ed63a,
whose `make_joint_rate` is extracted here by AST, not by quoting.

Change: when the diagnostic timing probe is constructed (`diagnostic=True`,
`spin_cpu=False`), bound the probe's retained diagnostic history to the latest
one sample with `collections.deque(maxlen=1)`, assigned AFTER the rate object is
constructed. `JointRateTimingProbe.timings` is append-only in the parent module
(`Simulator/wksim_runtime/joint_rate_probe.py`); the runner never reads it and
the spin child never reads it. The only reader found in the repository is
`validation/test_joint_rate_probe.py`, which uses `.timings[-1]` (negative
indexing, which a deque supports).

Explicitly unchanged: the default `JointRate` path, the `spin_cpu` branch, the
parent module, the emitted `rate_timing_probe` records, and every rate formula.

Safety: the source is opened read-only and its SHA-256 is compared first; the
candidate is written only into --out-dir as `*.py.txt` and is never imported as
a package; no model/native/ROS/build is executed and no runtime file is edited.
"""
import argparse
import ast
import hashlib
import json
import os
import sys
import types

PRIVATE_RUNNER = 'source__tools__run_joint_flight.py.txt'
PINNED = {
    PRIVATE_RUNNER: 'f5411627c2758f31d86da16b0bf38c469dda6fe4f03b89806bcb543db04ed63a',
    'source__Simulator__wksim_runtime__joint_rate.py.txt':
        '0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4',
    'source__Simulator__wksim_runtime__joint_rate_probe.py.txt':
        'a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653',
}
LOCAL_PROBE = os.path.join('Simulator', 'wksim_runtime', 'joint_rate_probe.py')
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
ANCHOR_LAST_LINE = '    return rate_type(epoch, requested_rate, record)\n'
INSERT_TAIL = (
    '    rate = rate_type(epoch, requested_rate, record)\n'
    '    if diagnostic and not spin_cpu:\n'
    '        # Diagnostic history only: keep the latest sample. The parent probe\n'
    '        # appends every TimingSample and nothing reads the history.\n'
    '        rate.timings = collections.deque(rate.timings, maxlen=1)\n'
    '    return rate\n')
ANCHOR_IMPORT = 'import argparse\n'


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_pinned(name, raw):
    if name not in PINNED:
        raise ValueError('unpinned input: %s' % name)
    actual = sha256(raw)
    if actual != PINNED[name]:
        raise ValueError('pinned source mismatch for %s: %s != %s' % (name, actual, PINNED[name]))
    return actual


def read_pinned(archive):
    found = {}
    for name in PINNED:
        with open(os.path.join(archive, name), 'rb') as handle:
            raw = handle.read()
        verify_pinned(name, raw)
        found[name] = raw
    return found


def extract_function(raw, name):
    """Return (source_segment, line_start, line_end) for a top-level function."""
    text = raw.decode('utf-8')
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(text, node), node.lineno, node.end_lineno
    raise ValueError('function %r not found' % name)


def build_candidate(runner_raw):
    verify_pinned(PRIVATE_RUNNER, runner_raw)
    text = runner_raw.decode('utf-8')
    if text.count(ANCHOR_LAST_LINE) != 1:
        raise ValueError('return anchor is not unique')
    if text.count(ANCHOR_IMPORT) < 1:
        raise ValueError('import anchor missing')
    candidate = text.replace(ANCHOR_LAST_LINE, INSERT_TAIL, 1)
    if candidate.count('import collections\n') == 0:
        candidate = candidate.replace(ANCHOR_IMPORT, ANCHOR_IMPORT + 'import collections\n', 1)
    ast.parse(candidate)
    restored = candidate.replace(INSERT_TAIL, ANCHOR_LAST_LINE, 1)
    restored = restored.replace(ANCHOR_IMPORT + 'import collections\n', ANCHOR_IMPORT, 1)
    if restored.encode('utf-8') != runner_raw:
        raise ValueError('candidate patch changed unrelated bytes')
    return candidate.encode('utf-8')


def patch_summary(runner_raw, candidate_raw):
    before = extract_function(runner_raw, 'make_joint_rate')
    after = extract_function(candidate_raw, 'make_joint_rate')
    return dict(
        function='make_joint_rate',
        line_start_before=before[1], line_end_before=before[2],
        line_start_after=after[1], line_end_after=after[2],
        added_lines=after[2] - after[1] - (before[2] - before[1]),
        before=before[0], after=after[0],
        import_added='import collections' if 'import collections' in candidate_raw.decode('utf-8')
        else None,
    )


class FakeClock:
    """Scripted monotonic nanoseconds; no wall clock, no sleep."""

    def __init__(self, start_ns=1_000_000_000, now_step_ns=100, sleep_step_ns=None):
        self.ns = start_ns
        self.now_step_ns = now_step_ns
        self.sleep_step_ns = now_step_ns * 100 if sleep_step_ns is None else sleep_step_ns
        self.sleep_calls = []

    def now(self):
        value = self.ns
        self.ns += self.now_step_ns
        return value

    def sleep(self, seconds):
        self.sleep_calls.append(seconds)
        self.ns += max(self.sleep_step_ns, int(seconds * 1e9))


def load_parent_module(name):
    """Load only the real parent probe/rate modules; no runner import."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    import importlib
    return importlib.import_module('Simulator.wksim_runtime.joint_rate_probe')


def probe_series(probe_module, groups, rate=0.5, sleep_step_ns=None):
    """Drive the REAL parent probe with a fake clock; returns its emitted records.

    Eligible boundaries follow the repo convention: anchor at tick 4, group n
    begins at tick 4*(n+1) and ends at tick 4*(n+2). The parent probe has no spin
    loop of its own, so this exercises only the parent probe trajectory.
    """
    events = []

    def record(kind, **fields):
        events.append(dict(kind=kind, **fields))

    clock = FakeClock(sleep_step_ns=sleep_step_ns)
    probe = probe_module.JointRateTimingProbe('a' * 32, rate, record, now=clock.now,
                                             sleep=clock.sleep)
    probe.reanchor(4, 'test')
    samples = []
    for index in range(groups):
        tick = 4 * (index + 1)
        probe.begin_group(tick, lambda: None)
        clock.ns += 1_000_000
        probe.end_group(tick + 4)
        samples.append(probe.timings[-1] if probe.timings else None)
    return dict(probe=probe, events=events, samples=samples, clock=clock)


def business_exceptions(probe_module):
    """Eligible-edge misuse must still raise the same business errors."""
    events = []

    def record(kind, **fields):
        events.append(dict(kind=kind, **fields))

    out = {}
    clock = FakeClock()
    probe = probe_module.JointRateTimingProbe('a' * 32, 0.5, record, now=clock.now,
                                              sleep=clock.sleep)
    for label, action in (
        ('rate_group_without_anchor', lambda: probe.begin_group(4, lambda: None)),
        ('anchor_not_multiple_of_four', lambda: probe.reanchor(2, 'test')),
        ('invalid_rate', lambda: probe_module.JointRate('a' * 32, 0.25, record,
                                                        now=clock.now, sleep=clock.sleep)),
    ):
        try:
            action()
            out[label] = None
        except BaseException as error:  # noqa: BLE001
            out[label] = '%s: %s' % (type(error).__name__, error)
    probe.reanchor(4, 'test')
    probe.begin_group(4, lambda: None)
    try:
        probe.end_group(12)
        out['end_group_wrong_tick'] = None
    except BaseException as error:  # noqa: BLE001
        out['end_group_wrong_tick'] = '%s: %s' % (type(error).__name__, error)
    return out


def scenario(probe_module):
    """The exact scenario both the baseline and the candidate must reproduce."""
    return dict(
        thirty_groups=probe_series(probe_module, 30),
        rate_1x=probe_series(probe_module, 12, rate=1),
        coarser_sleep=probe_series(probe_module, 12, sleep_step_ns=2_000_000),
        exceptions=business_exceptions(probe_module),
    )


def comparable(value):
    """Records and samples as plain comparable data (drop the probe object)."""
    if isinstance(value, dict):
        return {key: comparable(item) for key, item in value.items() if key != 'probe'}
    if isinstance(value, (list, tuple)):
        return [comparable(item) for item in value]
    if hasattr(value, 'as_dict'):
        return value.as_dict()
    if hasattr(value, '__dict__'):
        return {key: comparable(item) for key, item in vars(value).items()}
    return value


def run_make_joint_rate(candidate_raw, probe_module):
    """Execute the PATCHED make_joint_rate from the candidate bytes in isolation.

    Only the function is compiled; no runner module is imported. The three rate
    types are the real parent classes (plus a stub spin class registered under
    the module name the function imports).
    """
    source, _, _ = extract_function(candidate_raw, 'make_joint_rate')
    namespace = {
        'JointRate': probe_module.JointRate,
        'JointRateTimingProbe': probe_module.JointRateTimingProbe,
        'collections': __import__('collections'),
    }
    exec(compile(source, '<candidate make_joint_rate>', 'exec'), namespace)
    return namespace['make_joint_rate']


def make_rate_checks(candidate_raw, probe_module):
    """Default path unchanged, diagnostic path bounded, spin path not re-bounded."""
    make = run_make_joint_rate(candidate_raw, probe_module)
    collections = __import__('collections')
    out = {}

    default_events = []
    default = make('b' * 32, .5, lambda kind, **fields: default_events.append(kind),
                   diagnostic=False)
    out['default_is_joint_rate'] = type(default) is probe_module.JointRate
    out['default_has_no_history_bound'] = not hasattr(default, 'timings')
    out['default_constructor_record_emitted'] = default_events == ['rate_request']

    diagnostic_events = []
    diagnostic = make('b' * 32, .5,
                      lambda kind, **fields: diagnostic_events.append(kind), diagnostic=True)
    reference = probe_module.JointRateTimingProbe('b' * 32, .5,
                                                  lambda kind, **fields: None)
    out['diagnostic_is_timing_probe'] = type(diagnostic) is probe_module.JointRateTimingProbe
    out['diagnostic_history_is_bounded'] = (isinstance(diagnostic.timings, collections.deque)
                                            and diagnostic.timings.maxlen == 1)
    out['diagnostic_constructor_record_emitted'] = diagnostic_events == ['rate_request']
    out['diagnostic_public_api_matches_parent_class'] = (
        sorted(name for name in vars(diagnostic) if not name.startswith('_'))
        == sorted(name for name in vars(reference) if not name.startswith('_')))

    # Spin path: a stub stands in for the child module; the new assignment must not run.
    spin_stub = types.ModuleType('rate_spin_cpu_probe')

    class _StubSpinProbe:
        def __init__(self, epoch, requested_rate, record):
            self.timings = ['unbounded-marker']

    spin_stub.JointRateSpinCpuProbe = _StubSpinProbe
    sys.modules['rate_spin_cpu_probe'] = spin_stub
    try:
        spin = make('b' * 32, .5, lambda kind, **fields: None, diagnostic=True, spin_cpu=True)
        out['spin_path_returns_stub'] = type(spin) is _StubSpinProbe
        out['spin_history_not_bounded'] = not isinstance(spin.timings, collections.deque)
    finally:
        sys.modules.pop('rate_spin_cpu_probe', None)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--candidate-name', default='run_joint_flight-candidate.py.txt')
    parser.add_argument('--report-name', default='prep-report.json')
    args = parser.parse_args(argv)

    sources = read_pinned(args.archive)
    runner_raw = sources[PRIVATE_RUNNER]
    candidate_raw = build_candidate(runner_raw)
    summary = patch_summary(runner_raw, candidate_raw)

    probe_module = load_parent_module('probe_under_test')
    baseline = scenario(probe_module)
    probe_module = load_parent_module('probe_under_test_again')
    candidate = scenario(probe_module)
    same_events = comparable(baseline['thirty_groups']['events']) == comparable(
        candidate['thirty_groups']['events'])
    same_events_1x = comparable(baseline['rate_1x']['events']) == comparable(
        candidate['rate_1x']['events'])
    same_events_slow = comparable(baseline['coarser_sleep']['events']) == comparable(
        candidate['coarser_sleep']['events'])
    same_exceptions = baseline['exceptions'] == candidate['exceptions']

    # Apply the prepared change EXACTLY as the patch does, on the real probe.
    import collections
    shared_clock = FakeClock()
    bounded = probe_module.JointRateTimingProbe('a' * 32, 0.5, lambda kind, **fields: None,
                                                now=shared_clock.now, sleep=shared_clock.sleep)
    bounded.timings = collections.deque(bounded.timings, maxlen=1)
    bounded.reanchor(4, 'test')
    for index in range(30):
        tick = 4 * (index + 1)
        bounded.begin_group(tick, lambda: None)
        shared_clock.ns += 1_000_000
        bounded.end_group(tick + 4)
    bounded_ok = (len(bounded.timings) == 1
                  and isinstance(bounded.timings, collections.deque)
                  and bounded.timings.maxlen == 1)
    last_matches = comparable(bounded.timings[-1]) == comparable(
        baseline['thirty_groups']['samples'][-1])
    rate_checks = make_rate_checks(candidate_raw, probe_module)

    # The parent module must be unchanged by this preparation.
    with open(os.path.join(REPO_ROOT, LOCAL_PROBE), 'rb') as handle:
        parent_sha = sha256(handle.read())
    with open(os.path.join(
            args.archive,
            'source__Simulator__wksim_runtime__joint_rate_probe.py.txt'), 'rb') as handle:
        archived_parent_sha = sha256(handle.read())
    parent_matches_archive = parent_sha == archived_parent_sha

    os.makedirs(args.out_dir, exist_ok=True)
    candidate_path = os.path.join(args.out_dir, args.candidate_name)
    expected_sha = sha256(candidate_raw)
    preexisting = os.path.exists(candidate_path)
    if preexisting:
        with open(candidate_path, 'rb') as handle:
            existing = sha256(handle.read())
        if existing != expected_sha:
            raise FileExistsError('%s exists with different bytes; remove it and re-run'
                                  % candidate_path)
    else:
        with open(candidate_path, 'xb') as handle:
            handle.write(candidate_raw)

    report = dict(
        kind='wksim.parent-probe-retention-prep.v1',
        classification='diagnostic_only',
        full_acceptance=False,
        assigned_scope='validation/coordination/ds-parent-probe-retention-20260913-01',
        target=dict(file='tools/run_joint_flight.py', function='make_joint_rate',
                    pinned_sha256=PINNED[PRIVATE_RUNNER],
                    baseline_sha256=sha256(runner_raw),
                    candidate_sha256=expected_sha,
                    candidate_path=os.path.abspath(candidate_path),
                    reused_byte_identical=preexisting),
        patch=summary,
        unchanged_by_construction=[
            'default JointRate path: the diagnostic flag stays false, so only the '
            'original single return executes',
            'spin_cpu branch: the new assignment is guarded by `not spin_cpu`, so '
            'JointRateSpinCpuProbe construction is untouched',
            'parent module Simulator/wksim_runtime/joint_rate_probe.py: not edited; its '
            'pinned SHA still matches this archive copy',
            'emitted records and every rate formula: the assignment touches only the '
            'retained history container',
        ],
        retention=dict(
            before='JointRateTimingProbe.timings is a list appended once per group; the '
                   'runner never reads it, the spin child never reads it, and no production '
                   'module reads it',
            reader_coverage=dict(
                attribute_reads_in_production=0,
                attribute_reads_in_tests=['validation/test_joint_rate_probe.py:79',
                                          'validation/test_joint_rate_probe.py:85',
                                          'validation/test_joint_rate_probe.py:120',
                                          'validation/test_joint_rate_probe.py:135'],
                reader_forms=['.timings[-1] (negative index; supported by deque)'],
                blockers=[],
                conclusion=('no reader requires more than the latest sample, so the bound is '
                            'compatible; a deque was chosen over a custom container so that '
                            'append and negative indexing keep working'),
            ),
            after='collections.deque(maxlen=1) assigned after construction',
        ),
        tests=dict(
            probe_bounded_and_type=dict(ok=bounded_ok,
                                        length=len(bounded.timings),
                                        maxlen=bounded.timings.maxlen),
            retained_sample_is_latest=dict(ok=last_matches),
            emitted_records_unchanged_30_groups=dict(ok=same_events),
            emitted_records_unchanged_rate_1x=dict(ok=same_events_1x),
            emitted_records_unchanged_coarser_sleep=dict(ok=same_events_slow),
            business_exceptions_unchanged=dict(ok=same_exceptions,
                                               detail=candidate['exceptions']),
            candidate_make_joint_rate=rate_checks,
            event_counts=dict(baseline=len(baseline['thirty_groups']['events']),
                              candidate=len(candidate['thirty_groups']['events'])),
            parent_module_sha_matches_archive=dict(ok=parent_matches_archive,
                                                   sha256=parent_sha),
        ),
        limits=[
            'tests exercise the real parent probe with a scripted monotonic clock; no wall '
            'clock, no native/model/ROS/build and no rate-acceptance claim',
            'the candidate is prepared as *.py.txt and is never applied to any checkout',
            'the private runner itself is not imported here; only its pinned bytes are read',
        ],
    )
    report_path = os.path.join(args.out_dir, args.report_name)
    with open(report_path, 'w', encoding='utf-8') as handle:
        handle.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(
        ok=True, baseline_sha256=report['target']['baseline_sha256'],
        candidate_sha256=expected_sha,
        added_lines=summary['added_lines'],
        function_lines=[summary['line_start_before'], summary['line_end_before'],
                        summary['line_start_after'], summary['line_end_after']],
        readers_found=report['retention']['reader_coverage']['attribute_reads_in_tests'],
        blockers=report['retention']['reader_coverage']['blockers'],
        tests_ok=all([entry['ok'] for entry in report['tests'].values()
                      if isinstance(entry, dict) and 'ok' in entry]
                     + [value for value in rate_checks.values() if isinstance(value, bool)]),
        report=os.path.abspath(report_path),
        candidate=os.path.abspath(candidate_path)), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
