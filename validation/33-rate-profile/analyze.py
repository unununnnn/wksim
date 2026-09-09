"""Read-only attribution of the three frozen final-combination failures."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ('z5ediqxp', 'h6jijdzn', 'jo7l_p0b')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def analyze(suffix):
    case = ROOT / 'validation' / ('joint-public-flight-' + suffix)
    result = json.loads((case / 'result.json').read_text())
    rows = [json.loads(line) for line in (case / 'rate.jsonl').open()]
    starts = [r for r in rows if r['kind'] == 'rate_group_start']
    ends = {r['start_tick']: r for r in rows if r['kind'] == 'rate_group_end'}
    assert result['status'] == 'failed' and result['mixed_admission']
    assert len([r for r in rows if r['kind'] == 'rate_anchor']) == 1
    assert all(r['requested_rate'] == .5 for r in starts)
    periods = []
    for previous, current in zip(starts, starts[1:]):
        end = ends[previous['start_tick']]
        work = end['actual_end_ns'] - previous['actual_start_ns']
        gap = current['actual_start_ns'] - previous['actual_start_ns']
        periods.append(dict(tick=previous['start_tick'], work_ns=work,
            release_excess_ns=gap-8_000_000,
            work_over_period_ns=max(0, work-8_000_000),
            outside_work_excess_ns=max(0, gap-max(8_000_000,work))))
    unmet = [r for r in rows if r['kind'] == 'rate_unmet']
    assert unmet and unmet[-1]['lateness_ns'] > 100_000_000
    return dict(run=result['run_id'], error=result['error'], live=result['live'],
        hashes={p.name:digest(p) for p in (case/'result.json',case/'rate.jsonl',case/'joint-wire.jsonl')},
        manifests={p.name:digest(p) for p in (case/'ap-build.json',case/'control-build.json')},
        manager_scheduling=result.get('manager_scheduling'),
        initialization=result.get('initialization'), failure=unmet[-1], groups=len(starts),
        sums={key:sum(p[key] for p in periods) for key in
              ('release_excess_ns','work_over_period_ns','outside_work_excess_ns')},
        top_release_excess=sorted(periods,key=lambda p:p['release_excess_ns'],reverse=True)[:10],
        limitations='Work includes physics, health, publication and recording. Outside-work includes release wait, callbacks, task supervision and scheduler delays; no CPU attribution is implied.')

if __name__ == '__main__':
    print(json.dumps(dict(schema=1, runs=[analyze(s) for s in RUNS],
        current_source_hashes={name:digest(ROOT/name) for name in (
            'tools/run_joint_flight.py','tools/run-joint-flight.sh',
            'Simulator/wksim_core/joint.py','Simulator/wksim_runtime/joint_rate.py')}), indent=2))
