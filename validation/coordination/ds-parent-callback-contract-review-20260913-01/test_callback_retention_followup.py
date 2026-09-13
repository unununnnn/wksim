"""Independent follow-up: F2 correction, v1 defect proof, v2 fix verification.

Owner: validation/coordination/ds-parent-callback-contract-review-20260913-01 (only
directory written). Pure offline Python; the reviewed modules and B's directory are read
only. No native, model, ROS, build or MATLAB.

Three modules are loaded from their actual bytes under their own package name:

  old = Simulator/wksim_runtime/joint_rate_probe.py
  v1  = validation/coordination/ds-parent-last-callbacks-20260913-01/
        joint_rate_probe-candidate-v2.py.txt   (predecessor, defect)
  v2  = same directory, joint_rate_probe-candidate-v2.py.txt

Parts
-----
1. F2 CROSSING. A clock that advances 100 ns per read and whose sleep advances only the
   requested duration reaches the parent's loop-health branch, because the parent's sleep
   is capped at 2 ms while the period is 8 ms. The harness verifies that a loop-health
   callback actually runs and that its interval crosses the release edge
   (`earliest_start_ns` lies between the callback's retained before/after).
2. V1 DEFECT. One begin attempt whose first sleep completes and whose second sleep fails
   yields a before from the failed call with an after from the completed one, so
   `last_sleep_before_ns > last_sleep_after_ns` (a mixed/reversed pair).
3. V2 FIX. The same attempt against the atomic writer leaves all three retained sleep
   values absent or mutually consistent, and the raised exception is the SAME object the
   scripted sleep raised (identity, not just type and message).

Run:
    python -B validation/coordination/ds-parent-callback-contract-review-20260913-01/test_callback_retention_followup.py
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / 'evidence'
sys.path.insert(0, str(ROOT))

OLD_PATH = ROOT / 'Simulator' / 'wksim_runtime' / 'joint_rate_probe.py'
BPREP = ROOT / 'validation/coordination/ds-parent-last-callbacks-20260913-01'
V1_CANDIDATES = (BPREP / 'rejected-v1' / 'joint_rate_probe-candidate.py.txt',
                 BPREP / 'joint_rate_probe-candidate.py.txt')
V1_PATH = next((path for path in V1_CANDIDATES if path.is_file()), V1_CANDIDATES[0])
V2_PATH = BPREP / 'joint_rate_probe-candidate-v2.py.txt'
OLD_SHA_EXPECTED = 'a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653'
V1_SHA_EXPECTED = 'e1dd28558e36f40ea9ec87cddcbe517339f6196198dec0a28b164fecafe75a70'
V2_SHA_EXPECTED = '7855409d1f28e955dc9fcafc2d90f94e13ef5ab35eb1a0d239b61a4c919a4be1'
ADDED_KEYS = ('last_sleep_before_ns', 'last_sleep_after_ns', 'last_sleep_requested_ns',
              'last_health_before_ns', 'last_health_after_ns')
RATE = 0.5
TICK = 4


class FakeClock:
    """Monotonic clock advancing 100 ns per read; sleep advances the requested duration.

    `sleep_failures` lists 1-based sleep-call indices that must raise `sleep_error`
    WITHOUT advancing the clock, so the after read never runs for those calls.
    """

    def __init__(self, start_ns, step_ns=100):
        self.ns = start_ns
        self.step_ns = step_ns
        self.reads = []
        self.sleep_requests = []
        self.sleep_failures = set()
        self.sleep_error = None

    def now(self):
        value = self.ns
        self.reads.append(value)
        self.ns += self.step_ns
        return value

    def sleep(self, seconds):
        requested = round(seconds * 1e9)
        self.sleep_requests.append(requested)
        if len(self.sleep_requests) in self.sleep_failures:
            raise self.sleep_error
        self.ns += requested


class Recorder:
    def __init__(self):
        self.records = []

    def __call__(self, kind, **fields):
        self.records.append(dict(kind=kind, **fields))


def ensure_package():
    if 'wksim_runtime' not in sys.modules:
        package_dir = ROOT / 'Simulator' / 'wksim_runtime'
        spec = importlib.util.spec_from_file_location(
            'wksim_runtime', package_dir / '__init__.py',
            submodule_search_locations=[str(package_dir)])
        module = importlib.util.module_from_spec(spec)
        sys.modules['wksim_runtime'] = module
        spec.loader.exec_module(module)
    if 'wksim_runtime.joint_rate' not in sys.modules:
        path = ROOT / 'Simulator' / 'wksim_runtime' / 'joint_rate.py'
        spec = importlib.util.spec_from_file_location('wksim_runtime.joint_rate', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules['wksim_runtime.joint_rate'] = module
        spec.loader.exec_module(module)
        sys.modules['wksim_runtime'].joint_rate = module


def load_module(path, name):
    if not Path(path).is_file():
        return None
    ensure_package()
    text = Path(path).read_bytes()
    spec = importlib.util.spec_from_loader(name, loader=None, origin=str(path))
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    module.__package__ = 'wksim_runtime'
    saved = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(text.decode('utf-8'), str(path), 'exec'), module.__dict__)
    finally:
        if saved is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved
    return module


def run_groups(module, start_ns, groups, health_ns, read_step=100, gap_ns=100_000,
               sleep_failures=(), sleep_error=None, long_health_on=None,
               long_health_ns=0):
    """Run `groups` consecutive groups; return every externally observable trace.

    long_health_on:  (group_number, health_call_index) - that single health invocation
                     itself advances the scripted clock by `long_health_ns` in addition to
                     the normal per-read step, modelling a callback that takes that long.
                     Group numbers and call indices are 1-based.
    """
    clock = FakeClock(start_ns, read_step)
    clock.sleep_failures = set(sleep_failures)
    clock.sleep_error = sleep_error
    recorder = Recorder()
    health_calls = []
    state = {'group': 0, 'index': 0, 'loop_index': 0}

    def health():
        state['index'] += 1
        is_loop = state['index'] > 1          # call 1 is the initial health call
        if is_loop:
            state['loop_index'] += 1
        before = clock.ns
        health_calls.append({'group': state['group'], 'index': state['index'],
                             'kind': 'loop' if is_loop else 'initial',
                             'loop_index': state['loop_index'] if is_loop else None,
                             'long_advance_applied': False, 'before_ns': before})
        clock.ns += health_ns
        if long_health_on == (state['group'], state['loop_index'] if is_loop else 0):
            clock.ns += long_health_ns
            health_calls[-1]['long_advance_applied'] = True
        health_calls[-1]['after_ns'] = clock.ns

    probe = module.JointRateTimingProbe('e' * 32, RATE, recorder, now=clock.now,
                                        sleep=clock.sleep)
    probe.reanchor(TICK, 'segment', transition=False)
    raised = None
    trace = []
    try:
        for group in range(groups):
            tick = TICK + 4 * group
            state['group'] = group + 1
            state['index'] = 0
            state['loop_index'] = 0
            probe.begin_group(tick, health)
            probe.end_group(tick + 4)
            clock.ns += gap_ns
    except BaseException as error:                        # noqa: BLE001
        raised = error
    samples = [r for r in recorder.records if r['kind'] == 'rate_timing_probe']
    for index, sample in enumerate(samples):
        trace.append({
            'group': index,
            'added': {key: sample.get(key) for key in ADDED_KEYS},
            'sleep_calls': sample.get('sleep_calls'),
            'loop_health_calls': sample.get('loop_health_calls'),
            'loop_health_ns': sample.get('loop_health_ns'),
            'initial_health_end_ns': sample.get('initial_health_end_ns'),
            'sleep_elapsed_ns': sample.get('sleep_elapsed_ns'),
            'earliest_start_ns': sample.get('earliest_start_ns'),
            'terminal_ns': sample.get('terminal_ns'),
            'observed_elapsed_ns': sample.get('observed_elapsed_ns'),
        })
    return {
        'raised': raised,
        'exception_is_sentinel': raised is sleep_error if sleep_error is not None else None,
        'exception_type': type(raised).__name__ if raised else None,
        'exception_message': str(raised) if raised else None,
        'clock_reads': list(clock.reads),
        'sleep_requests': list(clock.sleep_requests),
        'callbacks': [[call['group'], call['before_ns']] for call in health_calls],
        'health_calls': health_calls,
        'groups': trace,
    }


def part1_f2_crossing(modules):
    """F2 correction: is the loop-health branch reachable, and does its callback cross?

    Reachability is the gated claim: a real clock at 100 ns per read whose sleep advances
    only the requested duration reaches the parent's loop-health branch, because the
    parent caps each sleep at 2 ms while the period is 8 ms. Whether that callback spans
    the release edge is measured separately (a sweep over read step and inter-group gap)
    and reported rather than assumed.
    """
    results = {}
    for label, module in modules.items():
        trace = run_groups(module, start_ns=1_000_000_000, groups=3, health_ns=0,
                           read_step=100, gap_ns=100_000)
        groups_with_health = [g for g in trace['groups'] if (g['loop_health_calls'] or 0) > 0]
        crossing = []
        windows = []
        for group in groups_with_health:
            start = group['initial_health_end_ns'] + (group['sleep_elapsed_ns'] or 0)
            end = start + (group['loop_health_ns'] or 0)
            windows.append({
                'group': group['group'],
                'health_start_ns': start,
                'health_end_ns': end,
                'earliest_start_ns': group['earliest_start_ns'],
                'release_minus_health_start_ns': group['earliest_start_ns'] - start,
                'health_end_minus_release_ns': end - group['earliest_start_ns'],
                'crosses_release': start <= group['earliest_start_ns'] <= end,
            })
            if windows[-1]['crosses_release']:
                crossing.append(windows[-1])
        results[label] = {
            'groups': trace['groups'],
            'groups_with_loop_health_call': len(groups_with_health),
            'loop_health_reachable': bool(groups_with_health),
            'loop_health_windows': windows,
            'crossing_groups': crossing,
            'f2_claim_supported_here': bool(crossing),
        }
    return results


def part1b_crossing_fixture(module):
    """Crossing fixture: the SECOND group's FIRST loop-health callback is the callback
    that itself advances the scripted clock by 3 ms, so it ends after the release edge
    even though more than 1 ms remained when the parent called it.

    Geometry (real parent class, clock advanced only by the predetermined script):
      * second group entered 3.4 ms before its release edge, so the initial health call is
        instantaneous and the parent takes the sleep branch;
      * one 2 ms-capped sleep brings the clock back to ~1.4 ms before the edge;
      * the next loop iteration reaches the health point, and THAT loop-health callback
        takes 3 ms (`long_health_on=(2, 1)`), overrunning the edge by ~1.6 ms.

    The callback's own before/after instants and the release instant come straight from the
    run. The aggregate fields are deliberately not used to reconstruct the window: only
    their existing totals (`loop_health_calls`, `sleep_calls`) are reported alongside.
    """
    read_step = 100
    health_advance = 3_000_000
    trace = run_groups(module, start_ns=1_000_000_000, groups=2, health_ns=0,
                       read_step=read_step, gap_ns=3_400_000,
                       long_health_on=(2, 1), long_health_ns=health_advance)
    second = trace['groups'][1]
    calls = [call for call in trace['health_calls'] if call['group'] == 2]
    loop_calls = [call for call in calls if call['kind'] == 'loop']
    target = loop_calls[0]
    before = target['before_ns']
    after = target['after_ns']
    release = second['earliest_start_ns']
    return {
        'second_group': second,
        'second_group_health_call_count': len(calls),
        'second_group_loop_health_call_count': len(loop_calls),
        'second_group_loop_health_calls': second['loop_health_calls'],
        'second_group_sleep_calls': second['sleep_calls'],
        'target_call': target,
        'target_is_first_loop_health_call': target['loop_index'] == 1,
        'long_advance_applied_to_target': target['long_advance_applied'],
        'callback_before_ns': before,
        'callback_after_ns': after,
        'release_ns': release,
        'callback_duration_ns': after - before,
        'remaining_when_called_ns': release - before,
        'call_started_with_over_1ms_remaining': (release - before) > 1_000_000,
        'overrun_past_release_ns': after - release,
        'crosses_release': before <= release <= after,
        'second_group_calls': calls,
        'sleep_requests': trace['sleep_requests'],
        'clock_reads_tail': trace['clock_reads'][-8:],
        'exception_is_sentinel': trace['exception_is_sentinel'],
    }


def part2_and_3_defect(modules, v1_label, v2_label):
    """One group whose first sleep completes and whose second sleep raises the sentinel.

    Geometry: two groups, the second entered ~1 ms after the first ends (gap 1 ms), 100 ns
    per read. The second group requests two sleeps of 2 ms; making the SECOND sleep fail
    without advancing leaves the predecessor's `before`/`requested` from the failed call
    alongside the `after` of the completed one.
    """
    sentinel = RuntimeError('scripted second-sleep failure')
    outcome = {}
    for label in (v1_label, v2_label):
        module = modules.get(label)
        if module is None:
            outcome[label] = {'available': False}
            continue
        trace = run_groups(module, start_ns=1_000_000_000, groups=2, health_ns=0,
                           read_step=100, gap_ns=1_000_000, sleep_failures=(2,),
                           sleep_error=sentinel)
        group = trace['groups'][-1] if trace['groups'] else {}
        added = group.get('added', {})
        before = added.get('last_sleep_before_ns')
        after = added.get('last_sleep_after_ns')
        outcome[label] = {
            'available': True,
            'sleep_requests': trace['sleep_requests'],
            'sleep_calls_recorded': group.get('sleep_calls'),
            'exception_is_sentinel_object': trace['exception_is_sentinel'],
            'exception_type': trace['exception_type'],
            'exception_message': trace['exception_message'],
            'added': added,
            'reversed_pair': (before is not None and after is not None and before > after),
            'all_three_consistent': (
                (before is None and after is None and added.get('last_sleep_requested_ns') is None)
                or (before is not None and after is not None and before <= after)),
        }
    return outcome


def main():
    checks = {
        'old_path': str(OLD_PATH.relative_to(ROOT)).replace('\\', '/'),
        'v1_path': str(V1_PATH.relative_to(ROOT)).replace('\\', '/'),
        'v2_path': str(V2_PATH.relative_to(ROOT)).replace('\\', '/'),
        'old_sha256': hashlib.sha256(OLD_PATH.read_bytes()).hexdigest(),
        'v1_sha256': hashlib.sha256(V1_PATH.read_bytes()).hexdigest() if V1_PATH.is_file() else None,
        'v2_sha256': hashlib.sha256(V2_PATH.read_bytes()).hexdigest() if V2_PATH.is_file() else None,
    }
    checks['old_sha_matches_expected'] = checks['old_sha256'] == OLD_SHA_EXPECTED
    checks['v1_sha_matches_expected'] = checks['v1_sha256'] == V1_SHA_EXPECTED
    checks['v2_sha_matches_expected'] = checks['v2_sha256'] == V2_SHA_EXPECTED

    old = load_module(OLD_PATH, 'wksim_runtime.joint_rate_probe')
    v1 = load_module(V1_PATH, 'wksim_runtime.joint_rate_probe')
    v2 = load_module(V2_PATH, 'wksim_runtime.joint_rate_probe')
    modules = {'old': old, 'v1-candidate': v1, 'v2-candidate': v2}

    checks['part1_f2_crossing'] = part1_f2_crossing(modules)
    checks['part1b_crossing_fixture'] = part1b_crossing_fixture(v2)
    checks['part2_3_sleep_failure'] = part2_and_3_defect(modules, 'v1-candidate', 'v2-candidate')

    f2_ok = all(item['loop_health_reachable']
                for item in checks['part1_f2_crossing'].values())
    crossing_item = checks['part1b_crossing_fixture']
    v1_item = checks['part2_3_sleep_failure']['v1-candidate']
    v2_item = checks['part2_3_sleep_failure']['v2-candidate']
    defect_ok = bool(v1_item.get('available') and v1_item.get('reversed_pair')
                     and not v1_item.get('all_three_consistent'))
    fix_ok = bool(v2_item.get('available') and v2_item.get('all_three_consistent')
                  and v2_item.get('exception_is_sentinel_object'))
    checks['f2_corrected_reachability'] = f2_ok
    checks['f2_crossing_observed'] = bool(crossing_item['crosses_release'])
    checks['v1_defect_reproduced'] = defect_ok
    checks['v2_fix_verified'] = fix_ok
    checks['all_passed'] = bool(f2_ok and crossing_item['crosses_release'] and defect_ok
                                and fix_ok and checks['old_sha_matches_expected'])

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE / 'callback-retention-followup.json'
    target.write_text(json.dumps(checks, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    print('part 1  F2 reachability:')
    for label, item in checks['part1_f2_crossing'].items():
        print('   {:<14} loop_health_reachable={} groups_with_health={} crossing_groups={}'.format(
            label, item['loop_health_reachable'], item['groups_with_loop_health_call'],
            len(item['crossing_groups'])))
    print('part 1b crossing fixture (second group, first LOOP-health callback = 3 ms) :')
    item = checks['part1b_crossing_fixture']
    print('   second group: health calls={} loop-health calls={} (retained loop_health_calls={}) sleep_calls={}'.format(
        item['second_group_health_call_count'], item['second_group_loop_health_call_count'],
        item['second_group_loop_health_calls'], item['second_group_sleep_calls']))
    print('   first loop-health call: index={} before={} after={} duration={} ns (long advance applied={})'.format(
        item['target_call']['loop_index'], item['callback_before_ns'], item['callback_after_ns'],
        item['callback_duration_ns'], item['long_advance_applied_to_target']))
    print('   release R={} remaining when called={} ns (>1ms: {}) overrun past R={} ns'.format(
        item['release_ns'], item['remaining_when_called_ns'],
        item['call_started_with_over_1ms_remaining'], item['overrun_past_release_ns']))
    print('   loop-health callback crosses the release edge: {}'.format(item['crosses_release']))
    print('part 2/3 sleep completion failure:')
    for label, item in checks['part2_3_sleep_failure'].items():
        if not item.get('available'):
            print('   {:<14} MISSING'.format(label))
            continue
        print('   {:<14} sleep_requests={} added={}'.format(
            label, item['sleep_requests'],
            {k: v for k, v in item['added'].items() if v is not None} or 'all None'))
        print('        reversed_pair={} all_three_consistent={} exception_is_sentinel={}'.format(
            item['reversed_pair'], item['all_three_consistent'],
            item['exception_is_sentinel_object']))
    print()
    print('F2 reachability corrected:', checks['f2_corrected_reachability'],
          '| crossing observed:', checks['f2_crossing_observed'],
          '| v1 defect reproduced:', checks['v1_defect_reproduced'],
          '| v2 fix verified:', checks['v2_fix_verified'])
    print('evidence:', str(target.relative_to(ROOT)).replace('\\', '/'))
    return 0 if checks['all_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
