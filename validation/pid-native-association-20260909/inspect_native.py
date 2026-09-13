"""Read-only target association diagnostics; no relaxed acceptance verdict."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, '/root/wksim-attitude-audit-deps-g_2y8olg')
from tools import audit_attitude_flight as wire

root = Path(sys.argv[1])
result = wire.read(root/'result.json')
data, _, _, _ = wire.decode_native(root, result)
requests = {m['request_id']: (r, m) for r, m in data['/uav1/prometheus/v2/command']}
trace = list(wire.lines(root/'pid-trace.jsonl'))
targets = [(r, m) for name, rows in data.items() if '/in/vehicle_attitude_setpoint' in name for r, m in rows]
native, log_id = wire.ulog(next(root.rglob('*.ulg')))
report = dict(run_id=result['run_id'], trace_count=len(trace), target_count=len(targets),
              native_log=log_id, requests=[])
for i, row in enumerate(trace[:8]):
    raw, msg = requests[row['public_request_id']]
    r,p,y,u = msg['command']['att_ref']
    q = wire.native_q(wire.q_from_euler(r,p,y))
    lo, hi = row['native_state_stamp_s'], trace[i+1]['native_state_stamp_s']
    nearby = [(rr,m) for rr,m in targets if lo-.08 <= m['timestamp']/1e6 <= hi+.2]
    report['requests'].append(dict(request_id=row['public_request_id'], window=[lo,hi],
        public_monotonic=raw['monotonic'], attitude=msg['command']['att_ref'],
        targets=[dict(time=m['timestamp']/1e6, receiver_delta=rr['monotonic']-raw['monotonic'],
                      quaternion_error=wire.q_distance(q,m['q_d']), thrust_error=abs(u+m['thrust_body'][2]))
                 for rr,m in nearby],
        native=[dict(time=m['timestamp']/1e6, quaternion_error=wire.q_distance(q,m['q_d']),
                     thrust_error=abs(u+m['thrust_body[2]']))
                for m in native['vehicle_attitude_setpoint'] if lo-.08 <= m['timestamp']/1e6 <= hi+.2]))
print(json.dumps(report, indent=2))
