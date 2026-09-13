"""Read-only timing decomposition of the actual failed #62 epoch."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
EPOCH=ROOT/'validation/lunar-20-epoch-1/case/run/epochs/2a8d5df1dd4244c3868dc7f38e85a369'
rows=[json.loads(line) for line in (EPOCH/'rate.jsonl').open()]
groups=[r for r in rows if r['kind']=='rate_group_end']
period=4_000_000
work=[g['actual_end_ns']-g['actual_start_ns'] for g in groups]
increments=[]
for a,b in zip(groups,groups[1:]):
    assert b['start_tick']==a['end_tick']
    delta=b['actual_start_ns']-a['actual_start_ns']-period
    work_late=max(0,a['actual_end_ns']-a['actual_start_ns']-period)
    assert delta>=work_late>=0
    increments.append(dict(previous_start_tick=a['start_tick'],next_start_tick=b['start_tick'],
        phase_increment_ns=delta,previous_work_overrun_ns=work_late,
        residual_release_delay_ns=delta-work_late))
anchor=groups[0]['ideal_start_ns']
first_late=groups[0]['actual_start_ns']-anchor
last=groups[-1]
reconstructed=first_late+sum(r['phase_increment_ns'] for r in increments)+work[-1]-period
assert reconstructed==last['lateness_ns']
ranked=sorted(groups,key=lambda g:g['actual_end_ns']-g['actual_start_ns'],reverse=True)[:8]
wire=[]
kinds=Counter()
for line in (EPOCH/'wire.jsonl').open():
    row=json.loads(line)
    kinds[row['kind']]+=1
    wire.append({k:row[k] for k in ('kind','tick','issued_monotonic_s','stack') if k in row})
for group in ranked:
    subset=[r for r in wire if group['actual_start_ns']/1e9<=r['issued_monotonic_s']<=group['actual_end_ns']/1e9]
    group['work_ns']=group['actual_end_ns']-group['actual_start_ns']
    group['largest_wire_gaps'] = sorted([dict(before=a,after=b,gap_ns=round((b['issued_monotonic_s']-a['issued_monotonic_s'])*1e9))
                                       for a,b in zip(subset,subset[1:])],key=lambda r:r['gap_ns'],reverse=True)[:3]
summary=dict(scope='Actual #62 raw timing arithmetic, not new performance acceptance',groups=len(groups),
    anchor_tick=groups[0]['start_tick'],last_tick=last['end_tick'],wall_ns=last['actual_end_ns']-anchor,
    phase_lateness_ns=last['lateness_ns'],reconstructed_lateness_ns=reconstructed,
    first_release_lateness_ns=first_late,previous_work_overrun_sum_ns=sum(r['previous_work_overrun_ns'] for r in increments),
    residual_release_delay_sum_ns=sum(r['residual_release_delay_ns'] for r in increments),
    final_work_minus_period_ns=work[-1]-period,
    work_summary_ns=dict(min=min(work),median=statistics.median(work),mean=statistics.mean(work),
        p99=sorted(work)[int(.99*(len(work)-1))],max=max(work)),
    groups_work_over_4ms=sum(v>period for v in work),wire_kinds=dict(kinds),
    top_phase_increments=sorted(increments,key=lambda r:r['phase_increment_ns'],reverse=True)[:12],
    longest_groups=ranked,
    inputs_sha256={name:hashlib.sha256((EPOCH/name).read_bytes()).hexdigest() for name in ('rate.jsonl','wire.jsonl')})
(OUT/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ('longest_groups','top_phase_increments','inputs_sha256')},indent=2))
