"""Independent sensor-chain, physical and explicit-recovery audit for GNSS flights."""
from collections import defaultdict
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

PROFILE_SHA='0f075f81a7ce9393d2108217c25afa1b1330293b22387d4de275cd62698c4a0a'


def require(value,reason):
    if not value:raise ValueError(reason)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lines(path):
    with Path(path).open() as stream:
        for line in stream:
            require(line.endswith('\n'),'Incomplete raw line')
            yield json.loads(line)


def gps_args(output):
    g=output[90:120];cog=round(math.degrees(math.atan2(g[8],g[7]))%360*100)%36000
    if math.hypot(g[7],g[8])<1:cog=0
    return [round(g[0]),round(g[11]),round(g[1]),round(g[2]),round(g[3]),round(g[4]),round(g[5]),round(g[6]),round(g[7]),round(g[8]),round(g[9]),cog,round(g[12])]


def ap_serial(root,plan,expected_json):
    groups=defaultdict(bytearray);samples={};warm=set();gens={};birth={};previous={};count=0;seen_plan=False
    suppressed_bytes=actual_after=0
    with (root/'gnss-native.tsv').open() as stream:
        for line in stream:
            c=line.rstrip('\n').split('\t');kind=c[0]
            require(kind!='FAIL','Native AP sensor failure')
            if kind=='JSON':
                require(bytes.fromhex(c[1])==next(expected_json),'AP actual input differs from physics sender');count+=1
            elif kind=='PLAN':
                require(not seen_plan and int(c[2])==plan['start_tick'] and int(c[3])==plan['end_tick']
                        and int(c[1])<=plan['start_tick']-1000,'Late/changed native AP plan');seen_plan=True
            elif kind=='GENERATION':
                tick,instance,gen=map(int,c[1:]);require(gen==gens.get(instance,0)+1,'Native sensor generation reused')
                gens[instance]=gen;birth[instance]=tick;previous[instance]=-1
            elif kind=='SAMPLE':
                tick,instance,source,hal=map(int,c[1:5]);gen=int(c[-1])
                require(instance==0 and gen==gens[instance] and hal==(tick-1)*1000,'Native source phase/generation differs')
                require(source>previous[instance] and (source==0 or birth[instance]<=source<=tick and tick-source<=500),'Old/replayed GPS source')
                previous[instance]=source;samples[tick,instance]=(source,gen)
            elif kind=='WARMUP':warm.add(tuple(map(int,c[1:3])))
            elif kind=='WRITE':
                tick,instance,suppressed,ret=map(int,c[1:5]);data=bytes.fromhex(c[5]);gen=int(c[6])
                require((tick,instance) in samples and (tick,instance) not in warm and gen==samples[tick,instance][1],'Write lacks fresh generation')
                loss=plan['start_tick']<=tick<plan['end_tick']
                require(suppressed==int(loss) and ret==(0 if loss else len(data)),'Actual write during loss or short serial write')
                if loss:suppressed_bytes+=len(data)
                elif tick>=plan['end_tick']:actual_after+=ret
                groups[tick,instance].extend(data)
    require(seen_plan and suppressed_bytes>0 and actual_after>0,'Missing real AP suppression/recovery')
    require(set(groups)==set(samples)-warm,'Missing native serial sample group')
    for data in groups.values():
        offset=0
        while offset<len(data):
            require(data[offset:offset+2]==b'\xb5\x62','Bad UBX sync')
            size=int.from_bytes(data[offset+4:offset+6],'little');packet=data[offset:offset+size+8]
            require(len(packet)==size+8,'Truncated UBX');a=b=0
            for value in packet[2:-2]:a=(a+value)&255;b=(b+a)&255
            require(packet[-2:]==bytes([a,b]),'Bad UBX checksum');offset+=len(packet)
    return dict(native_json=count,native_samples=len(samples),suppressed_bytes=suppressed_bytes,recovered_write_bytes=actual_after)


def audit(root):
    root=Path(root);result=json.loads((root/'result.json').read_text())
    require(result['status']=='observed' and result['safe_landing'] and result['children_reaped']
            and not result['cleanup_errors'] and result['source_unchanged'] and result['candidate_unchanged'],'Run/identity/cleanup incomplete')
    require(digest(root/'gnss-profile.json')==PROFILE_SHA,'Frozen GNSS profile changed')
    cfg=json.loads((root/'gnss-profile.json').read_text());plan=json.loads((root/'gnss-plan.json').read_text())
    native_parameters={}
    if result['stack']=='px4':
        sys.path.insert(0,'/root/wksim-attitude-audit-deps-g_2y8olg')
        from pyulog import ULog
        logs=list(root.rglob('*.ulg'));require(logs,'Native ULog missing')
        for path in logs:
            native_log=ULog(str(path),[])
            native_parameters={name:native_log.initial_parameters.get(name) for name in cfg['native_parameters']['px4']}
            require(native_parameters==cfg['native_parameters']['px4'],'Native failsafe parameter readback differs')
    else:
        from pymavlink import DFReader
        logs=list(root.rglob('*.BIN'));require(logs,'AP native parameter log missing')
        wanted={'GPS1_TYPE','GPS_AUTO_CONFIG','GPS_DRV_OPTIONS','FS_EKF_ACTION','FS_EKF_THRESH','FS_DR_ENABLE','FS_DR_TIMEOUT'}
        for path in logs:
            reader=DFReader.DFReader_binary(str(path))
            try:
                while True:
                    msg=reader.recv_match(type='PARM')
                    if msg is None:break
                    if msg.Name in wanted:native_parameters[msg.Name]=msg.Value
            finally:reader.close()
        require(set(native_parameters)==wanted and native_parameters['GPS1_TYPE']==2
                and native_parameters['GPS_AUTO_CONFIG']==0 and native_parameters['GPS_DRV_OPTIONS']==4,
                'AP GNSS detection parameters not confirmed')
    require(plan['run_id']==result['run_id'] and plan['scene_epoch']==result['scene_epoch']
            and plan['control_epoch']==result['task']['control_epoch'] and plan['profile_sha256']==PROFILE_SHA,'Foreign GNSS plan')
    start,end=plan['start_tick'],plan['end_tick']
    require(end-start==15000 and start-plan['origin_tick']>=2000 and start%200==0,'Wrong GNSS plan interval')
    for name,sha in result['source_sha256'].items():require(digest(root/'run-source'/name)==sha,'Run source changed')
    require(not (root/'gnss-failure.json').exists(),'Physical envelope failed')
    phases=result['task']['gnss']['phases'];by_name={p['phase']:p for p in phases}
    for name in ('initial_stable_hold','gnss_control_withdrawn','native_navigation_returned','no_automatic_reacquisition','explicit_new_takeover','new_point_accepted','recovery_point_completed','landed_disarmed'):
        require(name in by_name,'Missing GNSS phase '+name)
    if result['stack']=='arducopter':require('explicit_loss_land' in by_name,'Missing explicit native loss LAND confirmation')
    recovery_end=round(by_name['recovery_point_completed']['truth']['time']*1000)
    recovery_samples=0
    phase_ticks=defaultdict(list)
    for phase in phases:phase_ticks[round(phase['truth']['time']*1000)].append(phase['truth'])
    if result['stack']=='px4':wire={r['tick']:r for r in lines(root/'gnss-wire.jsonl') if r['phase']=='result'}
    else:wire=iter(lines(root/'gnss-wire.jsonl'))
    ticks=0;terminal=None;gps_count=suppressed=0;last_source=-1;stable=0;maximum_distance=0.
    wall_start=wall_end=None
    for row in lines(root/'physics-1ms.jsonl'):
        if row['kind']=='start':require(row['initial_tick']==0,'Nonzero start');continue
        if row['kind']=='end':terminal=row;continue
        require(terminal is None and row['tick']==ticks+1,'Physical tick gap');ticks+=1
        output=row['output120'];require(len(output)==120 and all(math.isfinite(v) for v in output),'Invalid physical truth')
        require(abs(output[2]-ticks*.001)<1e-10,'Physical time mismatch')
        p=[output[7],output[6],-output[8]];yaw=math.remainder(math.pi/2-output[11],2*math.pi)
        for cursor in phase_ticks.pop(ticks,[]):require(math.dist(cursor['position'],p)<1e-9 and abs(math.remainder(cursor['yaw']-yaw,2*math.pi))<1e-9,'Physical cursor relabelled')
        if plan['origin_tick']-6000<ticks<=plan['origin_tick']:
            require(math.dist(p,cfg['point_enu_m'])<=.3 and math.hypot(*output[3:6])<=.3 and abs(yaw)<=.15,'Initial physical hold failed');stable+=1
        if recovery_end-2000<ticks<=recovery_end:
            require(math.dist(p,cfg['recovery_point_enu_m'])<=.3 and math.hypot(*output[3:6])<=.3 and abs(yaw)<=.15,'Recovered task physical hold failed')
            recovery_samples+=1
        if ticks==start:wall_start=row['observed_monotonic_ns']
        if ticks==end:wall_end=row['observed_monotonic_ns']
        if ticks>=plan['origin_tick']:
            distance=math.dist(p,cfg['point_enu_m']);maximum_distance=max(maximum_distance,distance)
            require(-.3<=p[2]<=4.5 and distance<=4. and max(abs(output[9]),abs(output[10]))<=math.radians(15),'GNSS physical envelope violation')
        if result['stack']=='arducopter':
            item=next(wire,None)
            if item is None:continue  # One final model interval can end before sensor send during teardown.
            data=json.loads(bytes.fromhex(item['hex']))
            require(item['tick']==ticks and data['wksim']==f"{result['run_id']}:{result['scene_epoch']}:1:{ticks}",'AP wire identity mismatch')
            require(data['position']==output[6:9] and data['velocity']==output[3:6] and data['quaternion']==output[12:16]
                    and data['imu']==dict(gyro=output[64:67],accel_body=output[61:64]) and abs(data['timestamp']-ticks/1000)<1e-10,'GNSS altered physical truth')
        elif ticks in wire:
            entry=wire.pop(ticks);gps_count+=1;gps=gps_args(output)
            require(entry['original_gps']==gps,'Original GPS was retimestamped/rewritten')
            decision=entry['decision'];loss=start<=ticks<end
            require(entry['identity']==[result['run_id'],result['scene_epoch'],1] and decision['event_active']==loss,'GNSS decision identity/interval differs')
            if decision['accepted']:
                require(gps[0]>last_source and 0<=ticks*1000-gps[0]<=500000,'Old/future GPS source accepted');last_source=gps[0]
                require(entry['attempted']==(not loss) and entry['success']==(not loss),'Wrong actual send decision')
            else:require(not entry['attempted'] and not entry['success'],'Rejected GPS was sent')
            if loss:
                suppressed+=1;require(not entry['raw_frames_hex'],'GPS bytes offered during outage')
            elif entry['success']:
                from pymavlink.dialects.v20 import common
                packets=common.MAVLink(None).parse_buffer(b''.join(bytes.fromhex(v) for v in entry['raw_frames_hex']))
                require(packets and len(packets)==1 and packets[0].get_type()=='HIL_GPS','Missing actual GPS bytes')
                msg=packets[0]
                values=[getattr(msg,key) for key in ('time_usec','fix_type','lat','lon','alt','eph','epv','vel','vn','ve','vd','cog','satellites_visible')]
                require(values==gps,'Wire GPS changed source values')
    require(terminal and terminal['ticks']==ticks and not terminal['failed'] and not phase_ticks and stable==6000 and recovery_samples==2000 and ticks>end,'Incomplete physical run')
    if result['stack']=='arducopter':
        expected=(bytes.fromhex(r['hex']).strip() for r in lines(root/'gnss-wire.jsonl'))
        sensors=ap_serial(root,plan,expected)
        require(ticks-1<=sensors['native_json']<=ticks,'AP native/physical terminal mismatch')
    else:
        require(not wire and suppressed==150,'Missing exact PX4 outage candidates');sensors=dict(gps_candidates=gps_count,suppressed_candidates=suppressed)
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rclpy.serialization import deserialize_message
    states=[];requests=[];targets=[];homes=[];native_modes=[]
    for row in lines(root/'rc-dds.jsonl'):
        require(row['type'].split('/')[0] in ('std_msgs','prometheus_msgs','wksim_msgs','px4_msgs','ardupilot_msgs'),'Unexpected DDS type')
        msg=message_to_ordereddict(deserialize_message(bytes.fromhex(row['cdr_hex']),get_message(row['type'])))
        require(json.dumps(msg,sort_keys=True)==json.dumps(row['message'],sort_keys=True),'Raw DDS mismatch')
        if row['topic'].endswith('/v2/state'):states.append(row)
        if row['topic']=='/ap/wksim/local_state_v1' and msg['home_valid']:homes.append(row)
        if row['topic']=='/ap/status' or '/out/vehicle_status' in row['topic']:native_modes.append(row)
        if row['topic'].endswith(('/v2/setup','/v2/command')):requests.append(row)
        if '/in/trajectory_setpoint' in row['topic'] or row['topic']=='/ap/cmd_gps_pose':targets.append(row)
    require(any(wall_start<=r['monotonic_ns']<=wall_end and r['message']['state']['connected'] and not r['message']['state']['odom_valid'] for r in states),'No actual navigation invalidity on live transport')
    returned=by_name['native_navigation_returned']['monotonic_ns']
    takeover=by_name['explicit_new_takeover']['monotonic_ns']
    require(returned>wall_end and any(returned<=r['monotonic_ns']<=takeover
                and r['message']['state']['odom_valid'] and r['message']['state']['connected'] for r in states),
                'No fresh valid public navigation before new takeover')
    events=[]
    for line in (root/'control.log').read_text().splitlines():
        offset=line.find('{"event":')
        if offset>=0:events.append(json.loads(line[offset:]))
    revoked=[e for e in events if e['event']=='control_revoked' and wall_start<=e['emitted_monotonic_ns']<=wall_end]
    require(revoked,'No actual task withdrawal during outage')
    withdrawal=revoked[0]
    require(any(withdrawal['emitted_monotonic_ns']<=r['monotonic_ns']<=wall_end+5000000000
                and (r['message'].get('nav_state')==18 if result['stack']=='px4' else r['message'].get('mode')==9)
                for r in native_modes),'No actual native LAND action after withdrawal')
    new_requests=[r for r in requests if r['source_timestamp']>withdrawal['emitted_unix_ns']]
    require(new_requests,'No explicit recovery request')
    takeovers=[r for r in new_requests if r['message'].get('setup',{}).get('control_state')=='COMMAND_CONTROL']
    require(takeovers,'No explicit new position-control takeover')
    first=min(r['source_timestamp'] for r in takeovers)
    require(not any(withdrawal['emitted_unix_ns']+100000000<r['source_timestamp']<first for r in targets),'Native targets continued or automatically resumed')
    commands=[r['message'] for r in requests if 'command' in r['message']]
    expected_recovery=cfg['recovery_point_enu_m']
    if result['stack']=='arducopter':
        frame=by_name['recovery_navigation_frame'];old=frame['initial_home'];new=frame['current_home']
        for value,stamp in ((old,by_name['initial_navigation_frame']['monotonic_ns']),(new,frame['monotonic_ns'])):
            require(any(stamp-2000000000<=h['monotonic_ns']<=stamp+50000000 and
                all(h['message']['home_'+key]==expected for key,expected in value.items()) for h in homes),
                'Recovery home absent from actual native CDR')
        n=(new['latitude_e7']-old['latitude_e7'])*.011131884502145034
        e=(new['longitude_e7']-old['longitude_e7'])*.011131884502145034*math.cos(math.radians((new['latitude_e7']+old['latitude_e7'])/2e7))
        u=(new['altitude_cm']-old['altitude_cm'])/100.
        expected_recovery=[cfg['recovery_point_enu_m'][i]-offset for i,offset in enumerate((e,n,u))]
    require(len(commands)>2 and commands[0]['command']['position_ref']==cfg['point_enu_m']
            and max(abs(a-b) for a,b in zip(commands[-1]['command']['position_ref'],expected_recovery))<1e-5
            and all(a['request_id']<b['request_id'] and a['command']['command_id']<b['command']['command_id']
                    for a,b in zip(commands,commands[1:])),'Missing new distinct post-recovery task')
    final=states[-1]['message']['state'];require(not final['armed'] and abs(final['position'][2])<.3,'No final disarmed ground feedback')
    require(any(e['event']=='setup_completed' and e.get('control_state')=='COMMAND_CONTROL'
                and e['emitted_monotonic_ns']>returned for e in events),'New takeover lacks actual Control completion')
    return dict(status='pass',stack=result['stack'],run_id=result['run_id'],physical_ticks=ticks,sensors=sensors,
        maximum_distance_m=maximum_distance,withdrawal_reason=withdrawal['reason'],native_parameters=native_parameters,
        result_sha256=digest(root/'result.json'),audit_sha256=digest(__file__),scope='GNSS flight only; no G6 or joint-rate claim')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();require(not args.output.exists() and not args.output.resolve().is_relative_to(args.root.resolve()),'Use fresh external audit output')
    try:result=audit(args.root)
    except Exception as error:result=dict(status='failed',error=repr(error),audit_sha256=digest(__file__))
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    raise SystemExit(0 if result['status']=='pass' else 1)
