"""Independent ArduRover/Ackermann reference experiment in a private namespace."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.runtime import stop_children
from Simulator.wksim_runtime.build_identity import source_snapshot
from Simulator.wksim_core.ackermann import AckermannParameters
from Simulator.wksim_planning.ground_path import track_waypoint
from pymavlink import mavutil


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(manifest,checksum,path_controller='pure_pursuit'):
    if sha(manifest)!=checksum:raise ValueError('Rover candidate receipt SHA256 mismatch')
    candidate=json.loads(manifest.read_text());root=manifest.parent
    source=root/'src';binary=root/'build/sitl/bin/ardurover'
    if (root.parent!=Path('/root') or not root.name.startswith('wksim-rover-model-')
            or root.resolve()!=root or candidate['schema']!='wksim.rover-candidate.v1'
            or candidate['firmware_target']!='rover' or candidate['state']!='built'
            or candidate['binary']!=str(binary) or sha(binary)!=candidate['binary_sha256']
            or source_snapshot(source,commit=candidate['upstream_commit'])!=candidate['source']):
        raise ValueError('Rover build/source identity differs')
    if os.readlink('/proc/self/ns/net')==os.readlink('/proc/1/ns/net'):
        raise ValueError('Private network namespace required')
    output=Path(tempfile.mkdtemp(prefix='rover-reference-',dir=REPO/'validation'))
    work=Path(tempfile.mkdtemp(prefix='wksim-rover-run-'))
    print(json.dumps({'output':str(output)}),flush=True)
    model_parameters=AckermannParameters()
    # Native motor output divides steering by speed above MOT_SPD_SCA_BASE.
    # Match that convention to this model's steering angle, rather than using
    # the stock rover demo's unrelated feed-forward and minimum turn radius.
    steering_ff=model_parameters.wheelbase_m/model_parameters.max_steering_rad
    turn_radius=model_parameters.wheelbase_m/math.tan(model_parameters.max_steering_rad)
    parameters=f'''SERVO1_FUNCTION 26
SERVO3_FUNCTION 70
SERVO1_MIN 1000
SERVO1_MAX 2000
SERVO1_TRIM 1500
SERVO3_MIN 1000
SERVO3_MAX 2000
SERVO3_TRIM 1500
ARMING_SKIPCHK 0
SIM_RATE_HZ 1000
CRUISE_SPEED 2
CRUISE_THROTTLE 40
WP_SPEED 2
WP_RADIUS 0.75
GUID_OPTIONS 64
MOT_SPD_SCA_BASE 1
ATC_STR_RAT_FF {steering_ff:.9f}
TURN_RADIUS {turn_radius:.9f}
LOG_DISARMED 1
'''
    (work/'vehicle.parm').write_text(parameters)
    result=dict(status='failed',candidate_manifest=str(manifest),candidate_sha256=checksum,
        binary_sha256=sha(binary),vehicle_class='ground_vehicle',model_profile='ackermann_v1',
        controller='native_rover',path_controller=path_controller,firmware_inner_loop_replaced=False,
        scope='Flat-ground kinematic reference; no tire/suspension/fixed-wing acceptance',
        thresholds=dict(waypoint_distance_m=.75,stop_speed_m_s=.35,dwell_sim_s=2.,truth_distance_m=1.,wall_budget_s=150),
        waypoints=[[5.,0.],[5.,5.]],events=[],parameters=parameters,model_parameters=asdict(model_parameters),work_directory=str(work),
        source_sha256={name:sha(REPO/name) for name in ('tools/run_rover_experiment.py',
            'Simulator/wksim_core/ackermann.py','Simulator/wksim_core/rover_json.py',
            'Simulator/wksim_core/vehicle_models.py','Simulator/wksim_core/vehicle_state.py',
            'Simulator/wksim_core/actuator_layout.py','Simulator/wksim_planning/ground_path.py')})
    (output/'protocol.json').write_text(json.dumps(result,indent=2)+'\n')
    children=[];latest={};statuses=[];started=time.monotonic();heartbeat=0.;target=None;last_target=None;halt_for_dwell=False
    link=mavutil.mavlink_connection('udpin:127.0.0.1:14660',source_system=245)
    log=(output/'telemetry.jsonl').open('w',buffering=1)
    def launch(name,argv,cwd):
        stream=(output/(name+'.log')).open('w')
        child=subprocess.Popen(argv,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        children.append((name,child,stream))
    def pump():
        nonlocal heartbeat,last_target
        now=time.monotonic()
        if now-started>150:raise TimeoutError('Rover experiment wall budget')
        for name,child,_ in children:
            if child.poll() is not None:raise RuntimeError(name+' exited')
        if now-heartbeat>=1:
            link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,mavutil.mavlink.MAV_AUTOPILOT_INVALID,0,0,0)
            heartbeat=now
        if target is not None and 'LOCAL_POSITION_NED' in latest:
            state=latest['LOCAL_POSITION_NED']
            if path_controller=='native_scurve' and target!=last_target:
                link.mav.set_position_target_local_ned_send(state.time_boot_ms,241,1,
                    mavutil.mavlink.MAV_FRAME_LOCAL_NED,0xDF8,target[0],target[1],0,0,0,0,0,0,0,0,0)
                last_target=list(target)
            elif path_controller=='pure_pursuit' and state.time_boot_ms!=last_target and 'ATTITUDE' in latest:
                desired=track_waypoint((state.x,state.y),latest['ATTITUDE'].yaw,target,
                    minimum_turn_radius_m=turn_radius)
                link.mav.set_position_target_local_ned_send(state.time_boot_ms,241,1,
                    mavutil.mavlink.MAV_FRAME_BODY_NED,0x5C7,0,0,0,0. if halt_for_dwell else desired.speed_m_s,
                    0,0,0,0,0,0,0. if halt_for_dwell else desired.turn_rate_rad_s)
                last_target=state.time_boot_ms
        message=link.recv_match(blocking=True,timeout=.04)
        if message is None or message.get_srcSystem()!=241 or message.get_type()=='BAD_DATA':return
        latest[message.get_type()]=message
        log.write(json.dumps(message.to_dict())+'\n')
        if message.get_type()=='STATUSTEXT':
            statuses.append(message.text);print(message.text,flush=True)
    def wait(label,predicate,seconds=30):
        deadline=time.monotonic()+seconds
        while not predicate():
            if time.monotonic()>deadline:raise TimeoutError(label+': '+repr(statuses[-8:]))
            pump()
        result['events'].append(dict(event=label,wall_s=time.monotonic()-started,
            position=latest['LOCAL_POSITION_NED'].to_dict() if 'LOCAL_POSITION_NED' in latest else None))
        print(label,flush=True)
    def command(number,params):
        latest.pop('COMMAND_ACK',None)
        link.mav.command_long_send(241,1,number,0,*params)
        wait('ACK '+str(number),lambda:'COMMAND_ACK' in latest and latest['COMMAND_ACK'].command==number,8)
        if latest['COMMAND_ACK'].result!=0:raise ValueError('Command rejected: '+repr(latest['COMMAND_ACK'].to_dict()))
    def interrupted(*_):raise InterruptedError('Rover experiment interrupted')
    old={sig:signal.signal(sig,interrupted) for sig in (signal.SIGTERM,signal.SIGINT)}
    try:
        launch('physics',[sys.executable,'-m','Simulator.wksim_core.rover_json','--trace',str(output/'truth.jsonl')],REPO)
        defaults=str(source/'Tools/autotest/default_params/rover.parm')+','+str(work/'vehicle.parm')
        launch('rover',[str(binary),'--model','JSON:127.0.0.1','--rate','1000','--speedup','3',
            '--base-port','16600','--instance','11','--sysid','241','--sim-address','127.0.0.1',
            '--sim-port-out','19002','--sim-port-in','19003','--rc-in-port','19004',
            '--serial0','udpclient:127.0.0.1:14660','--serial1','none','--serial2','none',
            '--defaults',defaults,'--home','40.1540302,116.2593683,50,0'],work)
        wait('heartbeat',lambda:'HEARTBEAT' in latest,25)
        for msg in (32,24,33,30,193):link.mav.command_long_send(241,1,511,0,msg,100000,0,0,0,0,0)
        wait('position ready',lambda:'LOCAL_POSITION_NED' in latest and 'GPS_RAW_INT' in latest and latest['GPS_RAW_INT'].fix_type>=3,40)
        result['verified_parameters']={}
        for line in parameters.strip().splitlines():
            name,expected=line.split()
            latest.pop('PARAM_VALUE',None)
            link.mav.param_request_read_send(241,1,name.encode(),-1)
            wait('parameter '+name,lambda:'PARAM_VALUE' in latest and latest['PARAM_VALUE'].param_id==name,5)
            actual=latest['PARAM_VALUE'].param_value
            if abs(actual-float(expected))>1e-6:raise ValueError('Native parameter differs: '+name)
            result['verified_parameters'][name]=actual
        link.mav.set_mode_send(241,mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,15)
        wait('GUIDED',lambda:latest['HEARTBEAT'].custom_mode==15)
        command(400,[1,0,0,0,0,0,0])
        wait('armed',lambda:bool(latest['HEARTBEAT'].base_mode&128))
        for point in result['waypoints']:
            target=point;halt_for_dwell=False
            def reached():
                p=latest['LOCAL_POSITION_NED']
                return math.hypot(p.x-point[0],p.y-point[1])<=.75 and math.hypot(p.vx,p.vy)<=.35
            wait('waypoint '+repr(point),reached,35)
            halt_for_dwell=True
            began=latest['LOCAL_POSITION_NED'].time_boot_ms
            while latest['LOCAL_POSITION_NED'].time_boot_ms-began<2000:
                pump()
                if not reached():raise ValueError('Waypoint stopped dwell lost')
        target=None
        link.mav.set_mode_send(241,mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,4)
        wait('HOLD',lambda:latest['HEARTBEAT'].custom_mode==4)
        command(400,[0,0,0,0,0,0,0])
        wait('disarmed',lambda:not latest['HEARTBEAT'].base_mode&128)
        truth=[json.loads(line) for line in (output/'truth.jsonl').read_text().splitlines()]
        final=truth[-1]['state'];error=math.dist(final['position_ned_m'][:2],result['waypoints'][-1])
        if error>1.:raise ValueError('Physical ground truth missed the final target')
        result.update(status='pass',final_truth=final,final_truth_error_m=error,truth_records=len(truth))
    except Exception as error:
        result['error']=repr(error)
        raise
    finally:
        result['cleanup_errors']=stop_children(children)
        link.close();log.close()
        for sig,handler in old.items():signal.signal(sig,handler)
        if result['cleanup_errors']:result['status']='failed'
        result['binary_unchanged']=sha(binary)==candidate['binary_sha256']
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'result':str(output/'result.json'),'status':result['status']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--path-controller',choices=['pure_pursuit','native_scurve'],default='pure_pursuit')
    args=parser.parse_args()
    run(args.manifest,args.sha256,args.path_controller)
