"""Throwaway reconnaissance probe 2 (not a deliverable). Read-only on the archive."""
import json, os, sys, collections

A = sys.argv[1]

def rows(name):
    with open(os.path.join(A, name), 'r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)

reps = list(rows('group-work-timing.jsonl'))
rate = [r for r in rows('rate.jsonl') if r['kind'] in ('rate_group_start', 'rate_group_end', 'rate_anchor', 'rate_request', 'rate_unmet', 'rate_bootstrap')]
starts = [r for r in rate if r['kind'] == 'rate_group_start']
ends = [r for r in rate if r['kind'] == 'rate_group_end']
by_start = {(r['segment_id'], r['start_tick']): r for r in starts}
by_end = {(r['segment_id'], r['start_tick']): r for r in ends}

# over-budget set in stream order
ob = [e for e in ends if e['actual_end_ns'] - e['actual_start_ns'] > e['ideal_end_ns'] - e['ideal_start_ns']]
print('over-budget', len(ob))
print('report starts', [r['start_tick'] for r in reps])
print('over-budget starts', [e['start_tick'] for e in ob])
print('prefix match', [r['start_tick'] for r in reps] == [e['start_tick'] for e in ob[:16]])

# previous actual start contiguity / earliest equation
prev = None
bad_prev = 0
for s in starts:
    expected = s['ideal_start_ns'] if prev is None else max(s['ideal_start_ns'], prev + (s['ideal_end_ns'] - s['ideal_start_ns']))
    if s['earliest_start_ns'] != expected:
        bad_prev += 1
        if bad_prev < 5:
            print('earliest mismatch', s['start_tick'], s['earliest_start_ns'], expected)
    prev = s['actual_start_ns']
print('earliest equation violations', bad_prev)

# contiguity of start ticks
gaps = [b['start_tick'] - a['end_tick'] for a, b in zip(starts, starts[1:])]
print('tick contiguity distinct', collections.Counter(gaps))

# report vs rate field agreement
for r in reps:
    key = (r['segment_id'], r['start_tick'])
    s, e = by_start[key], by_end[key]
    pre, fol = r['preceding_boundary'], r['following_boundary']
    assert pre['ideal_start_ns'] == s['ideal_start_ns'], 'ideal'
    assert pre['earliest_start_ns'] == s['earliest_start_ns'], 'earliest'
    assert pre['actual_start_ns'] == s['actual_start_ns'], 'actual'
    assert pre['lateness_ns'] == s['lateness_ns'], 'lateness'
    assert fol['ideal_end_ns'] == s['ideal_end_ns'], 'ideal_end'
    assert fol['actual_end_ns'] == e['actual_end_ns'], 'actual_end'
    assert fol['lateness_ns'] == e['lateness_ns'], 'end lateness'
    assert r['work_ns'] == e['actual_end_ns'] - e['actual_start_ns'], 'work'
    assert r['period_ns'] == s['ideal_end_ns'] - s['ideal_start_ns'], 'period'
print('report/rate field agreement: OK')

# native wait containment vs step_windows stage bounds
worst = []
for r in reps:
    windows = {w['tick']: w for w in r['step_windows']}
    for wait in r['visible_native_waits']:
        w = windows[wait['tick']]
        ss = w['wall_start_ns'] + w['stages']['health_and_models']['wall_ns'] + w['stages']['encode_send']['wall_ns']
        inside = ss <= wait['wall_start_ns'] and wait['wall_end_ns'] <= w['wall_end_ns']
        overlap_step = wait['wall_start_ns'] < w['wall_end_ns']
        worst.append((r['start_tick'], wait['tick'], wait['stack'], inside, overlap_step,
                      wait['wall_ns'], wait['thread_cpu_ns'], wait['wall_end_ns'] - w['wall_end_ns']))
print('native waits', len(worst), 'all inside their tick native_inputs stage',
      all(x[3] for x in worst), 'any overlapping step end', any(x[4] for x in worst))
print('cpu>wall waits', sum(1 for x in worst if x[6] > x[5]))

# top-level magnitudes
tot_work = sum(r['work_ns'] for r in reps)
print('16-report work sum', tot_work, 'excess sum', sum(r['excess_ns'] for r in reps))
agg = collections.Counter()
for r in reps:
    for name, p in r['phases'].items():
        agg[name] += p['wall_ns']
print('phase wall totals', dict(agg))
print('unaccounted (gaps+suffix)', sum(sum(r['work_decomposition']['step_gaps_ns']) + r['work_decomposition']['suffix_ns'] + r['work_decomposition']['prefix_ns'] for r in reps))
print('dropped work', [(e['start_tick'], e['actual_end_ns'] - e['actual_start_ns']) for e in ob[16:]])
