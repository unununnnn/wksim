"""Read-only raw audit of owned model/FC death, freeze and explicit cold reset."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

from audit_joint_flight import digest, lines, require, kinematics
from audit_joint_product import ProductTimeline, audit_product_timeline, cdr_string, lifecycle
from audit_joint_product_lifecycle import recorded_host, retained_identity, raw_public
from Simulator.wksim_core.ap_json import decode_servos, sensor_message
from Simulator.wksim_core.px4_mavlink import actuator_commands, gps_arguments
from Simulator.wksim_runtime.evidence import group_members, write_json
from Simulator.wksim_runtime.joint_actions import validate_request

RUNTIME_NAMES={'arducopter-fc','px4-fc','arducopter-model','px4-model'}
PHYSICAL_KEYS=('epoch','tick','time_ns','last_barrier_tick','last_input_tick','pending_tick',
               'synchronized','single_remaining','recoverable','input_pending')


def read(path):
    return json.loads(path.read_text())


def physical(authority):
    return {key:authority[key] for key in PHYSICAL_KEYS}


def death_identity(directory, item, run_id, target, *, current_host=False):
    """Only the named SIGKILL victim may lack stopping mappings."""
    result=read(directory/'result.json')
    require(result==item['result'] and result['epoch']==item['epoch'] and result['run_id']==run_id,
            'Manager and retained epoch identity differ')
    require(result['status']=='cold_reset' and not result['cleanup_errors'] and result['changed_sources']==[],
            'Retired epoch cleanup/source integrity failed')
    recorded_host(result,item,current_host=current_host)
    for name,sha in result['source_sha256'].items():
        require(digest(directory/'source'/name)==sha,'Retained executed source differs: '+name)
    preflight=read(directory/'preflight.json')
    require(preflight==result['preflight'] and preflight['ok'],'Original admitted identity differs')
    require(target in RUNTIME_NAMES,'Unapproved death target')
    for label in ('ready','stopping'):
        records=result['runtime_images'][label]
        require(set(records)==RUNTIME_NAMES,'Missing runtime image identity')
        for name,record in records.items():
            child=result['children'][name]
            require(all(record['identity'][key]==child['identity'][key] for key in ('pid','pgid','start_ticks'))
                    and child['identity']['pgid']==item['process_identity']
                    and child['returncode']==(-9 if name==target else 0),'Runtime victim/normal exit identity differs')
            if name==target and label=='stopping':
                require(record==dict(state='exited',identity=child['identity'],returncode=-9,maps_available=False),
                        'Victim must explicitly retain unavailable stopping maps')
                continue
            path=directory/record['maps_file']
            require(digest(path)==record['maps_sha256'] and not record['forbidden_libraries'],'Runtime maps differ')
            content=path.read_text()
            require(not any(token in content.lower() for token in
                    ('libgz-','libgazebo','libignition','matlab','coptersim.exe')),'Forbidden runtime image was loaded')
            if current_host:
                require(digest(record['executable'])==record['executable_sha256'],'Executed binary changed after run')
            if name.endswith('-fc'):
                pin=preflight['identities']['ap' if name.startswith('arducopter') else 'px4']
                require(record['executable']==pin['path'] and record['executable_sha256']==pin['sha256'],
                        'Executed firmware differs from admitted firmware')
            else:
                require(preflight['model_library'] in content,'Admitted model missing from mappings')
    for name,child in result['children'].items():
        require(child['identity']['pgid']==item['process_identity'] and child['returncode'] is not None,
                'Unretired/foreign child: '+name)
        if name.endswith('-control'):
            require(child['returncode']==0,'Control failed cleanup: '+name)
    return result


def retirement_timeline(root, r, incomplete_input=None):
    windows=None; require_flight=True; require_ground=False
    pending_model_tick=r["final_authority"]["pending_tick"]
    """Raw parser specialized for a terminal, explicitly unacknowledged input.

    Kept separate from the healthy audit: a missing final native ACK is an
    audited failure boundary, never an accepted healthy step.
    """
    from pymavlink.dialects.v20 import common
    total=r['final_authority']['tick']; epoch=r['scene_epoch']
    if pending_model_tick is not None:
        require(pending_model_tick==total+1==r['final_authority']['pending_tick'],
                'Uncommitted model audit requires the actual one-step pending authority')
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
        require(len(data)==total or pending_model_tick is not None and len(data)==pending_model_tick,
                'Model was stepped a different number of times')
        model[stack]=data; sensors[stack]=sensor_hash; imu[stack]=imu_expected; gps[stack]=gps_expected
        committed=data[:total]
        physical[stack]=dict(max_height_m=max(-d[0][2] for d in committed),final_height_m=-committed[-1][0][2],
            min_waypoint_error_m=min(math.dist(d[0][:3],[3,2,-3]) for d in committed))
        if require_ground: require(abs(physical[stack]['final_height_m'])<.3,'Independent final ground truth failed')
        if require_flight:
            require(physical[stack]['max_height_m']>=2.5
                    and (windows is None or physical[stack]['min_waypoint_error_m']<=.5),'Independent truth failed')
        if windows is not None:
            for finish,start,label in (('hold_completed','takeoff_reached','hold'),('waypoint_completed','waypoint_reached','waypoint')):
                lo=windows[stack][start]['ros_time_ns']//1000000; hi=windows[stack][finish]['ros_time_ns']//1000000
                rows=data[max(0,lo-1):hi]
                error=max((abs(d[0][2]+3) if label=='hold' else math.dist(d[0][:3],[3,2,-3])) for d in rows)
                physical[stack][label+'_truth_max_error_m']=error
                require(error<=(.6 if label=='hold' else .5),'Truth disagrees with task scene-time dwell')
    overlap=sum(-a[0][2]>1 and -b[0][2]>1 for a,b in zip(model['arducopter'][:total],model['px4'][:total]))
    require(not require_flight or overlap>0,'No simultaneous true flight interval')

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
    incomplete=int(incomplete_input is not None)
    require(incomplete_input in (None, 'ap_input', 'px4_input'), 'Unknown terminal input stage')
    require(counts==dict(ap_sensor=total,px_sensor=total//4,gps=total//100,step=total-incomplete,
            barrier=total//4-int(bool(incomplete) and total%4==0)), 'Missing/extra raw wire steps')
    expected_ap=total-int(incomplete_input=='ap_input')
    require(ap_frames==list(range(expected_ap+1)), 'Raw AP acknowledgements differ from terminal input stage')
    authority=r['final_authority']
    require(authority['last_input_tick']==expected_ap and authority['last_barrier_tick']==(total-incomplete)//4*4,
            'Input/barrier authority differs from actual raw ACKs')
    if pending_model_tick is not None:
        require(ap_current[0]==total,'Pending model step lacks its true AP input source')
        for stack,commands in (('arducopter',ap_current[1]),('px4',px_current)):
            if len(model[stack])>total:
                require(model[stack][total][1]==commands,'Uncommitted model input differs from retained native output')
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
    result=dict(total_ticks=total,shared_epoch=epoch,physical=physical,
        simultaneous_height_above_1m_ticks=overlap,wire_counts=counts,ap_identical_duplicates=ap_duplicates,
        clock_publications=r['clock_publications'],unique_clock_ticks=clock_count,
        paused_clock_republications=r.get('paused_clock_republications',0),
        faulted_clock_republications=r.get('faulted_clock_republications',0))
    if pending_model_tick is not None:
        result['uncommitted_model_state']=dict(pending_tick=pending_model_tick,
            retained_model_ticks={name:len(rows) for name,rows in model.items()},
            committed_physical_metrics_only=True,ground_completion_required=require_ground)
    return result,model



def freeze_boundary(flow, retired, directory):
    life=list(lines(directory/'scene-lifecycle.jsonl'))
    faults=read(directory/'faults.json')
    require(faults==retired['faults']==[row['observation'] for row in life if row['kind']=='fault_latched']
            and 1<=len(faults)<=2,'Fault summary differs from original lifecycle')
    allowed_errors={repr(RuntimeError(flow['target']+' exited: -9'))}
    if flow['target'].endswith('-model'):
        allowed_errors.add(repr(RuntimeError('Worker exited without a complete response')))
    if flow['target']=='px4-fc':
        allowed_errors.add(repr(ConnectionError('PX4 simulator TCP closed')))
    require(all(row['error'] in allowed_errors and row['type'] in ('RuntimeError','ConnectionError')
                for row in faults),'Unexpected additional fault cause')
    first=faults[0]; frozen=first['authority']; tick=frozen['tick']
    require(frozen['phase']=='faulted' and not frozen['recoverable'] and not frozen['input_pending'],
            'Death was offered unsafe hot recovery')
    require(any(row['error']==repr(RuntimeError(flow['target']+' exited: -9')) for row in faults),
            'No owned victim exit observation in raw lifecycle')
    for row in faults:
        require(physical(row['authority'])==physical(frozen) and row['authority']['phase']=='faulted',
                'Additional fault advanced physical authority')
    late=flow['late_process_resumed']
    for status in (flow['fault'],late['status']):
        require(status['epoch']==retired['epoch'] and status['phase']=='faulted'
                and physical(status['authority'])==physical(frozen)
                and set(status['allowed_actions'])=={'stop','cold-reset'},'Fault status resumed or advanced authority')
    require(physical(retired['authority'])==physical(frozen) and retired['authority']['phase']=='stopped',
            'Retirement changed frozen physical authority')
    require(late['before']==late['after'] and late['status']['issued_monotonic_s']>flow['fault']['issued_monotonic_s'],
            'Missing later unchanged physical observation')
    require(flow['injection']['monotonic_s']<=first['issued_monotonic_s']<=flow['fault']['issued_monotonic_s'],
            'Fault observation preceded injection')
    inflight=first['physical_inflight']; pending=frozen['pending_tick']
    incomplete=None
    if pending is not None:
        require(pending==tick+1 and inflight['stage']=='model' and inflight['tick']==pending,
                'Uncommitted model stage differs from authority')
    elif inflight is not None:
        incomplete=inflight['stage']
        require(incomplete in ('ap_input','px4_input') and inflight['tick']==tick
                and inflight['model_ticks']==dict(arducopter=tick,px4=tick),'Incomplete input differs from authority')
    for stack in ('arducopter','px4'):
        tail=None
        for row in lines(directory/(stack+'-truth.jsonl')): tail=row
        require(tail==late['after'][stack] and tail['tick'] in (tick,pending)
                and -tail['state'][8]>2.5,'Freeze observation differs from airborne raw model tail')
        channel=first['model_channels'][stack]
        require(channel['last_response_tick'] in (tick,pending), 'RPC channel skipped a tick')
    previous=(-1,-1.);steps=[];barriers=[]
    for row in lines(directory/'wire.jsonl'):
        require(row['tick']>=previous[0] and row['issued_monotonic_s']>=previous[1],'Wire ordering moved backwards')
        previous=(row['tick'],row['issued_monotonic_s'])
        require(row['tick']<=tick,'Uncommitted model reached native wire')
        require(row['issued_monotonic_s']<first['issued_monotonic_s'],'Native wire progressed after death latch')
        if row['kind']=='step':steps.append(row['tick'])
        if row['kind']=='barrier':barriers.append(row)
    require(steps==list(range(1,tick+1-int(incomplete is not None))), 'Completed raw step continuity differs')
    require(any(row['synchronized'] for row in barriers),'No strict dual native barrier')
    synchronized=False
    for row in barriers:
        require(not synchronized or row['synchronized'],'Native synchronization was lost')
        synchronized |= row['synchronized']
    fault_permissions=[]
    for row in life:
        require(row['kind'] not in ('input_recovery_requested','input_recovery_verified','physics_recovery_verified'),
                'Death attempted hot recovery')
        if row['kind']=='permission':
            value=cdr_string(row['cdr_hex'])
            if value['phase']=='faulted':fault_permissions.append(value)
            if value['issued_monotonic_s']>=first['issued_monotonic_s']:
                require(value['tick']==tick and value['phase'] in ('faulted','stopped'),
                        'Post-death lifecycle resumed or advanced')
    require(fault_permissions and all(value['tick']==tick for value in fault_permissions),'Fault permissions differ')
    return first,incomplete


def public_evidence(directory, result, *, ground=False):
    from rclpy.serialization import deserialize_message
    from prometheus_msgs.msg import TextInfo
    from wksim_msgs.msg import SessionState
    counts={1:0,2:0}; events={1:[],2:[]};epochs={1:set(),2:set()}; airborne={1:[],2:[]}
    for row in lines(directory/'public-dds.jsonl'):
        require(row['epoch']==result['epoch'] and 0<=row['tick']<=result['authority']['tick'],
                'Public DDS crossed authority identity/time')
        uid=next((uid for uid in (1,2) if row['topic'].startswith(f'/uav{uid}/prometheus/')),None)
        require(uid is not None,'Unknown public vehicle')
        if row['topic'].endswith('/text_info'):
            value=json.loads(deserialize_message(bytes.fromhex(row['cdr_hex']),TextInfo).message)
            require(value['run_id']==result['run_id'],'Public event crossed run identity')
            events[uid].append(value)
            if ground:
                require(value['event'] not in ('native_ack','setup_completed','command_accepted'),
                        'Cold reset replayed a native task')
        else:
            require(row['topic'].endswith('/v2/state'),'Unknown public topic')
            value=deserialize_message(bytes.fromhex(row['cdr_hex']),SessionState)
            require(value.run_id==result['run_id'] and value.state.uav_id==value.control.uav_id==uid,
                    'Public state identity differs')
            counts[uid]+=1;epochs[uid].add(value.control_epoch)
            if ground:require(not value.state.armed,'Fresh ground epoch armed without an explicit task')
            if value.state.armed and value.state.odom_valid and value.state.connected and value.state.position[2]>2.5:
                airborne[uid].append((row['received_monotonic_s'],value.control_epoch))
    require(all(counts.values()) and all(len(value)==1 for value in epochs.values()),'Missing/changed dual Control identity')
    return events,epochs,airborne,counts


def failed_tasks(directory, result, events, epochs):
    reports={}
    for path in directory.glob('tasks/*/*/result.json'):
        report=read(path);stack=path.parent.name;uid=1 if stack=='arducopter' else 2
        name=stack+'-task-'+path.parent.parent.name
        require(report==result['tasks'][name] and report['status']=='failed' and report['task_mode']=='initial'
                and report['run_id']==result['run_id'] and report['scene_epoch']==result['epoch']
                and result['children'][name]['returncode']==1,'Retired task identity/status differs')
        require(report['task']['control_epoch'] in epochs[uid],'Task consumed another Control epoch')
        require(report['worker_source_sha256']==digest(directory/'source/Simulator/wksim_runtime/joint_task.py'),
                'Task worker differs from retained executed source')
        ready=read(path.parent/'ready.json');go=read(path.parent.parent/'go.json')
        require(ready['run_id']==result['run_id'] and ready['epoch']==result['epoch']
                and ready['control_epoch']==report['task']['control_epoch'] and ready['uav_id']==uid
                and ready['request_high_water']==0
                and go['run_id']==result['run_id'] and go['epoch']==result['epoch'] and go['tasks'][stack]==ready,
                'Task bypassed original ready/go')
        records=list(lines(path.parent/'prometheus.jsonl'))
        requests=[row['message'] for row in records if row.get('request_envelope')]
        payloads=[row['message'] for row in records if 'public_payload' in row]
        require(requests==report['task']['request_envelopes'] and payloads==report['task']['sent']
                and len(requests)>=3,'Task summary differs from original public requests')
        for number,request in enumerate(requests,1):
            require(request['version']==1 and request['run_id']==result['run_id']
                    and request['control_epoch']==report['task']['control_epoch'] and request['request_id']==number,
                    'Task request identity/replay differs')
        require(any(event['event']=='native_ack' and event.get('accepted') and event.get('request_id')==3
                    and event.get('control_epoch')==report['task']['control_epoch'] for event in events[uid]),
                'Airborne task lacks raw native takeoff ACK')
        reports[name]=dict(status='failed',request_ids=[r['request_id'] for r in requests])
    require(set(reports)==set(result['tasks']) and len(reports)==2,'Expected two failed initial tasks only')
    return reports


def audit(evidence, *, current_host=False):
    root=evidence/'run';flow=read(evidence/'flow.json');result=read(root/'result.json')
    require(flow['status']=='pass' and flow['exit_process'] is True and flow['result']==result
            and flow['returncode']==0 and result['status']=='stopped' and not flow['remaining_manager_group'],
            'Driver/manager death flow or cleanup failed')
    require(digest(evidence/'driver.py')==flow['driver_source_sha256'] and '--exit-process' in flow['invocation'],
            'Retained death driver identity differs')
    require(len(result['epochs'])==2,'Expected death and fresh ground epochs')
    old,new=result['epochs'];epoch=old['epoch'];new_epoch=new['epoch'];run_id=result['run_id']
    require(epoch!=new_epoch and all(item['namespace_comparison']=='held_file_descriptors' for item in (old,new))
            and all(old['namespace_objects'][kind]!=new['namespace_objects'][kind] for kind in ('net','ipc','mnt')),
            'Cold reset reused epoch/namespaces')
    first=root/'epochs'/epoch;second=root/'epochs'/new_epoch
    retired=death_identity(first,old,run_id,flow['target'],current_host=current_host)
    ground=retained_identity(second,new,run_id,current_host=current_host)
    require(ground['status']=='stopped' and not ground['tasks'] and not ground['flight_completed']
            and not retired['flight_completed'] and retired['physical_task_proof'] is None,
            'Death falsely completed flight or reset replayed tasks')
    if current_host:require(not group_members(flow['manager']['pgid']),'Current owned manager group remains')
    injection=flow['injection'];victim=retired['children'][flow['target']]
    require(all(injection['identity'][key]==victim['identity'][key] for key in ('pid','pgid','start_ticks'))
            and injection['executable']==retired['runtime_images']['ready'][flow['target']]['executable'],
            'Injection targeted another process/executable identity')
    require('kernel_exited' in injection,'No observed kernel exit')
    kernel=injection['kernel_exited']
    require(kernel is None or kernel==dict(pid=victim['identity']['pid'],pgid=victim['identity']['pgid'],
            start_ticks=victim['identity']['start_ticks'],state='Z'),'Kernel zombie identity differs')
    require(injection['status']['epoch']==epoch and injection['status']['phase']=='running'
            and set(injection['status']['participants'])=={'1','2'}
            and all(v['state']['armed'] and v['state']['position'][2]>2.5
                    for v in injection['status']['participants'].values()),'Death did not occur during dual flight')
    require([row['response']['action'] for row in flow['actions']]==['start-task','cold-reset','stop'],
            'Unexpected death action sequence')
    requests={};responses={}
    for row in flow['actions']:
        request=row['submitted']['request'];response=row['response']
        validate_request(request,run_id,new_epoch if request['action']=='stop' else epoch)
        name=f"{request['command_id']:020d}-{request['token']}.json"
        require(read(root/'actions'/name)==request and read(root/'action-results'/request['epoch']/(request['token']+'.json'))==response
                and response['state']=='completed' and all(response[key]==request[key]
                    for key in ('version','run_id','epoch','command_id','action','token')),
                'Formal action lacks retained matching completion')
        requests[request['action']]=request;responses[request['action']]=response
    require(responses['cold-reset']['new_epoch']==new_epoch and all(a['command_id']<b['command_id']
            for a,b in zip(requests.values(),list(requests.values())[1:])), 'Action order/new epoch differs')
    fault,incomplete=freeze_boundary(flow,retired,first)
    require(requests['cold-reset']['command_id']/1e9>flow['late_process_resumed']['status']['issued_monotonic_s'],
            'Cold reset preceded retained freeze observation')
    timeline,_=retirement_timeline(ProductTimeline(first),dict(final_authority=retired['authority'],
        scene_epoch=epoch,clock_publications=retired['clock_publications']),incomplete)
    lc=lifecycle(first,epoch,retired['authority']['tick'],retired['clock_publications'],run_id)
    events,epochs,airborne,counts=public_evidence(first,retired)
    for uid in (1,2):
        require(any(t<=injection['monotonic_s'] and ce==injection['status']['participants'][str(uid)]['control_epoch']
                    for t,ce in airborne[uid]),'Injection flight lacks preceding raw native airborne DDS')
    tasks=failed_tasks(first,retired,events,epochs)
    reset,strict,reset_lc=audit_product_timeline(second,ground,require_flight=False)
    _,new_epochs,_,ground_counts=public_evidence(second,ground,ground=True)
    raw_public(second,new_epoch,run_id)
    require(all(epochs[uid].isdisjoint(new_epochs[uid]) for uid in (1,2))
            and all(value['max_height_m']<.3 for value in reset['physical'].values()),
            'Fresh ground epoch reused Control identity or moved')
    return dict(status='pass',scope='Owned process death, frozen committed authority, explicit cold reset and stopped fresh ground epoch',
        target=flow['target'],flight_completed=False,epochs=[epoch,new_epoch],tasks=tasks,
        death_boundary=dict(committed_tick=retired['authority']['tick'],pending_tick=retired['authority']['pending_tick'],
                            incomplete_input=incomplete,fault_observations=len(retired['faults']),
                            retained_status_freeze_seconds=flow['late_process_resumed']['status']['issued_monotonic_s']
                                -flow['fault']['issued_monotonic_s']),
        committed_timeline=timeline,reset_timeline=reset,reset_strict_barriers=strict,lifecycle=[lc,reset_lc],
        raw_state_counts=[counts,ground_counts],current_host_verification=current_host,
        limitations=['Victim stopping maps are explicitly unavailable after SIGKILL. Ready mappings and other stopping mappings were checked; this is not complete lifetime no-dependency proof.',
                     'SIGKILL causality uses retained driver identity and kernel exit observations, not an independent kernel signal trace.',
                     'Pending model rows are uncommitted evidence, not rollback, hot recovery or flight completion.',
                     'Cleanup and executable identity are historical unless --current-host checks the matching recorded boot.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--current-host',action='store_true');args=parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.directory.resolve()),'Output must be outside evidence')
    repo=Path(__file__).resolve().parents[1]
    paths=[Path(__file__),repo/'tools/audit_joint_flight.py',repo/'tools/audit_joint_product.py',
           repo/'tools/audit_joint_product_lifecycle.py',repo/'Simulator/wksim_runtime/evidence.py',
           repo/'Simulator/wksim_runtime/joint_actions.py',repo/'Simulator/wksim_runtime/joint_evidence.py',
           repo/'Simulator/wksim_core/ap_json.py',repo/'Simulator/wksim_core/px4_mavlink.py']
    before={str(p.relative_to(repo)):digest(p) for p in paths}
    try:
        report=audit(args.directory,current_host=args.current_host)
        report['evidence_sha256']={str(p.relative_to(args.directory)):digest(p)
                                  for p in sorted(args.directory.rglob('*')) if p.is_file()}
    except (ValueError,KeyError,OSError,TypeError,ImportError,StopIteration,AssertionError,IndexError) as error:
        report=dict(status='failed',error=repr(error))
    after={str(p.relative_to(repo)):digest(p) for p in paths}
    report.update(audit_dependencies_before=before,audit_dependencies_after=after)
    if before!=after: report.update(status='failed',error='Audit dependency changed during execution')
    write_json(args.output,report)
    print(json.dumps({k:v for k,v in report.items() if k!='evidence_sha256'},indent=2))
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
