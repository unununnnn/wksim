"""Frozen #61 host-placement candidate. --check never launches flight processes.

One numbered invocation is one attempt; failures are not retried in this directory.
The actual flight remains the existing shipped service and steady rate driver.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from Simulator.wksim_runtime.evidence import write_json, json_identity, group_members, host_boot_id
from Simulator.wksim_runtime.joint_config import validate_joint_config


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(number):
    manifest = json.loads((HERE / 'candidate.json').read_text())
    for name, expected in manifest['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('Frozen source/config changed: ' + name)
    config = validate_joint_config(json.loads((HERE / f'experiment-{number}.json').read_text()))
    if config['requested_rate'] != 1 or config['task_dwell_seconds'] != {'hold':35, 'waypoint':35}:
        raise ValueError('Frozen rate/dwell changed')
    if sys.platform != 'linux' or sorted(os.sched_getaffinity(0)) != manifest['affinity_cpus']:
        raise ValueError('Launch with the frozen Linux CPU set 0-7')
    if platform.release() != manifest['linux_kernel']:
        raise ValueError('Frozen host kernel changed')
    if os.environ.get('WKSIM_JOINT_CPU_TIMING'):
        raise ValueError('Acceptance candidate must not enable CPU timing instrumentation')
    return manifest, config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('number', type=int, choices=(1,2,3))
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    manifest, config = check(args.number)
    if args.check:
        print(json.dumps(dict(status='identity_checked_only', affinity_cpus=sorted(os.sched_getaffinity(0)),
            run_id=config['run_id'], performance_pass=False)))
        return 0
    # Each later cohort member needs the preceding independently audited result.
    if args.number > 1:
        previous = json.loads((ROOT / manifest['runs'][str(args.number-1)]['audit']).read_text())
        if previous['status'] != 'pass':
            raise ValueError('Previous epoch has not passed independent audit')
    evidence = ROOT / manifest['runs'][str(args.number)]['evidence']
    evidence.mkdir(exist_ok=False)
    case = evidence / 'case'
    case.mkdir()
    output = Path(manifest['runs'][str(args.number)]['output_root'])
    output.mkdir(exist_ok=False)
    write_json(case / 'experiment.json', config)
    shutil.copyfile(__file__, case / 'wrapper.py')
    command = ['bash', str(ROOT / 'tools/run-wksim.sh'), str(case / 'experiment.json'), '--output-root', str(output)]
    record = dict(command=command, requested_rate=1.0, mode='steady', host_boot_id=host_boot_id(),
        started_unix_s=time.time(), wrapper_sha256=sha(Path(__file__)), candidate_id=manifest['candidate_id'],
        affinity_cpus=sorted(os.sched_getaffinity(0)), candidate_sha256=sha(HERE / 'candidate.json'))
    manager = None
    code = 1
    with (case / 'service.log').open('x') as log:
        try:
            # Current resource admission is mandatory immediately before each attempt.
            preflight = command + ['--preflight']
            with (case / 'preflight.log').open('x') as stream:
                checked = subprocess.run(preflight, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
            record.update(preflight_command=preflight, preflight_returncode=checked.returncode)
            if checked.returncode:
                raise RuntimeError('Current resource preflight rejected candidate')
            check(args.number)
            manager = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            record['manager'] = json_identity(manager.pid)
            directory = output / config['run_id']
            deadline = time.monotonic() + 180
            while True:
                if manager.poll() is not None:
                    raise RuntimeError('Manager exited before initial status')
                if (directory / 'status.json').is_file():
                    status = json.loads((directory / 'status.json').read_text())
                    if 'start-task' in status.get('allowed_actions', []):
                        break
                    if status.get('phase') in ('failed', 'faulted', 'stopped'):
                        raise RuntimeError('Ground readiness failed: ' + status['phase'])
                if time.monotonic() >= deadline:
                    raise TimeoutError('Initial formal ground readiness')
                time.sleep(.05)
            identities = {'supervisor':status['supervisor']}
            children = json.loads((directory / 'epochs' / status['epoch'] / 'children.json').read_text())
            identities.update({name:value['identity'] for name,value in children.items()})
            record['affinity_readback'] = {}
            for name, original in identities.items():
                current = json_identity(original['pid'])
                if current is None or any(current[key] != original[key] for key in ('pid','pgid','start_ticks')):
                    raise RuntimeError('Owned process identity differs before affinity readback: ' + name)
                affinity = sorted(os.sched_getaffinity(original['pid']))
                record['affinity_readback'][name] = dict(identity=current, cpus=affinity)
                if affinity != manifest['affinity_cpus']:
                    raise ValueError('Owned process did not inherit candidate affinity: ' + name)
            driver = [sys.executable, '-B', str(ROOT / 'tools/validate_joint_rate.py'), str(directory),
                '--output', str(case / 'flow.json'), '--mode', 'steady']
            record['driver_command'] = driver
            with (case / 'driver.log').open('x') as stream:
                tested = subprocess.run(driver, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=1500)
            record['driver_returncode'] = tested.returncode
            manager.wait(timeout=25)
            check(args.number)
            code = tested.returncode
        except BaseException as error:
            record['error'] = repr(error)
        finally:
            if manager is not None and manager.poll() is None:
                current = json_identity(manager.pid)
                if current is None or any(current[key] != record['manager'][key] for key in ('pid','pgid','start_ticks')):
                    raise RuntimeError('Owned manager identity changed; do not signal a reused PID')
                os.killpg(manager.pid, signal.SIGTERM)
                try:
                    manager.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(manager.pid, signal.SIGKILL)
                    manager.wait(timeout=5)
            record['manager_returncode'] = None if manager is None else manager.returncode
            record['remaining_manager_group'] = [] if manager is None else group_members(manager.pid)
            if (output / config['run_id']).exists():
                shutil.copytree(output / config['run_id'], case / 'run')
            record['finished_unix_s'] = time.time()
            write_json(case / 'wrapper.json', record)
    print(json.dumps(dict(returncode=code, evidence=str(case), error=record.get('error'))))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
