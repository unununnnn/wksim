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
GATE_READY_SCHEMA='wksim.private-tracefs.capture-gate-ready.v1'
GATE_RELEASE_SCHEMA='wksim.private-tracefs.capture-release.v1'


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _identity_fields(value,label):
    if (not isinstance(value,dict) or type(value.get('pid')) is not int
            or value.get('pid')<=0 or type(value.get('start_ticks')) is not int
            or value.get('start_ticks')<=0):
        raise RuntimeError(label+' identity is invalid')
    if 'pgid' in value and (type(value.get('pgid')) is not int or value.get('pgid')<=0):
        raise RuntimeError(label+' process-group identity is invalid')
    if 'argv' in value and (not isinstance(value.get('argv'),list)
                            or any(type(item) is not str for item in value['argv'])):
        raise RuntimeError(label+' argv identity is invalid')
    return value['pid'],value['start_ticks']


def _read_instance_owner(path):
    try:raw=Path(path).read_bytes()
    except OSError as error:
        raise RuntimeError('Capture instance owner is unreadable') from error
    try:value=json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError('Capture instance owner is unreadable') from error
    if not isinstance(value,dict):
        raise RuntimeError('Capture instance owner is malformed')
    return value,hashlib.sha256(raw).hexdigest()


def _identity_subset_matches(observed,expected,label):
    """Compare required identity fields and optional fields present on both sides."""
    observed_pid,observed_start=_identity_fields(observed,label+' observed')
    expected_pid,expected_start=_identity_fields(expected,label+' expected')
    if (observed_pid,observed_start)!=(expected_pid,expected_start):
        raise RuntimeError(label+' identity differs')
    for field in ('pgid','argv'):
        if field in observed and field in expected and observed[field]!=expected[field]:
            raise RuntimeError(label+' '+field+' identity differs')


def _identity_expected_fields_match(observed,expected,label):
    """Require every optional identity field declared by the scheduler."""
    _identity_subset_matches(observed,expected,label)
    for field in ('pgid','argv'):
        if field in expected and field not in observed:
            raise RuntimeError(label+' '+field+' identity is missing')


def _validate_expected_owners(observed,expected):
    """Validate the collector's normalized owner map against scheduler identities."""
    if (not isinstance(observed,dict) or not isinstance(expected,dict)
            or set(observed)!=set(expected)):
        raise RuntimeError('Capture owner role set differs')
    for role,expected_identity in expected.items():
        observed_identity=observed.get(role)
        _identity_expected_fields_match(observed_identity,expected_identity,'Capture owner '+role)


def _validate_instance_owner(owner,active,supervisor_proof,collector_identity,expected_owners=None):
    """Bind owner.json to identities and the active token/gate chain.

    ``supervisor_proof`` may be a gate-ready record (with run/epoch) or a
    plain scheduler identity (with only pid/start_ticks).  The top-level
    collector/supervisor schema only carries pid/start_ticks; nested role
    owners must carry every optional identity field supplied by the scheduler.
    """
    if (not isinstance(owner,dict) or not isinstance(active,dict)
            or not isinstance(supervisor_proof,dict)):
        raise RuntimeError('Capture owner identity is malformed')
    _identity_fields(collector_identity,'Collector')
    _identity_fields(supervisor_proof,'Supervisor')
    owner_collector={'pid':owner.get('collector_pid'),
                     'start_ticks':owner.get('collector_start_ticks')}
    owner_supervisor={'pid':owner.get('supervisor_pid'),
                      'start_ticks':owner.get('supervisor_start_ticks')}
    if (owner.get('schema')!='wksim.private-tracefs.instance-owner.v1'
            or owner.get('run_id')!=active.get('run_id')
            or owner.get('epoch')!=active.get('epoch')
            or owner.get('instance')!=active.get('instance')
            or owner.get('instance_inode')!=active.get('instance_inode')):
        raise RuntimeError('Capture instance owner identity differs')
    _identity_subset_matches(owner_collector,collector_identity,'Capture collector')
    _identity_subset_matches(owner_supervisor,supervisor_proof,'Capture supervisor')
    for field in ('run_id','epoch'):
        if field in supervisor_proof and active.get(field)!=supervisor_proof.get(field):
            raise RuntimeError('Capture instance owner identity differs')
    if (type(owner.get('instance')) is not str or not owner.get('instance')
            or type(owner.get('instance_inode')) is not list or len(owner['instance_inode'])!=2
            or any(type(value) is not int or value<=0 for value in owner['instance_inode'])):
        raise RuntimeError('Capture instance owner fields are invalid')
    if active.get('instance_owner_sha256') is not None:
        # The caller compares the digest separately, after reading the raw bytes.
        if not isinstance(active.get('instance_owner_sha256'),str):
            raise RuntimeError('Capture owner digest is invalid')
    if expected_owners is not None:
        _validate_expected_owners(owner.get('owners'),expected_owners)
    return owner


def install_cleanup_signal_handlers():
    """Convert termination into a handled interrupt so run() reaches cleanup."""
    previous={}
    def interrupt(signum,frame):
        raise KeyboardInterrupt()
    for signum in (signal.SIGINT,signal.SIGTERM):
        previous[signum]=signal.signal(signum,interrupt)
    return previous


def restore_cleanup_signal_handlers(previous):
    for signum,handler in previous.items():
        signal.signal(signum,handler)


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
                       collector_identity=None,supervisor_identity=None,expected_owners=None,
                       timeout=CAPTURE_ACTIVE_TIMEOUT_S):
    """Wait for the collector's exclusive post-enable token, or fail closed."""
    expected_collector=collector_identity or json_identity(collector.pid)
    _identity_fields(expected_collector,'Collector')
    expected_supervisor=supervisor_identity
    if expected_supervisor is not None:
        _identity_fields(expected_supervisor,'Supervisor')
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if token.exists():
            try:
                value=json.loads(token.read_bytes())
                owner,owner_sha256=_read_instance_owner(token.parent/'instance-owner.json')
            except (OSError,json.JSONDecodeError) as error:
                raise RuntimeError('Capture-active token is unreadable') from error
            if (not isinstance(value,dict) or not isinstance(owner,dict)
                    or value.get('schema')!='wksim.private-tracefs.capture-active.v1'
                    or owner.get('schema')!='wksim.private-tracefs.instance-owner.v1'
                    or value.get('collector_pid')!=collector.pid
                    or owner.get('collector_pid')!=collector.pid
                    or value.get('collector_start_ticks')!=expected_collector['start_ticks']
                    or owner.get('collector_start_ticks')!=expected_collector['start_ticks']
                    or value.get('state')!='active'
                    or value.get('instance')!=owner.get('instance')
                    or value.get('instance_inode')!=owner.get('instance_inode')
                    or value.get('run_id')!=owner.get('run_id')
                    or value.get('epoch')!=owner.get('epoch')
                    or value.get('instance_owner_sha256')!=owner_sha256
                    or run_id is not None and value.get('run_id')!=run_id
                    or epoch is not None and value.get('epoch')!=epoch):
                raise RuntimeError('Capture-active token identity differs')
            if expected_supervisor is not None:
                if (value.get('supervisor_pid')!=expected_supervisor['pid']
                        or value.get('supervisor_start_ticks')!=expected_supervisor['start_ticks']):
                    raise RuntimeError('Capture-active supervisor identity differs')
            supervisor_proof=expected_supervisor or {
                'pid':value.get('supervisor_pid'),
                'start_ticks':value.get('supervisor_start_ticks'),
                'run_id':value.get('run_id'),'epoch':value.get('epoch')}
            _validate_instance_owner(owner,value,supervisor_proof,
                                     expected_collector,expected_owners)
            current=json_identity(collector.pid)
            if current is None or (current.get('pid'),current.get('start_ticks')) != \
                    (expected_collector['pid'],expected_collector['start_ticks']):
                raise RuntimeError('Collector identity changed before capture became active')
            return value
        if manager is not None and manager.poll() is not None:
            raise RuntimeError('Manager exited before capture became active')
        if collector.poll() is not None:
            raise RuntimeError('Collector exited before capture became active')
        time.sleep(READY_POLL_S)
    raise TimeoutError('Capture-active token was not published')


def wait_gate_ready(path,run_id,epoch,supervisor_identity,*,manager=None,
                    timeout=CAPTURE_ACTIVE_TIMEOUT_S):
    """Wait for the supervisor's tick-zero gate before launching the collector."""
    supervisor_pid,supervisor_start=_identity_fields(supervisor_identity,'Supervisor')
    path=Path(path)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if manager is not None and manager.poll() is not None:
            raise RuntimeError('Manager exited before first-step gate became ready')
        if path.exists():
            try:value=json.loads(path.read_text())
            except (OSError,json.JSONDecodeError) as error:
                raise RuntimeError('First-step gate-ready proof is unreadable') from error
            if (not isinstance(value,dict) or value.get('schema')!=GATE_READY_SCHEMA
                    or value.get('state')!='ready' or value.get('run_id')!=run_id
                    or value.get('epoch')!=epoch or value.get('pid')!=supervisor_pid
                    or value.get('start_ticks')!=supervisor_start
                    or type(value.get('pid')) is not int or value.get('pid')<=0
                    or type(value.get('start_ticks')) is not int or value.get('start_ticks')<=0
                    or type(value.get('tick')) is not int or value.get('tick')!=0
                    or type(value.get('published_monotonic_ns')) is not int
                    or value.get('published_monotonic_ns')<=0):
                raise RuntimeError('First-step gate-ready proof identity differs')
            return value
        time.sleep(READY_POLL_S)
    raise TimeoutError('First-step gate-ready proof was not published')


def wait_gate_release(path,gate_ready,active_token,run_id,epoch,collector,*,manager=None,
                      collector_identity=None,expected_owners=None,
                      timeout=CAPTURE_ACTIVE_TIMEOUT_S):
    """Require the supervisor to release exactly the active collector token."""
    path=Path(path); active_token=Path(active_token)
    gate_ready_path=path.with_name('gate-ready.json')
    expected_collector=collector_identity or json_identity(collector.pid)
    _identity_fields(expected_collector,'Collector')
    _identity_fields(gate_ready,'Supervisor')
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if manager is not None and manager.poll() is not None:
            raise RuntimeError('Manager exited before first-step gate release')
        if collector is not None and collector.poll() is not None:
            raise RuntimeError('Collector exited before first-step gate release')
        if path.exists():
            try:value=json.loads(path.read_text())
            except (OSError,json.JSONDecodeError) as error:
                raise RuntimeError('First-step gate-release proof is unreadable') from error
            if not active_token.exists():
                raise RuntimeError('Capture-active token disappeared before gate release')
            try:
                active=json.loads(active_token.read_bytes())
                owner,owner_sha256=_read_instance_owner(active_token.parent/'instance-owner.json')
            except (OSError,json.JSONDecodeError) as error:
                raise RuntimeError('Capture owner chain is unreadable before gate release') from error
            active_sha256=digest(active_token)
            _validate_instance_owner(owner,active,gate_ready,expected_collector,expected_owners)
            current=json_identity(collector.pid)
            if current is None or (current.get('pid'),current.get('start_ticks')) != \
                    (expected_collector['pid'],expected_collector['start_ticks']):
                raise RuntimeError('Collector identity changed before first-step gate release')
            if (not isinstance(value,dict) or value.get('schema')!=GATE_RELEASE_SCHEMA
                    or value.get('state')!='released' or value.get('run_id')!=run_id
                    or value.get('epoch')!=epoch
                    or value.get('supervisor_pid')!=gate_ready.get('pid')
                    or value.get('supervisor_start_ticks')!=gate_ready.get('start_ticks')
                    or value.get('collector_pid')!=collector.pid
                    or value.get('collector_start_ticks')!=expected_collector['start_ticks']
                    or value.get('capture_active_sha256')!=active_sha256
                    or value.get('instance_owner_sha256')!=owner_sha256
                    or value.get('gate_ready_sha256')!=digest(gate_ready_path)
                    or value.get('instance')!=owner.get('instance')
                    or value.get('instance_inode')!=owner.get('instance_inode')
                    or active.get('schema')!='wksim.private-tracefs.capture-active.v1'
                    or active.get('state')!='active'
                    or active.get('instance_owner_sha256')!=owner_sha256
                    or type(value.get('tick')) is not int or value.get('tick')<0
                    or value.get('tick')>=EARLY_CAPTURE_TICK_LIMIT
                    or value.get('tick')!=gate_ready.get('tick')
                    or type(value.get('capture_active_published_monotonic_ns')) is not int
                    or type(value.get('released_monotonic_ns')) is not int
                    or value.get('capture_active_published_monotonic_ns')!=active.get('published_monotonic_ns')
                    or value.get('released_monotonic_ns')<value.get('capture_active_published_monotonic_ns')
                    or value.get('released_monotonic_ns')<gate_ready.get('published_monotonic_ns')):
                raise RuntimeError('First-step gate-release proof identity differs')
            return value
        time.sleep(READY_POLL_S)
    raise TimeoutError('First-step gate-release proof was not published')


def _read_proof(path,label):
    try:
        raw=Path(path).read_bytes()
        value=json.loads(raw)
    except (OSError,json.JSONDecodeError) as error:
        raise RuntimeError(label+' is unreadable') from error
    if not isinstance(value,dict):
        raise RuntimeError(label+' is malformed')
    return value,hashlib.sha256(raw).hexdigest()


def _validate_gate_ready_proof(value):
    if (not isinstance(value,dict)
            or value.get('schema')!=GATE_READY_SCHEMA
            or value.get('state')!='ready'
            or type(value.get('tick')) is not int or value.get('tick')!=0
            or type(value.get('published_monotonic_ns')) is not int
            or value.get('published_monotonic_ns')<=0):
        raise RuntimeError('First-step gate-ready proof identity differs')
    _identity_fields(value,'Supervisor')


def validate_capture_owner_final(active_token,gate_ready,collector_identity,expected_owners=None,
                                 release_path=None):
    """Re-read the complete active/owner/release chain after collector retirement."""
    if release_path is None:
        raise RuntimeError('First-step gate-release proof path is required')
    active_token=Path(active_token)
    active,active_sha256=_read_proof(active_token,'Capture-active token')
    owner,owner_sha256=_read_instance_owner(active_token.parent/'instance-owner.json')
    release_path=Path(release_path)
    release,release_sha256=_read_proof(release_path,'First-step gate-release proof')
    gate_ready_path=release_path.with_name('gate-ready.json')
    recorded_gate_ready,gate_ready_sha256=_read_proof(gate_ready_path,'First-step gate-ready proof')
    _validate_gate_ready_proof(gate_ready)
    _validate_gate_ready_proof(recorded_gate_ready)
    if recorded_gate_ready!=gate_ready:
        raise RuntimeError('First-step gate-ready proof changed after capture')
    _identity_fields(collector_identity,'Collector')
    collector_pid,collector_start=collector_identity['pid'],collector_identity['start_ticks']
    supervisor_pid,supervisor_start=gate_ready['pid'],gate_ready['start_ticks']
    published=active.get('published_monotonic_ns')
    started=active.get('started_monotonic_ns')
    if (active.get('schema')!='wksim.private-tracefs.capture-active.v1'
            or active.get('state')!='active'
            or active.get('run_id')!=gate_ready.get('run_id')
            or active.get('epoch')!=gate_ready.get('epoch')
            or active.get('collector_pid')!=collector_pid
            or active.get('collector_start_ticks')!=collector_start
            or active.get('supervisor_pid')!=supervisor_pid
            or active.get('supervisor_start_ticks')!=supervisor_start
            or type(started) is not int or started<=0
            or type(published) is not int or published<=0
            or published<started
            or published<gate_ready['published_monotonic_ns']):
        raise RuntimeError('Capture-active token identity differs after collector retirement')
    _validate_instance_owner(owner,active,gate_ready,collector_identity,expected_owners)
    if active.get('instance_owner_sha256')!=owner_sha256:
        raise RuntimeError('Capture owner digest changed after collector retirement')
    released=release.get('released_monotonic_ns')
    release_published=release.get('capture_active_published_monotonic_ns')
    if (release.get('schema')!=GATE_RELEASE_SCHEMA
            or release.get('state')!='released'
            or release.get('run_id')!=gate_ready.get('run_id')
            or release.get('epoch')!=gate_ready.get('epoch')
            or release.get('supervisor_pid')!=supervisor_pid
            or release.get('supervisor_start_ticks')!=supervisor_start
            or release.get('collector_pid')!=collector_pid
            or release.get('collector_start_ticks')!=collector_start
            or release.get('capture_active_sha256')!=active_sha256
            or release.get('instance_owner_sha256')!=owner_sha256
            or release.get('gate_ready_sha256')!=gate_ready_sha256
            or release.get('instance')!=owner.get('instance')
            or release.get('instance_inode')!=owner.get('instance_inode')
            or release.get('tick')!=gate_ready.get('tick')
            or type(release_published) is not int or release_published<=0
            or release_published!=published
            or type(released) is not int or released<=0
            or released<release_published
            or released<gate_ready.get('published_monotonic_ns')):
        raise RuntimeError('First-step gate-release proof identity differs after collector retirement')
    return dict(owner=owner,sha256=owner_sha256,active_sha256=active_sha256,
                release_sha256=release_sha256)


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
    gate_ready = hook/'gate-ready.json'
    gate_release = hook/'gate-release.json'
    capture_output=output/'capture'
    active_token=capture_output/'capture-active.json'
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
    cleanup_handlers = install_cleanup_signal_handlers()
    try:
        with (output/'preflight.log').open('x') as stream:
            checked = subprocess.run(command+['--preflight'], cwd=ROOT, stdout=stream,
                stderr=subprocess.STDOUT, timeout=180)
        result['preflight_returncode'] = checked.returncode
        if checked.returncode: raise RuntimeError('Resource preflight rejected probe')
        with (output/'service.log').open('x') as service, (output/'collector.log').open('x') as trace_log:
            environment = dict(os.environ, WKSIM_JOINT_CPU_TIMING='1', WKSIM_TRACE_RUN=run_id,
                WKSIM_TRACE_HOOK_OUTPUT=str(hook), WKSIM_TRACE_GATE_READY=str(gate_ready),
                WKSIM_TRACE_GATE_RELEASE=str(gate_release),
                WKSIM_TRACE_CAPTURE_ACTIVE_TOKEN=str(active_token),
                PYTHONPATH=str(hook)+os.pathsep+os.environ.get('PYTHONPATH',''))
            result['diagnostic_environment'] = {k:environment[k] for k in (
                'WKSIM_JOINT_CPU_TIMING','WKSIM_TRACE_RUN','WKSIM_TRACE_HOOK_OUTPUT',
                'WKSIM_TRACE_GATE_READY','WKSIM_TRACE_GATE_RELEASE',
                'WKSIM_TRACE_CAPTURE_ACTIVE_TOKEN','PYTHONPATH')}
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
            result['gate_ready'] = wait_gate_ready(gate_ready,run_id,state['epoch'],
                owners['supervisor'],manager=manager)
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
                active_token,collector,run_id,state['epoch'],manager=manager,
                collector_identity=result['collector'],supervisor_identity=owners['supervisor'],
                expected_owners=owners)
            result['gate_release'] = wait_gate_release(
                gate_release,result['gate_ready'],active_token,run_id,state['epoch'],collector,
                manager=manager,collector_identity=result['collector'],expected_owners=owners)
            result['capture_active_status'] = validate_capture_started_early(
                directory/'status.json',run_id,state['epoch'],result['capture_active'],
                manager=manager,collector=collector)
            collector.wait(timeout=40)
            result['collector_returncode'] = collector.returncode
            result['capture_owner_final'] = validate_capture_owner_final(
                active_token,result['gate_ready'],result['collector'],owners,gate_release)
            result['capture'] = json.loads((output/'capture/metadata.json').read_text())
            result['last_observation'] = json.loads((directory/'status.json').read_text())
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = f'{type(error).__name__}: {error}'
    finally:
        try:
            try:
                retire_collector(collector,result)
            except BaseException as error:
                result['collector_cleanup_error']=repr(error)
            try:
                retire_manager(manager,directory,result)
            except BaseException as error:
                result['manager_cleanup_error']=repr(error)
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
        finally:
            restore_cleanup_signal_handlers(cleanup_handlers)
    print(json.dumps({k:result.get(k) for k in ('status','error','manager_cleanup_error','manager_returncode')}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    raise SystemExit(0 if result['status'] == 'diagnostic_captured_and_retired' else 1)
