"""Audit real airborne case5 geometry and enable timing, not target-following flight."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.audit_aruco_scene import rotation,require


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(root, *, experiment=False):
    report=json.loads((root/'report.json').read_text())
    if experiment:
        from Simulator.wksim_runtime.joint_aruco_profile import TASK
        require(report['status']=='captured_pending_independent_audit' and report['config']['task']==TASK,
                'Not an acquired tracking experiment')
        require(report['manager_returncode']==0 and report['result']['status']=='stopped','Candidate retirement incomplete')
    else:
        require(report['status']=='acquired_airborne_scene' and report['flight_scene'],'Not an acquired flight scene')
        require(report['manager_returncode']==0 and report['result']['status']=='pass','Mission/retirement incomplete')
    require(report['result']['epochs'] and all(not e['remaining_group_members'] for e in report['result']['epochs']),'Live epoch groups')
    require(not report.get('cleanup_error') and not report.get('retention_error'),'Cleanup/retention failed')
    return inspect_geometry(root,report,experiment=experiment)


def inspect_geometry(root,report,*,experiment=False):
    """Content-only measurement; callers still owe lifecycle/rate acceptance."""
    initial=report['initial_scene']
    require(initial['case_id']==5 and not initial['anchor_valid'] and initial['first_step']==-1,'Capture consumed before enable')
    enabled=report['enable_state']
    require(len(enabled['participants'])==2 and all(p['state']['armed'] and abs(p['state']['position'][2]-3)<=.2
        for p in enabled['participants'].values()),'Enable did not occur in real airborne hold')
    dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
    bits=''.join(str(int(v>0)) for v in cv2.aruco.generateImageMarker(dictionary,23,8).flat)
    params=cv2.aruco.DetectorParameters();params.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
    detector=cv2.aruco.ArucoDetector(dictionary,params)
    counts=Counter();results=[];origin=None;first_step=None;previous_step=-1;failures=[];previous_estimate=None
    width,height=report['settings']['width'],report['settings']['height']
    for entry in report['frames']:
        frame=entry['frame'];m=frame['metadata'];s=json.loads(Path(entry['scene_path']).read_text())
        require(digest(entry['scene_path'])==entry['scene_sha256'],'Scene readback changed')
        require(digest(frame['image_path'])==entry['image_sha256'],'Image changed')
        require(json.loads(Path(frame['metadata_path']).read_text())==m,'Metadata changed')
        require(s['case_id']==s['scene_case']==5 and s['anchor_valid'],'Wrong or unbound scene')
        step=int(m['step']);require(previous_step<step<=entry['now_step']<=step+300,'Invalid capture freshness/order')
        previous_step=step
        for key,value in (('run_id',report['config']['run_id']),('instance_id',report['session']['instance_id']),
                          ('stream_id',report['stream_id']),('epoch',enabled['epoch'])):
            require(m[key]==s[key]==value,'Capture identity differs: '+key)
        if experiment:
            notice=frame['notification']
            require(notice.get('schema')=='wksim.rgb-ready.v2' and type(notice.get('generation')) is int
                and notice['generation']==enabled['generation']
                and all(notice.get(key)==m[key] for key in ('run_id','instance_id','stream_id','epoch'))
                and notice.get('metadata')==Path(frame['metadata_path']).name,'Raw RGB notification binding differs')
        require(step==s['step'] and s['generation']==enabled['generation'],'Scene step/generation differs')
        require(m.get('render_show_flags')==dict.fromkeys(('post_processing','anti_aliasing','bloom',
            'depth_of_field','eye_adaptation','motion_blur','temporal_aa'),False),'Uncontrolled image postprocessing')
        require(s['row_major_bits']==bits and s['dictionary']=='DICT_6X6_250' and s['marker_id']==23,'Marker identity differs')
        p=np.asarray(s['anchor_position_cm']);r=rotation(s['anchor_quaternion_xyzw'])
        if origin is None:
            origin=(p,r);first_step=s['first_step']
            require(p[2]>240,'Scene anchor is not airborne')
            first_scene=json.loads((Path(entry['scene_path']).parent/f"aruco-{s['epoch']}-{first_step}.json").read_text())
            mount=m['camera_in_vehicle'];mr=rotation(mount['quaternion_xyzw'])
            first_camera_r=rotation(first_scene['camera_quaternion_xyzw'])
            expected_r=first_camera_r@mr.T
            expected_p=np.asarray(first_scene['camera_position_cm'])-expected_r@np.asarray(mount['position_cm'])
            require(first_scene['step']==first_step and first_scene['epoch']==s['epoch'] and
                np.allclose(r,expected_r,atol=1e-6,rtol=0) and np.allclose(p,expected_p,atol=1e-5,rtol=0),
                'Anchor does not reconstruct the actual initial vehicle transform')
        require(first_step==s['first_step'] and np.allclose(p,origin[0],atol=1e-8,rtol=0)
            and np.allclose(r,origin[1],atol=1e-8,rtol=0),'Anchor changed during episode')
        elapsed=step-first_step
        require(elapsed>=0,'Scene step precedes its origin')
        phase='static_initial' if elapsed<2000 else 'moving' if elapsed<6000 else 'occluded' if elapsed<8000 else 'recovered'
        expected_label='settled' if elapsed>=12000 else phase
        require(s['phase']==expected_label,'Phase is not tied to authority time')
        offset=np.array([0,min(4000,max(0,elapsed-2000))*.025,0])
        objects=s['objects'];require(len(objects)==66,'Incomplete geometry')
        for i,part in enumerate(objects):
            value=1 if i in (0,65) else int(bits[i-1])
            require(part['material_unlit'] and part['material_opaque'] and part['material_emissive_rgba']==[value,value,value,1]
                and not part['collision_enabled'] and not part['simulating_physics'],'Material or physical side effect differs')
            require(np.allclose(rotation(part['quaternion_xyzw']),r,atol=1e-6,rtol=0),'Component rotation differs from anchor')
            if 1<=i<=64:
                row,column=divmod(i-1,8)
                local=np.array([230.05,32+(column-3.5)*6.25,6+(3.5-row)*6.25])
                require(np.allclose(part['position_cm'],p+r@local+offset,atol=1e-5,rtol=0),'Actual cell position/motion differs')
                extent=(np.asarray(part['mesh_bounds_max'])-part['mesh_bounds_min'])*part['scale']
                require(np.allclose(extent,[.1,6.25,6.25],atol=1e-5,rtol=0),'Wrong marker size')
        def front(part):
            lo=np.asarray(part['mesh_bounds_min'])*part['scale'];hi=np.asarray(part['mesh_bounds_max'])*part['scale']
            local=np.array([[lo[0],lo[1],hi[2]],[lo[0],hi[1],hi[2]],
                [lo[0],hi[1],lo[2]],[lo[0],lo[1],lo[2]]])
            return np.asarray(part['position_cm'])+local@rotation(part['quaternion_xyzw']).T
        corners=np.array([front(objects[1])[0],front(objects[8])[1],front(objects[64])[2],front(objects[57])[3]])
        camera=m['camera_world_pose'];cr=rotation(camera['quaternion_xyzw']);cp=np.asarray(camera['position_cm'])
        require(np.allclose(cp,s['camera_position_cm'],atol=1e-6,rtol=0),'Camera position readback differs')
        require(np.allclose(cr,rotation(s['camera_quaternion_xyzw']),atol=1e-6,rtol=0),'Camera rotation readback differs')
        k=np.asarray(m['K']).reshape(3,3)
        require(report['settings']['horizontal_fov_degrees']==90 and
            np.allclose(k,[[width/2,0,width/2],[0,width/2,height/2],[0,0,1]],atol=1e-5,rtol=0),'Frozen intrinsics differ')
        def optical(world):return ((np.asarray(world)-cp)@cr)[...,[1,2,0]]*[1,-1,1]/100
        def project(world):
            xyz=optical(world);require(np.all(xyz[...,2]>0),'Marker behind camera')
            hp=xyz@k.T;return hp[...,:2]/hp[...,2,None]
        projection=project(corners);truth=optical(corners.mean(axis=0))
        image=cv2.imdecode(np.frombuffer(Path(frame['image_path']).read_bytes(),dtype=np.uint8),cv2.IMREAD_UNCHANGED)
        require(image is not None and image.shape==(height,width,4) and np.all(image[:,:,3]==255),'Invalid raw RGBA')
        detected,ids,_=detector.detectMarkers(cv2.cvtColor(image,cv2.COLOR_BGRA2GRAY))
        matches=[] if ids is None else np.flatnonzero(ids.ravel()==23)
        target=entry['target'];item=dict(step=step,elapsed=elapsed,phase=phase)
        require(objects[-1]['visible']==(phase=='occluded'),'Occluder time differs')
        if phase=='occluded':
            cover=project(front(objects[-1]))
            require(np.all(projection>=cover.min(axis=0)) and np.all(projection<=cover.max(axis=0)),'Target not fully covered')
            require(len(matches)==0 and target is None and entry['reason']=='not_detected','Occlusion did not invalidate target')
            previous_estimate=None
        else:
            require(len(matches)==1 and target is not None,'Visible target was not consumed')
            pixels=detected[matches[0]].reshape(4,2)+.5
            # Reproduce the measured optical translation from the actual PNG,
            # independently of the geometric truth used for the accuracy gates.
            object_points=np.array([[-.25,.25,0],[.25,.25,0],[.25,-.25,0],[-.25,-.25,0]],dtype=np.float64)
            ok,rv,tv=cv2.solvePnP(object_points,pixels.astype(np.float64),k,np.zeros(5),flags=cv2.SOLVEPNP_ITERATIVE)
            require(ok and np.allclose(tv.ravel(),target['position_optical_m'],atol=1e-9,rtol=0),
                'Stored target does not reproduce the raw image pose')
            measured_world=cr@(tv.ravel()[[2,0,1]]*[1,1,-1])+cp/100
            if previous_estimate is not None and entry['now_step']<=previous_estimate[0]+300:
                measured_velocity=(measured_world-previous_estimate[1])/((step-previous_estimate[0])/1000)
                require(target['velocity_world_ue_mps'] is not None and np.allclose(
                    measured_velocity,target['velocity_world_ue_mps'],atol=1e-8,rtol=0),
                    'Stored velocity does not reproduce raw image positions')
            else:
                require(target['velocity_world_ue_mps'] is None,'Velocity history survives a lost/expired target')
            previous_estimate=(step,measured_world)
            error=float(np.max(np.abs(pixels-projection)))
            translation=float(np.max(np.abs(np.asarray(target['position_optical_m'])-truth)))
            world_error=float(np.max(np.abs(np.asarray(target['position_world_ue_m'])-corners.mean(axis=0)/100)))
            mount=m['camera_in_vehicle']
            body=(rotation(mount['quaternion_xyzw'])@(truth[[2,0,1]]*[1,1,-1])+np.asarray(mount['position_cm'])/100)*[1,-1,1]
            body_error=float(np.max(np.abs(np.asarray(target['position_body_flu_m'])-body)))
            if error>2 or max(translation,world_error,body_error)>.035:
                failures.append(dict(step=step,gate='geometry',pixels=error,optical_m=translation,
                    world_m=world_error,body_m=body_error))
            require(np.allclose(pixels,target['corners_edge_px'],atol=1e-5,rtol=0),'Consumer corners differ from raw image')
            if results and results[-1]['phase']=='occluded':require(target['velocity_world_ue_mps'] is None,'Recovery reused velocity')
            if results and phase==results[-1]['phase']=='moving':
                if entry['now_step']>results[-1]['step']+300:
                    require(target['velocity_world_ue_mps'] is None,'Expired target reused for speed')
                else:
                    require(target['velocity_world_ue_mps'] is not None,'Continuous motion velocity missing')
                    velocity_error=float(np.max(np.abs(np.asarray(target['velocity_world_ue_mps'])-[0,.25,0])))
                    item['velocity_error_mps']=velocity_error
                    if velocity_error>.12:failures.append(dict(step=step,gate='velocity',error_mps=velocity_error))
            item.update(pixel_error=error,translation_error_m=translation,world_error_m=world_error,body_error_m=body_error)
        counts[phase]+=1;results.append(item)
    require(all(counts[k]>=5 for k in ('static_initial','moving','occluded','recovered')),'Insufficient phase samples')
    if experiment:
        # Capture ends on the authority deadline. The last async image must
        # cover that deadline within its already frozen 300-step freshness.
        require(report['disable_state']['authority']['tick']>=first_step+12000
                and results[-1]['elapsed']>=12000-300,'Incomplete tracking scene coverage')
    else:
        require(results[-1]['elapsed']>=12000,'Incomplete 12-second scene')
    return dict(status='failed' if failures else 'pass',scope='Real airborne case5 rendering/geometry/occlusion only; no camera-driven flight claim',
        counts=dict(counts),failures=failures,report_sha256=digest(root/'report.json'),auditor_sha256=digest(__file__),frames=results)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    try:result=audit(args.root)
    except Exception as error:result=dict(status='failed',error=str(error))
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='frames'}))
    raise SystemExit(result['status']!='pass')
