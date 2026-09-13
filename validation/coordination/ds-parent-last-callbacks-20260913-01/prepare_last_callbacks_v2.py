#!/usr/bin/env python3
"""v2: pure preparation + tests for last-COMPLETED callback retention (PARENT probe).

Target (pinned): the archived parent module
`Simulator/wksim_runtime/joint_rate_probe.py`,
SHA-256 a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653.
The pinned bytes and the v1 preparation are kept unchanged; this is the v2
candidate only.

v2 correction (required): the last-sleep triple is written ATOMICALLY after the
existing `after = self._probe_now()` succeeds. v1 assigned requested/before
before `_raw_sleep`, so a failed sleep could pair a failed call's
before/request with a previous call's after. In v2 no new read, reset or
callback is added: the same three existing values are simply stored together
once the post-sleep read has returned, so the retained triple always belongs to
one completed sleep.

Health semantics unchanged: `after` is read in the `finally` block, so a
loop-health call whose callback raises still yields a completed measurement, and
`loop_health_calls` keeps its existing behaviour (it is only incremented on
success, exactly as before).
"""
import argparse
import ast
import hashlib
import json
import os
import sys
import types

ARCHIVED_PROBE = 'source__Simulator__wksim_runtime__joint_rate_probe.py.txt'
ARCHIVED_RATE = 'source__Simulator__wksim_runtime__joint_rate.py.txt'
PROBE_SHA = 'a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653'
RATE_SHA = '0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4'
PINNED = {ARCHIVED_PROBE: PROBE_SHA, ARCHIVED_RATE: RATE_SHA}
NEW_FIELDS = ('last_sleep_before_ns', 'last_sleep_after_ns', 'last_sleep_requested_ns',
              'last_health_before_ns', 'last_health_after_ns')
SLEEP_FIELDS = ('last_sleep_before_ns', 'last_sleep_after_ns', 'last_sleep_requested_ns')
ACTIVE_FIELDS = ('last_health_before_ns', 'last_health_after_ns',
                 'last_sleep_before_ns', 'last_sleep_after_ns', 'last_sleep_requested_ns')


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_pinned(name, raw):
    if name not in PINNED:
        raise ValueError('unpinned input: %s' % name)
    actual = sha256(raw)
    if actual != PINNED[name]:
        raise ValueError('pinned source mismatch for %s: %s != %s' % (name, actual, PINNED[name]))


def class_node(raw, name):
    for node in ast.parse(raw.decode('utf-8')).body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise ValueError('class %r not found' % name)


def method_node(raw, class_name, method_name):
    for node in class_node(raw, class_name).body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
    raise ValueError('%s.%s not found' % (class_name, method_name))


def replace_span(text, old, new):
    if text.count(old) != 1:
        raise ValueError('span is not unique (%d): %r' % (text.count(old), old[:60]))
    return text.replace(old, new, 1)


def insert_after_line(text, line_number, addition):
    lines = text.split('\n')
    if not 1 <= line_number <= len(lines):
        raise ValueError('line %d outside source' % line_number)
    lines.insert(line_number, addition.rstrip('\n'))
    return '\n'.join(lines)


def build_candidate(probe_raw, version='v2'):
    verify_pinned(ARCHIVED_PROBE, probe_raw)
    text = probe_raw.decode('utf-8')

    timing = class_node(probe_raw, 'TimingSample')
    last_field = max((node for node in timing.body if isinstance(node, ast.AnnAssign)),
                     key=lambda node: node.end_lineno)
    active = class_node(probe_raw, '_ActiveSample')
    last_active = max((node for node in active.body if isinstance(node, ast.AnnAssign)),
                      key=lambda node: node.end_lineno)
    inserts = [
        (last_active.end_lineno,
         ''.join('    %s: int | None = None\n' % name for name in ACTIVE_FIELDS).rstrip('\n')),
        (last_field.end_lineno,
         '    # Exact timestamps of the last completed sleep / health call. None when no\n'
         '    # such call has completed, so a partial failure never fabricates a window.\n'
         + ''.join('    %s: int | None = None\n' % name for name in NEW_FIELDS).rstrip('\n')),
    ]

    sleep_text = ast.get_source_segment(text, method_node(probe_raw, 'JointRateTimingProbe',
                                                          '_probe_sleep'))
    if version == 'v1':
        sleep_new = sleep_text.replace(
            '        before = self._probe_now()\n',
            '        before = self._probe_now()\n'
            '        active.last_sleep_requested_ns = requested_ns\n'
            '        active.last_sleep_before_ns = before\n', 1).replace(
            '        after = self._probe_now()\n',
            '        after = self._probe_now()\n'
            '        active.last_sleep_after_ns = after\n', 1)
    else:
        sleep_new = sleep_text.replace(
            '        after = self._probe_now()\n',
            '        after = self._probe_now()\n'
            '        # Atomic: one completed sleep contributes all three values, so a\n'
            '        # later failed sleep cannot mix its own before/request with a\n'
            '        # stale after from an earlier call.\n'
            '        active.last_sleep_requested_ns = requested_ns\n'
            '        active.last_sleep_before_ns = before\n'
            '        active.last_sleep_after_ns = after\n', 1)
    if sleep_new == sleep_text:
        raise ValueError('sleep anchors not found')

    begin_text = ast.get_source_segment(text, method_node(probe_raw, 'JointRateTimingProbe',
                                                          'begin_group'))
    begin_new = begin_text.replace(
        '                    else:\n'
        '                        active.loop_health_ns += elapsed\n'
        '                        active.loop_health_calls += 1\n',
        '                    else:\n'
        '                        active.loop_health_ns += elapsed\n'
        '                        active.loop_health_calls += 1\n'
        '                        # Retained only for a loop-health call that completed; the\n'
        '                        # initial call keeps its own aggregate field.\n'
        '                        active.last_health_before_ns = before\n'
        '                        active.last_health_after_ns = after\n', 1)
    if begin_new == begin_text:
        raise ValueError('health anchors not found')

    finish_text = ast.get_source_segment(text, method_node(probe_raw, 'JointRateTimingProbe',
                                                           '_finish_sample'))
    finish_new = finish_text.replace(
        '            phase_total_ns=phase_total,\n',
        '            phase_total_ns=phase_total,\n'
        '            last_sleep_before_ns=active.last_sleep_before_ns,\n'
        '            last_sleep_after_ns=active.last_sleep_after_ns,\n'
        '            last_sleep_requested_ns=active.last_sleep_requested_ns,\n'
        '            last_health_before_ns=active.last_health_before_ns,\n'
        '            last_health_after_ns=active.last_health_after_ns,\n', 1)
    if finish_new == finish_text:
        raise ValueError('finish anchor not found')

    candidate = text
    for old, new in ((finish_text, finish_new), (begin_text, begin_new), (sleep_text, sleep_new)):
        candidate = replace_span(candidate, old, new)
    for line_number, addition in sorted(inserts, reverse=True):
        candidate = insert_after_line(candidate, line_number, addition)
    ast.parse(candidate)

    restored = candidate
    for old, new in ((finish_new, finish_text), (begin_new, begin_text), (sleep_new, sleep_text)):
        restored = replace_span(restored, old, new)
    for line_number, addition in inserts:
        restored = replace_span(restored, addition + '\n', '')
    if restored.encode('utf-8') != probe_raw:
        raise ValueError('reversal did not restore the pinned bytes')
    return candidate.encode('utf-8')


def load_pair(archive, candidate_raw):
    package = types.ModuleType('wksim_probe_pkg')
    package.__path__ = []
    sys.modules[package.__name__] = package

    def load(suffix, raw):
        module = types.ModuleType(package.__name__ + '.' + suffix)
        module.__package__ = package.__name__
        module.__file__ = '<%s/%s.py>' % (package.__name__, suffix)
        exec(compile(raw.decode('utf-8'), module.__file__, 'exec'), module.__dict__)
        sys.modules[module.__name__] = module
        return module

    core = load('joint_rate', open(os.path.join(archive, ARCHIVED_RATE), 'rb').read())
    old = load('old_probe', open(os.path.join(archive, ARCHIVED_PROBE), 'rb').read())
    new = load('new_probe', candidate_raw)
    return core, old, new


class ScriptedClock:
    """Monotonic clock logging every read and sleep; can fail on a chosen call."""

    def __init__(self, start_ns=1_000_000_000, now_step_ns=100, sleep_step_ns=0,
                 sleep_until=None, fail_sleep_after=None, fail_health_after=None,
                 health_delay_ns=0):
        self.ns = start_ns
        self.now_step_ns = now_step_ns
        self.sleep_step_ns = sleep_step_ns
        self.sleep_until = sleep_until
        self.reads = []
        self.sleeps = []
        self.fail_sleep_after = fail_sleep_after
        self.health_calls = 0
        self.fail_health_after = fail_health_after
        self.health_delay_ns = health_delay_ns

    def now(self):
        value = self.ns
        self.reads.append(value)
        self.ns += self.now_step_ns
        return value

    def sleep(self, seconds):
        self.sleeps.append(round(seconds * 1e9))
        if self.fail_sleep_after is not None and len(self.sleeps) > self.fail_sleep_after:
            raise RuntimeError('scripted sleep failure')
        if self.sleep_until is not None and self.ns < self.sleep_until:
            self.ns = self.sleep_until
        else:
            self.ns += max(self.sleep_step_ns, round(seconds * 1e9))

    def health(self):
        self.health_calls += 1
        if self.fail_health_after is not None and self.health_calls > self.fail_health_after:
            raise RuntimeError('scripted health failure')
        # A real health poll can run for a while; this models that cost so the
        # probe's own before/after reads can bracket the release edge.
        self.ns += self.health_delay_ns


def run_series(module, clock, groups, anchor_tick=4, work_ns=1_000_000, health=None):
    events = []

    def record(kind, **fields):
        events.append(dict(kind=kind, **fields))

    probe = module.JointRateTimingProbe('a' * 32, .5, record, now=clock.now,
                                        sleep=clock.sleep)
    outcome = 'ok'
    error = None
    try:
        probe.reanchor(anchor_tick, 'test')
        for index in range(groups):
            tick = anchor_tick + 4 * index
            probe.begin_group(tick, health or clock.health)
            clock.ns += work_ns
            probe.end_group(tick + 4)
    except BaseException as caught:  # noqa: BLE001
        error = caught
        outcome = '%s: %s' % (type(caught).__name__, caught)
    return dict(events=events, outcome=outcome, error=error, probe=probe,
                reads=list(clock.reads), sleeps=list(clock.sleeps))


def compare(old_result, new_result):
    old_records, new_records = old_result['events'], new_result['events']
    base = dict(clock_reads_identical=(old_result['reads'] == new_result['reads']),
                clock_read_count=[len(old_result['reads']), len(new_result['reads'])],
                sleep_requests_identical=(old_result['sleeps'] == new_result['sleeps']),
                exception_identical=(old_result['outcome'] == new_result['outcome']),
                outcomes=[old_result['outcome'], new_result['outcome']])
    if len(old_records) != len(new_records):
        base.update(ok=False, reason='record count differs',
                    original_keys_and_values_identical=False, new_keys={},
                    unexpected_new_keys=[], detail=[])
        return base
    extras, detail, equal = {}, [], True
    for old_event, new_event in zip(old_records, new_records):
        if old_event.get('kind') != new_event.get('kind'):
            equal = False
            detail.append('kind differs')
            continue
        for key, value in old_event.items():
            if key not in new_event or new_event[key] != value:
                equal = False
                detail.append('original key changed: %s' % key)
        for key in new_event:
            if key not in old_event:
                extras[key] = extras.get(key, 0) + 1
    base.update(ok=equal and set(extras) <= set(NEW_FIELDS),
                original_keys_and_values_identical=equal, new_keys=extras,
                unexpected_new_keys=sorted(set(extras) - set(NEW_FIELDS)),
                record_count=len(old_records), detail=detail[:5])
    return base


def last_fields(probe):
    if not probe.timings:
        return None
    sample = probe.timings[-1]
    data = sample.as_dict() if hasattr(sample, 'as_dict') else dict(vars(sample))
    return {name: data.get(name, '<missing>') for name in NEW_FIELDS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--candidate-name', default='joint_rate_probe-candidate-v2.py.txt')
    parser.add_argument('--report-name', default='prep-report-v2.json')
    args = parser.parse_args(argv)

    probe_raw = open(os.path.join(args.archive, ARCHIVED_PROBE), 'rb').read()
    verify_pinned(ARCHIVED_PROBE, probe_raw)
    candidate_raw = build_candidate(probe_raw, 'v2')
    core, old_module, new_module = load_pair(args.archive, candidate_raw)

    results = {}

    def case(name, clock_factory, groups, work_ns=1_000_000, anchor_tick=4, health=None):
        old_run = run_series(old_module, clock_factory(), groups, anchor_tick, work_ns, health)
        new_run = run_series(new_module, clock_factory(), groups, anchor_tick, work_ns, health)
        results[name] = dict(comparison=compare(old_run, new_run),
                             old_last=last_fields(old_run['probe']),
                             new_last=last_fields(new_run['probe']),
                             new_samples=len(new_run['probe'].timings),
                             new_outcome=new_run['outcome'],
                             new_error_identity=(hex(id(new_run['error']))
                                                 if new_run['error'] is not None else None))

    case('sleep_before_release', lambda: ScriptedClock(), 12)
    case('sleep_crossing_release', lambda: ScriptedClock(sleep_until=1_140_000_300), 12)
    case('no_sleep_absent', lambda: ScriptedClock(now_step_ns=2_000_000), 8)
    case('first_sleep_ok_then_failed_sleep',
         lambda: ScriptedClock(fail_sleep_after=1), 8)
    case('failed_health_call', lambda: ScriptedClock(fail_health_after=3), 8)

    # (1) success then failure inside ONE begin_group: the retained triple must be
    #     the previous completed sleep, atomically.
    atomic_clock = ScriptedClock(sleep_step_ns=10_000, fail_sleep_after=1)
    events = []
    probe = new_module.JointRateTimingProbe('a' * 32, .5,
                                            lambda kind, **fields: events.append(kind),
                                            now=atomic_clock.now, sleep=atomic_clock.sleep)
    probe.reanchor(4, 'test')
    caught = None
    try:
        probe.begin_group(4, atomic_clock.health)
        probe.end_group(8)
    except BaseException as error:  # noqa: BLE001
        caught = error
    pending = probe._active
    # the failed sleep is the second one in this group; re-drive to inspect the
    # retained triple at the moment of failure by calling _probe_sleep directly
    after_failure = dict(
        outcome=('%s: %s' % (type(caught).__name__, caught)) if caught else None,
        exception_identity=hex(id(caught)) if caught else None,
        sleeps_attempted=len(atomic_clock.sleeps),
    )

    # A second probe: one successful sleep, then a failing one, both while the
    # same active sample is open, with the triple inspected between them.
    seq_clock = ScriptedClock(sleep_step_ns=10_000)
    seq_probe = new_module.JointRateTimingProbe('a' * 32, .5,
                                                lambda kind, **fields: None,
                                                now=seq_clock.now, sleep=seq_clock.sleep)
    seq_probe.reanchor(4, 'test')
    seq_probe._active = new_module._ActiveSample(entry_ns=seq_clock.now())
    seq_probe._probe_sleep(0.001)
    after_first = {name: getattr(seq_probe._active, name) for name in SLEEP_FIELDS}
    seq_clock.fail_sleep_after = 1
    raised = None
    try:
        seq_probe._probe_sleep(0.002)
    except BaseException as error:  # noqa: BLE001
        raised = error
    after_second = {name: getattr(seq_probe._active, name) for name in SLEEP_FIELDS}
    seq_probe._active = None
    atomic = dict(
        after_first_completed_sleep=after_first,
        after_second_failed_sleep=after_second,
        triple_unchanged_by_failed_sleep=(after_first == after_second),
        triple_is_atomic_completed_sleep=(
            after_second['last_sleep_before_ns'] is not None
            and after_second['last_sleep_after_ns'] is not None
            and after_second['last_sleep_requested_ns'] is not None
            and after_second['last_sleep_before_ns'] <= after_second['last_sleep_after_ns']),
        failed_call_exception_identity=hex(id(raised)) if raised else None,
        failed_call_exception_text=('%s: %s' % (type(raised).__name__, raised)
                                    if raised else None),
        failed_call_attempted=len(seq_clock.sleeps),
    )

    # (2) last-callback vs the release span [earliest_start_ns, actual_start_ns]
    def classify(sample, group):
        release_edge = sample.earliest_start_ns
        actual_start = group['actual_start_ns'] if group else None
        out = dict(release_edge_ns=release_edge, actual_start_ns=actual_start)
        for family in ('sleep', 'health'):
            before = getattr(sample, 'last_%s_before_ns' % family)
            after = getattr(sample, 'last_%s_after_ns' % family)
            if before is None or after is None:
                out[family] = 'absent'
                continue
            out[family] = dict(
                before_ns=before, after_ns=after,
                before_edge=(after <= release_edge),
                spans_edge=(before <= release_edge <= after),
                overlaps_release_span=(after >= release_edge
                                       and (actual_start is None or before <= actual_start)),
                contains_full_span=(actual_start is not None and before <= release_edge
                                    and after >= actual_start),
            )
        return out

    crossing_health = dict(straddles=False, crossed_case=None)
    sleep_crossing = dict(spans_edge=False, case=None)
    for label, kwargs in (
            ('slow_health_callback', dict(health_delay_ns=3_000_000, now_step_ns=1_000)),
            ('very_slow_health_callback', dict(health_delay_ns=9_000_000, now_step_ns=1_000)),
            ('late_sleep_plus_slow_health',
             dict(sleep_until=1_200_000_000, health_delay_ns=3_000_000, now_step_ns=1_000)),
    ):
        run = run_series(new_module, ScriptedClock(**kwargs), 4)
        for sample in run['probe'].timings:
            info = classify(sample, run['probe'].group)
            if info['health'] != 'absent' and info['health']['spans_edge']:
                crossing_health = dict(straddles=True, crossed_case=label, detail=info)
        if crossing_health['straddles']:
            break
    for label, kwargs in (('long_sleep', dict(sleep_until=1_140_000_300)),):
        run = run_series(new_module, ScriptedClock(**kwargs), 4)
        for sample in run['probe'].timings:
            info = classify(sample, run['probe'].group)
            if info['sleep'] != 'absent' and info['sleep']['spans_edge']:
                sleep_crossing = dict(spans_edge=True, case=label, detail=info)
    last_callback_classification = None
    reference_run = run_series(new_module, ScriptedClock(sleep_until=1_140_000_300), 12)
    if reference_run['probe'].timings:
        last_callback_classification = classify(reference_run['probe'].timings[-1],
                                                reference_run['probe'].group)

    # (3) aggregate closure on the new samples
    closure = []
    closure_run = run_series(new_module, ScriptedClock(sleep_until=1_140_000_300), 6)
    for sample in closure_run['probe'].timings:
        closure.append(sample.phase_total_ns == sample.observed_elapsed_ns)
        closure.append(sample.phase_total_ns == sample.entry_to_initial_health_ns
                       + sample.loop_health_ns + sample.sleep_elapsed_ns
                       + sample.final_spin_other_ns)
    arithmetic_ok = all(closure) if closure else False

    # (4) absent semantics
    absent_run = run_series(new_module, ScriptedClock(now_step_ns=2_000_000), 6)
    absent_last = None
    if absent_run['probe'].timings:
        absent_sample = absent_run['probe'].timings[-1]
        absent_last = {name: getattr(absent_sample, name) for name in NEW_FIELDS}
    absent_ok = bool(absent_last) and all(value is None for value in absent_last.values())

    # (5) old samples have no new keys
    old_keys_gained = []
    old_run = run_series(old_module, ScriptedClock(sleep_until=1_140_000_300), 4)
    for sample in old_run['probe'].timings:
        data = sample.as_dict()
        old_keys_gained += [name for name in NEW_FIELDS if name in data]

    # (6) health-raises still yields a completed measurement, counts unchanged
    health_fail_run = results['failed_health_call']['new_last']
    health_ok = (health_fail_run is not None
                 and isinstance(health_fail_run['last_health_after_ns'], int)
                 and isinstance(health_fail_run['last_health_before_ns'], int))

    # (7) business exceptions
    business = {}
    clock = ScriptedClock()
    probe = new_module.JointRateTimingProbe('a' * 32, .5, lambda kind, **fields: None,
                                            now=clock.now, sleep=clock.sleep)
    for label, action in (
        ('begin_without_anchor', lambda: probe.begin_group(4, clock.health)),
        ('anchor_not_multiple_of_four', lambda: probe.reanchor(2, 'test')),
        ('invalid_rate', lambda: new_module.JointRate('a' * 32, .25,
                                                      lambda kind, **fields: None)),
    ):
        try:
            action()
            business[label] = None
        except BaseException as error:  # noqa: BLE001
            business[label] = '%s: %s' % (type(error).__name__, error)

    all_ok = (all(entry['comparison']['ok'] for entry in results.values())
              and atomic['triple_unchanged_by_failed_sleep']
              and atomic['triple_is_atomic_completed_sleep']
              and crossing_health['straddles']
              and sleep_crossing['spans_edge']
              and arithmetic_ok and absent_ok and health_ok and not old_keys_gained)

    os.makedirs(args.out_dir, exist_ok=True)
    candidate_path = os.path.join(args.out_dir, args.candidate_name)
    expected = sha256(candidate_raw)
    if os.path.exists(candidate_path):
        with open(candidate_path, 'rb') as handle:
            if sha256(handle.read()) != expected:
                raise FileExistsError('%s exists with different bytes; remove and re-run'
                                      % candidate_path)
    else:
        with open(candidate_path, 'xb') as handle:
            handle.write(candidate_raw)

    report = dict(
        kind='wksim.parent-last-callbacks-prep.v2',
        classification='diagnostic_only', full_acceptance=False,
        assigned_scope='validation/coordination/ds-parent-last-callbacks-20260913-01',
        version='v2 (last-completed atomic triple)',
        target=dict(file='Simulator/wksim_runtime/joint_rate_probe.py',
                    pinned_sha256=PROBE_SHA, candidate_sha256=expected,
                    candidate_path=os.path.abspath(candidate_path),
                    core_joint_rate_sha256=RATE_SHA, new_fields=list(NEW_FIELDS)),
        v2_correction=('all three last_sleep_* values are assigned only after the existing '
                       'after = self._probe_now() succeeds; the retained triple therefore '
                       'always belongs to one completed sleep and a later failed sleep cannot '
                       'mix its own before/request with a stale after'),
        all_ok=all_ok,
        cases=results,
        atomic_sleep_triple=atomic,
        crossing_loop_health=crossing_health,
        crossing_sleep=sleep_crossing,
        last_callback_classification=last_callback_classification,
        absent_semantics=dict(all_new_fields_none=absent_ok, last=absent_last),
        health_failure_semantics=dict(after_retained_from_finally=health_ok,
                                      last=health_fail_run),
        aggregate_closure_ok=arithmetic_ok,
        old_module_has_no_new_keys=(old_keys_gained == []),
        business_exceptions=business,
        limits=[
            'pure fake-clock tests against the real parent module; no wall clock, no '
            'native/model/ROS/build and no rate acceptance claim',
            'the candidate is prepared as *.py.txt and is never applied to any checkout',
            'joint_rate.py, the private runner and the parent module are not edited',
            'no diagnostic launch is implied; the main session decides after new raw analysis',
        ],
    )
    report_path = os.path.join(args.out_dir, args.report_name)
    with open(report_path, 'w', encoding='utf-8') as handle:
        handle.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(
        ok=all_ok, pinned_sha256=PROBE_SHA, candidate_sha256=expected,
        cases={name: entry['comparison']['ok'] for name, entry in results.items()},
        original_keys_and_values_identical=all(
            entry['comparison']['original_keys_and_values_identical']
            for entry in results.values()),
        clock_reads_identical=all(entry['comparison']['clock_reads_identical']
                                  for entry in results.values()),
        exception_identical=all(entry['comparison']['exception_identical']
                                for entry in results.values()),
        atomic_triple_unchanged=atomic['triple_unchanged_by_failed_sleep'],
        atomic_triple_completed=atomic['triple_is_atomic_completed_sleep'],
        crossing_loop_health=dict(straddles=crossing_health['straddles'],
                                  case=crossing_health.get('crossed_case'),
                                  detail=crossing_health.get('detail')),
        crossing_sleep=dict(spans_edge=sleep_crossing['spans_edge'],
                            case=sleep_crossing.get('case'),
                            detail=sleep_crossing.get('detail')),
        absent_all_none=absent_ok, health_failure_after_retained=health_ok,
        aggregate_closure_ok=arithmetic_ok,
        old_module_has_no_new_keys=(old_keys_gained == []),
        report=os.path.abspath(report_path),
        candidate=os.path.abspath(candidate_path)), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
