"""Run isolated PX4 physical diagnostics for each built inner-loop selector.

The existing mission exercises normal arm/takeoff/hold/waypoint/land. This is
physical firmware evidence, not native-DDS, UE, hardware or Full acceptance.
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile

from rate_control_candidate import REPO, digest, verify


def rate_metrics(path, algorithm, activity_basis='PX4 armed and not landed'):
    expected = {'native':0, 'pid':1, 'lqr':2, 'mpc':3}[algorithm]
    squared = [0.,0.,0.]
    peak = [0.,0.,0.]
    timings, count, last, sequence, ground_fallbacks = [], 0, None, 0, 0
    with Path(path).open() as source:
        for row in csv.DictReader(source):
            numeric = {k:float(v) for k,v in row.items()}
            if not all(math.isfinite(v) for v in numeric.values()):
                raise ValueError('Nonfinite inner-loop sample')
            current = int(row['sample_us'])
            if int(row['sequence']) != sequence+1 or (last is not None and current <= last):
                raise ValueError('Inner-loop source sequence/time discontinuity')
            sequence += 1; last = current
            if int(row['requested']) != expected:
                raise ValueError('Controller request differs from the selected experiment')
            if int(row['armed']) and not int(row['landed']):
                if int(row['effective']) != expected or int(row.get('status',0)) != 0:
                    raise ValueError('Requested controller was not effective throughout airborne measurement')
                for i,key in enumerate(('p','q','r')):
                    error = numeric[key]-numeric[key+'_sp']
                    squared[i] += error*error
                    peak[i] = max(peak[i],abs(error))
                timings.append(numeric['compute_ns'])
                count += 1
            elif int(row['effective']) != expected:
                ground_fallbacks += 1
    if count < 500:
        raise ValueError('Too few airborne native inner-loop samples')
    timings.sort()
    return dict(control_stage='firmware_body_rate', algorithm=algorithm,
        active_control_samples=count, activity_basis=activity_basis, total_samples=sequence,
        ground_fallbacks=ground_fallbacks,
        rate_rmse_rad_s=[math.sqrt(x/count) for x in squared], rate_peak_error_rad_s=peak,
        compute_p50_ns=timings[len(timings)//2],compute_p99_ns=timings[int(.99*(len(timings)-1))],
        compute_max_ns=max(timings),trace_sha256=digest(path))


def run(manifest, checksum, algorithms, motor_fault=False):
    candidate = verify(manifest, checksum)
    if not algorithms or any(a not in candidate['algorithms'] for a in algorithms):
        raise ValueError('Algorithm is not built into this candidate')
    output = Path(tempfile.mkdtemp(prefix='inner-loop-comparison-', dir=REPO/'validation'))
    print(json.dumps({'output':str(output)}),flush=True)
    result = dict(status='failed', candidate_manifest=str(manifest),candidate_sha256=checksum,
        scope='Independent physical SITL mission; actual firmware rate-loop output; not product/native-DDS/UE/hardware acceptance',
        runs=[], launcher_sha256=digest(__file__),mission_sha256=digest(REPO/'tools/validate_sitl_physics.py'))
    stack=candidate.get('stack','px4')
    result['stack']=stack
    result['disturbance']='motor0_command_97pct_1s' if motor_fault else 'none'
    result['activity_basis']=candidate.get('activity_basis','PX4 armed and not landed')
    (output/'candidate.json').write_bytes(Path(manifest).read_bytes())
    try:
        for algorithm in algorithms:
            folder=output/algorithm
            folder.mkdir()
            trace=folder/'rate.csv'
            env=dict(os.environ,WKSIM_RATE_ALGORITHM=algorithm,WKSIM_RATE_TRACE=str(trace))
            argv=['unshare','--net','--ipc','--mount','--propagation','private','bash','-c',
                'set -euo pipefail; ip link set lo up; mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm; exec "$@"',
                'wksim-inner',sys.executable,str(REPO/'tools/validate_sitl_physics.py'),
                '--stack',stack,'--ap-root' if stack=='arducopter' else '--px4-root',candidate['source_root']]
            if motor_fault:argv.append('--motor-command-disturbance')
            with (folder/'mission.log').open('w') as log:
                child=subprocess.Popen(argv,cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try: code=child.wait(timeout=230)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGTERM)
                    try: child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL);child.wait()
                    raise RuntimeError('Physical diagnostic exceeded wall budget')
            entries=[]
            for line in (folder/'mission.log').read_text().splitlines():
                try: value=json.loads(line)
                except ValueError: continue
                if isinstance(value,dict) and 'result_dir' in value: entries.append(value['result_dir'])
            row=dict(algorithm=algorithm,returncode=code,argv=argv,trace=str(trace))
            result['runs'].append(row)
            if len(entries)!=1:
                raise ValueError('Missing unique physical diagnostic result directory')
            physical=Path(entries[0])/'result.json'
            proof=json.loads(physical.read_text())
            row.update(physical_result=str(physical),physical_result_sha256=digest(physical))
            if code!=0 or proof['status']!='pass' or proof['fc_binary_sha256']!=candidate['binary_sha256']:
                raise ValueError('Physical firmware diagnostic did not pass; see '+str(folder/'mission.log'))
            if motor_fault:
                from audit_rate_control import audit_fault
                row['actuator_disturbance_audit']=audit_fault(proof)
            retained_model=folder/'model.so'
            shutil.copyfile(proof['model_build']['library'],retained_model)
            if digest(retained_model)!=proof['model_build']['library_sha256']:
                raise ValueError('Retained physical model differs from the executed model')
            row['retained_model']=dict(path=str(retained_model),sha256=digest(retained_model))
            row['metrics']=rate_metrics(trace,algorithm,result['activity_basis'])
            print(json.dumps(row['metrics']),flush=True)
        verify(manifest,checksum)
        result['status']='pass'
    except Exception as error:
        result['error']=repr(error)
        raise
    finally:
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'result':str(output/'result.json'),'status':result['status']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--algorithms',nargs='+',default=['native','pid'])
    parser.add_argument('--motor-command-disturbance',action='store_true')
    args=parser.parse_args()
    run(args.manifest,args.sha256,args.algorithms,args.motor_command_disturbance)
