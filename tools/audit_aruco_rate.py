"""Verify a recorded ArUco schedule/windows; not the complete three-epoch G2 campaign."""
import argparse
from bisect import bisect_left
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from audit_joint_rate import schedule,measurement
from audit_joint_flight import digest,require


def audit(root):
    root=Path(root);run=json.loads((root/'run/result.json').read_text())
    require(len(run['epochs'])==1,'Expected one actual epoch')
    item=run['epochs'][0];epoch=item['epoch'];result=item['result'];directory=root/'run/epochs'/epoch
    require(not item['remaining_group_members'] and result['authority']['fault'] is None,'Unretired or faulted epoch')
    total=result['authority']['tick'];air=[True]*(total+1);air[0]=False
    for stack in ('arducopter','px4'):
        count=0
        with (directory/(stack+'-truth.jsonl')).open() as stream:
            for count,line in enumerate(stream,1):
                row=json.loads(line)
                require(row['tick']==count and row['epoch']==epoch and count<=total,'Truth identity differs')
                air[count]=air[count] and -row['state'][8]>1
        require(count==total,'Incomplete truth for rate phase labels')
    bad=[0]
    for airborne in air[1:]:bad.append(bad[-1]+int(not airborne))
    segments=[]
    planned=schedule(directory/'rate.jsonl',epoch)
    require(len(planned)==1,'ArUco capture must not silently restart its rate plan')
    for sid,value in planned.items():
        anchor=value['anchor'];groups=value['groups'];ends=[r['actual_end_ns'] for r in groups]
        require(anchor['requested_rate']==run['config']['requested_rate']==.5
                and anchor['anchor']['transition'] is False
                and anchor['steady_after_ns']==anchor['anchor']['wall_ns']+2_000_000_000,
                'Frozen ArUco rate/stabilization plan differs')
        first=bisect_left(ends,anchor['steady_after_ns']);start=first;windows=[]
        def sample(lo,hi):
            row=measurement(groups[lo],groups[hi],anchor['requested_rate'])
            missing=bad[row['end_tick']]-bad[row['start_tick']]
            row['phase']='airborne' if missing==0 else 'ground' if missing==row['end_tick']-row['start_tick'] else 'mixed'
            return row
        while start<len(groups):
            end=bisect_left(ends,ends[start]+10_000_000_000)
            if end==len(groups):break
            row=sample(start,end);require(abs(row['relative_error'])<=.02,'10s rate window failed')
            windows.append(row);start=end
        sixty=air_sixty=None
        for begin in range(first,len(groups)):
            end=bisect_left(ends,ends[begin]+60_000_000_000)
            if end==len(groups):break
            row=sample(begin,end)
            if begin==first:sixty=row
            if row['phase']=='airborne':air_sixty=row;break
        for row in (sixty,air_sixty):
            if row:require(abs(row['relative_error'])<=.01,'60s rate window failed')
        require(windows and sixty is not None,'Missing complete recorded 10s/60s windows')
        segments.append(dict(segment_id=sid,worst_lateness_ns=value['worst_ns'],windows=windows,
                             first_sixty_seconds=sixty,airborne_sixty_seconds=air_sixty))
    return dict(status='pass',scope=__doc__,epoch=epoch,segments=segments,
                rate_sha256=digest(directory/'rate.jsonl'),auditor_sha256=digest(__file__))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    try:result=audit(args.root)
    except Exception as error:result=dict(status='failed',error=str(error))
    with args.output.open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='segments'}))
    raise SystemExit(result['status']!='pass')
