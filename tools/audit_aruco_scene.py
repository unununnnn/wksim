"""Independent geometry projection and raw-image audit for the live ArUco scene."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np


def require(value,reason):
    if not value:raise ValueError(reason)


def rotation(q):
    x,y,z,w=map(float,q)
    require(abs(x*x+y*y+z*z+w*w-1)<1e-6,'Nonunit camera quaternion')
    return np.array([[1-2*y*y-2*z*z,2*x*y-2*z*w,2*x*z+2*y*w],
        [2*x*y+2*z*w,1-2*x*x-2*z*z,2*y*z-2*x*w],
        [2*x*z-2*y*w,2*y*z+2*x*w,1-2*x*x-2*y*y]])


def bounds(part):
    require(np.allclose(part['quaternion_xyzw'],[0,0,0,1],rtol=0,atol=1e-8),'Rotated fixture cell')
    position=np.asarray(part['position_cm']);scale=np.asarray(part['scale'])
    require(np.all(scale>0),'Invalid fixture scale')
    return (position+np.asarray(part['mesh_bounds_min'])*scale,
            position+np.asarray(part['mesh_bounds_max'])*scale)


def audit(root):
    report=json.loads((root/'report.json').read_text())
    require(report['status']=='acquired' and report['manager_returncode']==0,'Acquisition/retirement did not pass')
    require(not report.get('cleanup_error') and not report.get('retention_error'),'Cleanup/retention error')
    require(report['result']['epochs'] and all(not e['remaining_group_members'] for e in report['result']['epochs']),
        'Epoch processes remain')
    dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
    bits=''.join(str(int(value>0)) for value in cv2.aruco.generateImageMarker(dictionary,23,8).flat)
    parameters=cv2.aruco.DetectorParameters();parameters.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
    detector=cv2.aruco.ArucoDetector(dictionary,parameters)
    counts=Counter();results=[];previous=None;first_step=None;last_step=-1;velocity_pairs=0
    for row in report['frames']:
        frame=row['frame'];m=frame['metadata'];step=int(m['step']);target=row['target']
        scene_path=Path(row['scene_path']);scene=json.loads(scene_path.read_text())
        require(hashlib.sha256(scene_path.read_bytes()).hexdigest()==row['scene_sha256'],'Scene file changed')
        require(json.loads(Path(frame['metadata_path']).read_text())==m,'RGB metadata changed')
        require(hashlib.sha256(Path(frame['image_path']).read_bytes()).hexdigest()==row['image_sha256'],'RGB image changed')
        require(scene['scene_schema']=='wksim.aruco-scene.v1' and scene['case_id']==4,'Wrong scene')
        require(m.get('render_show_flags')==dict.fromkeys(('post_processing','anti_aliasing','bloom',
            'depth_of_field','eye_adaptation','motion_blur','temporal_aa'),False),'Uncontrolled calibration postprocessing')
        for key,expected in (('run_id',report['config']['run_id']),('instance_id',report['session']['instance_id']),
                ('stream_id',report['stream_id']),('epoch',row['authority']['epoch'])):
            require(m[key]==expected and scene[key]==expected,'Scene/RGB/authority identity differs: '+key)
        require(scene['generation']==row['authority']['generation'] and step==scene['step'],'Scene generation/step differs')
        require(last_step<step<=row['now_step']<=step+300 and row['now_step']==row['authority']['tick'],
            'Repeated/future/stale admitted frame');last_step=step
        if first_step is None:first_step=scene['first_step']
        require(first_step==scene['first_step'] and first_step<=step,'Scene origin changed')
        elapsed=step-first_step
        phase='appearance' if elapsed<1000 else 'movement' if elapsed<2000 else 'occlusion' if elapsed<3000 else 'recovery'
        require(scene['dictionary']=='DICT_6X6_250' and scene['marker_id']==23 and scene['row_major_bits']==bits,'Marker dictionary differs')
        parts=scene['objects'];require(len(parts)==66,'Incomplete scene geometry')
        for index,part in enumerate(parts):
            color=1 if index in (0,65) else int(bits[index-1])
            require(part.get('material_unlit') is True and part.get('material_opaque') is True and
                part.get('material_emissive_rgba')==[color,color,color,1] and
                part.get('collision_enabled') is False and part.get('simulating_physics') is False,
                'Actual material/collision readback differs')
        offset=min(1000,max(0,elapsed-1000))*.025
        for r in range(8):
            for c in range(8):
                lo,hi=bounds(parts[1+r*8+c])
                require(parts[1+r*8+c]['visible'],'Hidden marker cell')
                expected=[230,32+offset+(c-4)*6.25,6+(3-r)*6.25]
                require(np.allclose(lo,expected,atol=1e-5,rtol=0) and np.allclose(hi-lo,[.1,6.25,6.25],atol=1e-5,rtol=0),
                    'Actual marker dimensions/motion differ')
        # Black outer corners from actual mesh bounds, TL/TR/BR/BL.
        corners=[]
        for index,upper_y,upper_z in ((1,False,True),(8,True,True),(64,True,False),(57,False,False)):
            lo,hi=bounds(parts[index]);corners.append([lo[0],hi[1] if upper_y else lo[1],hi[2] if upper_z else lo[2]])
        corners=np.asarray(corners);center=corners.mean(axis=0)
        camera=m['camera_world_pose'];position=np.asarray(camera['position_cm']);r=rotation(camera['quaternion_xyzw'])
        require(np.allclose(position,scene['camera_position_cm'],atol=1e-6,rtol=0) and
            np.allclose(camera['quaternion_xyzw'],scene['camera_quaternion_xyzw'],atol=1e-6,rtol=0),'Capture camera differs')
        k=np.asarray(m['K']).reshape(3,3)
        require(np.allclose(k,[[320,0,320],[0,320,240],[0,0,1]],atol=1e-5,rtol=0),'Frozen intrinsics differ')
        def optical(world):return ((np.asarray(world)-position)@r)[...,[1,2,0]]*[1,-1,1]/100
        def project(world):
            p=optical(world);require(np.all(p[...,2]>0),'Reference behind camera')
            h=p@k.T;return h[...,:2]/h[...,2,None]
        projected=project(corners);truth=optical(center)
        image=cv2.imread(frame['image_path'],cv2.IMREAD_UNCHANGED)
        require(image is not None and image.shape==(480,640,4) and np.all(image[:,:,3]==255),'Invalid raw RGB')
        found,ids,_=detector.detectMarkers(cv2.cvtColor(image,cv2.COLOR_BGRA2GRAY))
        matches=[] if ids is None else np.flatnonzero(ids.ravel()==23)
        require(parts[-1]['visible']==(phase=='occlusion'),'Wrong occluder phase')
        result=dict(step=step,elapsed=elapsed,phase=phase,projected_corners=projected.tolist(),truth_optical_m=truth.tolist())
        if phase=='occlusion':
            lo,hi=bounds(parts[-1]);cover=project([[lo[0],lo[1],lo[2]],[lo[0],hi[1],lo[2]],
                [lo[0],hi[1],hi[2]],[lo[0],lo[1],hi[2]]])
            require(np.all(projected>=cover.min(axis=0)) and np.all(projected<=cover.max(axis=0)),'Incomplete projected occlusion')
            require(len(matches)==0 and target is None and row['reason']=='not_detected','Occlusion did not clear target')
        else:
            require(len(matches)==1 and target is not None,'Expected live target missing at step '+str(step)+': '+row['reason'])
            detected=found[matches[0]].reshape(4,2)+.5
            require(np.allclose(detected,target['corners_edge_px'],atol=1e-5,rtol=0),'Live consumer corners differ from raw PNG')
            pixel_error=float(np.max(np.abs(detected-projected)))
            error=float(np.max(np.abs(np.asarray(target['position_optical_m'])-truth)))
            world_error=float(np.max(np.abs(np.asarray(target['position_world_ue_m'])-center/100)))
            require(pixel_error<=2 and error<=.035 and world_error<=.035,
                f'Independent projection/translation gate failed: step={step}, pixels={pixel_error}, optical_m={error}, world_m={world_error}')
            require(target['step']==m['step'] and target['run_id']==m['run_id'],'Consumer target identity differs')
            if previous and previous['phase']=='occlusion':require(target['velocity_world_ue_mps'] is None,'Recovery reused stale velocity')
            if previous and phase==previous['phase']=='movement':
                # Consumer.current expires the old target on authority updates,
                # including polls without a frame. A fresh new frame after that
                # gap must not manufacture a velocity from the expired target.
                if row['now_step']>previous['step']+300:
                    require(target['velocity_world_ue_mps'] is None,'Velocity reused an expired target')
                    result['velocity_comparison']='previous_target_expired'
                else:
                    require(target['velocity_world_ue_mps'] is not None and np.max(np.abs(
                        np.asarray(target['velocity_world_ue_mps'])-[0,.25,0]))<=.12,'Motion velocity gate failed')
                    velocity_pairs+=1
            result.update(pixel_error=pixel_error,translation_error_m=error,world_error_m=world_error)
        counts[phase]+=1;results.append(result);previous=result
    require(all(counts[name]>=5 for name in ('appearance','movement','occlusion','recovery')),'Insufficient samples per phase')
    require(results[-1]['elapsed']>=5000,'Incomplete five-second scene')
    return dict(status='pass',scope='Actual UE ground RGB appearance/motion/occlusion/recovery calibration; no flight or G6 claim',
        report_sha256=hashlib.sha256((root/'report.json').read_bytes()).hexdigest(),
        auditor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),counts=dict(counts),
        motion_velocity_pairs=velocity_pairs,frames=results)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    try:result=audit(args.root)
    except Exception as error:result=dict(status='failed',error=str(error))
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps({key:value for key,value in result.items() if key!='frames'}))
    raise SystemExit(result['status']!='pass')
