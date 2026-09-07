"""Audit original native RGB pixels/metadata against the retained live state feed."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from PIL import Image, ImageStat

REPO=Path(__file__).resolve().parents[1]


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def rotated(q,v):
    a=cross(q[:3],v);b=cross(q[:3],a)
    return [v[i]+2*q[3]*a[i]+2*b[i] for i in range(3)]
def multiplied(a,b):
    v=cross(a[:3],b[:3])
    return [a[3]*b[i]+b[3]*a[i]+v[i] for i in range(3)]+[a[3]*b[3]-sum(a[i]*b[i] for i in range(3))]


def audit(directory):
    directory=Path(directory).resolve();r=read(directory/'report.json')
    require(r['status']=='pass' and r['manager_returncode']==0,'Ground RGB run failed')
    require(r['result']['status']==('pass' if r.get('airborne_requested') else 'stopped') and all(not e['remaining_group_members'] for e in r['result']['epochs']),
            'Joint scene did not retire')
    provenance=read(directory/'implementation.json')
    for name,digest in provenance['sha256'].items():
        require(sha(directory/'sources'/name)==digest,'Captured source changed')
    build=read(REPO/r['manifest']);loaded=read(directory/'ue-loaded-module.json')
    require(build['build_exit_code']==0 and loaded['path']==build['binary'] and
            loaded['sha256'].lower()==build['binary_sha256'],'Loaded UE module differs')
    require(sha(build['binary'])==build['binary_sha256'],'Retained UE binary changed')
    for item in build['build_inputs']:
        source=directory/'sources/Simulator/ue55'/item['path']
        if source.is_file():require(sha(source)==item['source_sha256']==item['staging_sha256'],'Captured UE source/build mismatch')
    view=r['view_final'];root=Path(view['rgb_directory'])
    require(root.resolve().is_relative_to(directory),'RGB recording escaped owned output')
    config=view['rgb_config']
    streams={view.get('rgb_stream_id')}
    if r.get('lifecycle_requested'):
        commands=[json.loads(line) for line in (Path(view['readback_path']).parent/'rgb-actions.jsonl').read_text().splitlines()]
        life=r['rgb_lifecycle']
        require(commands==[life['disable'],life['enable']],'Camera control history differs')
        previous=r['producer_streams'][0];streams={previous}
        for enabled,record in zip((False,True),commands):
            request=record['request']
            require(record['response']==dict(request,kind='rgb_stream_controlled') and
                    request['run_id']==r['config']['run_id'] and request['instance_id']==r['session']['instance_id'] and
                    request['stream_id']==previous and request['enabled'] is enabled,
                    'Uncorrelated producer control')
            if enabled:
                require(request['next_stream_id'] not in streams,'Producer restart reused identity')
                streams.add(request['next_stream_id']);previous=request['next_stream_id']
            else:require(request['next_stream_id']==previous,'Disable changed source identity')
        require(streams==set(r['producer_streams']) and previous==view['rgb_stream_id'],'Producer identity ledger differs')
    packets={}
    for line in Path(view['readback_path']).read_text().splitlines():
        row=json.loads(line)
        if 'packet' in row and row['packet'].get('kind')=='joint_state':
            p=row['packet'];packets.setdefault((p['epoch'],p['step']),[]).append(p)
    truth={};committed={};evidence_files=[directory/'report.json',Path(view['readback_path'])]
    for epoch in r['result']['epochs']:
        folder=directory/'run/epochs'/epoch['epoch']
        clock=folder/'clock.jsonl';evidence_files.append(clock)
        # Clock rows are written after each model commit, before the next
        # actuator barrier updates synchronized/last_barrier_tick.
        committed[epoch['epoch']]={row['tick'] for row in map(json.loads,clock.read_text().splitlines())
                                  if row['pending_tick'] is None and row['time_ns']==row['tick']*1000000}
        for uid,stack in ((1,'arducopter'),(2,'px4')):
            path=folder/(stack+'-truth.jsonl');evidence_files.append(path)
            for row in map(json.loads,path.read_text().splitlines()):
                key=(row['epoch'],row['tick'],uid)
                require(key not in truth,'Repeated physical step')
                truth[key]=row['state']
    checked=[]
    for frame in r['frames']:
        metadata=Path(frame['metadata_path']);image=Path(frame['image_path'])
        require(metadata.parent==root and image.parent==root,'Consumer frame escaped output')
        data=read(metadata);require(data==frame['metadata'],'Consumer metadata differs from original')
        schema='wksim.rgb.v2' if view.get('rgb_stream_id') else 'wksim.rgb.v1'
        require(data['schema']==schema and data['run_id']==r['config']['run_id'] and
                data['instance_id']==r['session']['instance_id'] and data['sensor_id']==config['sensor_id'] and
                data['vehicle_id']==str(config['vehicle_id']),'RGB identity differs')
        if schema=='wksim.rgb.v2':
            require(data['stream_id'] in streams and data['stream_id']==frame['notification']['stream_id'],'RGB producer stream differs')
        step=int(data['step']);require(data['sim_time_seconds']==step/1000,'Image time was relabelled')
        candidates=packets.get((data['epoch'],step),[]);require(candidates,'Image lacks an original source packet/Actor ACK')
        require(step in committed[data['epoch']],'Image step was not committed by the authority')
        errors=[]
        for packet in candidates:
            require(len(packet['vehicles'])==2,'RGB source omitted a moving vehicle')
            for actor in packet['vehicles']:
                state=truth[(data['epoch'],step,actor['vehicle_id'])]
                require(actor['position_ned_m']==state[6:9] and actor['quaternion_wxyz']==state[12:16]
                        and actor['rotor_rpm']==state[16:20] and actor['model_time_s']==state[2],
                        'Displayed actor was not the independently recorded physical state')
            vehicle=next(v for v in packet['vehicles'] if v['vehicle_id']==config['vehicle_id'])
            p=vehicle['position_ned_m'];w,x,y,z=vehicle['quaternion_wxyz'];q=[-x,-y,z,w]
            offset=rotated(q,config['position_cm']);expected=[p[0]*100+offset[0],p[1]*100+offset[1],-p[2]*100+offset[2]]
            q=multiplied(q,config['quaternion_xyzw'])
            pose=data['camera_world_pose']
            errors.append((math.dist(pose['position_cm'],expected),
                           min(math.dist(pose['quaternion_xyzw'],q),math.dist(pose['quaternion_xyzw'],[-v for v in q]))))
        position,quaternion=min(errors)
        # Existing UE coordinate transport limits; this is not a G6 model budget.
        require(position<=2e-4 and quaternion<=2e-6,'Actual capture pose differs from authoritative vehicle/mount')
        focal=data['width']/(2*math.tan(math.radians(data['horizontal_fov_degrees'])/2))
        expected=[focal,0,data['width']/2,0,focal,data['height']/2,0,0,1]
        require(max(abs(a-b) for a,b in zip(data['K'],expected))<1e-9,'Declared pinhole intrinsics differ')
        with Image.open(image) as pixels:
            pixels.load();require(pixels.format=='PNG' and pixels.size==(config['width'],config['height']),'Actual PNG decode/size differs')
            stat=ImageStat.Stat(pixels.convert('RGB'));extrema=pixels.convert('RGB').getextrema()
        checked.append(dict(epoch=data['epoch'],stream_id=data.get('stream_id'),step=step,frame_id=data['frame_id'],metadata_sha256=sha(metadata),image_sha256=sha(image),
                            position_error_cm=position,quaternion_l2=quaternion,rgb_mean=stat.mean,rgb_extrema=extrema))
    order={e['epoch']:i for i,e in enumerate(r['result']['epochs'])}
    require(len(checked)>=15 and all(
        b['step']>a['step'] if b['epoch']==a['epoch'] else order[b['epoch']]>order[a['epoch']]
        for a,b in zip(checked,checked[1:])),'Missing or replayed consumed frames')
    outage=r['consumer_outage'];reconnect=r['consumer_reconnect']
    require(outage['wall_seconds']>=3 and outage['after_tick']-outage['before']['tick']>=1000,'Physics did not advance during consumer outage')
    require(int(reconnect['first_frame']['metadata']['step'])>=reconnect['start_tick']>outage['before']['tick'],
            'Consumer reconnect replayed older frames')
    if r.get('lifecycle_requested'):
        life=r['rgb_lifecycle'];window=life['disabled_window']
        require(window['wall_seconds']>=3 and window['end_tick']-window['start_tick']>=1000,'Producer outage halted physics')
        require(life['old_producer_rejections']>=1 and life['old_epoch_rejections']>=1,'Retired image notifications were not rejected')
        require(life['before_epoch']!=life['after_epoch'] and life['after_generation']==life['before_generation']+1,
                'Cold reset did not replace physical epoch')
        require(life['reset_first_frame']['metadata']['epoch']==life['after_epoch'] and
                life['restarted_first_frame']['metadata']['stream_id']==view['rgb_stream_id'],
                'Missing real frames after producer/epoch restart')
        require(len(order)==2,'Expected exactly two actual physical epochs')
    airborne_frames=[]
    if r.get('airborne_requested'):
        for frame in checked:
            if all(truth[(frame['epoch'],frame['step'],uid)][8]<-2.5 for uid in (1,2)):
                airborne_frames.append(frame['step'])
        require(len(airborne_frames)>=5,'Fewer than five images from actual dual-airborne physical states')
        require(all(e['result']['flight_completed'] for e in r['result']['epochs']),'Public flight did not complete')
    return dict(status='pass',report_sha256=sha(directory/'report.json'),build_binary_sha256=build['binary_sha256'],
                evidence_sha256={str(p.relative_to(directory)):sha(p) for p in evidence_files},
                captured_pngs=len(list(root.glob('*.png'))),consumed_and_decoded=len(checked),frames=checked,
                consumer_outage_tick_advance=outage['after_tick']-outage['before']['tick'],
                producer_lifecycle_verified=bool(r.get('lifecycle_requested')),
                airborne_frame_steps=airborne_frames,
                limitations=[('Airborne image binding verified; geometric/pixel calibration is a separate audit.' if r.get('airborne_requested') else
                              'Ground only, no flight or geometric/pixel calibration acceptance.'),
                             'City buildings are currently visual decoration; no collision-feedback claim.',
                             'Shared-host scheduling and GPU/disk resource exhaustion are not isolated by asynchronous capture.',
                             ('Required dynamic-environment-feedback expiry remains unverified.' if r.get('lifecycle_requested') else
                              'No cold-reset or required dynamic-environment-feedback expiry acceptance in this case.')])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    result=dict(status='failed',audit_sha256=sha(__file__))
    try:result.update(audit(a.directory))
    except (ValueError,KeyError,TypeError,OSError,StopIteration) as error:result['error']=repr(error)
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','error','captured_pngs','consumed_and_decoded','consumer_outage_tick_advance') if k in result}))
    raise SystemExit(result['status']!='pass')
