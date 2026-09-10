"""Pair owned write syscalls with loss-checked sched events; no workload replay."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.replay_joint_rate_timing import replay

HEADER=re.compile(r'\s*.*-(\d+)\s+\[(\d+)\]\s+\S+\s+(\d+)\.(\d+):\s+(.*)')
SWITCH=re.compile(r'prev_comm=.*? prev_pid=(\d+) prev_prio=\d+ prev_state=(\S+) ==> next_comm=.*? next_pid=(\d+)')


def require(value,reason):
    if not value:raise ValueError(reason)


def parse(line):
    match=HEADER.fullmatch(line.rstrip('\n'))
    require(match is not None,'Unrecognized trace header')
    pid,cpu,seconds,fraction,body=match.groups()
    stamp=int(seconds)*10**9+int(fraction.ljust(9,'0'))
    if body.startswith('sys_write(fd:'):
        fields=re.search(r'fd: ([0-9a-fx]+), .*count: ([0-9a-fx]+)\)',body)
        require(fields is not None,'Unrecognized write entry')
        return dict(kind='write_enter',pid=int(pid),ns=stamp,fd=int(fields[1],16),count=int(fields[2],16))
    if body.startswith('sys_write ->'):
        ret=int(body.split('->',1)[1].strip(),16)
        if ret>=2**63:ret-=2**64
        return dict(kind='write_exit',pid=int(pid),ns=stamp,ret=ret)
    if body.startswith('sched_switch:'):
        fields=SWITCH.search(body);require(fields is not None,'Unrecognized switch')
        return dict(kind='switch',ns=stamp,prev=int(fields[1]),state=fields[2],next=int(fields[3]))
    if body.startswith('sched_wakeup:'):
        fields=re.search(r'\bpid=(\d+)\b',body);require(fields is not None,'Unrecognized wakeup')
        return dict(kind='wakeup',pid=int(fields[1]),ns=stamp)
    raise ValueError('Unexpected trace event: '+body[:60])


def pair(events,pids):
    writes,pending,off,pending_off=[],{},defaultdict(list),{}
    boundaries=Counter()
    for event in sorted(events,key=lambda e:e['ns']):
        kind=event['kind']
        if kind=='write_enter':
            require(event['pid'] in pids,'Write outside mapped owner set')
            if event['pid'] in pending:boundaries['entry_without_exit']+=1
            pending[event['pid']]=event
        elif kind=='write_exit':
            entry=pending.pop(event['pid'],None)
            if entry is None:boundaries['exit_without_entry']+=1;continue
            require(event['ns']>=entry['ns'],'Write time regressed')
            writes.append(dict(entry,end_ns=event['ns'],duration_ns=event['ns']-entry['ns'],ret=event['ret']))
        elif kind=='switch':
            if event['prev'] in pids:
                if event['prev'] in pending_off:boundaries['switch_out_without_in']+=1
                pending_off[event['prev']]=dict(start_ns=event['ns'],state=event['state'],wake_ns=None)
            if event['next'] in pids:
                value=pending_off.pop(event['next'],None)
                if value is None:boundaries['switch_in_without_out']+=1;continue
                off[event['next']].append(dict(value,end_ns=event['ns']))
        elif kind=='wakeup':
            value=pending_off.get(event['pid'])
            if value is not None and value['wake_ns'] is None:value['wake_ns']=event['ns']
    boundaries['open_writes_at_end']=len(pending)
    boundaries['open_off_cpu_at_end']=len(pending_off)
    return writes,off,dict(boundaries)


def explain(write,intervals):
    begin,end=write['ns'],write['end_ns']
    result=dict(off_cpu_ns=0,runnable_ns=0,blocked_before_wake_ns=0,unknown_off_cpu_ns=0,intervals=[])
    for value in intervals:
        lo,hi=max(begin,value['start_ns']),min(end,value['end_ns'])
        if hi<=lo:continue
        result['off_cpu_ns']+=hi-lo
        result['intervals'].append(value)
        if value['state'].startswith('R'):
            result['runnable_ns']+=hi-lo
        elif value['wake_ns'] is None:
            result['unknown_off_cpu_ns']+=hi-lo
        else:
            wake=value['wake_ns']
            result['blocked_before_wake_ns']+=max(0,min(hi,wake)-lo)
            result['runnable_ns']+=max(0,hi-max(lo,wake))
    require(result['off_cpu_ns']<=write['duration_ns'],'Overlapping scheduler intervals')
    return result


def native_wait(timing,intervals):
    """Attribute only the observed supervisor wait, not an untraced FC thread."""
    stages=timing['stages']
    require(timing['wall_end_ns']-timing['wall_start_ns']==sum(
        stages[name]['wall_ns'] for name in ('health_and_models','encode_send','native_inputs')),
        'Stage timestamps do not cover the recorded step')
    begin=timing['wall_start_ns']+stages['health_and_models']['wall_ns']+stages['encode_send']['wall_ns']
    span=dict(ns=begin,end_ns=timing['wall_end_ns'],duration_ns=stages['native_inputs']['wall_ns'])
    return dict(tick=timing['tick'],**span,thread_cpu_ns=stages['native_inputs']['thread_cpu_ns'],
        native_path='AP input only' if timing['tick']%4 else 'AP then PX4 inputs; not separated',
        supervisor_scheduler=explain(span,intervals),
        limitation='Supervisor blocking/runnable time does not identify the native FC or host cause')


def analyze(root):
    report=json.loads((root/'report.json').read_text());meta=report['capture']
    require(meta['complete'] and meta['loss_free'] and meta['global_controls_unchanged'] and meta['instance_removed'],
            'Incomplete or lossy capture')
    require(meta.get('pid_mapping') and meta.get('trace_bytes',0)>0,'Missing kernel mapping or empty capture')
    raw=root/'capture/trace.txt'
    require(hashlib.sha256(raw.read_bytes()).hexdigest()==meta['trace_sha256'],'Trace identity changed')
    pids=meta['pid_mapping']['kernel_pids'];roles={pid:role for role,pid in pids.items()}
    with raw.open() as stream:
        events=[parse(line) for line in stream if line.strip() and not line.startswith('#')]
    writes,off,boundaries=pair(events,set(pids.values()))
    require(writes,'No complete owned write syscall')
    epoch=Path(report['directory'])/'epochs'/report['epoch']
    with (epoch/'rate.jsonl').open() as stream:
        groups=[json.loads(line) for line in stream if '"kind":"rate_group_end"' in line]
    require(groups,'No completed rate group in retained run')
    largest=max(groups,key=lambda g:g['actual_end_ns']-g['actual_start_ns'])
    with (epoch/'wire.jsonl').open() as stream:
        timing=[row for line in stream if (row:=json.loads(line))['kind']=='diagnostic_step_cpu_timing'
                and largest['start_tick']<row['tick']<=largest['end_tick']]
    starts=[g['actual_start_ns'] for g in groups]
    summary=[]
    for role in ('ap_worker','px4_worker'):
        mapping=meta['fd_before'][role]['fds']
        for kind in ('trace_file','rpc_stdout'):
            descriptors={int(fd) for fd,v in mapping.items() if (v.get('target','').endswith('-truth.jsonl')
                if kind=='trace_file' else fd=='1' and v.get('target','').startswith('pipe:['))}
            subset=[w for w in writes if w['pid']==pids[role] and w['fd'] in descriptors]
            require(subset,'Missing observed '+role+'/'+kind)
            durations=sorted(w['duration_ns'] for w in subset)
            top=[]
            for w in sorted(subset,key=lambda v:v['duration_ns'],reverse=True)[:10]:
                entry=dict(w,scheduler=explain(w,off[w['pid']]))
                group_index=bisect_right(starts,w['ns'])-1
                if group_index>=0 and w['end_ns']<=groups[group_index]['actual_end_ns']:
                    entry['rate_group']=groups[group_index]
                top.append(entry)
            summary.append(dict(role=role,kind=kind,complete_writes=len(subset),
                short_or_failed_writes=sum(w['ret']!=w['count'] for w in subset),
                median_ns=statistics.median(durations),p99_ns=durations[int(.99*(len(durations)-1))],
                maximum_ns=max(durations),over_1ms=sum(v>10**6 for v in durations),top=top))
    return dict(schema='wksim.scheduler-write-analysis.v1',acceptance_eligible=False,run_id=report['run_id'],
        analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        epoch=report['epoch'],pid_mapping=meta['pid_mapping'],trace_sha256=meta['trace_sha256'],
        event_counts=dict(Counter(e['kind'] for e in events)),boundary_counts=boundaries,writes=summary,
        largest_group=dict(group=largest,timings=timing,
            native_waits=[native_wait(row,off[pids['supervisor']]) for row in timing],
            inside_capture=meta['started_monotonic_ns']<=largest['actual_start_ns']
                and largest['actual_end_ns']<=meta['stopped_monotonic_ns']),
        rate=replay(epoch/'rate.jsonl'),limits=['10-second ground diagnostic, not flight/rate acceptance.',
            'Printed trace timestamps have microsecond precision.',
            'Boundary half-events are excluded; missing wakeups remain unknown.',
            'Guest scheduler states do not identify a Windows or physical storage cause.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=analyze(args.root)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(writes=[{k:v for k,v in row.items() if k!='top'} for row in result['writes']],
        rate=result['rate']['replay'],boundaries=result['boundary_counts']),indent=2))
