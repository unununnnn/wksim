"""claude-last-callback-integration-20260913-01: real producer -> consumer replay.

Producer side: the REAL parent-probe modules (old a8bac9ac and B candidate v2
7855409d) are driven through D's fake-clock driver mechanics
(ds-parent-callback-contract-review-20260913-01/test_parent_callback_contract.py,
302b2d3d; imported, not copied) and every COMPLETE emitted rate_timing_probe row
is captured as a reusable fixture. Nothing is reconstructed from expected
partition outputs.

Coverage captured: a completed sleep crossing the release edge, a loop-health
call crossing the release edge, a group with no retained callback, and a group
whose first sleep completes but whose second sleep fails before the edge
(outcome 'rejected', terminal < earliest).

Consumer side: the raw fixture rows are fed row by row into OMP's stable
partition_callback_tail (callback_partition_v2.py e6e7399b, its own suite 11/11)
with clock/socket/subprocess rigged to raise: no new clock reads, failed
attempts are never fabricated into releases, an empty lateness window is legal,
original-field and SHA bindings hold, and pre-retention rows (old parent) come
back 'unavailable'.

Pure offline Python; no model/ROS/build/flight/native, no edits to others' files.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

D_DRIVER = ROOT / 'validation/coordination/ds-parent-callback-contract-review-20260913-01/test_parent_callback_contract.py'
B_V2 = ROOT / 'validation/coordination/ds-parent-last-callbacks-20260913-01/joint_rate_probe-candidate-v2.py.txt'
OLD_PARENT = ROOT / 'Simulator/wksim_runtime/joint_rate_probe.py'
OMP_V2 = ROOT / 'validation/coordination/omp-last-callback-partition-20260913-01/callback_partition_v2.py'

B_V2_SHA = '7855409d1f28e955dc9fcafc2d90f94e13ef5ab35eb1a0d239b61a4c919a4be1'
OLD_PARENT_SHA = 'a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653'
D_DRIVER_SHA = '302b2d3d7fab0d9084ac587e38bf71bef22c83d23b85de436c572d03f779632d'
OMP_V2_SHA = 'e6e7399b9218059f128e6ac5fce26382b49b5b8539ad6ec32555eadfcdafd967'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


assert sha256(B_V2) == B_V2_SHA, 'B candidate v2 bytes differ from the pinned SHA'
assert sha256(OLD_PARENT) == OLD_PARENT_SHA
assert sha256(D_DRIVER) == D_DRIVER_SHA
assert sha256(OMP_V2) == OMP_V2_SHA

_spec = importlib.util.spec_from_file_location('ds_driver', D_DRIVER)
driver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(driver)


class SecondSleepFailClock(driver.FakeClock):
    """D's scripted clock, extended to fail the Nth sleep within one group."""

    def __init__(self, *args, fail_group=None, fail_within_group=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_group = fail_group
        self.fail_within_group = fail_within_group
        self._seen_begin = None
        self._within = 0

    def sleep(self, seconds):
        if self._seen_begin != self.begin_calls:
            self._seen_begin = self.begin_calls
            self._within = 0
        self._within += 1
        if self.begin_calls == self.fail_group and self._within == self.fail_within_group:
            self.sleep_requests.append(round(seconds * 1e9))
            raise RuntimeError('scripted second-sleep failure')
        super().sleep(seconds)


def run_with_clock(spec, module, clock):
    """D's run_scenario mechanics with a caller-supplied scripted clock."""
    recorder = driver.Recorder()
    raised = None

    def health():
        clock.health_step(spec['health_ns'])

    probe = module.JointRateTimingProbe('e' * 32, driver.RATE, recorder,
                                        now=clock.now, sleep=clock.sleep)
    probe.reanchor(driver.ANCHOR_TICK, 'segment', transition=False)
    try:
        for group in range(spec['groups']):
            clock.begin_calls += 1
            tick = driver.FIRST_TICK + 4 * group
            probe.begin_group(tick, health)
            probe.end_group(tick + 4)
    except BaseException as error:  # noqa: BLE001 - recorded as data
        raised = error
    return {'outcome': 'returned' if raised is None else type(raised).__name__,
            'records': recorder.records,
            'emitted': [r for r in recorder.records if r['kind'] == 'rate_timing_probe'],
            'clock_reads': list(clock.reads),
            'sleep_requests': list(clock.sleep_requests)}


BASE = dict(start_ns=1_000_000_000, step_ns=100_000, groups=3, overshoot_ns=0,
            health_ns=0, sleep_advance_ns=1_000_000)
SCENARIOS = (
    dict(name='sleep_crosses_edge', sleep_advance_ns=4_000_000),
    dict(name='loop_health_crosses_edge', health_ns=3_000_000),
    dict(name='no_callback', health_ns=20_000_000, groups=2),
    dict(name='sleep_done_then_failure_before_edge'),
)

new_module = driver.load_module(B_V2, 'wksim_runtime.joint_rate_probe')
old_module = driver.load_module(OLD_PARENT, 'wksim_runtime.joint_rate_probe')

fixtures = []
for spec0 in SCENARIOS:
    spec = dict(BASE)
    spec.update(spec0)
    if spec['name'] == 'sleep_done_then_failure_before_edge':
        clock = SecondSleepFailClock(spec['start_ns'], spec['step_ns'],
                                     spec['overshoot_ns'], fail_group=2,
                                     fail_within_group=2)
        trace = run_with_clock(spec, new_module, clock)
    else:
        trace = driver.run_scenario(spec, new_module)
    emitted = trace['emitted']
    entry = {'scenario': spec['name'], 'outcome': trace['outcome'],
             'rows': emitted, 'clock_reads': trace['clock_reads'],
             'sleep_requests': trace['sleep_requests']}
    fixtures.append(entry)

# Old-parent rows for the pre-retention 'unavailable' case.
old_trace = driver.run_scenario(dict(BASE, name='sleep_crosses_edge',
                                     sleep_advance_ns=4_000_000), old_module)
old_rows = old_trace['emitted']

# ---- producer-side truth: the four coverage cases really happened
def added(row):
    return {key: row.get(key) for key in
            ('last_sleep_before_ns', 'last_sleep_after_ns', 'last_health_before_ns',
             'last_health_after_ns')}


by_name = {f['scenario']: f for f in fixtures}
s1 = by_name['sleep_crosses_edge']['rows']
assert any((a := added(r))['last_sleep_before_ns'] is not None
           and a['last_sleep_before_ns'] <= r['earliest_start_ns'] <= a['last_sleep_after_ns']
           for r in s1), 'sleep crossing not captured'
s2 = by_name['loop_health_crosses_edge']['rows']
assert any((a := added(r))['last_health_before_ns'] is not None
           and a['last_health_before_ns'] <= r['earliest_start_ns'] <= a['last_health_after_ns']
           for r in s2), 'loop-health crossing not captured'
s3 = by_name['no_callback']['rows']
assert all(all(value is None for value in added(r).values()) for r in s3), \
    'no-callback scenario retained a callback field'
s4 = by_name['sleep_done_then_failure_before_edge']
s4_row = s4['rows'][-1]
assert s4['outcome'] == 'RuntimeError'
assert s4_row['outcome'] == 'rejected'
assert s4_row['terminal_ns'] < s4_row['earliest_start_ns'], 'terminal must precede the edge'
assert s4_row['last_sleep_after_ns'] is not None, 'the completed first sleep must be retained'

fixture_doc = dict(schema='wksim.last-callback-fixtures.v1',
                   classification='diagnostic_only', full_acceptance=False,
                   provenance=dict(producer='B candidate v2 via D fake-clock driver',
                                   b_candidate_v2_sha256=B_V2_SHA,
                                   old_parent_sha256=OLD_PARENT_SHA,
                                   driver_sha256=D_DRIVER_SHA,
                                   driver_note=('D run_scenario mechanics; a subclass extends the '
                                                'clock only to fail the second in-group sleep')),
                   scenarios=fixtures, old_parent_rows=old_rows)
with (HERE / 'fixtures.json').open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(fixture_doc, stream, indent=2)
    stream.write('\n')

# ---- consumer side: row-by-row replay into OMP's stable partition_callback_tail
_spec = importlib.util.spec_from_file_location('omp_partition_v2', OMP_V2)
omp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(omp)

guards = [patch.object(time, 'monotonic_ns', side_effect=AssertionError('no new clock reads')),
          patch.object(time, 'monotonic', side_effect=AssertionError('no new clock reads')),
          patch.object(time, 'sleep', side_effect=AssertionError('no sleeping')),
          patch.object(socket, 'socket', side_effect=AssertionError('no sockets')),
          patch.object(subprocess, 'Popen', side_effect=AssertionError('no subprocess'))]
for guard in guards:
    guard.start()

replay = []
try:
    for entry in fixtures:
        for index, row in enumerate(entry['rows']):
            result = omp.partition_callback_tail(dict(row))
            replay.append(dict(scenario=entry['scenario'], group=index,
                               outcome=row['outcome'], result=result))
    old_results = [omp.partition_callback_tail(dict(row)) for row in old_rows]
finally:
    for guard in guards:
        guard.stop()

checks = []


def check(name, condition):
    checks.append(dict(name=name, ok=bool(condition)))
    assert condition, name


for item in replay:
    row = by_name[item['scenario']]['rows'][item['group']]
    result = item['result']
    check('closure_exact:%s:%d' % (item['scenario'], item['group']),
          result['closure_exact'])
    if row['outcome'] == 'started':
        check('started_is_release:%s:%d' % (item['scenario'], item['group']),
              result['status'] == 'ok' and result['terminal_is_release'])
    else:
        check('failed_never_fabricated_release:%s:%d' % (item['scenario'], item['group']),
              result['status'] == 'failed_attempt' and not result['terminal_is_release'])

def replay_result(scenario, row):
    rows = by_name[scenario]['rows']
    index = next(i for i, r in enumerate(rows) if r is row)
    return next(item['result'] for item in replay
                if item['scenario'] == scenario and item['group'] == index)


sleep_row = next(r for r in s1
                 if r['last_sleep_before_ns'] is not None
                 and r['last_sleep_before_ns'] <= r['earliest_start_ns'] <= r['last_sleep_after_ns'])
sleep_result = replay_result('sleep_crosses_edge', sleep_row)
check('sleep_crossing_visible_in_window', sleep_result['sleep_in_window_ns'] > 0)
health_row = next(r for r in s2
                  if r['last_health_before_ns'] is not None
                  and r['last_health_before_ns'] <= r['earliest_start_ns'] <= r['last_health_after_ns'])
health_result = replay_result('loop_health_crosses_edge', health_row)
check('health_crossing_visible_in_window', health_result['health_in_window_ns'] > 0)
for row, item in zip(s3, [r for r in replay if r['scenario'] == 'no_callback']):
    check('no_callback_zero_union', item['result']['callback_union_ns'] == 0
          and item['result']['tail_after_last_callback_ns'] is None
          and item['result']['unattributed_ns'] == item['result']['window_ns'])
fail_result = replay_result('sleep_done_then_failure_before_edge', s4_row)
check('empty_lateness_window_legal', fail_result['window_ns'] == 0
      and fail_result['closure_exact'])
check('failed_attempt_not_a_release', fail_result['status'] == 'failed_attempt'
      and not fail_result['terminal_is_release'])
check('old_records_unavailable', all(r.get('status') == 'unavailable' for r in old_results))

result_doc = dict(schema='wksim.last-callback-replay.v1',
                  classification='diagnostic_only', full_acceptance=False,
                  producer_sha256=dict(b_candidate_v2=B_V2_SHA, old_parent=OLD_PARENT_SHA,
                                       driver=D_DRIVER_SHA),
                  consumer_sha256=dict(omp_callback_partition_v2=OMP_V2_SHA,
                                       omp_v2_own_suite='11/11 OK before integration'),
                  fixture_sha256=sha256(HERE / 'fixtures.json'),
                  rows_replayed=len(replay), old_rows_replayed=len(old_results),
                  clock_reads_during_replay='forbidden by guard; none occurred',
                  checks=checks, all_passed=all(c['ok'] for c in checks),
                  scope='producer->consumer actual replay only; no acceptance claim')
with (HERE / 'replay-result.json').open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(result_doc, stream, indent=2)
    stream.write('\n')
print(json.dumps({'fixtures': str(HERE / 'fixtures.json'),
                  'replay': str(HERE / 'replay-result.json'),
                  'rows_replayed': len(replay),
                  'all_passed': result_doc['all_passed']}, indent=1))
