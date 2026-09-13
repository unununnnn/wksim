"""Correlate retained thread-counter intervals with rate releases; not a causal verdict."""
import argparse
from bisect import bisect_right
from collections import defaultdict
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze(probe, rate_path):
    probe,rate_path=Path(probe),Path(rate_path)
    result=json.loads((probe/'result.json').read_text())
    assert result['status']=='sampled' and sha(probe/'samples.jsonl')==result['samples_sha256']
    with (probe/'samples.jsonl').open() as f: rows=[json.loads(line) for line in f]
    assert rows[0]['kind']=='header' and rows[-1]['kind']=='close'
    samples=[row for row in rows if row['kind']=='sample']
    assert len(samples)==result['samples'] and len(samples)>1
    assert sum(len(row['threads']) for row in samples)==result['thread_rows']
    assert all(row['run_id']==result['run_id'] and row['epoch']==result['epoch'] for row in samples)
    stamps=[row['monotonic_ns'] for row in samples]
    assert all(b>a for a,b in zip(stamps,stamps[1:]))
    with rate_path.open() as f: rate=[json.loads(line) for line in f]
    assert all(row['epoch']==result['epoch'] for row in rate)
    starts=[row for row in rate if row['kind']=='rate_group_start']
    assert len({row['segment_id'] for row in starts})==1
    intervals=[]
    totals=defaultdict(int)
    for left,right in zip(samples,samples[1:]):
        before={(t['pid'],t['tid'],t['start_ticks']):t for t in left['threads']}
        cpu=defaultdict(int);new=0
        for thread in right['threads']:
            old=before.get((thread['pid'],thread['tid'],thread['start_ticks']))
            if old is None:
                new+=1;continue
            delta=thread['run_ns']-old['run_ns']
            assert delta>=0, 'Counter regressed for the same thread identity'
            cpu[thread['target']]+=delta
            totals[thread['target']]+=delta
        intervals.append(dict(begin_ns=left['monotonic_ns'],end_ns=right['monotonic_ns'],
            elapsed_ns=right['monotonic_ns']-left['monotonic_ns'],cpu_ns=dict(cpu),
            newly_observed_threads=new,release_delay_ns=0,release_ticks=[]))
    for previous,current in zip(starts,starts[1:]):
        at=current['actual_start_ns'];index=bisect_right(stamps,at)-1
        if not 0<=index<len(intervals):continue
        period=int(4_000_000/current['requested_rate'])
        delay=at-previous['actual_start_ns']-period
        assert delay>=0, 'Recorded release caught up'
        intervals[index]['release_delay_ns']+=delay
        if delay>1_000_000:intervals[index]['release_ticks'].append(current['start_tick'])
    covered=[r for r in starts if stamps[0]<=r['actual_start_ns']<stamps[-1]]
    return dict(scope=__doc__,run_id=result['run_id'],epoch=result['epoch'],
        host_boot_id=result.get('host_boot_id'),samples=len(samples),thread_rows=result['thread_rows'],
        covered_start_ticks=[covered[0]['start_tick'],covered[-1]['start_tick']] if covered else None,
        observed_wall_ns=stamps[-1]-stamps[0],cpu_ns_by_target=dict(totals),
        sampler_thread_cpu_ns=result['sampler_thread_cpu_ns'],maximum_batch_ns=result['maximum_batch_ns'],
        runqueue_counters_valid=result['runqueue_counters_valid'],
        covered_release_delay_ns=sum(r['release_delay_ns'] for r in intervals),
        largest_release_intervals=sorted(intervals,key=lambda r:r['release_delay_ns'],reverse=True)[:12],
        largest_sample_interval_ns=max(r['elapsed_ns'] for r in intervals),
        limitations=['Counters are read sequentially within each recorded batch, not simultaneous.',
          'Multiple threads may execute on different CPUs; summed CPU is not one-core utilization.',
          'Runqueue counters are not used when the retained kernel flag is disabled.',
          'Release events and CPU intervals overlap in time; this does not establish their cause.',
          'Sampling and guest/host scheduling or accounting can affect the measurement.'],
        source_sha256=sha(__file__),rate_sha256=sha(rate_path),probe_sha256=sha(probe/'samples.jsonl'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('probe',type=Path);p.add_argument('rate',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=analyze(a.probe,a.rate)
    with a.output.open('x') as f:json.dump(r,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in r.items() if k not in ('largest_release_intervals','limitations')}))
