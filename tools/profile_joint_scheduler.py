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
import select
import signal
import subprocess
import sys
import time
import uuid
import shutil
import tempfile
import threading

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
BOOTSTRAP_SCHEMA='wksim.private-tracefs.capture-bootstrap-active.v1'
ACTIVE_SCHEMA='wksim.private-tracefs.capture-active.v1'
STARTUP_READINESS_SCHEMA='wksim.private-tracefs.startup-readiness.v1'
STARTUP_REQUIRED=('supervisor','ap_worker','px4_worker','ap_fc','px4_fc')


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def create_only_json(path,value):
    """Publish one complete JSON fact without replacing an existing fact."""
    target=Path(path)
    raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
    descriptor,temporary=tempfile.mkstemp(prefix='.'+target.name+'-',suffix='.tmp',dir=target.parent)
    try:
        offset=0
        while offset<len(raw):
            offset += os.write(descriptor,raw[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor=None
        if target.exists():
            raise FileExistsError(str(target))
        os.link(temporary,target)
        os.unlink(temporary)
        temporary=None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def startup_readiness(state,child_owners=None,gate_ready=None):
    """Describe startup ownership and preserve an authority terminal state."""
    observed={}
    if isinstance(state,dict) and isinstance(state.get('supervisor'),dict):
        observed['supervisor']=state['supervisor']
    if isinstance(child_owners,dict):
        observed.update(dict(
            ap_worker=child_owners.get('arducopter-model'),
            px4_worker=child_owners.get('px4-model'),
            ap_fc=child_owners.get('arducopter-fc'),
            px4_fc=child_owners.get('px4-fc')))
        observed={key:value for key,value in observed.items() if value is not None}
    if gate_ready is not None:
        observed['gate_ready']=gate_ready
    missing=[name for name in STARTUP_REQUIRED if name not in observed]
    authority=state.get('authority',{}) if isinstance(state,dict) else {}
    phase=state.get('phase') if isinstance(state,dict) else None
    authority_phase=authority.get('phase') if isinstance(authority,dict) else None
    terminal=phase if phase in ('faulted','stopped') else authority_phase if authority_phase in ('faulted','stopped') else None
    return dict(schema=STARTUP_READINESS_SCHEMA,state='authority_'+terminal if terminal else ('ready' if not missing and gate_ready is not None else 'waiting'),
                required=list(STARTUP_REQUIRED),observed=observed,missing=missing,
                authority=authority,phase=phase,run_id=state.get('run_id') if isinstance(state,dict) else None,
                epoch=state.get('epoch') if isinstance(state,dict) else None,
                gate_ready=gate_ready)


def publish_startup_readiness(path,state,child_owners=None,gate_ready=None):
    value=startup_readiness(state,child_owners,gate_ready)
    create_only_json(path,value)
    return value


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


def install_cleanup_signal_handlers(cancelled=None):
    """Convert termination into a handled interrupt so run() reaches cleanup."""
    previous={}
    def interrupt(signum,frame):
        if cancelled is not None:
            cancelled.set()
            return
        raise KeyboardInterrupt()
    for signum in (signal.SIGINT,signal.SIGTERM):
        previous[signum]=signal.signal(signum,interrupt)
    return previous


def restore_cleanup_signal_handlers(previous):
    for signum,handler in previous.items():
        signal.signal(signum,handler)


class _HostInputWatcher:
    """Own the watcher thread so callers can stop and reap it explicitly."""

    def __init__(self, stream, callback):
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._watch, args=(stream, callback),
                                         name='wksim-host-stdin')
        self._thread.daemon = True
        self._thread.start()

    def _watch(self, stream, callback):
        fd = None
        try:
            fd = stream.fileno()
        except (AttributeError, OSError, ValueError):
            pass

        if os.name == 'posix' and isinstance(fd, int) and fd >= 0:
            try:
                while not self._stopped.is_set():
                    readable, _, _ = select.select([fd], [], [], .1)
                    if not readable:
                        continue
                    chunk = os.read(fd, 4096)
                    if not chunk:
                        break
                if not self._stopped.is_set():
                    callback()
                return
            except (OSError, ValueError):
                # Once a real POSIX fd was selected, never fall back to a
                # BufferedReader read: a closed or invalid fd must not leave
                # the interpreter blocked on its internal buffer lock.
                if not self._stopped.is_set():
                    callback()
                return

        try:
            while not self._stopped.is_set() and stream.read(1):
                pass
        except (OSError, ValueError):
            pass
        if not self._stopped.is_set():
            callback()

    def set(self):
        self._stopped.set()

    def is_set(self):
        return self._stopped.is_set()

    def wait(self, timeout=None):
        return self._stopped.wait(timeout)

    def clear(self):
        self._stopped.clear()

    def is_alive(self):
        return self._thread.is_alive()

    def join(self, timeout=None):
        self._thread.join(timeout)


def watch_host_input(stream, on_eof=None):
    """Signal this Linux runner once on host EOF; never signal its children."""
    callback = on_eof or (lambda: os.kill(os.getpid(), signal.SIGTERM))
    return _HostInputWatcher(stream, callback)


def check_host_cancelled(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise KeyboardInterrupt('Scheduler termination requested')


def wait_owned_process(process, timeout, cancelled=None):
    deadline = time.monotonic() + timeout
    while True:
        check_host_cancelled(cancelled)
        code = process.poll()
        if code is not None:
            return code
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, timeout)
        time.sleep(min(.05, remaining))


def _append_preflight_cleanup_error(result, message):
    _append_cleanup_error(result, 'preflight_cleanup_error', message)


def _append_cleanup_error(result, key, message):
    existing = result.get(key)
    result[key] = (
        str(existing) + '; ' + str(message) if existing else str(message))


def _record_component_started(result, role):
    """Record a component handle as soon as its Popen call returns."""
    expected_roles = {'preflight', 'manager', 'collector'}
    started = result.get('components_started')
    if started is None:
        started = {name: False for name in expected_roles}
        result['components_started'] = started
    if (not isinstance(started, dict) or set(started) != expected_roles
            or any(type(value) is not bool for value in started.values())):
        raise RuntimeError('components_started schema is invalid')
    started[role] = True


def _reap_owned_handle(process, result, *, returncode_key, error_key, label):
    """Reap an owned direct child when group identity cannot be used."""
    def append(message):
        existing = result.get(error_key)
        result[error_key] = str(existing) + '; ' + str(message) if existing else str(message)

    try:
        live = process.poll() is None
    except BaseException as error:
        append(label+' handle poll failed: '+repr(error))
        live = True
    if live:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        except BaseException as error:
            append(label+' terminate failed: '+repr(error))
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired as error:
            append(repr(error))
        except BaseException as error:
            append(label+' wait failed: '+repr(error))
    try:
        live = process.poll() is None
    except BaseException as error:
        append(label+' handle poll failed: '+repr(error))
        live = True
    if live:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        except BaseException as error:
            append(label+' kill failed: '+repr(error))
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired as error:
            append(repr(error))
        except BaseException as error:
            append(label+' final wait failed: '+repr(error))
    try:
        result[returncode_key] = process.poll()
    except BaseException as error:
        append(label+' handle poll failed: '+repr(error))
        result[returncode_key] = None
    if result[returncode_key] is None:
        append('Owned '+label.lower()+' handle remains live')


def _reap_preflight_handle(process, result):
    """Reap an owned direct child when its procfs identity is unavailable."""
    _reap_owned_handle(process, result, returncode_key='preflight_returncode',
                       error_key='preflight_cleanup_error', label='Preflight')


def run_owned_preflight(command, stream, result, cancelled=None):
    """Track the static preflight separately so host loss cannot orphan it."""
    process = None
    expected = None
    snapshot = None
    try:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
        _record_component_started(result, 'preflight')
        try:
            expected = json_identity(process.pid)
        except BaseException as error:
            result['preflight_identity'] = None
            raise RuntimeError('Preflight identity unavailable') from error
        result['preflight_identity'] = expected
        if not isinstance(expected, dict):
            raise RuntimeError('Preflight identity unavailable')
        # Capture ownership while the leader is alive. This is the proof used
        # later if the leader exits before descendants in its private group.
        snapshot = manager_group_snapshot(process, expected)
        result['preflight_group_snapshot'] = [
            dict(pid=pid, start_ticks=start) for pid, start in sorted(snapshot)]
        code = wait_owned_process(process, 180, cancelled)
        result['preflight_returncode'] = code
        return code
    finally:
        if process is not None:
            if snapshot is None:
                _append_preflight_cleanup_error(result, 'Preflight group identity unavailable')
                _reap_preflight_handle(process, result)
                result['remaining_preflight_group'] = [True]
            else:
                previous_snapshot=snapshot
                if process.poll() is None:
                    try:
                        # The leader is still alive here, so refresh ownership
                        # immediately before signaling. This captures children
                        # created after the startup snapshot.
                        snapshot=manager_group_snapshot(process, expected)
                        result['preflight_group_snapshot']=[
                            dict(pid=pid,start_ticks=start)
                            for pid,start in sorted(snapshot)]
                    except BaseException as error:
                        # If the leader exited during the refresh race, retain
                        # only the prior leader-alive proof. A still-live leader
                        # cannot be group-killed from a stale snapshot.
                        if process.poll() is not None:
                            snapshot=previous_snapshot
                        else:
                            snapshot=None
                        _append_preflight_cleanup_error(
                            result,'Preflight group snapshot refresh failed: '+repr(error))
                try:
                    if process.poll() is None and snapshot is not None:
                        # The snapshot is mandatory: never signal an unverified
                        # group member while retiring this owned direct child.
                        kill_manager_group(process, expected, snapshot)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired as error:
                            _append_preflight_cleanup_error(result, repr(error))
                except BaseException as error:
                    _append_preflight_cleanup_error(result, repr(error))
                if snapshot is not None:
                    try:
                        # This also handles a leader that exited between snapshot
                        # and the first poll: only saved members qualify.
                        kill_manager_group_after_leader(expected, snapshot)
                    except BaseException as error:
                        _append_preflight_cleanup_error(result, repr(error))
                try:
                    still_live = process.poll() is None
                except BaseException as error:
                    _append_preflight_cleanup_error(result, 'Preflight handle poll failed: '+repr(error))
                    still_live = True
                if still_live:
                    _reap_preflight_handle(process, result)
                else:
                    try:
                        result['preflight_returncode'] = process.poll()
                    except BaseException as error:
                        _append_preflight_cleanup_error(result, 'Preflight handle poll failed: '+repr(error))
                        result['preflight_returncode'] = None
                try:
                    result['remaining_preflight_group'] = group_members(expected['pgid'])
                    if result['remaining_preflight_group']:
                        _append_preflight_cleanup_error(result, 'Owned preflight group remains')
                except BaseException as error:
                    _append_preflight_cleanup_error(result, repr(error))
                    result['remaining_preflight_group'] = [True]


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
                        timeout=CAPTURE_ACTIVE_TIMEOUT_S,token_schema=ACTIVE_SCHEMA,
                        token_state='active',token_phase=None):
    """Wait for one collector token, or fail closed on an identity mismatch."""
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
                    or value.get('schema')!=token_schema
                    or owner.get('schema')!='wksim.private-tracefs.instance-owner.v1'
                    or value.get('collector_pid')!=collector.pid
                    or owner.get('collector_pid')!=collector.pid
                    or value.get('collector_start_ticks')!=expected_collector['start_ticks']
                    or owner.get('collector_start_ticks')!=expected_collector['start_ticks']
                    or value.get('state')!=token_state
                    or token_phase is not None and value.get('phase')!=token_phase
                    or value.get('instance')!=owner.get('instance')
                    or value.get('instance_inode')!=owner.get('instance_inode')
                    or value.get('run_id')!=owner.get('run_id')
                    or value.get('epoch')!=owner.get('epoch')
                    or value.get('instance_owner_sha256')!=owner_sha256
                    or run_id is not None and value.get('run_id')!=run_id
                    or epoch is not None and value.get('epoch')!=epoch):
                raise RuntimeError('Capture-active token identity differs')
            token_started=value.get('started_monotonic_ns')
            token_published=value.get('published_monotonic_ns')
            if (type(token_started) is not int or token_started<=0
                    or type(token_published) is not int or token_published<token_started):
                raise RuntimeError('Capture-active token timing differs')
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
                      timeout=CAPTURE_ACTIVE_TIMEOUT_S,token_schema=ACTIVE_SCHEMA,
                      token_state='active',token_phase=None):
    """Require the supervisor to release exactly the selected collector token."""
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
                    or value.get('capture_token_sha256',value.get('capture_active_sha256'))!=active_sha256
                    or value.get('capture_token_schema',token_schema)!=token_schema
                    or value.get('instance_owner_sha256')!=owner_sha256
                    or value.get('gate_ready_sha256')!=digest(gate_ready_path)
                    or value.get('instance')!=owner.get('instance')
                    or value.get('instance_inode')!=owner.get('instance_inode')
                    or active.get('schema')!=token_schema
                    or active.get('state')!=token_state
                    or token_phase is not None and active.get('phase')!=token_phase
                    or active.get('instance_owner_sha256')!=owner_sha256
                    or type(value.get('tick')) is not int or value.get('tick')<0
                    or value.get('tick')>=EARLY_CAPTURE_TICK_LIMIT
                    or value.get('tick')!=gate_ready.get('tick')
                    or type(value.get('capture_token_published_monotonic_ns',value.get('capture_active_published_monotonic_ns'))) is not int
                    or type(value.get('released_monotonic_ns')) is not int
                    or value.get('capture_token_published_monotonic_ns',value.get('capture_active_published_monotonic_ns'))!=active.get('published_monotonic_ns')
                    # NOTE: the token's publication and the gate-ready publication are
                    # intentionally NOT ordered against each other; only the release is
                    # required to follow both (below).
                    or type(active.get('started_monotonic_ns')) is not int
                    or active.get('published_monotonic_ns')<active.get('started_monotonic_ns')
                    or value.get('released_monotonic_ns')<value.get('capture_token_published_monotonic_ns',value.get('capture_active_published_monotonic_ns'))
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
                                 release_path=None,gate_token=None):
    """Re-read the complete active/owner/release chain after collector retirement."""
    if release_path is None:
        raise RuntimeError('First-step gate-release proof path is required')
    active_token=Path(active_token)
    active,active_sha256=_read_proof(active_token,'Capture-active token')
    owner,owner_sha256=_read_instance_owner(active_token.parent/'instance-owner.json')
    gate_token_path=Path(gate_token) if gate_token is not None else active_token
    gate_token_value,gate_token_sha256=_read_proof(gate_token_path,'Capture gate token')
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
            or active.get('phase')!='filtered'
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
    bootstrap_gate=gate_token_path!=active_token
    release_published=release.get('capture_token_published_monotonic_ns',
                                   release.get('capture_active_published_monotonic_ns'))
    release_token_sha=release.get('capture_token_sha256',release.get('capture_active_sha256'))
    release_token_schema=release.get('capture_token_schema',ACTIVE_SCHEMA)
    if bootstrap_gate:
        bootstrap_started=gate_token_value.get('started_monotonic_ns')
        bootstrap_published=gate_token_value.get('published_monotonic_ns')
        if (gate_token_value.get('schema')!=BOOTSTRAP_SCHEMA
                or gate_token_value.get('state')!='bootstrap_active'
                or gate_token_value.get('phase')!='bootstrap_sched_switch'
                or gate_token_value.get('run_id')!=gate_ready.get('run_id')
                or gate_token_value.get('epoch')!=gate_ready.get('epoch')
                or gate_token_value.get('collector_pid')!=collector_pid
                or gate_token_value.get('collector_start_ticks')!=collector_start
                or gate_token_value.get('supervisor_pid')!=supervisor_pid
                or gate_token_value.get('supervisor_start_ticks')!=supervisor_start
                or gate_token_value.get('instance')!=owner.get('instance')
                or gate_token_value.get('instance_inode')!=owner.get('instance_inode')
                or gate_token_value.get('instance_owner_sha256')!=owner_sha256
                or type(bootstrap_started) is not int or bootstrap_started<=0
                or type(bootstrap_published) is not int
                # bootstrap start<=publish is required here; the bootstrap and
                # gate-ready publications are deliberately NOT ordered against each
                # other (both only need to precede the release, checked below).
                or bootstrap_published<bootstrap_started):
            raise RuntimeError('Bootstrap gate token identity differs after collector retirement')
        _validate_instance_owner(owner,gate_token_value,gate_ready,collector_identity,expected_owners)
    if (release.get('schema')!=GATE_RELEASE_SCHEMA
            or release.get('state')!='released'
            or release.get('run_id')!=gate_ready.get('run_id')
            or release.get('epoch')!=gate_ready.get('epoch')
            or release.get('supervisor_pid')!=supervisor_pid
            or release.get('supervisor_start_ticks')!=supervisor_start
            or release.get('collector_pid')!=collector_pid
            or release.get('collector_start_ticks')!=collector_start
            or release_token_sha!=(gate_token_sha256 if bootstrap_gate else active_sha256)
            or release_token_schema!=(BOOTSTRAP_SCHEMA if bootstrap_gate else ACTIVE_SCHEMA)
            or release.get('instance_owner_sha256')!=owner_sha256
            or release.get('gate_ready_sha256')!=gate_ready_sha256
            or release.get('instance')!=owner.get('instance')
            or release.get('instance_inode')!=owner.get('instance_inode')
            or release.get('tick')!=gate_ready.get('tick')
            or type(release_published) is not int or release_published<=0
            or release_published!=gate_token_value.get('published_monotonic_ns')
            or (not bootstrap_gate and release_published!=published)
            or type(released) is not int or released<=0
            or released<release_published
            or released<gate_ready.get('published_monotonic_ns')):
        raise RuntimeError('First-step gate-release proof identity differs after collector retirement')
    # Timing contract for the bootstrap gate (the #102-diagnostic correction):
    #   bootstrap start<=publish<=release, gate-ready publish<=release, and
    #   release<=formal start<=formal publish.  The bootstrap and gate-ready
    #   publications are NOT ordered against each other.  `released` is a validated
    #   positive int >= both publications (above), and `started`/`published` are
    #   validated positive ints with started<=publish (active-token check above),
    #   so the remaining new constraint is release<=formal start.
    if bootstrap_gate and not (released<=started<=published):
        raise RuntimeError('First-step gate-release proof timing order differs after collector retirement')
    return dict(owner=owner,sha256=owner_sha256,active_sha256=active_sha256,
                gate_token_sha256=gate_token_sha256,release_sha256=release_sha256)


def validate_capture_started_early(status_path,run_id,epoch,active,*,manager=None,
                                   collector=None,timeout=CAPTURE_ACTIVE_TIMEOUT_S,
                                   bootstrap=None):
    """Validate the formal token after the bootstrap gate has released.

    The bootstrap token and gate-release proof own the tick-zero/early-start
    contract.  A formal filtered token is checked for phase, ownership and
    strict ordering after bootstrap; it is deliberately not required to land
    before tick 40.
    """
    if (active.get('run_id') != run_id or active.get('epoch') != epoch
            or active.get('state') != 'active' or active.get('phase') != 'filtered'):
        raise RuntimeError('Capture-active token run/epoch identity differs')
    published=active.get('published_monotonic_ns')
    if (not isinstance(published,int) or isinstance(published,bool) or published<=0):
        raise RuntimeError('Capture-active token publication time is invalid')
    if bootstrap is not None:
        if (not isinstance(bootstrap,dict)
                or bootstrap.get('schema') != BOOTSTRAP_SCHEMA
                or bootstrap.get('state') != 'bootstrap_active'
                or bootstrap.get('phase') != 'bootstrap_sched_switch'
                or bootstrap.get('run_id') != run_id
                or bootstrap.get('epoch') != epoch):
            raise RuntimeError('Bootstrap token identity differs from formal capture')
        bootstrap_published=bootstrap.get('published_monotonic_ns')
        bootstrap_started=bootstrap.get('started_monotonic_ns')
        active_started=active.get('started_monotonic_ns')
        if (not isinstance(bootstrap_published,int) or bootstrap_published<=0
                or not isinstance(bootstrap_started,int) or bootstrap_started<=0
                or not isinstance(active_started,int) or active_started<=0
                or bootstrap_published < bootstrap_started
                or active_started < bootstrap_published
                or published <= bootstrap_published):
            raise RuntimeError('Formal capture token ordering differs from bootstrap')
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
                if bootstrap is None and tick >= EARLY_CAPTURE_TICK_LIMIT:
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
        _reap_owned_handle(collector, result, returncode_key='collector_returncode',
                           error_key='collector_cleanup_error', label='Collector')
    result['collector_returncode']=collector.poll()


def _record_collector_capture(output, result):
    """Retain the collector's raw terminal metadata after its retirement."""
    capture_path = Path(output) / 'capture' / 'metadata.json'
    try:
        capture = json.loads(capture_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        _append_cleanup_error(
            result, 'collector_cleanup_error',
            'Collector capture metadata is unavailable: '+repr(error))
        return
    if not isinstance(capture, dict):
        _append_cleanup_error(result, 'collector_cleanup_error',
                              'Collector capture metadata is malformed')
        result['capture'] = capture
        return
    # Preserve the collector's original complete/errors fields verbatim.  A
    # failed capture can still prove that its private instance was removed;
    # callers must see that partial evidence instead of a fabricated success.
    result['capture'] = capture
    owner_path = Path(output) / 'capture' / 'instance-owner.json'
    try:
        owner, owner_sha256 = _read_instance_owner(owner_path)
        result['capture_instance_owner'] = owner
        expected_collector = result.get('collector')
        _identity_subset_matches(
            {'pid': capture.get('collector_pid'),
             'start_ticks': capture.get('collector_start_ticks')},
            expected_collector, 'Capture collector')
        if (capture.get('schema') != 'wksim.private-tracefs.v1'
                or capture.get('run_id') != result.get('run_id')
                or capture.get('epoch') != result.get('epoch')
                or capture.get('instance') != owner.get('instance')
                or capture.get('instance_inode') != owner.get('instance_inode')
                or capture.get('collector_pid') != owner.get('collector_pid')
                or capture.get('collector_start_ticks') != owner.get('collector_start_ticks')):
            raise RuntimeError('Collector capture metadata identity differs')
        if owner.get('run_id') != result.get('run_id') or owner.get('epoch') != result.get('epoch'):
            raise RuntimeError('Capture instance owner run/epoch differs')
        if owner.get('boot_id') != result.get('boot_id'):
            raise RuntimeError('Capture instance owner boot identity differs')
        if (type(owner.get('instance')) is not str or not owner.get('instance')
                or type(owner.get('instance_inode')) is not list
                or len(owner['instance_inode']) != 2
                or any(type(value) is not int or value <= 0
                       for value in owner['instance_inode'])):
            raise RuntimeError('Capture instance owner fields are invalid')
        expected_owners = result.get('owners')
        _validate_expected_owners(owner.get('owners'), expected_owners)
        metadata_owners = capture.get('owners')
        if (not isinstance(metadata_owners, dict)
                or set(metadata_owners) != set(owner['owners'])):
            raise RuntimeError('Collector capture owner role set differs')
        for role, owner_identity in owner['owners'].items():
            _identity_subset_matches(metadata_owners.get(role), owner_identity,
                                     'Collector capture owner '+role)
        _identity_subset_matches(
            {'pid': owner.get('collector_pid'),
             'start_ticks': owner.get('collector_start_ticks')},
            expected_collector, 'Capture instance owner collector')
        _identity_subset_matches(
            {'pid': owner.get('supervisor_pid'),
             'start_ticks': owner.get('supervisor_start_ticks')},
            expected_owners.get('supervisor'), 'Capture instance owner supervisor')
        if owner_sha256 and capture.get('instance_owner_sha256') is not None:
            # The collector may include this digest in active-token metadata;
            # when present in the terminal capture it must bind to this file.
            if capture.get('instance_owner_sha256') != owner_sha256:
                raise RuntimeError('Collector capture owner digest differs')
    except BaseException as error:
        _append_cleanup_error(
            result, 'collector_cleanup_error',
            'Collector capture metadata validation failed: '+repr(error))


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
        previous_snapshot=group_snapshot
        try:
            # The leader is still alive here, so refresh ownership immediately
            # before signaling. Children may have appeared since startup.
            group_snapshot=save_manager_group_snapshot(manager,result)
        except BaseException as error:
            if manager.poll() is not None:
                # Once the leader is gone, only the previously verified
                # snapshot may be used to retire its former group.
                group_snapshot=previous_snapshot
            elif os.name != 'posix':
                # Windows has no verified group-kill path here; the helper
                # falls back to the owned Popen handle.  Keep the prior
                # value so the existing handle cleanup still runs.
                group_snapshot=previous_snapshot
            else:
                group_snapshot=None
            result['manager_cleanup_error']=str(result.get('manager_cleanup_error',''))+\
                '; refresh group snapshot: '+repr(error)
        if group_snapshot is not None or os.name != 'posix':
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
        if manager.poll() is None:
            _reap_owned_handle(manager, result, returncode_key='manager_returncode',
                               error_key='manager_cleanup_error', label='Manager')
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


def run(output, *, exchange_dir=None, watch_host_stdin=False):
    if exchange_dir is not None:
        exchange_dir = Path(exchange_dir)
        if (not exchange_dir.is_absolute() or exchange_dir.is_symlink()
                or not exchange_dir.is_dir() or exchange_dir.resolve() != exchange_dir):
            raise ValueError('Use an existing canonical shared exchange directory')
    if watch_host_stdin and exchange_dir is None:
        raise ValueError('Host stdin monitoring requires an exchange directory')
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
    bootstrap_token=capture_output/'capture-bootstrap-active.json'
    active_token=capture_output/'capture-active.json'
    hook_source = ROOT/'validation/rate-remediation-ff63c72/sitecustomize.py'
    shutil.copy2(hook_source, hook/'sitecustomize.py')
    command = ['taskset', '-c', '0-7', 'bash', str(ROOT/'tools/run-wksim.sh'),
               str(output/'experiment.json'), '--output-root', str(runs)]
    result = dict(status='diagnostic_partial', acceptance_eligible=False, run_id=run_id,
        directory=str(directory), command=command, boot_id=host_boot_id(),
        components_started=dict(preflight=False, manager=False, collector=False),
        started_monotonic_ns=time.monotonic_ns(), source_sha256={str(p.relative_to(ROOT)):digest(p) for p in (
            Path(__file__).resolve(), COLLECTOR, ROOT/'Simulator/wksim_core/worker.py',
            hook_source,
            ROOT/'Simulator/wksim_core/joint.py', ROOT/'Simulator/wksim_runtime/joint_rate.py',
            ROOT/'Simulator/wksim_runtime/joint_runtime.py')})
    manager = collector = None
    # Defer signal exceptions to explicit checkpoints, so child handles and
    # identities are recorded before cancellation enters the finally block.
    cancelled = threading.Event()
    host_watch = None
    if exchange_dir is not None:
        result['exchange_directory'] = str(exchange_dir)
        for name in ('tools/wsl_root_task_snapshot.py', 'tools/wsl_snapshot_exchange.py',
                     'tools/serve_wsl_snapshot_requests.py', 'tools/run_joint_scheduler_windows.py'):
            result['source_sha256'][name] = digest(ROOT/name)
    cleanup_handlers = install_cleanup_signal_handlers(cancelled)
    try:
        if watch_host_stdin:
            host_watch = watch_host_input(sys.stdin.buffer)
            check_host_cancelled(cancelled)
        with (output/'preflight.log').open('x') as stream:
            code = run_owned_preflight(command+['--preflight'], stream, result, cancelled)
        if code or result.get('preflight_cleanup_error'):
            raise RuntimeError('Resource preflight rejected probe or did not retire cleanly')
        check_host_cancelled(cancelled)
        with (output/'service.log').open('x') as service, (output/'collector.log').open('x') as trace_log:
            environment = dict(os.environ, WKSIM_JOINT_CPU_TIMING='1', WKSIM_TRACE_RUN=run_id,
                WKSIM_TRACE_HOOK_OUTPUT=str(hook), WKSIM_TRACE_GATE_READY=str(gate_ready),
                WKSIM_TRACE_GATE_RELEASE=str(gate_release),
                WKSIM_TRACE_CAPTURE_BOOTSTRAP_TOKEN=str(bootstrap_token),
                WKSIM_TRACE_CAPTURE_ACTIVE_TOKEN=str(active_token),
                PYTHONPATH=str(hook)+os.pathsep+os.environ.get('PYTHONPATH',''))
            result['diagnostic_environment'] = {k:environment[k] for k in (
                'WKSIM_JOINT_CPU_TIMING','WKSIM_TRACE_RUN','WKSIM_TRACE_HOOK_OUTPUT',
                'WKSIM_TRACE_GATE_READY','WKSIM_TRACE_GATE_RELEASE',
                'WKSIM_TRACE_CAPTURE_BOOTSTRAP_TOKEN','WKSIM_TRACE_CAPTURE_ACTIVE_TOKEN','PYTHONPATH')}
            manager = subprocess.Popen(command, cwd=ROOT, env=environment,
                stdout=service, stderr=subprocess.STDOUT, start_new_session=True)
            _record_component_started(result, 'manager')
            try:
                result['manager'] = json_identity(manager.pid)
                _identity_fields(result['manager'], 'Manager')
            except BaseException as error:
                result['manager'] = None
                raise RuntimeError('Manager identity unavailable') from error
            if os.name=='posix' and result['manager'] is not None:
                try:
                    save_manager_group_snapshot(manager,result)
                except (OSError,RuntimeError):
                    # Startup can race /proc task publication; the ownership-ready
                    # checkpoint below is the required pre-retirement snapshot.
                    pass
            write_json(output/'launch.json', result)
            deadline = time.monotonic()+180
            child_owners=None
            while True:
                check_host_cancelled(cancelled)
                if manager.poll() is not None: raise RuntimeError('Manager exited before native targets were ready')
                if time.monotonic() >= deadline: raise TimeoutError('Native target startup')
                status_path = directory/'status.json'
                if status_path.exists():
                    state = json.loads(status_path.read_text())
                    authority=state.get('authority',{})
                    if (state.get('phase') in ('faulted','stopped')
                            or isinstance(authority,dict) and authority.get('phase') in ('faulted','stopped')):
                        result['startup_readiness']=publish_startup_readiness(
                            output/'startup-readiness.json',state,child_owners)
                        result['startup_authority']=state
                        raise RuntimeError('Native target startup authority '+str(
                            state.get('phase') or authority.get('phase')))
                    child_path = directory/'epochs'/state['epoch']/'children.json'
                    if child_path.exists():
                        children = json.loads(child_path.read_text())
                        child_owners=complete_child_ownership(children,state.get('supervisor'))
                        if child_owners is not None:
                            if os.name=='posix':
                                save_manager_group_snapshot(manager,result)
                            break
                time.sleep(READY_POLL_S)
            owners = dict(ap_worker=child_owners['arducopter-model'],
                          px4_worker=child_owners['px4-model'], supervisor=state['supervisor'],
                          ap_fc=child_owners['arducopter-fc'],px4_fc=child_owners['px4-fc'])
            result.update(epoch=state['epoch'], owners=owners, capture_start_state=state)
            argv = [sys.executable, '-B', str(COLLECTOR), '--boot-id', result['boot_id'],
                    '--run-id', run_id, '--epoch', state['epoch'], '--duration', '10',
                    '--map-comm',
                    '--capture-bootstrap-token', str(bootstrap_token),
                    '--capture-active-token', str(active_token),
                    '--capture-gate-release', str(gate_release),
                    '--output', str(capture_output)]
            for role, identity in owners.items():
                argv += ['--'+role.replace('_', '-'), f"{identity['pid']}:{identity['start_ticks']}"]
            if exchange_dir is not None:
                argv += ['--exchange-dir', str(exchange_dir)]
            result['collector_command'] = argv
            collector = subprocess.Popen(argv, cwd=ROOT, stdout=trace_log,
                stderr=subprocess.STDOUT, start_new_session=True)
            _record_component_started(result, 'collector')
            try:
                result['collector'] = json_identity(collector.pid)
                _identity_fields(result['collector'], 'Collector')
            except BaseException as error:
                result['collector'] = None
                raise RuntimeError('Collector identity unavailable') from error
            write_json(output/'capture-launch.json', result)
            result['capture_bootstrap'] = wait_capture_active(
                bootstrap_token,collector,run_id,state['epoch'],manager=manager,
                collector_identity=result['collector'],supervisor_identity=owners['supervisor'],
                expected_owners=owners,token_schema=BOOTSTRAP_SCHEMA,
                token_state='bootstrap_active',token_phase='bootstrap_sched_switch')
            check_host_cancelled(cancelled)
            result['gate_ready'] = wait_gate_ready(gate_ready,run_id,state['epoch'],
                owners['supervisor'],manager=manager)
            check_host_cancelled(cancelled)
            result['startup_readiness']=publish_startup_readiness(
                output/'startup-readiness.json',state,owners,result['gate_ready'])
            result['gate_release'] = wait_gate_release(
                gate_release,result['gate_ready'],bootstrap_token,run_id,state['epoch'],collector,
                manager=manager,collector_identity=result['collector'],expected_owners=owners,
                token_schema=BOOTSTRAP_SCHEMA,token_state='bootstrap_active',
                token_phase='bootstrap_sched_switch')
            check_host_cancelled(cancelled)
            result['capture_active'] = wait_capture_active(
                active_token,collector,run_id,state['epoch'],manager=manager,
                collector_identity=result['collector'],supervisor_identity=owners['supervisor'],
                expected_owners=owners,token_phase='filtered')
            check_host_cancelled(cancelled)
            result['capture_active_status'] = validate_capture_started_early(
                directory/'status.json',run_id,state['epoch'],result['capture_active'],
                manager=manager,collector=collector,bootstrap=result['capture_bootstrap'])
            wait_owned_process(collector, 40, cancelled)
            result['collector_returncode'] = collector.returncode
            result['capture_owner_final'] = validate_capture_owner_final(
                active_token,result['gate_ready'],result['collector'],owners,gate_release,
                gate_token=bootstrap_token)
            result['last_observation'] = json.loads((directory/'status.json').read_text())
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = f'{type(error).__name__}: {error}'
    finally:
        if host_watch is not None:
            host_watch.set()
            host_watch.join(timeout=1)
            if host_watch.is_alive():
                result['host_watch_cleanup_error'] = 'Host stdin watcher did not stop'
        try:
            try:
                retire_collector(collector,result)
            except BaseException as error:
                result['collector_cleanup_error']=repr(error)
            if result.get('components_started', {}).get('collector'):
                _record_collector_capture(output, result)
            try:
                retire_manager(manager,directory,result)
            except BaseException as error:
                result['manager_cleanup_error']=repr(error)
            if (directory/'result.json').exists(): result['product_result'] = json.loads((directory/'result.json').read_text())
            result['epoch_groups_retired'] = epoch_groups_retired(result.get('product_result'))
            result['sources_unchanged'] = all(digest(ROOT/name) == sha for name, sha in result['source_sha256'].items())
            capture = result.get('capture')
            if (isinstance(capture, dict) and capture.get('complete') is True
                    and capture.get('instance_removed') is True
                    and failure_payload_clean(capture)
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
    parser.add_argument('--exchange-dir', type=Path)
    parser.add_argument('--watch-host-stdin', action='store_true')
    args = parser.parse_args()
    result = run(args.output, exchange_dir=args.exchange_dir, watch_host_stdin=args.watch_host_stdin)
    raise SystemExit(0 if result['status'] == 'diagnostic_captured_and_retired' else 1)
