"""Throwaway reconnaissance probe (not a deliverable). Read-only on the archive."""
import json, os, sys

A = sys.argv[1]

def rows(name):
    with open(os.path.join(A, name), 'r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)

reps = list(rows('group-work-timing.jsonl'))
print('reports', len(reps))
print('schema set', {r['schema'] for r in reps})
print('epochs', {r['epoch'] for r in reps})
print('segments', {r['segment_id'] for r in reps})
print('census', {r['census'] for r in reps})
print('rates', {r['requested_rate'] for r in reps})
print('keys uniform', {tuple(sorted(r)) for r in reps})

for r in reps:
    dec = r['work_decomposition']
    steps = r['retained_steps']
    windows = r['step_windows']
    prefix = windows[0]['wall_start_ns'] - r['preceding_boundary']['actual_start_ns']
    suffix = r['following_boundary']['actual_end_ns'] - windows[-1]['wall_end_ns']
    durations = [w['wall_end_ns'] - w['wall_start_ns'] for w in windows]
    gaps = [windows[i+1]['wall_start_ns'] - windows[i]['wall_end_ns'] for i in range(3)]
    recomputed = prefix + sum(durations) + sum(gaps) + suffix
    phase_wall = sum(p['wall_ns'] for p in r['phases'].values())
    phase_cpu = sum(p['thread_cpu_ns'] for p in r['phases'].values())
    step_wall = sum(s['wall_ns'] for s in steps)
    step_cpu = sum(s['thread_cpu_ns'] for s in steps)
    print(r['start_tick'],
          'work_ok', recomputed == r['work_ns'] == dec['prefix_ns'] + sum(dec['step_durations_ns']) + sum(dec['step_gaps_ns']) + dec['suffix_ns'],
          'prefix', prefix == dec['prefix_ns'] == 42432 if r['start_tick'] == 1996 else prefix == dec['prefix_ns'],
          'phase_wall==step_wall(pre)', phase_wall == step_wall,
          'phase_wall', phase_wall, 'stepwall', step_wall, 'durations', sum(durations),
          'phase_cpu', phase_cpu == step_cpu,
          'gapmatch', gaps == dec['step_gaps_ns'],
          'suffix', suffix == dec['suffix_ns'])
