"""Independent per-tick physical/visual audit; raw command audit is a separate gate."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.audit_aruco_scene import rotation,require
from tools.audit_aruco_flight_scene import audit as audit_geometry


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluate_trace(path,epoch,first,end,anchor,anchor_rotation,profile,selected):
    """Every committed physics tick participates; no task/vision estimates used."""
    mission=profile['mission'];desired=np.asarray(profile['controller']['desired_body_flu_m'])
    maximum_error=0.;recovery_max=0.;maximum_tilt=0.;maximum_radius=0.;samples=0
    window_start=None;window_end=None;reference_position=None;final=None;failures=[]
    with path.open() as stream:
        for ordinal,line in enumerate(stream,1):
            require(line.endswith('\n'),'Incomplete physical trace record')
            row=json.loads(line);state=row['state'];final=state
            require(row['tick']==ordinal and row['epoch']==epoch and len(state)==120
                    and all(type(x) in (int,float) and math.isfinite(x) for x in state)
                    and abs(state[2]-ordinal/1000)<1e-8,'Physical identity/time/numeric mismatch')
            if ordinal<first or ordinal>end:continue
            position=np.asarray(state[6:9])*[1,1,-1]
            if reference_position is None:reference_position=position
            q=state[12:16];rot=rotation([-q[1],-q[2],q[3],q[0]])
            tilt=max(abs(x) for x in state[9:11])
            radius=float(np.linalg.norm((position-reference_position)[:2]))
            maximum_tilt=max(maximum_tilt,tilt);maximum_radius=max(maximum_radius,radius)
            if not mission['altitude_min_m']<=position[2]<=mission['altitude_max_m']:
                failures.append(dict(tick=ordinal,gate='altitude',height_m=float(position[2])))
            if tilt>mission['maximum_tilt_rad'] or radius>mission['maximum_position_radius_m']:
                failures.append(dict(tick=ordinal,gate='envelope',tilt_rad=tilt,radius_m=radius))
            if selected:
                movement=np.array([0,min(4000,max(0,ordinal-first-2000))*.00025,0])
                target=anchor+anchor_rotation@np.array([2.3,.32,.06])+movement
                body=((target-position)@rot)*[1,-1,1]
                error=float(np.linalg.norm(body-desired));maximum_error=max(maximum_error,error)
                if error>mission['tracking_error_m']:
                    failures.append(dict(tick=ordinal,gate='tracking',error_m=error))
                if ordinal>=end-mission['recovery_hold_steps']:
                    recovery_max=max(recovery_max,error)
                    if error>mission['recovery_error_m']:
                        failures.append(dict(tick=ordinal,gate='recovery',error_m=error))
            samples+=1;window_start=ordinal if window_start is None else window_start;window_end=ordinal
    require(final is not None and abs(final[8])<.3,'Final model is not landed')
    require(window_start==first and window_end==end and samples==end-first+1,'Physical tracking interval incomplete')
    return dict(status='failed' if failures else 'pass',trace_sha256=digest(path),total_ticks=ordinal,
        from_tick=first,to_tick=end,samples=samples,max_tracking_error_m=maximum_error if selected else None,
        max_final_recovery_error_m=recovery_max if selected else None,max_tilt_rad=maximum_tilt,
        max_radius_m=maximum_radius,final_height_m=-final[8],failure_count=len(failures),failure_examples=failures[:20])


def audit(root):
    root=Path(root);report=json.loads((root/'report.json').read_text())
    profile=json.loads((root/'sources/Simulator/wksim_runtime/aruco-tracking-v1.json').read_text())
    require(profile==report['profile'] and digest(root/'sources/Simulator/wksim_runtime/aruco-tracking-v1.json')==
            report['profile_sha256'],'Tracking budgets differ from retained pre-run profile')
    geometry=audit_geometry(root,experiment=True)
    require(len(report['result']['epochs'])==1,'Unexpected reset/replayed episode')
    epoch_record=report['result']['epochs'][0];epoch=epoch_record['epoch'];result=epoch_record['result']
    directory=root/'run/epochs'/epoch
    require(json.loads((directory/'result.json').read_text())==result,'Retained runtime result differs')
    require(result['experimental'] is True and result['production_admitted'] is False
            and not result['flight_completed'] and not result['changed_sources'] and not result['cleanup_errors'],
            'Candidate scope or source/cleanup integrity differs')
    require(result['authority']['fault'] is None,'Candidate retained an unresolved authority/rate fault')
    require(result['source_sha256']['Simulator/wksim_runtime/aruco-tracking-v1.json']==report['profile_sha256'],
            'Coordinator and actual runtime used different tracking budgets')
    tasks=list(result['tasks'].values())
    require(len(tasks)==2 and {t['stack'] for t in tasks}=={'arducopter','px4'}
            and all(t['status']=='pass' and t['scene_epoch']==epoch for t in tasks),'Incomplete real task execution')
    binding=report['binding'];first=binding['first_step']
    require(json.loads((directory/'aruco/binding.json').read_text())==binding,'Retained trusted binding differs')
    require(binding['profile_sha256']==report['profile_sha256'] and binding['epoch']==epoch,'Binding identity differs')
    scene=json.loads(Path(report['frames'][0]['scene_path']).read_text())
    require(first==scene['first_step'],'Physical target anchor time differs')
    anchor=np.asarray(scene['anchor_position_cm'])/100;rot=rotation(scene['anchor_quaternion_xyzw'])
    end=first+sum(profile['scene'][key] for key in ('initial_steps','moving_steps','occluded_steps','recovery_steps'))
    for task in tasks:
        require(task['task']['aruco']['binding']==dict(first_step=first,stream_id=binding['stream_id'],episode_end_step=end)
                and task['task']['aruco']['profile_sha256']==report['profile_sha256'],
                'Peer/selected task did not consume the same trusted episode binding')
    selected=report['config']['aruco_experiment']['selected_stack']
    proof={stack:evaluate_trace(directory/(stack+'-truth.jsonl'),epoch,first,end,anchor,rot,profile,stack==selected)
           for stack in ('arducopter','px4')}
    return dict(status='pass' if geometry['status']=='pass' and all(v['status']=='pass' for v in proof.values()) else 'failed',
        scope='Physical per-tick tracking, image geometry and camera loss/recovery only; raw DDS/public/native chain remains required',
        report_sha256=digest(root/'report.json'),auditor_sha256=digest(__file__),geometry=geometry,physics=proof)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    try:result=audit(args.root)
    except Exception as error:result=dict(status='failed',error=str(error))
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k not in ('geometry','physics')}))
    raise SystemExit(result['status']!='pass')
