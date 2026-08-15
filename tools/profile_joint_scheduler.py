"""One owned ground run and one private, PID-filtered scheduler/write capture.

No flight task is started. Diagnostic overhead is not deducted from RateUnmet,
and this probe cannot establish rate acceptance. The product and collector own
their respective process and tracefs lifecycles.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Simulator.wksim_runtime.evidence import write_json, json_identity, group_members, host_boot_id
from Simulator.wksim_runtime.joint_actions import submit

COLLECTOR = ROOT/'validation/rate-syscall-scheduler-plan-20260909/collect_tracefs.py'
FC_THREAD_NAMES={'arducopter-fc':{'arducopter','log_io','DDS'},
                 'px4-fc':{'sim_send','logger','wq:lp_default'}}


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def epoch_groups_retired(product_result):
    epochs=product_result.get('epochs') if isinstance(product_result,dict) else None
    return bool(epochs) and all(isinstance(e,dict) and e.get('remaining_group_members')==[] for e in epochs)


def fc_threads_ready(children):
    """Avoid spending the only diagnostic run before required FC tasks exist."""
    try:
        for role,required in FC_THREAD_NAMES.items():
            pid=children[role]['identity']['pid']
            names={(path/'comm').read_text().strip()
                   for path in (Path('/proc')/str(pid)/'task').iterdir() if path.name.isdigit()}
            if not required.issubset(names):return False
        return True
    except (KeyError,OSError):
        return False


def run(output):
    if output.parent != Path('/root') or not output.name.startswith('wksim-scheduler-probe-') or output.exists():
        raise ValueError('Use a fresh /root/wksim-scheduler-probe-* directory')
    output.mkdir(mode=0o700)
    runs = output/'runs'; runs.mkdir()
    run_id = 'scheduler-'+uuid.uuid4().hex[:12]
    directory = runs/run_id
    config = dict(schema_version=1, kind='joint_scene', run_id=run_id,
                  runtime_profile='joint_quad_dds_v1', requested_rate=1.)
    write_json(output/'experiment.json', config)
    hook = output/'hook'; hook.mkdir()
    hook_source = ROOT/'validation/rate-remediation-ff63c72/sitecustomize.py'
    shutil.copy2(hook_source, hook/'sitecustomize.py')
    command = ['taskset', '-c', '0-7', 'bash', str(ROOT/'tools/run-wksim.sh'),
               str(output/'experiment.json'), '--output-root', str(runs)]
    result = dict(status='diagnostic_partial', acceptance_eligible=False, run_id=run_id,
        directory=str(directory), command=command, boot_id=host_boot_id(),
        started_monotonic_ns=time.monotonic_ns(), source_sha256={str(p.relative_to(ROOT)):digest(p) for p in (
            Path(__file__).resolve(), COLLECTOR, ROOT/'Simulator/wksim_core/worker.py',
            hook_source,
            ROOT/'Simulator/wksim_core/joint.py', ROOT/'Simulator/wksim_runtime/joint_rate.py',
            ROOT/'Simulator/wksim_runtime/joint_runtime.py')})
    manager = collector = None
    try:
        with (output/'preflight.log').open('x') as stream:
            checked = subprocess.run(command+['--preflight'], cwd=ROOT, stdout=stream,
                stderr=subprocess.STDOUT, timeout=180)
        result['preflight_returncode'] = checked.returncode
        if checked.returncode: raise RuntimeError('Resource preflight rejected probe')
        with (output/'service.log').open('x') as service, (output/'collector.log').open('x') as trace_log:
            environment = dict(os.environ, WKSIM_JOINT_CPU_TIMING='1', WKSIM_TRACE_RUN=run_id,
                WKSIM_TRACE_HOOK_OUTPUT=str(hook), PYTHONPATH=str(hook)+os.pathsep+os.environ.get('PYTHONPATH',''))
            result['diagnostic_environment'] = {k:environment[k] for k in ('WKSIM_JOINT_CPU_TIMING','WKSIM_TRACE_RUN','WKSIM_TRACE_HOOK_OUTPUT','PYTHONPATH')}
            manager = subprocess.Popen(command, cwd=ROOT, env=environment,
                stdout=service, stderr=subprocess.STDOUT, start_new_session=True)
            result['manager'] = json_identity(manager.pid)
            write_json(output/'launch.json', result)
            deadline = time.monotonic()+180
            while True:
                if manager.poll() is not None: raise RuntimeError('Manager exited before native targets were ready')
                if time.monotonic() >= deadline: raise TimeoutError('Native target startup')
                status_path = directory/'status.json'
                if status_path.exists():
                    state = json.loads(status_path.read_text())
                    child_path = directory/'epochs'/state['epoch']/'children.json'
                    if child_path.exists() and state['authority']['tick'] >= 40:
                        children = json.loads(child_path.read_text())
                        if (all(k in children for k in ('arducopter-model','px4-model','arducopter-fc','px4-fc'))
                                and fc_threads_ready(children)):
                            break
                time.sleep(.02)
            owners = dict(ap_worker=children['arducopter-model']['identity'],
                          px4_worker=children['px4-model']['identity'], supervisor=state['supervisor'],
                          ap_fc=children['arducopter-fc']['identity'],px4_fc=children['px4-fc']['identity'])
            result.update(epoch=state['epoch'], owners=owners, capture_start_state=state)
            argv = [sys.executable, '-B', str(COLLECTOR), '--boot-id', result['boot_id'],
                    '--run-id', run_id, '--epoch', state['epoch'], '--duration', '10',
                    '--map-comm',
                    '--output', str(output/'capture')]
            for role, identity in owners.items():
                argv += ['--'+role.replace('_', '-'), f"{identity['pid']}:{identity['start_ticks']}"]
            result['collector_command'] = argv
            collector = subprocess.Popen(argv, cwd=ROOT, stdout=trace_log,
                stderr=subprocess.STDOUT, start_new_session=True)
            result['collector'] = json_identity(collector.pid)
            write_json(output/'capture-launch.json', result)
            collector.wait(timeout=40)
            result['collector_returncode'] = collector.returncode
            result['capture'] = json.loads((output/'capture/metadata.json').read_text())
            result['last_observation'] = json.loads((directory/'status.json').read_text())
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = f'{type(error).__name__}: {error}'
    finally:
        if collector is not None and collector.poll() is None:
            # Signal only the owned collector, which cleans its own instance.
            collector.terminate()
            try: collector.wait(timeout=30)
            except subprocess.TimeoutExpired: result['collector_cleanup_error'] = 'Collector still live; inspect owned instance'
        if manager is not None and manager.poll() is None:
            try:
                state = json.loads((directory/'status.json').read_text())
                result['stop_request'] = submit(directory, 'stop', state['epoch'])
                manager.wait(timeout=40)
            except Exception as error: result['manager_cleanup_error'] = repr(error)
        if manager is not None:
            result['manager_returncode'] = manager.poll()
            result['remaining_manager_group'] = group_members(manager.pid)
        if (directory/'result.json').exists(): result['product_result'] = json.loads((directory/'result.json').read_text())
        result['epoch_groups_retired'] = epoch_groups_retired(result.get('product_result'))
        result['sources_unchanged'] = all(digest(ROOT/name) == sha for name, sha in result['source_sha256'].items())
        if (result.get('capture', {}).get('complete') and result.get('manager_returncode') is not None
                and not result.get('remaining_manager_group', [True]) and result['sources_unchanged']
                and result['epoch_groups_retired']
                and not any(k.endswith('error') for k in result)):
            result['status'] = 'diagnostic_captured_and_retired'
        result['finished_monotonic_ns'] = time.monotonic_ns()
        write_json(output/'report.json', result)
    print(json.dumps({k:result.get(k) for k in ('status','error','manager_cleanup_error','manager_returncode')}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    raise SystemExit(0 if result['status'] == 'diagnostic_captured_and_retired' else 1)
