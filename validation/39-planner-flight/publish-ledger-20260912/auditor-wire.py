"""Read-only audit of moving P+V handoff -> public BRAKE -> LAND, not Full/EGO/PV acceptance."""
import hashlib
import json
import math
from pathlib import Path


def require(condition, message):
    if not condition: raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def enu(state):
    return [state[7],state[6],-state[8]],[state[4],state[3],-state[5]]


def stop_metrics(state, anchor):
    position,velocity=enu(state)
    speed,drift=math.hypot(*velocity),math.dist(position,anchor)
    require(math.isfinite(speed) and speed<=.25,'1ms stop speed exceeded .25m/s')
    require(math.isfinite(drift) and drift<=1.,'1ms stop drift exceeded 1m from original anchor')
    return speed,drift


def tick_of(ns):
    require(type(ns) is int and ns>0 and ns%1000000==0,'off-grid physical time')
    return ns//1000000


def event_id_contiguous(event_ids):
    '''Source-assigned ControlNode emission counter (node.py event(): self.event_id += 1
    BEFORE publish).  Contiguity of the RECEIVED ids from first to last proves no
    TextInfo loss inside that range even under BEST_EFFORT capture; it says nothing
    about events outside the range, which the caller scopes explicitly.'''
    ids=sorted(set(event_ids))
    require(ids and all(b==a+1 for a,b in zip(ids,ids[1:])),'source event_id gap: TextInfo delivery loss in range')
    return ids

def publication_records(log_path):
    """Record of calls to the owned Task publish path, written BEFORE publish.

    Completion is anchored separately to the normally completed Task report;
    this is not a claim about every possible writer or network delivery.
    """
    records=[]
    with Path(log_path).open('r',encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if not row.get('request_envelope'):continue
            require(row.get('published') in ('CommandRequest','SetupRequest'),'unknown publication record')
            records.append(row['message'])
    return records


def published_envelopes(log_path):
    records=publication_records(log_path)
    return ([(m['request_id'],m['command']['command_id']) for m in records if 'command' in m],
            [(m['request_id'],m['setup']['px4_mode']) for m in records if 'setup' in m])


def verify_publication_coverage(ledger,completed,captured,*,run_id,control_epoch,wire_value=None):
    """Compare full messages; cross-topic arrival order need not equal emission order."""
    require(ledger==completed,'publish ledger differs from completed Task report')
    for records in (ledger,captured):
        require(records and all(type(m.get('request_id')) is int and m['request_id']>0
                and m.get('version')==1 and m.get('run_id')==run_id
                and m.get('control_epoch')==control_epoch
                and (('command' in m)^('setup' in m)) for m in records),'publication identity malformed')
        require(len({m['request_id'] for m in records})==len(records),'duplicate publication ID')
    require(all(b['request_id']>a['request_id'] for a,b in zip(ledger,ledger[1:])),
            'source request IDs not increasing')
    # Task logs precede ROS serialization: canonicalize via the frozen wire types,
    # never by a numeric tolerance (notably Python float vs ROS float32 yaw_ref).
    encoded=[wire_value(message) for message in ledger] if wire_value else ledger
    require(encoded==sorted(captured,key=lambda m:m['request_id']),
            'publish ledger and captured envelopes differ')
    return dict(requests=len(ledger),first_request_id=ledger[0]['request_id'],
                last_request_id=ledger[-1]['request_id'])


def audit(root):
    root=Path(root).resolve(strict=True)
    result=json.loads((root/'result.json').read_text())
    require(result['status']=='observed' and result['planner_release_proof'] is True
            and result['nominal_pv_acceptance'] is False and result['flight_completed'] is False,
            'requires explicit successful release observation')
    require(result['source_unchanged'] and result['planner_control_unchanged'] and result['message_unchanged']
            and result['control_shutdown_clean'] and not result['cleanup_errors'],'run integrity or cleanup failed')
    require(len(result['children'])==10 and all(not c['remaining_group_members'] for c in result['children'].values()),
            'original child groups not empty')
    require(result['unowned_ap_before']==result['unowned_ap_after'],'unowned process identity changed')
    epoch=result['scene_epoch'];final=result['final_authority']
    require(final['epoch']==epoch and final['phase']=='stopped' and final['fault'] is None
            and final['tick']==final['last_barrier_tick']==final['last_input_tick']
            and final['pending_tick'] is None,'final native barrier incomplete')
    ticks=final['tick']
    for name,expected in result['source_sha256'].items():
        require(sha(root/('source__'+name.replace('/','__')+'.txt'))==expected,'retained source changed: '+name)
    require(sha(root/'control-build.json')==result['manifest_sha256']['control'],'Control manifest changed')
    control=json.loads((root/'control-build.json').read_text())
    for name,expected in control['simulator_python_sha256'].items():
        retained=root/('source__Simulator__'+name.replace('/','__')+'.txt')
        require(sha(retained)==expected,'retained installed Simulator bytes differ: '+name)
    ap=result['tasks']['arducopter'];task=ap['task'];stop=task['release_stop'];release=task['release']
    require(ap['status']=='pass' and task['experiment']=='planner_public_release','AP task not completed')
    require(release==json.loads((root/'arducopter/planner-release/planner-release-handoff.json').read_text()),
            'helper record differs from task report')
    require(release['outcome']=='release_confirmed_observed' and release['child_returncode']==0
            and release['child_teardown'] in ('terminated','already_exited'),'planner child not retired normally')
    require(release['child']['pgid']==result['children']['arducopter-task']['identity']['pgid'],'planner escaped task group')
    require(release['timestamps']['node_spawned_ros_ns']==release['timestamps']['warm_ready_ros_ns']==0,'prewarm not at clock zero')
    bound=release['planner_bound'];request=release['verified_request_high_water']+1
    require(bound==dict(run_id=result['run_id'],control_epoch=task['control_epoch'],
                       request_high_water=request-1,command_high_water=release['verified_command_high_water']),
            'binding identity or high waters differ')
    require(release['adopted_request_high_water']==request,'release request not adopted exactly')
    require(result['planner_executed_modules']==release['planner_loaded_modules'],'child module report differs')
    prefix=Path(control['package']).parent/'Simulator'
    for name,record in release['planner_loaded_modules'].items():
        relative=Path(record['path']).relative_to(prefix).as_posix()
        module_path=name.removeprefix('Simulator.').replace('.','/')
        require(relative in (module_path+'.py',module_path+'/__init__.py')
                and control['simulator_python_sha256'].get(relative)==record['sha256'],'unsealed executed module')
    lo,hi=tick_of(stop['hold_start_ros_ns']),tick_of(stop['hold_end_ros_ns'])
    require(stop['hold_start_ros_ns']-stop['confirmed_ros_ns']>=2000000000
            and hi-lo>=4000,'stop preparation or hold window shortened')
    movement_tick=tick_of(stop['requested_ros_ns'])
    require(0<movement_tick<tick_of(stop['confirmed_ros_ns'])<lo<hi<=ticks,'release windows out of order or incomplete')
    require(math.hypot(*stop['pre_release_velocity'])>.25,'public state did not show pre-release movement')
    events=[row['event'] for row in release['events']]
    ack=[e for e in events if e['event']=='native_ack'];done=[e for e in events if e['event']=='setup_completed']
    require(len(ack)==len(done)==1,'two-phase release evidence absent or duplicated')
    ack,done=ack[0],done[0]
    for event in (ack,done):
        require(event['run_id']==result['run_id'] and event['control_epoch']==task['control_epoch']
                and event['request_id']==request,'release event identity mismatch')
    require(ack['accepted'] is True and ack['stage']=='simple' and done['action']=='mode'
            and done['value']==done['native_mode']=='BRAKE'
            and ack['event_id']<done['event_id'] and ack['emitted_monotonic_ns']<=done['emitted_monotonic_ns'],
            'release ACK/native mode order differs')
    require(0<=release['timestamps']['release_confirmed_ros_ns']-release['timestamps']['cancel_sent_ros_ns']<10000000000,
            'release confirmation outside original deadline')
    hashes={'result.json':sha(root/'result.json')};physical={}
    for stack in ('arducopter','px4'):
        report=result['tasks'][stack];record=report['task'];leg=record['pv_legs'][0]
        phases={p['phase']:p['ros_time_ns'] for p in report['phases']}
        require(report['status']=='pass' and report['run_id']==result['run_id'] and report['scene_epoch']==epoch,
                'task identity/completion differs')
        require(record['final']['state']['armed'] is False and record['final']['state']['connected'] is True
                and record['final']['state']['odom_valid'] is True and abs(record['final']['state']['position'][2])<.3,
                'public final state not grounded/disarmed')
        start=tick_of(leg['offer']['start_ns'])
        endpoint=movement_tick if stack=='arducopter' else start+12000
        window=(lo,hi,stop['anchor']) if stack=='arducopter' else (
            tick_of(phases['pv_1_stop_prepared']),tick_of(phases['pv_1_stop_held']),leg['stop_anchor'])
        require(window[1]-window[0]>=4000 and start<endpoint<=window[0]<window[1]<=ticks,'invalid physical windows')
        require(window[1]<tick_of(phases['landed_disarmed_public'])<=tick_of(phases['normal_stop_ready'])<=ticks,
                'landing phase outside complete truth')
        metrics=dict(samples=0,stop_samples=0,max_stop_speed=0.,max_stop_drift=0.,
                     max_position_error=0.,max_velocity_error=0.,max_yaw_error=0.)
        digest=hashlib.sha256(); previous=0;last=None
        with (root/(stack+'-truth.jsonl')).open('rb') as stream:
            for line in stream:
                digest.update(line);row=json.loads(line);tick=row['tick'];state=row['state']
                require(row['version']==1 and row['epoch']==epoch and tick==previous+1,'1ms truth gap or identity change')
                require(all(math.isfinite(x) for x in state[:13]),'nonfinite kinematics')
                previous=tick;last=state;metrics['samples']+=1
                if start<=tick<=endpoint:
                    t=(tick-start)/1000.;s=min(1.,max(0.,t/12.));q=s**3*(10+s*(-15+6*s));dq=30*s*s*(1-s)**2/12.
                    position,velocity=enu(state);delta=(1.5,1.,.4)
                    target=[a+b*q for a,b in zip(leg['ready']['position'],delta)]
                    p=math.dist(position,target);v=max(abs(a-b*dq) for a,b in zip(velocity,delta))
                    yaw=math.pi/2-state[11];target_yaw=leg['ready']['yaw']+.6*q
                    heading=abs((yaw-target_yaw+math.pi)%(2*math.pi)-math.pi)
                    require(p<=.5 and v<=.3 and heading<=.15,'1ms P+V tracking gate exceeded')
                    metrics['max_position_error']=max(metrics['max_position_error'],p)
                    metrics['max_velocity_error']=max(metrics['max_velocity_error'],v)
                    metrics['max_yaw_error']=max(metrics['max_yaw_error'],heading)
                if stack=='arducopter' and tick==movement_tick:
                    metrics['pre_release_speed']=math.hypot(*state[3:6])
                    require(metrics['pre_release_speed']>.25,'physical truth not moving at handoff')
                if window[0]<=tick<=window[1]:
                    speed,drift=stop_metrics(state,window[2]);metrics['stop_samples']+=1
                    metrics['max_stop_speed']=max(metrics['max_stop_speed'],speed)
                    metrics['max_stop_drift']=max(metrics['max_stop_drift'],drift)
                if tick==tick_of(phases['landed_disarmed_public']):require(abs(state[8])<.3,'physical touchdown not grounded')
        require(previous==ticks and metrics['stop_samples']==window[1]-window[0]+1 and abs(last[8])<.3,'incomplete truth/final ground')
        physical[stack]=metrics;hashes[stack+'-truth.jsonl']=digest.hexdigest()
    # Deserialize the independently captured DDS stream with the frozen generated messages.
    from rclpy.serialization import deserialize_message,serialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.set_message import set_message_fields
    from prometheus_msgs.msg import TextInfo
    from wksim_msgs.msg import SetupRequest,CommandRequest,SessionState
    observed_events=[];setups=[];commands=[];sequence=0;digest=hashlib.sha256();text_event_ids={}
    native_events={'arducopter':[],'px4':[]};ap_land=[];px4_land=[];px4_commands=[];final_states={}
    captured_public={'arducopter':[],'px4':[]}
    with (root/'pv-dds.jsonl').open('rb') as stream:
        for line in stream:
            digest.update(line);row=json.loads(line)
            require(row['sequence']==sequence+1 and row['epoch']==epoch and 0<=row['tick']<=ticks,
                    'capture reader order/identity change (probe-local sequence is NOT delivery proof)')
            sequence=row['sequence'];topic=row['topic']
            cls={'/uav1/prometheus/text_info':TextInfo,'/uav1/prometheus/v2/setup':SetupRequest,
                 '/uav1/prometheus/v2/command':CommandRequest,
                 '/uav2/prometheus/text_info':TextInfo,'/uav2/prometheus/v2/command':CommandRequest,
                 '/uav2/prometheus/v2/setup':SetupRequest,
                 '/uav1/prometheus/v2/state':SessionState,'/uav2/prometheus/v2/state':SessionState}.get(topic)
            if cls is None:continue
            msg=deserialize_message(bytes.fromhex(row['cdr_hex']),cls)
            if cls in (SetupRequest,CommandRequest):
                actor='arducopter' if topic.startswith('/uav1/') else 'px4'
                captured_public[actor].append(message_to_ordereddict(msg))
            if cls is SessionState:
                stack='arducopter' if topic.startswith('/uav1/') else 'px4'
                uid=1 if stack=='arducopter' else 2
                require(msg.version==1 and msg.run_id==result['run_id']
                        and msg.control_epoch==result['tasks'][stack]['task']['control_epoch']
                        and msg.state.uav_id==msg.control.uav_id==uid,'public state identity differs')
                final_states[stack]=msg
            elif cls is TextInfo:
                event=json.loads(msg.message)
                stack='arducopter' if topic.startswith('/uav1/') else 'px4'
                if (event.get('version')==1 and event.get('run_id')==result['run_id']
                        and event.get('control_epoch')==result['tasks'][stack]['task']['control_epoch']):
                    require(type(event.get('event_id')) is int,'captured event lacks source event_id')
                    text_event_ids.setdefault(topic,[]).append(event['event_id'])
                    native_events[stack].append((event,msg.message_type))
                if event in (ack,done):
                    require(msg.message_type==TextInfo.INFO,'release event type mismatch')
                    observed_events.append(event)
            elif cls is SetupRequest:
                if not topic.startswith('/uav1/'):continue
                if msg.setup.px4_mode=='AUTO.LAND':
                    require(msg.version==1 and msg.run_id==result['run_id'] and msg.control_epoch==task['control_epoch']
                            and msg.setup.cmd==1 and msg.request_id==request+1,'AP LAND identity differs')
                    ap_land.append(msg.request_id)
                if msg.request_id==request:
                    require(msg.run_id==result['run_id'] and msg.control_epoch==task['control_epoch']
                            and msg.setup.cmd==1 and msg.setup.px4_mode=='BRAKE','actual public release request differs')
                    setups.append(msg.request_id)
            elif topic.startswith('/uav1/'):commands.append((msg.request_id,msg.command.command_id))
            else:
                px4_commands.append((msg.request_id,msg.command.command_id))
                if msg.command.agent_cmd!=msg.command.LAND:continue
                require(msg.version==1 and msg.run_id==result['run_id']
                        and msg.control_epoch==result['tasks']['px4']['task']['control_epoch']
                        and msg.command.control_level==msg.command.EXIT_ABSOLUTE_CONTROL,'PX4 LAND identity/mode differs')
                px4_land.append((msg.request_id,msg.command.command_id))
    # TextInfo delivery completeness within the observed range is proven by the
    # SOURCE-assigned ControlNode event_id counter, never by the probe-local
    # capture sequence (BEST_EFFORT: a lost datagram is simply absent there).
    text_event_ranges={}
    for topic,ids in text_event_ids.items():
        ordered=event_id_contiguous(ids)
        text_event_ranges[topic]=dict(first=ordered[0],last=ordered[-1],count=len(ordered))
    require(set(text_event_ranges)=={'/uav1/prometheus/text_info','/uav2/prometheus/text_info'},
            'source event stream missing for a vehicle')
    require(observed_events==[ack,done] and setups==[request],'independent DDS release correlation failed')
    def wire_value(message):
        cls=CommandRequest if 'command' in message else SetupRequest
        generated=cls()
        set_message_fields(generated,message)
        return message_to_ordereddict(deserialize_message(serialize_message(generated),cls))

    # Anchor owned-writer publication logs to normally completed Task reports,
    # then compare full captured envelopes. The helper is a distinct AP writer.
    publish_proof={}
    for stack,captured in captured_public.items():
        ledger_path=root/stack/'prometheus.jsonl'
        require(ledger_path.is_file(),f'publish-side ledger missing for {stack}: source coverage unproven')
        ledger=publication_records(ledger_path)
        report=result['tasks'][stack]
        require(json.loads((root/stack/'result.json').read_text())==report,'standalone Task report differs')
        expected=report['task']['request_envelopes']
        owned_capture=[m for m in captured if not (stack=='arducopter' and 'setup' in m and m['request_id']==request)]
        proof=verify_publication_coverage(ledger,expected,owned_capture,
                run_id=result['run_id'],control_epoch=report['task']['control_epoch'],wire_value=wire_value)
        hashes[stack+'/prometheus.jsonl']=sha(ledger_path)
        hashes[stack+'/result.json']=sha(root/stack/'result.json')
        sent_commands=[(m['request_id'],m['command']['command_id']) for m in ledger if 'command' in m]
        if stack=='arducopter':
            require(sent_commands[-1]==(request-1,release['verified_command_high_water']),
                    'AP source commands continued beyond handoff')
            require([m['request_id'] for m in ledger]==list(range(1,request))+[request+1,request+2],
                    'AP source request prefix or completion suffix differs')
        else:
            require([m['request_id'] for m in ledger]==list(range(1,ledger[-1]['request_id']+1)),
                    'PX4 source request prefix has a gap')
        proof['sent_commands']=len(sent_commands)
        proof['last_command_id']=sent_commands[-1][1]
        publish_proof[stack]=proof
    for command_rows in (commands,px4_commands):
        require(command_rows and all(b[0]>a[0] and b[1]>a[1] for a,b in zip(command_rows,command_rows[1:])),
                'public command/request IDs are not strictly increasing')
    require(set(final_states)=={'arducopter','px4'},'final public SessionState missing')
    final_public={}
    for stack,msg in final_states.items():
        require(msg.state.armed is False and msg.state.connected and msg.state.odom_valid
                and not msg.control.failsafe and msg.state.header.frame_id=='map'
                and abs(float(msg.state.position[2]))<.3 and msg.source_received_valid
                and 0<=msg.published_monotonic_s-msg.source_received_monotonic_s<=2,
                'final captured public state not fresh, grounded and disarmed')
        require(msg.last_request_id==publish_proof[stack]['last_request_id'],'final public request counter differs from Task completion')
        final_public[stack]=dict(armed=msg.state.armed,mode=msg.state.mode,
                                last_request_id=msg.last_request_id,
                                position=[float(v) for v in msg.state.position])
    require(ap_land==[request+1] and len(px4_land)==1,'actual LAND request missing or duplicated')
    land_proof={}
    for stack,land_id in (('arducopter',ap_land[0]),('px4',px4_land[0][0])):
        entries=[(e,t) for e,t in native_events[stack] if e.get('request_id')==land_id]
        native=[e for e,t in entries if e['event']=='native_ack' and t==TextInfo.INFO]
        confirmations=[e for e,t in entries if e['event']==('setup_completed' if stack=='arducopter' else 'land_mode_confirmed') and t==TextInfo.INFO]
        require(len(native)==len(confirmations)==1,'native LAND acknowledgement missing')
        n,c=native[0],confirmations[0]
        require(n['accepted'] is True and n['stage']==('simple' if stack=='arducopter' else 'land')
                and n['event_id']<c['event_id'] and n['emitted_monotonic_ns']<=c['emitted_monotonic_ns'],'native LAND acknowledgement order differs')
        if stack=='arducopter':require(c['action']=='mode' and c['value']=='AUTO.LAND' and c['native_mode']=='LAND','AP LAND mode not observed')
        else:require(any(e['event']=='command_accepted' and e.get('command_id')==px4_land[0][1] and t==TextInfo.INFO for e,t in entries),'PX4 LAND command not accepted')
        land_proof[stack]=dict(request_id=land_id,native_ack=n,mode_confirmation=c)
    hashes['pv-dds.jsonl']=digest.hexdigest()
    groups=0;worst=0;previous_start=None;digest=hashlib.sha256()
    with (root/'rate.jsonl').open('rb') as stream:
        for line in stream:
            digest.update(line);row=json.loads(line)
            require(row['epoch']==epoch and row['kind']!='rate_unmet','rate fault present')
            if row['kind'] in ('rate_group_start','rate_group_end'):
                require(row['requested_rate']==.5 and row['end_tick']-row['start_tick']==4,'rate/step altered')
                require(row['lateness_ns']<=100000000,'original lateness bound exceeded')
                worst=max(worst,row['lateness_ns'])
            if row['kind']=='rate_group_start':
                if previous_start is not None:require(row['actual_start_ns']>=previous_start+8000000,'catch-up burst')
                previous_start=row['actual_start_ns']
            if row['kind']=='rate_group_end':groups+=1
    require(groups==result['rate']['completed_groups'] and worst==result['rate']['worst_lateness_ns'],'rate summary differs from raw')
    hashes['rate.jsonl']=digest.hexdigest()
    return dict(status='pass',scope='moving P+V handoff, public BRAKE and two-vehicle LAND only',
                full_acceptance=False,nominal_pv_acceptance=False,ego_obstacle_flight=False,
                run_id=result['run_id'],epoch=epoch,request_id=request,physical=physical,landing=land_proof,final_public=final_public,
                dds_capture_messages=sequence,
                dds_capture_delivery='Observed owned-Task envelopes match complete Task reports and source logs; event_id continuity covers only observed endpoints. BEST_EFFORT loss outside these bounded records and arbitrary other write attempts remain unproven',
                text_event_ranges=text_event_ranges,publish_side_proof=publish_proof,
                rate_groups=groups,worst_lateness_ns=worst,evidence_sha256=hashes)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root');parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:report=audit(args.root)
    except Exception as error:report=dict(status='failed',error=repr(error),full_acceptance=False)
    report['auditor_sha256']=sha(__file__)
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['status']=='pass' else 1)
