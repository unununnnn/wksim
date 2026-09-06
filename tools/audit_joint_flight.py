"""Offline public-task/physics/wire audit; no simulator or control publisher."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

REPO=Path(__file__).resolve().parents[1]
AUDIT_OUTPUTS=frozenset(('audit.json','pause-audit.json','lifecycle-audit.json','permission-loss-audit.json','dds-recovery-audit.json'))
sys.path.insert(0,str(REPO))
from Simulator.wksim_core.ap_json import decode_servos,sensor_message
from Simulator.wksim_core.px4_mavlink import actuator_commands,gps_arguments


def require(value,message):
    if not value: raise ValueError(message)


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): result.update(block)
    return result.hexdigest()


def lines(path):
    with path.open() as stream:
        for line in stream:
            require(line.endswith('\n'),'Incomplete evidence line')
            yield json.loads(line)


def kinematics(state):
    # The generated Vehicle60 ABI stores NED velocity at 3:6, position at 6:9;
    # 9:12 is attitude, not translational speed (see ap_json.sensor_message).
    return state[6:9]+state[3:6]


def verify_control_candidate(root, result, verify_current_sources=False):
    control=result['control_candidate']
    require(digest(root/'control-build.json')==result['manifest_sha256']['control'],'Control manifest changed')
    require(json.loads((root/'control-build.json').read_text())==control,'Control build record differs')
    directories=[Path(control['package']),Path(control['root'])/'src/prometheus_control/prometheus_control']
    if verify_current_sources:
        directories.append(REPO/'ros2/src/prometheus_control/prometheus_control')
    for directory in directories:
        actual={path.relative_to(directory).as_posix():digest(path) for path in directory.rglob('*.py')
                if '__pycache__' not in path.parts}
        require(actual==control['python_sha256'],'Executed/staged/current control candidate changed: '+str(directory))
    return control


def audit_timeline(root,r,windows=None):
    """Raw two-model/native-input/clock audit, shared by distinct public workflows."""
    from pymavlink.dialects.v20 import common
    total=r['final_authority']['tick']; epoch=r['scene_epoch']
    model={}; sensors={}; imu={}; gps={}; physical={}
    protocol=common.MAVLink(None)
    f32=lambda value:struct.unpack('<f',struct.pack('<f',value))[0]
    for stack in ('arducopter','px4'):
        data=[]; sensor_hash={}; imu_expected={}; gps_expected={}
        for tick,row in enumerate(lines(root/(stack+'-truth.jsonl')),1):
            state=row['state']; commands=row['commands']
            require(row['version']==1 and row['epoch']==epoch and row['tick']==tick and len(state)==120
                    and all(math.isfinite(x) for x in state) and abs(state[2]-tick/1000)<1e-8,
                    'Bad model epoch, time or numeric state')
            require(json.loads(row['input'])==row['request']==dict(version=1,epoch=epoch,tick=tick,commands=commands),
                    'Model did not use retained exact input')
            data.append((kinematics(state),commands))
            if stack=='arducopter':
                sensor=json.loads(sensor_message(state)); sensor.update(no_lockstep=False,no_time_sync=False)
                packet=('\n'+json.dumps(sensor,separators=(',',':'))+'\n').encode('ascii')
                sensor_hash[tick]=hashlib.sha256(packet).hexdigest()
            elif tick%4==0:
                sensor=state[60:90]
                imu_expected[tick]=protocol.hil_sensor_encode(round(sensor[0]),*[f32(x) for x in sensor[1:14]],round(sensor[14])).to_dict()
                if tick%100==0: gps_expected[tick]=protocol.hil_gps_encode(*gps_arguments(state)).to_dict()
        require(len(data)==total,'Model was stepped a different number of times')
        model[stack]=data; sensors[stack]=sensor_hash; imu[stack]=imu_expected; gps[stack]=gps_expected
        physical[stack]=dict(max_height_m=max(-d[0][2] for d in data),final_height_m=-data[-1][0][2],
            min_waypoint_error_m=min(math.dist(d[0][:3],[3,2,-3]) for d in data))
        require(physical[stack]['max_height_m']>=2.5 and abs(physical[stack]['final_height_m'])<.3
                and (windows is None or physical[stack]['min_waypoint_error_m']<=.5),'Independent truth failed')
        if windows is not None:
            for finish,start,label in (('hold_completed','takeoff_reached','hold'),('waypoint_completed','waypoint_reached','waypoint')):
                lo=windows[stack][start]['ros_time_ns']//1000000; hi=windows[stack][finish]['ros_time_ns']//1000000
                rows=data[max(0,lo-1):hi]
                error=max((abs(d[0][2]+3) if label=='hold' else math.dist(d[0][:3],[3,2,-3])) for d in rows)
                physical[stack][label+'_truth_max_error_m']=error
                require(error<=(.6 if label=='hold' else .5),'Truth disagrees with task scene-time dwell')
    overlap=sum(-a[0][2]>1 and -b[0][2]>1 for a,b in zip(model['arducopter'],model['px4']))
    require(overlap>0,'No simultaneous true flight interval')

    ap_current=None; ap_frames=[]; ap_duplicates=0; px_current=[0.]*16; px_time=None; pending={}; counts={'ap_sensor':0,'px_sensor':0,'gps':0,'step':0,'barrier':0}
    for e in lines(root/'joint-wire.jsonl'):
        tick=e['tick']; require(e['epoch']==epoch and 0<=tick<=total,'Wire epoch or tick differs')
        if e['kind']=='actuator' and e['stack']=='arducopter':
            frame,rate,pwm,commands=decode_servos(bytes.fromhex(e['raw_hex']))
            require((frame,rate,pwm,commands)==(e['frame'],e['rate'],e['pwm'],e['commands']),'AP raw actuator decode differs')
            if ap_current is None:
                require(frame==tick==0,'AP did not begin at frame zero')
                ap_frames.append(frame)
            elif frame==ap_current[0]:
                require(frame in (tick,tick-1) and commands==ap_current[1], 'AP duplicate changed controls or age')
                ap_duplicates+=1
            else:
                require(frame==tick==ap_current[0]+1,'AP next-frame no longer maps to model input')
                ap_frames.append(frame)
            ap_current=(frame,commands)
        elif e['kind']=='actuator':
            decoded=common.MAVLink(None).parse_buffer(bytes.fromhex(e['raw_hex']))
            require(len(decoded)==1 and decoded[0].to_dict()==e['message'],'PX raw actuator decode differs')
            message=decoded[0]
            require(message.get_type()=='HIL_ACTUATOR_CONTROLS' and message.flags&1
                    and message.time_usec<=tick*1000 and (px_time is None or message.time_usec>=px_time), 'PX input time differs')
            px_time,px_current=message.time_usec,actuator_commands(message)
        elif e['kind']=='sensor' and e['stack']=='arducopter':
            require(ap_current is not None and ap_current[0]==tick-1==e['source_frame'],'AP control source differs')
            require(model['arducopter'][tick-1][1]==ap_current[1] and model['px4'][tick-1][1]==px_current,
                    'Model input was not the last observed native actuator output')
            require(hashlib.sha256(bytes.fromhex(e['packet_hex'])).hexdigest()==sensors['arducopter'][tick], 'AP sensor payload differs from model')
            pending[tick]=(ap_current[0],px_time); counts['ap_sensor']+=1
        elif e['kind'] in ('sensor','gps'):
            decoded=common.MAVLink(None).parse_buffer(bytes.fromhex(e['raw_hex']))
            wanted=imu['px4'][tick] if e['kind']=='sensor' else gps['px4'][tick]
            require(len(decoded)==1 and decoded[0].to_dict()==wanted,'PX sensor/GPS payload differs from model')
            counts['px_sensor' if e['kind']=='sensor' else 'gps']+=1
        elif e['kind']=='barrier':
            require(tick%4==0 and e['ap_next_frame']==tick and (not e['synchronized'] or e['px4_time_us']==tick*1000), 'Bad input barrier')
            counts['barrier']+=1
        elif e['kind']=='step':
            require(pending[tick]==(e['ap_source_frame'],e['px4_source_time_us'])
                    and e['model_ticks']=={'arducopter':tick,'px4':tick}
                    and ap_current[0]==tick,'Step source identity differs or AP next frame is missing')
            counts['step']+=1
    require(counts==dict(ap_sensor=total,px_sensor=total//4,gps=total//100,step=total,barrier=total//4),'Missing/extra wire steps')
    require(ap_frames==list(range(total+1)),'AP did not acknowledge every model step')
    clock_count=0
    for tick,c in enumerate(lines(root/'clock.jsonl')):
        require(c['epoch']==epoch and c['tick']==tick and c['time_ns']==tick*1000000 and c['pending_tick'] is None,
                'Published scene clock skipped, repeated or fabricated a tick')
        clock_count+=1
    repetitions=r.get('paused_clock_republications',0)+r.get('faulted_clock_republications',0)
    require(type(repetitions) is int and repetitions>=0,'Invalid clock retransmission count')
    if repetitions:
        require(r.get('scene_lifecycle_requested') and (r.get('scene_lifecycle',{}).get('status')=='pass' or r.get('dds_recovery',{}).get('status')=='pass'),
                'Unexpected paused clock publication outside a lifecycle run')
        repeated=0
        for entry in lines(root/'scene-lifecycle.jsonl'):
            if entry['kind'] in ('paused_clock','faulted_clock'):
                repeated+=1
                require(entry['epoch']==epoch and entry['phase'] in ('paused','faulted') and (entry['phase']=='faulted' or entry['tick']%4==0)
                        and entry['time_ns']==entry['tick']*1000000
                        and entry['publication']==entry['tick']+1+repeated,
                        'Paused clock retransmission changed committed time or publication identity')
        require(repeated==repetitions,'Missing raw paused clock publication record')
    require(clock_count==total+1 and r['clock_publications']==clock_count+repetitions,'Clock count differs')
    return dict(total_ticks=total,shared_epoch=epoch,physical=physical,
        simultaneous_height_above_1m_ticks=overlap,wire_counts=counts,ap_identical_duplicates=ap_duplicates,
        clock_publications=r['clock_publications'],unique_clock_ticks=clock_count,
        paused_clock_republications=r.get('paused_clock_republications',0),
        faulted_clock_republications=r.get('faulted_clock_republications',0)),model


def audit(root,verify_current_sources=False):
    from pymavlink.dialects.v20 import common
    r=json.loads((root/'result.json').read_text())
    require(r['status']=='pass' and r['source_unchanged'] and not r['cleanup_errors'],'Run did not pass')
    require(r['unowned_ap_before']==r['unowned_ap_after'],'Unowned AP identity changed')
    total=r['final_authority']['tick']; epoch=r['scene_epoch']
    require(r['bounds']==dict(wall_seconds=900,simulation_ticks=180000,task_position_error_m=.5,
            task_speed_m_s=.5,takeoff_min_height_m=2.5,ground_abs_height_m=.3),'Predeclared bounds changed')
    require(total%4==0 and total<=180000 and r['final_authority']['phase']=='stopped','Bad final authority')
    for name,expected in r['source_sha256'].items():
        require(digest(root/('source__'+name.replace('/','__')+'.txt'))==expected,'Source snapshot differs: '+name)
        if verify_current_sources:
            require(digest(REPO/name)==expected,'Current executed source differs: '+name)
    for stack in ('arducopter','px4'):
        require(json.loads((root/(stack+'-preflight.json')).read_text())['ok'],'Baseline admission failed')
    require(digest(root/'ap-build.json')==r['manifest_sha256']['ap'],'AP manifest changed')
    control=verify_control_candidate(root,r,verify_current_sources)
    ap=json.loads((root/'ap-build.json').read_text())
    require(digest(ap['candidate_root']+'/build/sitl/bin/arducopter')==ap['artifacts']['build/sitl/bin/arducopter']['sha256'],
            'AP binary no longer matches selected build')
    require(len(r['children'])==10,'Unexpected model/FC/Agent/control/task process count')
    for name,child in r['children'].items():
        require(child['identity']['pid']==child['identity']['pgid'] and not child['remaining_group_members'],
                'Invalid or unretired owned group: '+name)
        if name.endswith('-model') or name.endswith('-task'):
            require(child['returncode']==0,'Model/task did not exit normally')
        if name.endswith('-control') and r.get('require_clean_control_exit'):
            require(child['returncode']==0,'Control node did not stop normally')

    task_reports={}; payloads={}; windows={}
    for stack,uid in (('arducopter',1),('px4',2)):
        t=json.loads((root/stack/'result.json').read_text())
        require(t==r['tasks'][stack] and t['status']=='pass' and t['uav_id']==uid
                and t['scene_epoch']==epoch and t['run_id']==r['run_id'] and t['use_sim_time'], 'Task identity differs')
        task=t['task']; events=task['events']; requests=task['request_envelopes']
        require(len(requests)==len(task['sent'])==6,'Expected six public operations')
        for number,request in enumerate(requests,1):
            require(request['version']==1 and request['run_id']==r['run_id']
                    and request['control_epoch']==task['control_epoch'] and request['request_id']==number,
                    'Bad task envelope or replay')
            body=request['setup'] if number in (1,2,3,6) else request['command']
            require(body==task['sent'][number-1],'Envelope differs from sent public payload')
        require(not any(e['event'] in ('setup_rejected','command_rejected','control_revoked') for e in events),
                'Task contains a rejected or revoked operation')
        acks=[e for e in events if e['event']=='native_ack' and e['accepted']]
        require(len(acks)>=6,'Missing native acknowledgements')
        payloads[stack]=[{key:value for key,value in msg.items() if key!='header'} for msg in task['sent']]
        phases={p['phase']:p for p in t['phases']}
        for name in ('hold_completed','waypoint_completed','landed_disarmed_public','normal_stop_ready'):
            require(name in phases,'Missing task completion phase '+name)
        for p in t['phases']:
            require(type(p['ros_time_ns']) is int and 0<p['ros_time_ns']<=total*1000000
                    and p['ros_time_ns']%1000000==0, 'Task time not on scene grid')
            if p['state'] is not None: require(p['state']['uav_id']==uid,'Task consumed another vehicle')
        for finish,start,seconds in (('hold_completed','takeoff_reached',5),('waypoint_completed','waypoint_reached',2)):
            require(phases[finish]['ros_time_ns']-phases[start]['ros_time_ns']>=seconds*10**9,
                    'Task dwell did not cover required scene time')
        final=task['final']['state']
        require(final['uav_id']==uid and final['connected'] and final['odom_valid']
                and not final['armed'] and abs(final['position'][2])<.3,'Not freshly landed/disarmed')
        for row in lines(root/stack/'prometheus.jsonl'):
            if 'topic' in row and row['topic'].startswith('/uav'):
                require(row['topic'].startswith(f'/uav{uid}/prometheus/'),'Public topic crossed vehicle identity')
        task_reports[stack]=dict(uav_id=uid,control_epoch=task['control_epoch'],native_accepted_acks=len(acks),
                                final_ros_ns=t['task_final_ros_ns'])
        windows[stack]=phases
    require(payloads['arducopter']==payloads['px4'],'Public task input sequences differ')
    require(task_reports['arducopter']['control_epoch']!=task_reports['px4']['control_epoch'], 'Control epochs not distinct')

    timeline,_=audit_timeline(root,r,windows)
    artifacts={p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*'))
               if p.is_file() and p.name not in AUDIT_OUTPUTS}
    return dict(status='pass',scope='continuous public joint Task flight only; no pause/recovery or collision acceptance',
                current_source_verification=verify_current_sources,
                control_exit_codes={name:child['returncode'] for name,child in r['children'].items() if name.endswith('-control')},
                tasks=task_reports,**timeline,
                result_sha256=digest(root/'result.json'),evidence_sha256=artifacts)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    p.add_argument('--verify-current-sources',action='store_true');args=p.parse_args()
    report=audit(args.directory,args.verify_current_sources)
    report['audit_source_sha256']=digest(Path(__file__))
    (args.directory/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='evidence_sha256'},indent=2))
