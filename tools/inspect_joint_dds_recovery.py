"""Read retained raw DDS; this program never creates a node or sends a command."""
import json
from pathlib import Path
import sys

from rclpy.serialization import deserialize_message
from wksim_msgs.msg import SessionState
from std_msgs.msg import String

root=Path(sys.argv[1])
states={}; changes=[]
for line in (root/'pause-dds.jsonl').open():
    row=json.loads(line)
    if row['topic'].endswith('/v2/state'):
        msg=deserialize_message(bytes.fromhex(row['cdr_hex']),SessionState)
        state=msg.state
        key=(state.connected,state.odom_valid,state.armed,state.mode,msg.control.failsafe,msg.native_generation)
        if states.get(state.uav_id)!=key:
            changes.append(dict(wall=row['wall'],tick=row['tick'],phase=row['phase'],uav_id=state.uav_id,
                connected=key[0],odom_valid=key[1],armed=key[2],mode=key[3],control_withdrawn=key[4],generation=key[5],
                gps_status=int(state.gps_status),gps_satellites=int(state.gps_num),
                source_boot_s=state.header.stamp.sec+state.header.stamp.nanosec/1e9,
                position=[float(value) for value in state.position]))
        states[state.uav_id]=key
acks={}
for line in (root/'scene-lifecycle.jsonl').open():
    row=json.loads(line)
    if row['kind']=='ack_raw' and row['phase']=='recovering':
        value=json.loads(deserialize_message(bytes.fromhex(row['cdr_hex']),String).data)
        stats=acks.setdefault(row['uav_id'],dict(count=0,ready=0,first_ready=None,last=value))
        stats['count']+=1;stats['ready']+=bool(value['ready']);stats['last']=value
        if value['ready'] and stats['first_ready'] is None:stats['first_ready']=row['wall']
print(json.dumps(dict(state_changes=changes,acks=acks),indent=2))
