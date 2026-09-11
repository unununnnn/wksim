"""One owned ground run and one private, PID-filtered scheduler/write capture.

No flight task is started. Diagnostic overhead is not deducted from RateUnmet,
and this probe cannot establish rate acceptance. The product and collector own
their respective process and tracefs lifecycles.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
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
REQUIRED_CHILDREN=('arducopter-model','px4-model','arducopter-fc','px4-fc')
READY_POLL_S=0.010
CAPTURE_ACTIVE_TIMEOUT_S=15.
EARLY_CAPTURE_TICK_LIMIT=40


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def epoch_groups_retired(product_result):
    epochs=product_result.get('epochs') if isinstance(product_result,dict) else None
    return bool(epochs) and all(isinstance(e,dict) and e.get('remaining_group_members')==[] for e in epochs)


def failure_payload_clean(value):
    """Reject any non-empty failure field, including nested evidence payloads."""
    failure_names={'error','errors','failures','unresolved'}

    def empty(item):
        return item is None or item=='' or (
            isinstance(item,(dict,list,tuple,set)) and not item)

    if isinstance(value,dict):
        for key,item in value.items():
            name=str(key).lower()
            if ((name in failure_names or name.endswith('_error') or name.endswith('_errors'))
                    and not empty(item)):
                return False
            if not failure_payload_clean(item):
                return False
    elif isinstance(value,(list,tuple,set)):
        if not all(failure_payload_clean(item) for item in value):
            return False
    return True


def product_result_clean(product_result):
    """Require a present product result with no failed top-level or epoch status."""
    allowed={'pass','stopped','cold_reset'}
    if (not isinstance(product_result,dict) or not failure_payload_clean(product_result)
            or product_result.get('status') not in allowed):
        return False
    epochs=product_result.get('epochs')
    if not isinstance(epochs,list) or not epochs:
        return False
    for epoch in epochs:
        if not isinstance(epoch,dict) or epoch.get('remaining_group_members')!=[]:
            return False
        report=epoch.get('result')
        if not isinstance(report,dict) or report.get('status') not in allowed:
            return False
    return True


def complete_child_ownership(children,supervisor=None):
    """Return child identities only after one complete, unambiguous snapshot."""
    if not isinstance(children,dict):
        return None
    missing=set(REQUIRED_CHILDREN)-set(children)
    if missing:
        return None
    owners={}
    identities=[]
    for name in REQUIRED_CHILDREN:
        row=children[name]
        identity=row.get('identity') if isinstance(row,dict) else None
        if not isinstance(identity,dict):
            raise ValueError('Incomplete child ownership identity: '+name)
        pid=identity.get('pid');start=identity.get('start_ticks')
        if not isinstance(pid,int) or isinstance(pid,bool) or pid<=0:
            raise ValueError('Invalid child ownership PID: '+name)
        if not isinstance(start,int) or isinstance(start,bool) or start<=0:
            raise ValueError('Invalid child ownership start time: '+name)
        owners[name]=identity
        identities.append((pid,start))
    if len(set(identities))!=len(identities):
        raise ValueError('Ambiguous child ownership identity')
    if supervisor is not None:
        supervisor_pid=supervisor.get('pid') if isinstance(supervisor,dict) else None
        if supervisor_pid in {identity['pid'] for identity in owners.values()}:
            raise ValueError('Child ownership overlaps supervisor identity')
    return owners


def complete_fc_thread_names(names,required):
    """Require one and only one local task for every diagnostic FC name."""
    if not isinstance(names,(list,tuple,set)):
        raise ValueError('FC thread inventory is not a name collection')
    counts={name:sum(value==name for value in names) for name in required}
    ambiguous=[name for name,count in counts.items() if count>1]
    if ambiguous:
        raise ValueError('Ambiguous FC thread ownership: '+','.join(sorted(ambiguous)))
    return all(count==1 for count in counts.values())


def fc_threads_ready(children):
    """Avoid spending the only diagnostic run before required FC tasks exist."""
    try:
        for role,required in FC_THREAD_NAMES.items():
            pid=children[role]['identity']['pid']
            names=[(path/'comm').read_text().strip()
                   for path in (Path('/proc')/str(pid)/'task').iterdir() if path.name.isdigit()]
            if not complete_fc_thread_names(names,required):return False
        return True
    except (KeyError,OSError):
        return False


def wait_capture_active(token,collector,run_id=None,epoch=None,*,manager=None,
                       timeout=CAPTURE_ACTIVE_TIMEOUT_S):
    """Wait for the collector's exclusive post-enable token, or fail closed."""
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if token.exists():
            try:
                value=json.loads(token.read_text())
                owner=json.loads((token.parent/'instance-owner.json').read_text())
            except (OSError,json.JSONDecodeError) as error:
                raise RuntimeError('Capture-active token is unreadable') from error
            if (not isinstance(value,dict) or not isinstance(owner,dict)
                    or value.get('schema')!='wksim.private-tracefs.capture-active.v1'
                    or owner.get('schema')!='wksim.private-tracefs.instance-owner.v1'
                    or value.get('collector_pid')!=collector.pid
                    or owner.get('collector_pid')!=collector.pid
                    or value.get('state')!='active'
                    or value.get('instance')!=owner.get('instance')
                    or value.get('instance_inode')!=owner.get('instance_inode')
                    or value.get('run_id')!=owner.get('run_id')
                    or value.get('epoch')!=owner.get('epoch')
                    or run_id is not None and value.get('run_id')!=run_id
                    or epoch is not None and value.get('epoch')!=epoch):
                raise RuntimeError('Capture-active token identity differs')
            return value
        if manager is not None and manager.poll() is not None:
            raise RuntimeError('Manager exited before capture became active')
        if collector.poll() is not None:
            raise RuntimeError('Collector exited before capture became active')
        time.sleep(READY_POLL_S)
    raise TimeoutError('Capture-active token was not published')


def validate_capture_started_early(status_path,run_id,epoch,active,*,manager=None,
                                   collector=None,timeout=CAPTURE_ACTIVE_TIMEOUT_S):
    """Require the active token and same-epoch status to precede timed tick 40."""
    if (active.get('run_id') != run_id or active.get('epoch') != epoch
            or active.get('state') != 'active'):
        raise RuntimeError('Capture-active token run/epoch identity differs')
    published=active.get('published_monotonic_ns')
    if (not isinstance(published,int) or isinstance(published,bool) or published<=0):
        raise RuntimeError('Capture-active token publication time is invalid')
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if manager is not None and manager.poll() is not None:
            raise RuntimeError('Manager exited before a fresh capture status')
        if collector is not None and collector.poll() is not None:
            raise RuntimeError('Collector exited before a fresh capture status')
        try:
            state=json.loads(Path(status_path).read_text())
        except (OSError,json.JSONDecodeError):
            state=None
        if isinstance(state,dict):
            authority=state.get('authority')
            if (state.get('run_id') != run_id or state.get('epoch') != epoch
                    or not isinstance(authority,dict)
                    or authority.get('epoch') != epoch):
                raise RuntimeError('Post-token status run/epoch changed')
            issued=state.get('issued_monotonic_s')
            fresh=(not isinstance(issued,bool) and isinstance(issued,(int,float))
                   and math.isfinite(float(issued)) and issued>0
                   and int(float(issued)*1_000_000_000)>=published)
            if fresh:
                tick=authority.get('tick')
                if not isinstance(tick,int) or isinstance(tick,bool) or tick < 0:
                    raise RuntimeError('Post-token status tick is invalid')
                if tick >= EARLY_CAPTURE_TICK_LIMIT:
                    raise RuntimeError('Capture became active at or after timed tick 40')
                return state
        time.sleep(READY_POLL_S)
    raise TimeoutError('Fresh capture status was not published')


def kill_collector_group(collector,expected):
    """Kill only the collector's private process group after graceful timeout."""
    if collector.poll() is not None:
        return
    if not isinstance(expected,dict):
        raise RuntimeError('Collector identity is unavailable')
    current=json_identity(collector.pid)
    if current is None:
        raise RuntimeError('Collector identity disappeared before group kill')
    for field in ('pid','start_ticks','pgid'):
        if current.get(field)!=expected.get(field):
            raise RuntimeError('Collector '+field+' identity differs')
    if os.name == 'posix':
        pgid=current['pgid']
        if pgid != collector.pid:
            raise RuntimeError('Collector process group identity differs')
        # start_new_session makes this a private group; the kernel does not
        # offer an atomic identity recheck together with signal delivery.
        os.killpg(pgid,signal.SIGKILL)
    else:
        # The diagnostic only runs under WSL/Linux; retain a portable fallback
        # for the pure lifecycle tests and native Windows imports.
        collector.kill()


def retire_collector(collector,result):
    """Bound collector cleanup and fail closed if its process remains live."""
    if collector is None:
        return
    if collector.poll() is not None:
        result['collector_returncode']=getattr(collector,'returncode',collector.poll())
        return
    try:
        collector.terminate()
    except ProcessLookupError:
        pass
    except BaseException as error:
        result['collector_cleanup_error']='Collector terminate failed: '+repr(error)
    try:
        collector.wait(timeout=30)
    except subprocess.TimeoutExpired:
        result['collector_cleanup_error']='Collector did not retire after terminate'
    if collector.poll() is None:
        try:
            kill_collector_group(collector,result.get('collector'))
            result['collector_group_killed']=True
        except ProcessLookupError:
            pass
        except BaseException as error:
            result['collector_cleanup_error']=str(result.get('collector_cleanup_error','')) + \
                '; force kill: '+repr(error)
        try:
            collector.wait(timeout=10)
        except subprocess.TimeoutExpired:
            result['collector_cleanup_error']=str(result.get('collector_cleanup_error','')) + \
                '; Collector still live after force kill'
    if collector.poll() is None:
        result['collector_cleanup_error']=str(result.get('collector_cleanup_error','')) + \
            '; Collector retirement could not be verified'
    result['collector_returncode']=collector.poll()


def kill_manager_group(manager,expected,group_snapshot=None):
    """Kill only the manager session after verifying this run still owns it."""
    if manager.poll() is not None:
        return
    if not isinstance(expected,dict):
        raise RuntimeError('Manager identity is unavailable')
    current=json_identity(manager.pid)
    if current is None:
        raise RuntimeError('Manager identity disappeared before group kill')
    for field in ('pid','start_ticks','pgid'):
        if current.get(field)!=expected.get(field):
            raise RuntimeError('Manager '+field+' identity differs')
    if group_snapshot is not None:
        verify_manager_group_snapshot(expected,group_snapshot)
    if os.name == 'posix':
        if current['pgid'] != current['pid'] or current['pgid'] != manager.pid:
            raise RuntimeError('Manager process group identity differs')
        # start_new_session makes this a private group; the kernel does not
        # offer an atomic identity recheck together with signal delivery.
        os.killpg(current['pgid'],signal.SIGKILL)
    else:
        manager.kill()


def manager_group_snapshot(manager,expected):
    """Capture the manager session's exact members before the leader can exit."""
    if os.name!='posix':
        return None
    if not isinstance(expected,dict):
        raise RuntimeError('Manager identity is unavailable')
    current=json_identity(manager.pid)
    if current is None:
        raise RuntimeError('Manager identity disappeared before group snapshot')
    for field in ('pid','start_ticks','pgid'):
        if current.get(field)!=expected.get(field):
            raise RuntimeError('Manager '+field+' identity differs')
    if current['pgid'] != current['pid'] or current['pgid'] != manager.pid:
        raise RuntimeError('Manager process group identity differs')
    members=group_members(expected['pgid'])
    identities={(row.get('pid'),row.get('start_ticks')) for row in members
                if isinstance(row,dict)}
    if (expected['pid'],expected['start_ticks']) not in identities:
        raise RuntimeError('Manager leader is absent from owned group snapshot')
    return identities


def save_manager_group_snapshot(manager,result):
    """Persist the latest leader-alive group identities in JSON-safe form."""
    snapshot=manager_group_snapshot(manager,result.get('manager'))
    result['manager_group_snapshot']=[dict(pid=pid,start_ticks=start)
                                     for pid,start in sorted(snapshot)]
    return snapshot


def verify_manager_group_snapshot(expected,snapshot):
    """Allow a group kill only for members observed before the leader exited."""
    if isinstance(snapshot,set):
        identities=snapshot
    elif isinstance(snapshot,list):
        identities=set()
        for row in snapshot:
            if isinstance(row,dict):
                identities.add((row.get('pid'),row.get('start_ticks')))
            elif isinstance(row,(list,tuple)) and len(row)==2:
                identities.add((row[0],row[1]))
            else:
                raise RuntimeError('Manager group snapshot is malformed')
    else:
        raise RuntimeError('Manager group snapshot is unavailable')
    if (expected.get('pid'),expected.get('start_ticks')) not in identities:
        raise RuntimeError('Manager leader is absent from group snapshot')
    members=group_members(expected['pgid'])
    for row in members:
        if (not isinstance(row,dict) or row.get('pgid')!=expected['pgid']
                or (row.get('pid'),row.get('start_ticks')) not in identities):
            raise RuntimeError('Manager group member identity differs')
    return members


def kill_manager_group_after_leader(expected,group_snapshot):
    """Kill only a previously verified manager group after leader reaping."""
    if os.name!='posix':
        return
    members=verify_manager_group_snapshot(expected,group_snapshot)
    if members:
        # The snapshot proves ownership; signal delivery still has a kernel
        # TOCTOU boundary because group inspection and killpg are separate.
        os.killpg(expected['pgid'],signal.SIGKILL)


def retire_manager(manager,directory,result):
    """Stop the owned manager, then fail closed with a verified group kill."""
    if manager is None:
        return
    expected=result.get('manager')
    group_snapshot=result.get('manager_group_snapshot')
    if getattr(manager,'returncode',None) is None:
        try:
            state=json.loads((directory/'status.json').read_text())
            if not isinstance(state,dict) or state.get('run_id')!=result.get('run_id'):
                raise RuntimeError('Manager status run identity differs')
            result['stop_request']=submit(directory,'stop',state['epoch'])
            manager.wait(timeout=40)
        except BaseException as error:
            result['manager_cleanup_error']=repr(error)
    if getattr(manager,'returncode',None) is None:
        try:
            kill_manager_group(manager,expected,group_snapshot)
            result['manager_group_killed']=True
        except BaseException as error:
            result['manager_cleanup_error']=str(result.get('manager_cleanup_error',''))+\
                '; force kill: '+repr(error)
        try:
            manager.wait(timeout=10)
        except subprocess.TimeoutExpired:
            result['manager_cleanup_error']=str(result.get('manager_cleanup_error',''))+\
                '; Manager still live after force kill'
    result['manager_returncode']=manager.poll()
    if (os.name=='posix' and getattr(manager,'returncode',None) is not None
            and group_snapshot is not None):
        try:
            if verify_manager_group_snapshot(expected,group_snapshot):
                kill_manager_group_after_leader(expected,group_snapshot)
                result['manager_group_killed']=True
                deadline=time.monotonic()+10
                while time.monotonic()<deadline and group_members(expected['pgid']):
                    time.sleep(.05)
        except BaseException as error:
            result['manager_cleanup_error'] = (
                str(result.get('manager_cleanup_error',''))
                + '; leader-exit group cleanup: '+repr(error))
    if isinstance(expected,dict) and isinstance(expected.get('pgid'),int):
        try:
            result['remaining_manager_group']=group_members(expected['pgid'])
        except BaseException as error:
            result['manager_cleanup_error']=str(result.get('manager_cleanup_error',''))+\
                '; group inspection: '+repr(error)
            result['remaining_manager_group']=[True]
    else:
        result['manager_cleanup_error']=str(result.get('manager_cleanup_error',''))+\
            '; Manager group identity is unavailable'
        result['remaining_manager_group']=[True]


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
            if os.name=='posix' and result['manager'] is not None:
                try:
                    save_manager_group_snapshot(manager,result)
                except (OSError,RuntimeError):
                    # Startup can race /proc task publication; the ownership-ready
                    # checkpoint below is the required pre-retirement snapshot.
                    pass
            write_json(output/'launch.json', result)
            deadline = time.monotonic()+180
            while True:
                if manager.poll() is not None: raise RuntimeError('Manager exited before native targets were ready')
                if time.monotonic() >= deadline: raise TimeoutError('Native target startup')
                status_path = directory/'status.json'
                if status_path.exists():
                    state = json.loads(status_path.read_text())
                    child_path = directory/'epochs'/state['epoch']/'children.json'
                    if child_path.exists():
                        children = json.loads(child_path.read_text())
                        child_owners=complete_child_ownership(children,state.get('supervisor'))
                        if child_owners is not None and fc_threads_ready(children):
                            if os.name=='posix':
                                save_manager_group_snapshot(manager,result)
                            break
                time.sleep(READY_POLL_S)
            owners = dict(ap_worker=child_owners['arducopter-model'],
                          px4_worker=child_owners['px4-model'], supervisor=state['supervisor'],
                          ap_fc=child_owners['arducopter-fc'],px4_fc=child_owners['px4-fc'])
            result.update(epoch=state['epoch'], owners=owners, capture_start_state=state)
            capture_output=output/'capture'
            active_token=capture_output/'capture-active.json'
            argv = [sys.executable, '-B', str(COLLECTOR), '--boot-id', result['boot_id'],
                    '--run-id', run_id, '--epoch', state['epoch'], '--duration', '10',
                    '--map-comm',
                    '--capture-active-token', str(active_token),
                    '--output', str(capture_output)]
            for role, identity in owners.items():
                argv += ['--'+role.replace('_', '-'), f"{identity['pid']}:{identity['start_ticks']}"]
            result['collector_command'] = argv
            collector = subprocess.Popen(argv, cwd=ROOT, stdout=trace_log,
                stderr=subprocess.STDOUT, start_new_session=True)
            result['collector'] = json_identity(collector.pid)
            write_json(output/'capture-launch.json', result)
            result['capture_active'] = wait_capture_active(
                active_token,collector,run_id,state['epoch'],manager=manager)
            result['capture_active_status'] = validate_capture_started_early(
                directory/'status.json',run_id,state['epoch'],result['capture_active'],
                manager=manager,collector=collector)
            collector.wait(timeout=40)
            result['collector_returncode'] = collector.returncode
            result['capture'] = json.loads((output/'capture/metadata.json').read_text())
            result['last_observation'] = json.loads((directory/'status.json').read_text())
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = f'{type(error).__name__}: {error}'
    finally:
        retire_collector(collector,result)
        retire_manager(manager,directory,result)
        if (directory/'result.json').exists(): result['product_result'] = json.loads((directory/'result.json').read_text())
        result['epoch_groups_retired'] = epoch_groups_retired(result.get('product_result'))
        result['sources_unchanged'] = all(digest(ROOT/name) == sha for name, sha in result['source_sha256'].items())
        if (result.get('capture', {}).get('complete')
                and result.get('manager_returncode')==0
                and result.get('collector_returncode')==0
                and not result.get('remaining_manager_group', [True]) and result['sources_unchanged']
                and result['epoch_groups_retired']
                and product_result_clean(result.get('product_result'))
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
