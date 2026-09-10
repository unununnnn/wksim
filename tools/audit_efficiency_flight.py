"""Independent raw actuator, ODE4, ownership and physical recovery audit for #44."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

PROFILE_SHA='f2ad9a91612dbda09150ee99bad581fce3dda50b072733a9aea6ee5bb379ec47'


def require(value,message):
    if not value:raise ValueError(message)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lines(path):
    with Path(path).open() as stream:
        for line in stream:
            require(line.endswith('\n'),'Incomplete raw record')
            yield json.loads(line)


def coordinates(output):
    return ([output[7],output[6],-output[8]],math.hypot(*output[3:6]),
            math.remainder(math.pi/2-output[11],2*math.pi),max(abs(output[9]),abs(output[10])))


def decode(packet):
    raw=bytes.fromhex(packet['packet_hex'])
    if packet['protocol']=='AP_JSON_SERVO16':
        require(len(raw)==40,'Wrong raw servo length')
        magic,rate,frame,*pwm=struct.unpack('<HHI16H',raw)
        require(magic==18458 and rate>0 and frame==packet['frame'],'Wrong raw servo header')
        require(all(value==0 or 1000<=value<=2000 for value in pwm[:4]),'Invalid servo value')
        values=[max(0,value-1000)/1000 for value in pwm[:4]]+[0.]*12
    else:
        require(packet['protocol']=='MAVLink_HIL_ACTUATOR_CONTROLS','Unknown actuator protocol')
        from pymavlink.dialects.v20 import common
        messages=common.MAVLink(None).parse_buffer(raw)
        require(messages and len(messages)==1 and messages[0].get_type()=='HIL_ACTUATOR_CONTROLS','Invalid raw MAVLink actuator packet')
        message=messages[0]
        values=list(message.controls[:4])+[0.]*12 if message.mode&128 else [0.]*16
    require(values==packet['decoded_input16'],'Recorded actuator decoding differs')
    return values


def audit(root):
    root=Path(root);result=json.loads((root/'result.json').read_text())
    require(result['status']=='observed' and result['safe_landing'] and result['children_reaped']
            and not result['cleanup_errors'] and result['source_unchanged'] and result['candidate_unchanged'],
            'Flight/cleanup/identity did not complete')
    require(digest(root/'efficiency-profile.json')==PROFILE_SHA,'Frozen physical budgets differ')
    profile=json.loads((root/'efficiency-profile.json').read_text())
    for name,checksum in result['source_sha256'].items():
        require(digest(root/'run-source'/name)==checksum,'Retained source differs: '+name)
    require(not (root/'efficiency-revoked.json').exists() and not (root/'efficiency-failure.json').exists(),'Efficiency run failed/revoked')
    origin=json.loads((root/'efficiency-origin.json').read_text())
    case=result['case'];require(case in ('baseline','fault'),'Unknown flight case')
    require(origin['event_enabled']==(case=='fault') and origin['run_id']==result['run_id']
            and origin['control_epoch']==result['task']['control_epoch'],'Wrong event run/epoch/case')
    begin=origin['origin_tick'];start=origin['start_tick'];end=origin['end_tick'];deadline=origin['recovery_deadline_tick']
    require(type(begin) is int and begin>=6000 and start==begin+2000 and end==start+1000
            and deadline==end+8000 and origin['recovery_dwell_ticks']==1500,'Wrong physical event timing')
    require(origin['motor_index']==0 and origin['multiplier']==.97 and origin['seed']==0
            and origin['library_sha256']==profile['library_sha256'] and origin['config_sha256']==PROFILE_SHA,'Wrong event/model config')
    if case=='fault':
        plan=json.loads((root/'efficiency-event.json').read_text())
        require(plan=={k:v for k,v in origin.items() if k!='event_enabled'},'Actual applied event differs')
    else:require(not (root/'efficiency-event.json').exists(),'Baseline contains a fault event')
    phase_ticks={}
    for phase in result['task']['efficiency']['phases']:
        require(phase['truth'] is not None,'Missing physical phase cursor')
        tick=round(phase['truth']['time']*1000)
        phase_ticks.setdefault(tick,[]).append(phase['truth'])
    packets={};records=0;applied=0;terminal=None;begun=False;seen_packet=False
    metrics=dict(disturbance_peak_error_m=0.,recovery_peak_error_m=0.,recovery_peak_speed_mps=0.,recovery_peak_yaw_rad=0.)
    stable_before=recovery_count=0
    wall_begin=wall_end=None
    for row in lines(root/'physics-1ms.jsonl'):
        if row['kind']=='start':
            require(not begun and records==0 and row['initial_tick']==0 and row['initial_eta']==[1.]*4,'Missing cold native start')
            require(row['initial_random_state']==result['admission']['efficiency_model']['initial_random_state'],'Native random state differs at cold start')
            begun=True;continue
        if row['kind']=='end':
            require(terminal is None,'Duplicate native terminal');terminal=row;continue
        require(begun and terminal is None and row['kind']=='step','Native record outside lifecycle')
        i=records;records+=1
        if i==begin:wall_begin=row['observed_monotonic_ns']
        if i==deadline-1:wall_end=row['observed_monotonic_ns']
        require(type(row['interval_tick']) is int and row['interval_tick']==i and row['tick']==i+1,'Native interval gap/replay')
        output=row['output120'];require(len(output)==120 and all(math.isfinite(v) for v in output),'Invalid physical output')
        require(abs(output[2]-(i+1)*.001)<1e-10,'Wrong model time')
        source=row['raw_actuator_packet']
        if source is None:
            require(not seen_packet and result['stack']=='px4','Missing actual actuator packet')
            values=[0.]*16
        else:
            seen_packet=True;key=source['packet_hex']
            if key not in packets:packets[key]=decode(source)
            values=packets[key]
        require(values==row['input16']==row['applied_input16'],'PWM scaled instead of aerodynamic efficiency')
        eta=.97 if case=='fault' and start<=i<end else 1.
        if eta==.97:applied+=1
        require(row['eta']==[eta,1.,1.,1.] and not row['revoked'],'Wrong rotor/timing/eta')
        require(row['origin']==(None if i<begin else begin),'Physical owner origin changed')
        stages=row['stages'];require(len(stages)==16,'Missing ODE4 stages')
        for index,s in enumerate(stages):
            require(len(s)==10 and all(math.isfinite(v) for v in s),'Invalid ODE4 stage')
            t,major,motor,factor,omega,t0,m0,thrust,torque,spin=s
            rotor=index%4;sub=index//4;expected_eta=eta if rotor==0 else 1.
            require(motor==rotor and major==(1 if sub==0 else 0) and factor==expected_eta
                    and abs(t-(i*.001+(0.,.0005,.0005,.001)[sub]))<1e-10,'ODE4 identity/timing/factor mismatch')
            require(spin==(-1 if rotor<2 else 1) and abs(t0-1.681e-5*omega*omega)<1e-12
                    and abs(m0-2.783e-7*omega*omega)<1e-12
                    and abs(thrust-expected_eta*t0)<1e-12 and abs(torque+expected_eta*m0*spin)<1e-12,'Native force/torque mapping mismatch')
        p,speed,yaw,tilt=coordinates(output);error=math.dist(p,profile['point_enu_m']);heading=abs(yaw-profile['yaw_enu_rad'])
        for cursor in phase_ticks.pop(i+1,[]):
            require(math.dist(cursor['position'],p)<1e-9 and abs(math.remainder(cursor['yaw']-yaw,2*math.pi))<1e-9,'Physical cursor relabelled')
        stable=error<=profile['position_error_m'] and speed<=profile['speed_mps'] and heading<=profile['yaw_error_rad']
        if begin-6000<=i<begin:
            require(stable,'Six-second initial physical hold failed');stable_before+=1
        if begin<=i<deadline:
            require(profile['minimum_height_m']<=p[2]<=profile['maximum_height_m']
                    and tilt<=math.radians(profile['maximum_axis_tilt_deg']) and error<=profile['maximum_distance_m'],'Physical flight envelope exceeded')
        if start<=i<end:
            require(error<=profile['disturbance_error_m'],'Disturbance error budget exceeded')
            metrics['disturbance_peak_error_m']=max(metrics['disturbance_peak_error_m'],error)
        if deadline-1500<=i<deadline:
            require(stable,'Final continuous 1500-tick recovery window failed');recovery_count+=1
            metrics['recovery_peak_error_m']=max(metrics['recovery_peak_error_m'],error)
            metrics['recovery_peak_speed_mps']=max(metrics['recovery_peak_speed_mps'],speed)
            metrics['recovery_peak_yaw_rad']=max(metrics['recovery_peak_yaw_rad'],heading)
    require(not phase_ticks and terminal is not None and terminal['ticks']==records and records>=deadline
            and terminal['final_eta']==[1.]*4 and terminal['failure'] is None,'Incomplete native terminal/physical cursor')
    require(stable_before==6000 and recovery_count==1500 and applied==(1000 if case=='fault' else 0),'Physical window coverage incomplete')
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rclpy.serialization import deserialize_message
    allowed={'std_msgs/msg/String','prometheus_msgs/msg/TextInfo','wksim_msgs/msg/SessionState',
        'wksim_msgs/msg/SetupRequest','wksim_msgs/msg/CommandRequest','ardupilot_msgs/msg/GlobalPosition',
        'ardupilot_msgs/msg/WksimState','ardupilot_msgs/msg/Status','px4_msgs/msg/TrajectorySetpoint',
        'px4_msgs/msg/VehicleLocalPosition','px4_msgs/msg/VehicleStatus','px4_msgs/msg/VehicleControlMode','px4_msgs/msg/VehicleCommand'}
    commands=[];native_targets=0;writers=set();latest_boot=None;maximum_dt=0.;public_states=[]
    home=None;measured_targets=measured_states=0
    for row in lines(root/'rc-dds.jsonl'):
        require(row['type'] in allowed,'Unexpected raw DDS type')
        msg=message_to_ordereddict(deserialize_message(bytes.fromhex(row['cdr_hex']),get_message(row['type'])))
        require(json.dumps(msg,sort_keys=True)==json.dumps(row['message'],sort_keys=True),'Raw DDS decode mismatch')
        if row['topic'].endswith('/v2/rc_input'):raise ValueError('Efficiency task emitted RC input')
        if row['topic'].endswith('/v2/command'):commands.append(row)
        if row['topic']=='/ap/wksim/local_state_v1' and msg['home_valid']:home=msg
        if '/in/trajectory_setpoint' in row['topic'] or row['topic']=='/ap/cmd_gps_pose':
            native_targets+=1;writers.add(row['publisher_gid'])
            if wall_begin<=row['monotonic_ns']<=wall_end:
                point=profile['point_enu_m']
                if result['stack']=='px4':
                    require(max(abs(a-b) for a,b in zip(msg['position'],[point[1],point[0],-point[2]]))<1e-5
                            and abs(math.remainder(msg['yaw']-math.pi/2,2*math.pi))<1e-5,'Native PX4 hold target differs')
                else:
                    require(home is not None,'Native AP home missing')
                    lat=home['home_latitude_e7']+int(point[1]/.011131884502145034)
                    lon=home['home_longitude_e7']+int(point[0]/(.011131884502145034*math.cos(math.radians((lat+home['home_latitude_e7'])/2e7))))
                    require(msg['type_mask']==0x9F8 and msg['coordinate_frame']==6
                            and abs(msg['latitude']-lat/1e7)<1e-8 and abs(msg['longitude']-lon/1e7)<1e-8
                            and abs(msg['altitude']-point[2])<1e-5 and abs(msg['yaw'])<1e-5,'Native AP hold target differs')
                measured_targets+=1
        if row['topic'].endswith('/v2/state'):
            public_states.append(msg)
            boot=msg['state']['header']['stamp']['sec']+msg['state']['header']['stamp']['nanosec']/1e9
            if latest_boot is not None and wall_begin<=row['monotonic_ns']<=wall_end:
                require(boot>=latest_boot,'Native state clock regressed')
                maximum_dt=max(maximum_dt,boot-latest_boot)
                measured_states+=1
            latest_boot=boot
    require(len(commands)==1 and native_targets>100 and len(writers)==1 and measured_targets>100
            and measured_states>100,'Missing unique public/native position stream')
    command=commands[0]['message']
    require(command['run_id']==result['run_id'] and command['control_epoch']==origin['control_epoch']
            and command['command']['agent_cmd']==4 and command['command']['move_mode']==0
            and command['command']['position_ref']==profile['point_enu_m'],'Wrong public point command')
    require(maximum_dt<=profile['maximum_native_dt_s']+1e-6,'Native state gap exceeds frozen budget')
    last=public_states[-1]['state']
    require(not last['armed'] and abs(last['position'][2])<.3,'Final disarmed ground feedback missing')
    events=[]
    for line in (root/'control.log').read_text().splitlines():
        offset=line.find('{"event":')
        if offset>=0:events.append(json.loads(line[offset:]))
    accepted=[e for e in events if e['event']=='command_accepted' and e['request_id']==command['request_id']]
    require(len(accepted)==1 and 0<=accepted[0]['emitted_unix_ns']-commands[0]['source_timestamp']<=200_000_000,'Public acceptance deadline/identity failed')
    require(not any(e['event']=='control_revoked' and e['emitted_monotonic_ns']>=accepted[0]['emitted_monotonic_ns'] for e in events),'Control revoked during efficiency flight')
    return dict(status='pass',stack=result['stack'],case=case,run_id=result['run_id'],metrics=metrics,
        native_intervals=records,applied_intervals=applied,initial_hold_intervals=stable_before,recovery_intervals=recovery_count,
        native_target_records=native_targets,maximum_native_state_gap_s=maximum_dt,
        result_sha256=digest(root/'result.json'),audit_sha256=digest(__file__),
        scope='native-position efficiency flight only; no external PID, deterministic replay or G6 claim')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();require(not args.output.exists() and not args.output.resolve().is_relative_to(args.root.resolve()),'Use fresh external audit output')
    try:result=audit(args.root)
    except Exception as error:result=dict(status='failed',error=repr(error),audit_sha256=digest(__file__))
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    raise SystemExit(0 if result['status']=='pass' else 1)
