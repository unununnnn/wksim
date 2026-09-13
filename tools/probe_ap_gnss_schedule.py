"""Real AP scheduled GPS serial probe with stationary ground truth, never arming."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
import uuid

TICKS=80000
PUBLISH=45000
START,END=50000,65000


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(build,out,observer_factory=None):
    if os.readlink('/proc/self/ns/net')==os.readlink('/proc/1/ns/net'):
        raise ValueError('Private network namespace required')
    out.mkdir(parents=True,exist_ok=False)
    identity=json.loads((build/'identity.json').read_text())
    binary=build/'build/sitl/bin/arducopter'
    if digest(binary)!=identity['binary_sha256']:raise ValueError('Native binary differs')
    run_id,epoch=uuid.uuid4().hex,uuid.uuid4().hex
    params=out/'ground.parm'
    params.write_text('SIM_GPS1_ENABLE 1\nSIM_GPS1_TYPE 1\nSIM_GPS1_LAG_MS 100\nSIM_GPS1_HZ 5\nSIM_GPS1_BYTELOS 0\nSIM_GPS2_ENABLE 0\nSIM_GPS2_TYPE 0\nGPS1_TYPE 2\nGPS_AUTO_CONFIG 0\nGPS_DRV_OPTIONS 4\nDDS_ENABLE 0\n')
    if observer_factory:
        params.write_text(params.read_text().replace('DDS_ENABLE 0','DDS_ENABLE 1')+'DDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n')
    command=[str(binary),'--model','JSON:127.0.0.1','--rate','1000','--speedup','1',
        '--sim-address','127.0.0.1','--sim-port-out','19002','--sim-port-in','19003','--rc-in-port','19004',
        '--serial0','none','--serial1','none','--serial2','none','--defaults',str(params),
        '--home','40.1540302,116.2593683,50,0']
    manifest=dict(schema='wksim.ap-gnss-scheduled-ground.v1',run_id=run_id,epoch=epoch,command=command,
        binary_sha256=digest(binary),build_manifest_sha256=digest(build/'scheduled-build.json'),
        source_sha256=digest(__file__),params_sha256=digest(params),
        plan=dict(published_tick=PUBLISH,start_tick=START,end_tick=END,max_tick=TICKS),
        scope='stationary native sensor probe; no arming/flight',dds_observation=bool(observer_factory),failure=None,frames_sent=0)
    environment=dict(os.environ,WKSIM_RUN=run_id,WKSIM_EPOCH=epoch,WKSIM_GNSS_TRACE=str(out/'native.tsv'))
    observer=observer_factory(out) if observer_factory else None
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock, (out/'process.log').open('x') as log, (out/'wire.jsonl').open('x') as wire:
        sock.bind(('127.0.0.1',19002));sock.settimeout(.2)
        child=subprocess.Popen(command,cwd=out,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        manifest.update(pid=child.pid,proc_stat=Path(f'/proc/{child.pid}/stat').read_text(),
                        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        expected=0;peer=None;deadline=time.monotonic()+120
        try:
            while time.monotonic()<deadline:
                if observer:observer.poll()
                if child.poll() is not None:raise RuntimeError('AP exited: '+str(child.returncode))
                try:packet,address=sock.recvfrom(4096)
                except socket.timeout:continue
                wire.write(json.dumps(dict(direction='receive',hex=packet.hex()))+'\n')
                if peer is None:peer=address
                if address!=peer or len(packet)!=40:raise ValueError('Unexpected actuator peer/packet')
                magic,rate,frame,*pwm=struct.unpack('<HHI16H',packet)
                if magic!=18458 or frame!=expected:raise ValueError('Nonconsecutive actuator frame')
                if expected==TICKS:break
                tick=expected+1
                data=dict(wksim=f'{run_id}:{epoch}:1:{tick}')
                if tick>=PUBLISH:data['gnss_plan']=f'{START}:{END}'
                data.update(timestamp=tick/1000,imu=dict(gyro=[0,0,0],accel_body=[0,0,-9.80665]),
                            position=[0,0,0],velocity=[0,0,0],quaternion=[1,0,0,0])
                raw=('\n'+json.dumps(data,separators=(',',':'),allow_nan=False)+'\n').encode()
                sock.sendto(raw,peer);wire.write(json.dumps(dict(direction='send',hex=raw.hex(),tick=tick))+'\n')
                expected+=1
                if expected%10000==0:print(json.dumps(dict(tick=expected)),flush=True)
            else:raise TimeoutError('120-second native ground watchdog')
        except Exception as error:manifest['failure']=repr(error)
        finally:
            manifest['frames_sent']=expected
            if child.poll() is None:child.terminate()
            try:manifest['returncode']=child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill();manifest['returncode']=child.wait(timeout=5)
                manifest['failure']=manifest['failure'] or 'Native process required KILL'
            if observer:
                try:observer.close()
                except Exception as error:manifest['failure']=manifest['failure'] or repr(error)
                manifest['dds_observer']=observer.identity
    manifest['raw_sha256']={name:digest(out/name) for name in ('native.tsv','wire.jsonl','process.log')}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if manifest['failure'] or manifest['returncode']!=0 or expected!=TICKS:
        raise RuntimeError(str(manifest))
    print(json.dumps(dict(status='observed',out=str(out),ticks=expected)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path);parser.add_argument('out',type=Path)
    args=parser.parse_args();run(args.build.resolve(),args.out.resolve())
