"""Native UE profile/pose/stale checks with explicitly labelled state fixtures."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_core.state_stream import METADATA
from Simulator.ue55.hex_bridge import METADATA as HEX_METADATA

ENGINE=Path('E:/ue5.5/files/UE_5.5/Engine/Binaries/Win64/UnrealEditor.exe')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def packet(profile,run_id,sequence,instance,model):
    base=dict(run_id=run_id,vehicle_id=1,sequence=sequence,sim_time_s=sequence*.04,
        position_ned_m=[.1*math.sin(sequence*.03),0.,0. if profile=='ackermann' else -1.],
        quaternion_wxyz=[math.cos(.1),0.,0.,math.sin(.1)],
        display_wall_time_s=time.time(),display_clock='windows_utc_bound')
    if profile=='ackermann':
        return dict(base,kind='vehicle_state',version=1,vehicle_class='ground_vehicle',
            model_profile='ackermann_v1' if sequence<50 else 'pose_compatible_ground_model',
            visual_profile='ackermann',source_mode='fixture',
            position_frame='NED',position_unit='m',body_frame='FRD',quaternion_order='WXYZ')
    if profile=='hex':
        return dict(base,version=4,kind='hex_state',instance_id=instance,model_identity=model,
            step=sequence*40,sim_time_ns=sequence*40000000,source_monotonic_s=time.monotonic(),
            source_age_s=0.,transport_age_bound_s=0.,rotor_order=['M'+str(i) for i in range(1,7)],
            rotor_rpm=[1200.]*6,**HEX_METADATA)
    return dict(base,version=2,source_wall_time_s=time.monotonic(),rotor_rpm=[1200.]*4,**METADATA)


def validate(manifest):
    build=json.loads(manifest.read_text(encoding='utf-8-sig'))
    stage=Path(build['project']).parent
    required={row['path'] for row in json.loads((REPO/'Simulator/ue55/state-build-manifest.json').read_text())['build_inputs']}
    required|={'Source/WksimVisual/WksimVehicleVisual.cpp','Source/WksimVisual/WksimVehicleVisual.h','Config/WksimVisualAssets.json'}
    if build['build_exit_code']!=0 or {r['path'] for r in build['build_inputs']}!=required or sha(build['binary'])!=build['binary_sha256']:
        raise ValueError('Native visual build inputs/binary differ')
    for row in build['build_inputs']+build['asset_inputs']:
        path=(stage/row['path']).resolve()
        if not path.is_relative_to(stage.resolve()) or sha(path)!=row['staging_sha256']:
            raise ValueError('Staged visual input differs: '+row['path'])
    output=Path(tempfile.mkdtemp(prefix='visual-profiles-',dir=REPO/'validation'))
    report=dict(status='failed',scope='UE native fixtures/pose/stale validation; no flight evidence',
                manifest=str(manifest),manifest_sha256=sha(manifest),profiles=[])
    print(json.dumps({'output':str(output)}),flush=True)
    try:
        for profile in ('p450','hex','ackermann'):
            folder=output/profile;folder.mkdir();frames=folder/'frames';frames.mkdir()
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
                probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            run_id='visual-'+uuid.uuid4().hex[:16];instance=uuid.uuid4().hex;model='sha256:'+sha(manifest)
            argv=[str(ENGINE),build['project'],'/Game/Maps/UrbanBlock?game=/Script/WksimVisual.WksimVisualGameMode',
                '-game','-windowed','-ResX=1280','-ResY=720','-NoSound','-NoSplash','-unattended','-RenderOffScreen',
                '-ExecCmds=t.IdleWhenNotForeground 0,t.MaxFPS 30',
                '-WksimVehicle=1','-WksimRunId='+run_id,'-WksimVisualProfile='+profile,'-WksimSourceMode=fixture',
                '-WksimPort='+str(port),'-WksimCaptureDir='+str(frames),'-abslog='+str(folder/'ue.log')]
            if profile=='hex':argv+=['-WksimConfiguration=hex-X','-WksimInstance='+instance,'-WksimModelIdentity='+model]
            info=subprocess.STARTUPINFO();info.dwFlags|=subprocess.STARTF_USESHOWWINDOW;info.wShowWindow=0
            with (folder/'stdout.log').open('w') as log:
                child=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,startupinfo=info)
                started=time.monotonic();ready_at=None;sent={};acks=[];seq=0;next_send=0.
                try:
                    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as link:
                        link.bind(('127.0.0.1',0));link.settimeout(.01)
                        while time.monotonic()-started<70:
                            now=time.monotonic()
                            if child.poll() is not None:raise RuntimeError('UE exited; see '+str(folder/'ue.log'))
                            text=(folder/'ue.log').read_text(encoding='utf-8',errors='replace') if (folder/'ue.log').exists() else ''
                            if ready_at is None and 'WKSIM_READY ' in text:ready_at=now
                            if ready_at is not None and now-ready_at>11:break
                            if ready_at is not None and now-ready_at<7 and now>=next_send:
                                seq+=1;p=packet(profile,run_id,seq,instance,model);sent[seq]=p
                                link.sendto(json.dumps(p,allow_nan=False).encode(),('127.0.0.1',port))
                                next_send=now+.04
                            try:
                                raw,_=link.recvfrom(16384);ack=json.loads(raw)
                            except socket.timeout:continue
                            key=ack.get('sequence')
                            if ack.get('run_id')!=run_id or key not in sent:continue
                            source=sent[key]
                            expected=[source['position_ned_m'][0]*100,source['position_ned_m'][1]*100,-source['position_ned_m'][2]*100]
                            if math.dist(ack['ue_position_cm'],expected)>2e-4:raise ValueError('Native UE pose differs')
                            q=source['quaternion_wxyz'];expected_q=[-q[1],-q[2],q[3],q[0]]
                            if min(math.dist(ack['ue_quaternion_xyzw'],expected_q),math.dist(ack['ue_quaternion_xyzw'],[-x for x in expected_q]))>2e-6:
                                raise ValueError('Native UE orientation differs')
                            acks.append(ack)
                        text=(folder/'ue.log').read_text(encoding='utf-8',errors='replace')
                        images=sorted(frames.glob('*.png'))
                        captures=[line for line in text.splitlines() if 'WKSIM_CAPTURE' in line]
                        if not ready_at or len(acks)<30 or len(images)<3 or not any('stale=1' in line and 'sequence=-1' not in line for line in captures):
                            raise ValueError('Incomplete native pose/render/stale evidence for '+profile)
                        if profile=='ackermann' and not any(a['sequence']>=100 for a in acks):
                            raise ValueError('Viewer did not accept the compatible replacement model identity')
                        (folder/'acks.json').write_text(json.dumps(acks)+'\n')
                        report['profiles'].append(dict(profile=profile,acks=len(acks),images=[str(p) for p in images],
                            argv=argv,ready=True,stale=True,source_mode='fixture',
                            compatible_model_identity=profile=='ackermann'))
                        print(json.dumps({'profile':profile,'acks':len(acks),'frames':len(images)}),flush=True)
                finally:
                    child.terminate()
                    try:child.wait(timeout=15)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
        report['status']='pass'
    except Exception as error:
        report['error']=repr(error);raise
    finally:
        (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'result':str(output/'result.json'),'status':report['status']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manifest',type=Path,required=True)
    args=parser.parse_args();validate(args.manifest)
