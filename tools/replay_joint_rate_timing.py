"""Offline captured-time JointRate diagnosis. Exit 1 when actual pacing rejects a trace.
No FC, model, network, sleeps, budget changes, or large wire-log reads.
"""
import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Simulator'))
from wksim_runtime.joint_rate import JointRate, RateUnmet, LATE_LIMIT_NS


def replay(path):
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    clock = [0]
    emitted = []
    rate = None
    rejection = None
    for e in events:
        kind = e['kind']
        clock[0] = e.get('issued_monotonic_ns', clock[0])
        try:
            if kind == 'rate_request':
                if rate is None:
                    rate = JointRate(e['epoch'], e['requested_rate'], lambda kind, **kw: emitted.append(dict(kind=kind, **kw)), now=lambda: clock[0], sleep=lambda _: None)
                else:
                    rate.set_rate(e['requested_rate'], e['request_id'], e['tick'])
            elif kind == 'rate_anchor':
                clock[0] = e['anchor']['wall_ns']
                rate.reanchor(e['anchor']['tick'], e['reason'], transition=e['anchor']['transition'], recovery=rate.latched)
            elif kind == 'rate_segment_end':
                rate.close_segment(e['reason'], e['tick'])
            elif kind == 'rate_boundary_check':
                clock[0] = e['actual_check_ns']
                rate.check_boundary(e['boundary_tick'])
            elif kind == 'rate_group_start':
                clock[0] = e['actual_start_ns']
                rate.begin_group(e['start_tick'], lambda: None)
            elif kind == 'rate_group_end':
                clock[0] = e['actual_end_ns']
                rate.end_group(e['end_tick'])
            elif kind == 'rate_unmet' and rejection is None:
                # begin_group rejects before recording a start, so recover that call's clock.
                clock[0] = rate.anchor['wall_ns'] + rate.completed * rate.period_ns + e['lateness_ns']
                rate.begin_group(e['tick'], lambda: None)
        except RateUnmet as exc:
            rejection = dict(kind=kind, tick=e['tick'], lateness_ns=exc.lateness_ns)
            break
    captured = next((e for e in events if e['kind'] == 'rate_unmet'), None)
    assert bool(rejection) == bool(captured), (rejection, captured)
    if captured:
        assert rejection['lateness_ns'] == captured['lateness_ns'], (rejection, captured)
    segments = []
    for sid in sorted({e['segment_id'] for e in events if e['kind'] == 'rate_group_end'}):
        ends = [e for e in events if e['kind'] == 'rate_group_end' and e['segment_id'] == sid]
        period = int(4_000_000 / ends[0]['requested_rate'])
        durations = [e['actual_end_ns'] - e['actual_start_ns'] for e in ends]
        spikes = []
        for prev, cur in zip(ends, ends[1:]):
            increment = cur['actual_start_ns'] - prev['actual_start_ns'] - period
            inside = max(0, prev['actual_end_ns'] - prev['actual_start_ns'] - period)
            spikes.append(dict(tick=cur['start_tick'], phase_increment_ns=increment,
                preceding_group_excess_ns=inside, residual_release_delay_ns=increment-inside,
                preceding_group_duration_ns=prev['actual_end_ns']-prev['actual_start_ns'],
                gap_from_previous_end_ns=cur['actual_start_ns']-prev['actual_end_ns'],
                actual_start_ns=cur['actual_start_ns']))
        positive = sum(max(0, x['phase_increment_ns']) for x in spikes)
        segments.append(dict(segment_id=sid, rate=ends[0]['requested_rate'], groups=len(ends),
            first_tick=ends[0]['start_tick'], last_tick=ends[-1]['end_tick'],
            wall_duration_ns=ends[-1]['actual_end_ns']-ends[0]['actual_start_ns'],
            group_duration_median_ns=statistics.median(durations), group_duration_max_ns=max(durations),
            group_duration_p99_ns=sorted(durations)[int(.99*(len(durations)-1))],
            group_over_period_count=sum(d>period for d in durations),
            phase_first_ns=ends[0]['actual_start_ns']-ends[0]['ideal_start_ns'],
            phase_last_ns=ends[-1]['actual_start_ns']-ends[-1]['ideal_start_ns'],
            summed_positive_phase_increment_ns=positive,
            preceding_group_excess_sum_ns=sum(x['preceding_group_excess_ns'] for x in spikes),
            top_phase_spikes=sorted(spikes,key=lambda x:x['phase_increment_ns'],reverse=True)[:10]))
    return dict(path=str(path), rate_log_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256((ROOT/'Simulator/wksim_runtime/joint_rate.py').read_bytes()).hexdigest(),
        late_limit_ns=LATE_LIMIT_NS, replay='RED' if rejection else 'GREEN', rejection=rejection,
        captured_failure_matches=True, segments=segments,
        limitation='Replays captured boundary timestamps through real JointRate, not underlying workload or OS scheduling. Release delay includes caller work, pacing and scheduling; it does not identify their cause.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rate_logs', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args=parser.parse_args()
    results=[replay(p) for p in args.rate_logs]
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(results,indent=2)+'\n')
    for r in results:
        print(r['replay'], r['path'], r['rejection'])
    sys.exit(int(any(r['replay']=='RED' for r in results)))
