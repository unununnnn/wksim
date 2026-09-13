"""Cross-check real native GNSS suppression against independently decoded DDS state."""
import argparse
import json
from pathlib import Path
from audit_ap_gnss_schedule import audit as audit_wire,require,digest


def audit(root):
    wire=audit_wire(root)
    from ardupilot_msgs.msg import WksimState,Status
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    types={'/ap/wksim/local_state_v1':WksimState,'/ap/status':Status}
    states=[];status=[];writers={topic:set() for topic in types}
    for line in (Path(root)/'dds.jsonl').read_text().splitlines():
        row=json.loads(line);require(row['topic'] in types,'Unexpected DDS channel')
        msg=message_to_ordereddict(deserialize_message(bytes.fromhex(row['cdr_hex']),types[row['topic']]))
        require(json.dumps(msg,sort_keys=True)==json.dumps(row['message'],sort_keys=True),'CDR/decoded state mismatch')
        writers[row['topic']].add(row['publisher_gid'])
        (states if row['topic'].endswith('local_state_v1') else status).append(msg)
    require(states and status and all(len(v)==1 for v in writers.values()),'Missing unique native DDS writers')
    require(not any(m['armed'] or m['flying'] for m in status),'Ground probe armed or flew')
    require(all(a['time_boot_us']<b['time_boot_us'] for a,b in zip(states,states[1:])),'Native state clock did not advance')
    select=lambda low,high:[m for m in states if low*1000000<=m['time_boot_us']<high*1000000]
    before=select(45,50);during=select(54,65);after=select(70,80)
    require(len(before)>50 and all(m['gps_fix_type']>=3 and m['position_valid'] for m in before),'No healthy pre-outage navigation')
    require(len(during)>100 and all(m['gps_fix_type']<3 for m in during),'Native GPS driver did not invalidate')
    require(any(not m['position_valid'] for m in during),'EKF position validity never became false')
    require(len(after)>100 and all(m['gps_fix_type']>=3 and m['position_valid'] for m in after),'Native navigation did not recover')
    invalid=next(m['time_boot_us'] for m in states if m['time_boot_us']>=50000000 and m['gps_fix_type']<3)
    recovered=next(m['time_boot_us'] for m in states if m['time_boot_us']>=65000000 and m['gps_fix_type']>=3 and m['position_valid'])
    return dict(status='pass',scope='real stationary native GPS/DDS invalidity and recovery; no task or flight acceptance',
        wire=wire,native_state_samples=len(states),first_invalid_boot_us=invalid,first_recovered_boot_us=recovered,
        dds_sha256=digest(Path(root)/'dds.jsonl'),audit_sha256=digest(__file__))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();require(not args.output.exists(),'Use fresh audit output')
    try:result=audit(args.root)
    except Exception as error:result=dict(status='failed',error=repr(error),audit_sha256=digest(__file__))
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    raise SystemExit(0 if result['status']=='pass' else 1)
