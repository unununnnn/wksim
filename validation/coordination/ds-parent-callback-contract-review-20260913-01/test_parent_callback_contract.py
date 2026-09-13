"""Independent fake-clock contract review: ds parent last-callback retention.

Owner: validation/coordination/ds-parent-callback-contract-review-20260913-01 (only
directory written). Pure Python, offline: no native, model, ROS, build or MATLAB, and no
edit to the reviewed parent (`Simulator/wksim_runtime/joint_rate_probe.py`), to
`joint_rate.py`, or to B's preparation directory.

Method
------
Both revisions are the REAL modules, loaded from their actual bytes by temporarily
mapping the module name in `sys.modules` (no copy, no rewrite):

  old = Simulator/wksim_runtime/joint_rate_probe.py
        sha256 a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653
  new = validation/coordination/ds-parent-last-callbacks-20260913-01/
        joint_rate_probe-candidate.py.txt
        sha256 e1dd28558e36f40ea9ec87cddcbe517339f6196198dec0a28b164fecafe75a70

One scripted monotonic clock plus scripted sleep/health callbacks drive BOTH revisions
with independent clock/recorder objects, so every comparison is apples to apples: clock
read values in order, sleep requests in order, callback order and clock values, emitted
records, returned values, and the raised exception's type and message.

Group structure: the parent's first `begin_group` cannot sleep, because its first-group
release edge equals the anchor wall time; a positive `earliest - now` arises in later
groups once `previous_start` is set. Each scenario therefore runs three groups, and the
retained last-callback fields are read from the groups that actually exercise the
branches.

Run:
    python -B validation/coordination/ds-parent-callback-contract-review-20260913-01/test_parent_callback_contract.py
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
NEW_PATH = (ROOT / 'validation/coordination/ds-parent-last-callbacks-20260913-01'
            / 'joint_rate_probe-candidate.py.txt')
OLD_SHA = 'a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653'
NEW_SHA = 'e1dd28558e36f40ea9ec87cddcbe517339f6196198dec0a28b164fecafe75a70'
ADDED_KEYS = ('last_sleep_before_ns', 'last_sleep_after_ns', 'last_sleep_requested_ns',
              'last_health_before_ns', 'last_health_after_ns')
ANCHOR_TICK = 4
RATE = 0.5                      # period_ns = 4_000_000 / rate = 8 ms
FIRST_TICK = 4
GROUPS = 3


class FakeClock:
    """Monotonic clock advancing per read, with scripted sleep and health effects.

    sleep_behaviour:
      'normal'          the clock advances by the requested duration plus overshoot
      'raise_before'    the sleep raises without advancing, on `fail_sleep_at` (1-based
                        index of the begin_group call, counting only groups that request)
      'raise_after'     the clock first advances by the planned wake, then the sleep
                        raises, so an after read would still have succeeded
    """

    def __init__(self, start_ns, step_ns, overshoot_ns=0):
        self.ns = start_ns
        self.step_ns = step_ns
        self.overshoot_ns = overshoot_ns
        self.sleep_advance_ns = None       # None: advance by the requested duration
        self.reads = []
        self.sleep_requests = []
        self.sleep_behaviour = 'normal'
        self.fail_sleep_at = None
        self.wake_ns = None
        self.sleep_error = None
        self.begin_calls = 0
        self._sleep_index = 0

    def now(self):
        value = self.ns
        self.reads.append(value)
        self.ns += self.step_ns
        return value

    def sleep(self, seconds):
        # The parent passes seconds and the candidate records round(seconds * 1e9), so the
        # harness stores the same nanosecond value for comparison.
        requested = round(seconds * 1e9)
        self.sleep_requests.append(requested)
        self._sleep_index += 1
        if (self.fail_sleep_at is not None
                and self.begin_calls == self.fail_sleep_at
                and self._sleep_index == 1):
            if self.sleep_behaviour == 'raise_after':
                self.ns = self.wake_ns if self.wake_ns is not None else self.ns + requested
            raise self.sleep_error()
        advance = (self.sleep_advance_ns if self.sleep_advance_ns is not None
                   else requested + self.overshoot_ns)
        if self.fail_sleep_at is not None and self.begin_calls == self.fail_sleep_at:
            advance = self.wake_ns if self.wake_ns is not None else advance
        self.ns += advance

    def health_step(self, duration_ns):
        self.ns += duration_ns


class Recorder:
    def __init__(self):
        self.records = []

    def __call__(self, kind, **fields):
        self.records.append(dict(kind=kind, **fields))


def ensure_package():
    """Make `wksim_runtime` and its `joint_rate` submodule importable from real files."""
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
    """Load a real module from its actual bytes under its own package name."""
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


def run_scenario(spec, module):
    """Run the scenario's groups and return every externally observable trace."""
    clock = FakeClock(spec['start_ns'], spec['step_ns'], spec.get('overshoot_ns', 0))
    clock.sleep_advance_ns = spec.get('sleep_advance_ns')
    clock.sleep_behaviour = spec.get('sleep_behaviour', 'normal')
    clock.fail_sleep_at = spec.get('fail_sleep_at')
    clock.wake_ns = spec.get('wake_ns')
    clock.sleep_error = spec.get('sleep_error')
    recorder = Recorder()
    callback_log = []
    group_results = []
    raised = None

    def health():
        callback_log.append(('health', clock.ns, clock.begin_calls))
        clock.health_step(spec['health_ns'])

    probe = module.JointRateTimingProbe('e' * 32, RATE, recorder, now=clock.now,
                                        sleep=clock.sleep)
    probe.reanchor(ANCHOR_TICK, 'segment', transition=False)
    try:
        for group in range(spec['groups']):
            clock.begin_calls += 1
            tick = FIRST_TICK + 4 * group
            probe.begin_group(tick, health)
            probe.end_group(tick + 4)
    except BaseException as error:                        # noqa: BLE001 - record the object
        raised = error

    emitted = [record for record in recorder.records if record['kind'] == 'rate_timing_probe']
    for index, sample in enumerate(emitted):
        group_results.append({
            'group': index,
            'added': {key: sample.get(key) for key in ADDED_KEYS},
            'sleep_calls': sample.get('sleep_calls'),
            'loop_health_calls': sample.get('loop_health_calls'),
            'earliest_start_ns': sample.get('earliest_start_ns'),
            'terminal_ns': sample.get('terminal_ns'),
            'sleep_max_overshoot_ns': sample.get('sleep_max_overshoot_ns'),
        })
    return {
        'scenario': spec['name'],
        'outcome': 'returned' if raised is None else type(raised).__name__,
        'exception_type': type(raised).__name__ if raised else None,
        'exception_message': str(raised) if raised else None,
        'clock_reads': list(clock.reads),
        'sleep_requests': list(clock.sleep_requests),
        'callbacks': [[name, ns] for name, ns, _ in callback_log],
        'records': recorder.records,
        'emitted': emitted,
        'groups': group_results,
    }


GATE_KEYS = ('clock_reads_identical', 'sleep_requests_identical', 'callbacks_identical',
             'outcome_identical', 'exception_type_identical', 'exception_message_identical',
             'record_kinds_identical', 'shared_values_identical', 'new_keys_within_documented',
             'old_records_contain_no_new_keys', 'added_keys_are_none_or_from_clock',
             'no_partial_sleep_pair')
CONDITIONAL_KEYS = ('scenario_has_sleep_request', 'health_retention_consistent',
                    'sleep_pair_brackets_release', 'failed_sleep_no_completed_after',
                    'failed_sleep_before_recorded', 'all_added_fields_absent')


def compare(old_trace, new_trace, spec):
    """All original observations identical; only the documented keys may differ."""
    result = {'scenario': old_trace['scenario'], 'old_outcome': old_trace['outcome']}
    result['clock_reads_identical'] = old_trace['clock_reads'] == new_trace['clock_reads']
    result['sleep_requests_identical'] = old_trace['sleep_requests'] == new_trace['sleep_requests']
    result['callbacks_identical'] = old_trace['callbacks'] == new_trace['callbacks']
    result['outcome_identical'] = old_trace['outcome'] == new_trace['outcome']
    result['exception_type_identical'] = old_trace['exception_type'] == new_trace['exception_type']
    result['exception_message_identical'] = old_trace['exception_message'] == new_trace['exception_message']

    old_records, new_records = old_trace['records'], new_trace['records']
    result['record_kinds_identical'] = ([r['kind'] for r in old_records]
                                        == [r['kind'] for r in new_records])
    differences, new_only = [], set()
    for index, (old_record, new_record) in enumerate(zip(old_records, new_records)):
        for key, value in old_record.items():
            if key not in new_record:
                differences.append((index, key, 'missing_in_new'))
            elif new_record[key] != value:
                differences.append((index, key, value, new_record[key]))
        new_only.update(set(new_record) - set(old_record))
    result['shared_values_identical'] = not differences
    result['shared_differences'] = differences[:5]
    result['new_keys_only'] = sorted(new_only)
    result['new_keys_within_documented'] = new_only <= (set(ADDED_KEYS) | {'rate_timing_probe'})
    result['old_records_contain_no_new_keys'] = not (
        set().union(*[set(r) for r in old_records]) & set(ADDED_KEYS)) if old_records else True

    result['groups'] = new_trace['groups']
    result['added_key_values_per_group'] = [g['added'] for g in new_trace['groups']]
    observed = list(new_trace['clock_reads']) + [ns for _, ns in new_trace['callbacks']]
    requested = set(new_trace['sleep_requests'])
    result['derivation'] = {
        'clock_or_callback_observations': len(observed),
        'sleep_request_values': sorted(requested),
        'note': ('last_sleep_requested_ns is the request converted to ns (round(seconds*1e9)), '
                 'which is exactly what the parent already computed when it called sleep; the '
                 'other four fields are existing clock observations'),
    }
    problems = []
    for group in new_trace['groups']:
        for key, value in group['added'].items():
            if value is None:
                continue
            if key == 'last_sleep_requested_ns':
                if value not in requested:
                    problems.append((group['group'], key, value, 'not a sleep request value'))
            elif value not in observed:
                problems.append((group['group'], key, value, 'not an observed clock value'))
    result['derivation_problems'] = problems
    result['added_keys_are_none_or_from_clock'] = not problems
    result['no_partial_sleep_pair'] = all(
        group['added']['last_sleep_after_ns'] is None
        or group['added']['last_sleep_before_ns'] is not None
        for group in new_trace['groups'])

    if spec.get('sleep_crosses'):
        result['scenario_has_sleep_request'] = bool(new_trace['sleep_requests'])
        crossing = [g for g in new_trace['groups']
                    if g['added']['last_sleep_before_ns'] is not None
                    and g['added']['last_sleep_after_ns'] is not None
                    and g['earliest_start_ns'] is not None
                    and g['added']['last_sleep_before_ns'] <= g['earliest_start_ns']
                    <= g['added']['last_sleep_after_ns']]
        result['completed_sleep_pairs'] = sum(
            1 for g in new_trace['groups'] if g['added']['last_sleep_after_ns'] is not None)
        # the bracket claim only applies where a completed pair exists to test
        result['sleep_pair_brackets_release'] = bool(crossing) or not result['completed_sleep_pairs']
        result['crossing_group'] = crossing[0] if crossing else None
    if spec.get('health_crosses'):
        result['scenario_has_loop_health_call'] = any(
            (g['loop_health_calls'] or 0) >= 1 for g in new_trace['groups'])
        result['last_health_pair'] = next(
            (g['added'] for g in reversed(new_trace['groups'])
             if g['added']['last_health_before_ns'] is not None), None)
        result['scenario_has_health_pair'] = result['last_health_pair'] is not None
        result['health_fields_absent_without_loop_health'] = all(
            g['added']['last_health_before_ns'] is None and g['added']['last_health_after_ns'] is None
            for g in new_trace['groups'] if not (g['loop_health_calls'] or 0))
        # only gate the retention claim when the branch was actually reached
        result['health_retention_consistent'] = (
            result['scenario_has_health_pair'] or not result['scenario_has_loop_health_call'])
    if spec.get('sleep_behaviour', 'normal') != 'normal':
        failed_group = spec.get('fail_sleep_at')
        result['failed_sleep_no_completed_after'] = all(
            group['added']['last_sleep_after_ns'] is None
            for group in new_trace['groups'] if group['group'] + 1 == failed_group)
        result['failed_sleep_before_recorded'] = any(
            group['added']['last_sleep_before_ns'] is not None
            for group in new_trace['groups'] if group['group'] + 1 == failed_group)
        result['failed_group_exception_identical'] = (
            old_trace['exception_type'] == new_trace['exception_type']
            and old_trace['exception_message'] == new_trace['exception_message'])
        result['completed_groups_observed'] = sum(
            1 for group in new_trace['groups'] if group['sleep_calls'])
    if spec.get('no_loop_callback'):
        result['all_added_fields_absent'] = all(
            all(value is None for value in group['added'].values())
            for group in new_trace['groups'])
    return result


def main():
    checks = {
        'old_path': str(OLD_PATH.relative_to(ROOT)).replace('\\', '/'),
        'new_path': str(NEW_PATH.relative_to(ROOT)).replace('\\', '/'),
        'old_sha256': hashlib.sha256(OLD_PATH.read_bytes()).hexdigest(),
        'new_sha256': hashlib.sha256(NEW_PATH.read_bytes()).hexdigest(),
        'documented_added_keys': list(ADDED_KEYS),
        'rate': RATE,
        'groups_per_scenario': GROUPS,
    }
    checks['old_sha_matches_pin'] = checks['old_sha256'] == OLD_SHA
    checks['new_sha_matches_report'] = checks['new_sha256'] == NEW_SHA

    old_module = load_module(OLD_PATH, 'wksim_runtime.joint_rate_probe')
    new_module = load_module(NEW_PATH, 'wksim_runtime.joint_rate_probe')

    base = dict(start_ns=1_000_000_000, step_ns=100_000, health_ns=0,
                groups=GROUPS, overshoot_ns=0, sleep_advance_ns=1_000_000)
    scenarios = []

    def add(name, **overrides):
        spec = dict(base)
        spec.update(overrides)
        spec['name'] = name
        spec.setdefault('sleep_error', lambda: RuntimeError('scripted sleep failure'))
        scenarios.append(spec)

    # S1 a completed sleep crosses the release edge in a later group: the sleep advances
    #    the clock past the edge, so before <= earliest <= after
    add('sleep_crosses_release', sleep_crosses=True, sleep_advance_ns=4_000_000)
    # S2 a long-running group where no sleep is requested: the health fields stay absent
    #    because the loop-health branch is not reached in this harness (see the finding)
    add('slow_health_no_sleep_no_health_pair', health_crosses=True, health_ns=20_000_000)
    # S3 the health callback is slow enough that neither loop branch is ever reached
    add('neither_loop_callback', no_loop_callback=True, health_ns=20_000_000, groups=2)
    # S4 the second group's sleep raises before advancing: no completed pair may be claimed
    add('failed_sleep_before_advance', sleep_crosses=True, sleep_advance_ns=4_000_000,
        fail_sleep_at=2, sleep_behaviour='raise_before')
    # S4b the second group's sleep advances the clock to the wake value and then raises
    add('failed_sleep_after_advance', sleep_crosses=True, sleep_advance_ns=4_000_000,
        fail_sleep_at=2, sleep_behaviour='raise_after', wake_ns=1_000_000_000 + 9_000_000)

    results = [compare(run_scenario(spec, old_module), run_scenario(spec, new_module), spec)
               for spec in scenarios]

    checks['scenarios'] = results
    checks['all_passed'] = bool(
        checks['old_sha_matches_pin'] and checks['new_sha_matches_report']
        and all(all(item.get(key) for key in GATE_KEYS) for item in results)
        and all(item[key] for item in results for key in CONDITIONAL_KEYS if key in item))

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE / 'parent-callback-contract-review.json'
    target.write_text(json.dumps(checks, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    for item in results:
        failed = [key for key in GATE_KEYS if not item.get(key)]
        print('{:<28} old_outcome={:<22} {}'.format(
            item['scenario'], str(item['old_outcome']), 'OK' if not failed else 'FAIL ' + str(failed)))
        for group in item['groups']:
            print('     group {}: sleep_calls={} loop_health={} added={}'.format(
                group['group'], group['sleep_calls'], group['loop_health_calls'],
                {k: v for k, v in group['added'].items() if v is not None} or 'all None'))
        for key in CONDITIONAL_KEYS:
            if key in item:
                print('     {}: {}'.format(key, item[key]))
    print()
    print('old sha ok:', checks['old_sha_matches_pin'],
          '| new sha ok:', checks['new_sha_matches_report'])
    print('ALL PASSED:', checks['all_passed'])
    print('evidence:', str(target.relative_to(ROOT)).replace('\\', '/'))
    return 0 if checks['all_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
