"""Locate event-time gaps inside the largest C2 group intervals; offline only."""
from pathlib import Path
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib, io, json, platform
ROOT=Path('/root/wksim-release-acceptance-fe3')
RAW=ROOT/'validation/joint-public-flight-lcgv0yte'
ANALYSIS=ROOT/'validation/33-final-combo-c2-20260913-01/main-rate-analysis.json'
OUT=Path('/mnt/c/Users/PC/Documents/odid编译/wksim/validation/coordination/c2-gap-localization-20260913')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads(ANALYSIS.read_text())
intervals=report['top_creep_intervals'][:8]
ticks={t for r in intervals for t in range(r['previous_start_tick']+1,r['current_start_tick']+1)}
class Sink(io.RawIOBase):
    def __init__(self): self.calls=0
    def writable(self): return True
    def write(self, data): self.calls+=1; return len(data)
sink=Sink()
writer=io.TextIOWrapper(io.BufferedWriter(sink,buffer_size=65536),encoding='utf-8',newline='')
selected={t:[] for t in ticks}
for number,line in enumerate((RAW/'joint-wire.jsonl').open(),1):
    row=json.loads(line,parse_float=Decimal)
    before=sink.calls
    writer.write(line)
    if row.get('tick') in selected:
        selected[row['tick']].append({'line':number,'kind':row['kind'],'tick':row['tick'],'stack':row.get('stack'),'wall_seconds':str(row['wall']),'simulated_raw_write':sink.calls!=before})
    if row.get('tick',-1)>max(ticks):break
writer.flush()
def gap(a,b):
    return int(((Decimal(b['wall_seconds'])-Decimal(a['wall_seconds']))*1_000_000_000).to_integral_value(rounding=ROUND_HALF_EVEN))
rows=[]
for entry in intervals:
    gaps=[]
    for tick in range(entry['previous_start_tick']+1,entry['current_start_tick']+1):
        events=selected[tick]
        for stack in ('arducopter','px4'):
            sensor=next((x for x in events if x['kind']=='sensor' and x['stack']==stack),None)
            actuator=next((x for x in events if x['kind']=='actuator' and x['stack']==stack),None)
            if sensor and actuator:
                gaps.append({'tick':tick,'stack':stack,'event_gap_ns_rounded':gap(sensor,actuator),'sensor':sensor,'actuator':actuator})
    rows.append({'interval':entry,'sensor_to_actuator_gaps':gaps,'largest_gap':max(gaps,key=lambda x:x['event_gap_ns_rounded']) if gaps else None})
result={'schema':'wksim.c2-wire-gap-localization.v1','run_id':'joint-public-flight-lcgv0yte','epoch':'710fc8826ea54e6ebfe028d7d2e2228c','python':platform.python_version(),'inputs':{str(p):sha(p) for p in (ANALYSIS,RAW/'joint-wire.jsonl',RAW/'source__tools__run_joint_flight.py.txt',RAW/'source__Simulator__wksim_core__joint.py.txt')},'intervals':rows,'limits':['Only same-stream relative wall timestamps and matching physical ticks are used. Values are rounded from serialized floating seconds, not independent exact CPU timings.','Sensor-to-actuator span includes record/serialization overhead, health service, I/O waiting and possible descheduling; it is not a pure network or FC latency measurement.','ArduCopter and PX4 spans can overlap; never sum them as a closed phase ledger.','Raw-write marker simulates standard CPython TextIOWrapper/BufferedWriter(65536) with complete sink writes and no extra flush. It is not an observed kernel-write trace and does not exclude logging or other I/O costs.'],'native_executed':False,'performance_pass':False}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps([{'ticks':[x['interval']['previous_start_tick'],x['interval']['current_start_tick']],'work_ns':x['interval']['previous_work_ns'],'largest_gap':{k:x['largest_gap'][k] for k in ('tick','stack','event_gap_ns_rounded')} if x['largest_gap'] else None} for x in rows]))
