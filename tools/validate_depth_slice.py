"""Real UE depth fixture smoke test with explicitly synthetic authoritative poses.

No flight controller or physics process is launched; this is optical evidence only.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.ue55.depth import Reader
from tools.audit_depth_geometry import compare


def run(manifest, output, case):
    output = output.resolve(); output.mkdir(parents=True, exist_ok=False)
    build = json.loads(manifest.read_text(encoding='utf-8-sig'))
    binary = Path(build['binary'])
    if hashlib.sha256(binary.read_bytes()).hexdigest() != build['binary_sha256']:
        raise ValueError('Candidate binary changed')
    for entry in build['build_inputs']:
        source = REPO/'Simulator/ue55'/entry['path']
        if hashlib.sha256(source.read_bytes()).hexdigest() != entry['source_sha256']:
            raise ValueError('Candidate source differs: '+entry['path'])
    run_id, instance, epoch, stream = 'depth-'+uuid.uuid4().hex[:10], uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
    settings = dict(version=1, vehicle_id=2, sensor_id='front_depth', width=160, height=120,
                    horizontal_fov_degrees=90, position_cm=[30, 80, 120] if case == 1 else [30, 0, 100],
                    quaternion_xyzw=[0, 0, math.sin(math.radians(10)), math.cos(math.radians(10))] if case == 3 else [0, 0, 0, 1],
                    interval_steps=100, notify_port=19074, max_depth_meters=100)
    images = output/'depth'; images.mkdir()
    config = output/'depth-config.json'
    config.write_text(json.dumps(dict(settings, stream_id=stream, output_directory=str(images))))
    fixture = output/'fixture.json'; log = output/'ue.log'
    threshold_doc = REPO/'docs/2026-09-08-depth-slice-wip.md'
    (output/'conditions.json').write_text(json.dumps(dict(scope=__doc__, fixture_case=case,
        width=160, height=120, document_sha256=hashlib.sha256(threshold_doc.read_bytes()).hexdigest(),
        absolute_error_m=.01, relative_error=.002, edge_pixels=2, coverage=.995, declared_before_launch=True)))
    argv = [str(Path(build['engine'])/'Engine/Binaries/Win64/UnrealEditor.exe'), build['project'],
            '/Game/Maps/UrbanBlock?game=/Script/WksimVisual.WksimVisualGameMode', '-game', '-windowed',
            '-ResX=640', '-ResY=480', '-NoSound', '-NoSplash', '-unattended', '-ExecCmds=t.MaxFPS 30',
            '-WksimVehicle=joint', '-WksimRunId='+run_id, '-WksimInstance='+instance, '-WksimPort=19073',
            '-WksimDepthConfig='+str(config), '-WksimRgbFixtureCase='+str(case),
            '-WksimRgbFixtureManifest='+str(fixture), '-abslog='+str(log)]
    report = dict(status='failed', scope=__doc__, command=argv, fixture_case=case, frames=[],
                  physical_progress_verified=False, manifest=str(manifest), run_id=run_id,
                  instance_id=instance, epoch=epoch, generation=1, stream_id=stream)
    reader = Reader(images, run_id, instance, settings, stream_id=stream)
    reader.set_epoch(epoch, 1, minimum_step=0)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sock.bind(('127.0.0.1', 0)); sock.settimeout(.15)
    process = None
    try:
        process = subprocess.Popen(argv, cwd=REPO, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        report['pid'] = process.pid
        deadline = time.monotonic()+120
        while not (log.exists() and 'WKSIM_READY run='+run_id in log.read_text(errors='replace')):
            if process.poll() is not None: raise RuntimeError('UE exited during startup')
            if time.monotonic() > deadline: raise TimeoutError('UE startup')
            time.sleep(.1)
        native = json.loads(fixture.read_text())
        if native['process_id'] != process.pid or Path(native['module_path']).resolve() != binary.resolve():
            raise ValueError('Actual fixture module differs')
        report['loaded_module_sha256'] = hashlib.sha256(Path(native['module_path']).read_bytes()).hexdigest()
        if report['loaded_module_sha256'] != build['binary_sha256']: raise ValueError('Loaded module bytes differ')
        sequence = 0; deadline = time.monotonic()+45; acknowledgements = {}
        while len(report['frames']) < 5:
            if time.monotonic() > deadline: raise TimeoutError('Five actual depth frames')
            sequence += 1; step = sequence*100; now = time.time()
            packet = dict(version=3, kind='joint_state', run_id=run_id, instance_id=instance, epoch=epoch,
                          generation=1, sequence=sequence, step=step, sim_time_ns=step*1000000, phase='running',
                          source_wall_time_s=now, display_clock='windows_utc_bound', display_wall_time_s=now,
                          transport_age_bound_s=0, position_frame='NED', position_unit='m', quaternion_order='WXYZ',
                          body_frame='FRD', rotor_unit='rpm', configuration='quad-X', rotor_order=['FR', 'RL', 'FL', 'RR'],
                          vehicles=[dict(vehicle_id=i, stack=stack, model_time_s=step/1000, position_ned_m=[0, 0, 0],
                                         quaternion_wxyz=[1, 0, 0, 0], rotor_rpm=[0, 0, 0, 0])
                                    for i, stack in ((1, 'arducopter'), (2, 'px4'))])
            sock.sendto(json.dumps(packet).encode(), ('127.0.0.1', 19073))
            try:
                ack = json.loads(sock.recv(8192))
                if ack['kind'] == 'joint_actor': acknowledgements[ack['step']] = ack
            except socket.timeout:
                pass
            for frame in reader.poll():
                meta = frame['metadata']; capture_step = int(meta['step'])
                if capture_step not in acknowledgements: raise ValueError('Capture has no applied authoritative pose ACK')
                if (math.dist(meta['camera_world_pose']['position_cm'], settings['position_cm']) > 1e-5 or
                        math.dist(meta['camera_world_pose']['quaternion_xyzw'], settings['quaternion_xyzw']) > 1e-5):
                    raise ValueError('Capture pose differs from synthetic authoritative mount')
                result = compare(meta, frame.pop('depths'), native)
                stem = Path(frame['metadata_path']).stem
                (output/(stem+'.cloud.json')).write_text(json.dumps(frame.pop('point_cloud'), allow_nan=False))
                (output/(stem+'.mask.u8')).write_bytes(frame.pop('valid_mask'))
                frame['geometry'] = result; report['frames'].append(frame)
            time.sleep(.05)
        report.update(status='pass', acknowledgements=list(acknowledgements.values()), rejected=reader.rejected)
    except Exception as error:
        report['error'] = repr(error)
    finally:
        reader.close(); sock.close()
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=20)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
        report['owned_process_returncode'] = None if process is None else process.poll()
        report['owned_process_reaped'] = process is not None and process.poll() is not None
        (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', type=int, choices=range(4), default=0)
    args = parser.parse_args()
    result = run(args.manifest, args.output, args.case)
    print(json.dumps({k: result.get(k) for k in ('status', 'error', 'pid')}))
    raise SystemExit(result['status'] != 'pass')
