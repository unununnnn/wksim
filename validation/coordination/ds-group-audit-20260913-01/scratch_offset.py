"""Scratch: implied S per step row (compare against its own window), across the flight."""
import json, os, sys

A = sys.argv[1]
audit = json.load(open(sys.argv[2]))
step_wall = {}
with open(os.path.join(A, 'joint-wire.jsonl')) as fh:
    for line in fh:
        if '"kind":"step"' in line:
            row = json.loads(line)
            step_wall[row['tick']] = row['wall']

def windows(region):
    base = region['interval_ns'][0]
    d = region['breakdown']['visible_step_durations_ns']
    g = region['breakdown']['inter_step_gaps_ns']
    cursor = base + region['breakdown']['prefix_ns']
    for i, dur in enumerate(d):
        yield region['start_tick'] + 1 + i, cursor, cursor + dur
        cursor += dur + (g[i] if i < 3 else 0)

rows = []
for region in audit['ranking']['ranked_measured_regions']:
    for tick, ws, we in windows(region):
        if tick not in step_wall:
            continue
        n = int(round(step_wall[tick] * 1e9))
        rows.append((tick, ws - n, we - n, we - ws, ws, n))

print('%8s %14s %14s %10s %12s' % ('tick', 'S_if_at_start', 'S_if_at_end', 'dur', 'rel_if_S_mid'))
for tick, lo, hi, dur, ws, n in rows[:8] + rows[24:28] + rows[56:64]:
    print('%8d %14d %14d %10d' % (tick, lo, hi, dur))
# monotonic drift of the implied S: use middle of each own-window interval
xs = [t for t, _, _, _, _, _ in rows]
mids = [(lo + hi) // 2 for _, lo, hi, _, _, _ in rows]
print('min mid', min(mids), 'max mid', max(mids), 'spread', max(mids) - min(mids))
print('first tick %d mid %d ; last tick %d mid %d ; delta %d over %d steps'
      % (xs[0], mids[0], xs[-1], mids[-1], mids[-1] - mids[0], xs[-1] - xs[0]))
