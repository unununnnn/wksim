"""Private diagnostic-only names for namespace-to-kernel PID correlation.

Activated only through a per-run PYTHONPATH. Production files and process
policy are untouched; only the three exactly bound processes name themselves.
"""
import json
import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile
import time

run_id = os.environ.get('WKSIM_TRACE_RUN')
args = getattr(sys, 'orig_argv', [])
role = epoch = None
if run_id and 'Simulator.wksim_core.worker' in args:
    epoch = args[args.index('--epoch')+1]
    trace = Path(args[args.index('--trace')+1])
    if trace.parent.name == epoch and trace.parent.parent.parent.name == run_id:
        role = {'arducopter-truth.jsonl':'a', 'px4-truth.jsonl':'p'}.get(trace.name)
elif run_id and 'Simulator.wksim_runtime.joint_runtime' in args:
    index = args.index('Simulator.wksim_runtime.joint_runtime')
    directory, epoch = Path(args[index+1]), args[index+2]
    if directory.name == run_id: role = 's'
def assign_name():
    name = 'wk'+epoch[:11]+role
    Path('/proc/self/comm').write_text(name)
    assert Path('/proc/self/comm').read_text().strip() == name
    out = Path(os.environ['WKSIM_TRACE_HOOK_OUTPUT'])
    with (out/('name-'+role+'.json')).open('x') as stream:
        json.dump(dict(pid=os.getpid(),role=role,epoch=epoch,run_id=run_id,name=name,argv=args),stream)


GATE_TIMEOUT_S = 15.0


def _exclusive_json(path, value):
    """Publish one complete diagnostic proof without replacing an existing file."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(str(path))
    descriptor, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', suffix='.tmp',
                                               dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            descriptor = None
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            raise FileExistsError(str(path))
        os.link(temporary, path)
        os.unlink(temporary)
        temporary = None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _read_json(path, label):
    try:
        return json.loads(Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(label+' is unreadable') from error


def _positive_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(label+' is invalid')


def _inode(value, label):
    if (not isinstance(value, list) or len(value) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value)):
        raise RuntimeError(label+' is invalid')


def _self_start_ticks():
    raw = Path('/proc/self/stat').read_text()
    fields = raw[raw.rfind(')')+2:].split()
    if len(fields) <= 19:
        raise RuntimeError('Supervisor identity is unreadable')
    value = int(fields[19])
    _positive_int(value, 'Supervisor start time')
    return value


def _capture_active(token, gate_ready):
    """Read and bind either the bootstrap or filtered collector token."""
    token = Path(token)
    raw = token.read_bytes()
    active = json.loads(raw)
    owner_path = token.parent/'instance-owner.json'
    owner_raw = owner_path.read_bytes()
    owner = json.loads(owner_raw)
    owner_sha256 = hashlib.sha256(owner_raw).hexdigest()
    token_state = {'wksim.private-tracefs.capture-active.v1':('active','filtered'),
                   'wksim.private-tracefs.capture-bootstrap-active.v1':('bootstrap_active','bootstrap_sched_switch')}
    if (not isinstance(active, dict) or active.get('schema') not in token_state
            or (active.get('state'),active.get('phase')) != token_state.get(active.get('schema'))
            or active.get('run_id') != run_id or active.get('epoch') != epoch
            or not isinstance(owner, dict)
            or owner.get('schema') != 'wksim.private-tracefs.instance-owner.v1'
            or owner.get('run_id') != run_id or owner.get('epoch') != epoch
            or active.get('collector_pid') != owner.get('collector_pid')
            or active.get('collector_start_ticks') != owner.get('collector_start_ticks')
            or active.get('supervisor_pid') != owner.get('supervisor_pid')
            or active.get('supervisor_start_ticks') != owner.get('supervisor_start_ticks')
            or owner.get('supervisor_pid') != gate_ready.get('pid')
            or owner.get('supervisor_start_ticks') != gate_ready.get('start_ticks')
            or active.get('instance') != owner.get('instance')
            or active.get('instance_inode') != owner.get('instance_inode')
            or active.get('instance_owner_sha256') != owner_sha256
            or not isinstance(active.get('instance'), str) or not active.get('instance')
            or not isinstance(owner.get('instance'), str) or not owner.get('instance')):
        raise RuntimeError('Capture-active token identity differs')
    _positive_int(active.get('collector_pid'), 'Capture collector PID')
    _positive_int(active.get('collector_start_ticks'), 'Capture collector start time')
    _positive_int(owner.get('collector_pid'), 'Capture owner PID')
    _positive_int(owner.get('collector_start_ticks'), 'Capture owner start time')
    _positive_int(active.get('supervisor_pid'), 'Capture supervisor PID')
    _positive_int(active.get('supervisor_start_ticks'), 'Capture supervisor start time')
    _positive_int(owner.get('supervisor_pid'), 'Capture owner supervisor PID')
    _positive_int(owner.get('supervisor_start_ticks'), 'Capture owner supervisor start time')
    _inode(active.get('instance_inode'), 'Capture instance inode')
    _inode(owner.get('instance_inode'), 'Capture owner inode')
    _positive_int(active.get('started_monotonic_ns'), 'Capture start time')
    _positive_int(active.get('published_monotonic_ns'), 'Capture publication time')
    if active['published_monotonic_ns'] < active['started_monotonic_ns']:
        raise RuntimeError('Capture publication precedes capture start')
    return active, hashlib.sha256(raw).hexdigest(), owner_sha256


def _first_step_gate(frame):
    """Hold the first physical step until this run's trace window is active."""
    instance = frame.f_locals.get('self')
    clock = getattr(instance, 'clock', None)
    tick = getattr(clock, 'tick', None)
    if tick != 0:
        raise RuntimeError('Diagnostic first-step gate requires clock tick 0')
    bootstrap_name = os.environ.get('WKSIM_TRACE_CAPTURE_BOOTSTRAP_TOKEN')
    if not bootstrap_name:
        raise RuntimeError('First-step gate requires a bootstrap capture token')
    gate_ready = Path(os.environ['WKSIM_TRACE_GATE_READY'])
    gate_release = Path(os.environ['WKSIM_TRACE_GATE_RELEASE'])
    active_token = Path(bootstrap_name)
    start_ticks = _self_start_ticks()
    ready = dict(schema='wksim.private-tracefs.capture-gate-ready.v1', state='ready',
                 run_id=run_id, epoch=epoch, pid=os.getpid(), start_ticks=start_ticks, tick=tick,
                 published_monotonic_ns=time.monotonic_ns())
    _exclusive_json(gate_ready, ready)
    deadline = time.monotonic() + GATE_TIMEOUT_S
    active = None
    token_sha256 = None
    owner_sha256 = None
    while time.monotonic() < deadline:
        if active_token.exists():
            active, token_sha256, owner_sha256 = _capture_active(active_token, ready)
            break
        time.sleep(.010)
    if active is None:
        raise TimeoutError('Capture-active token was not published before first step')
    released_monotonic_ns = time.monotonic_ns()
    if (released_monotonic_ns < active['published_monotonic_ns']
            or released_monotonic_ns < ready['published_monotonic_ns']):
        raise RuntimeError('Capture release precedes capture publication')
    released = dict(schema='wksim.private-tracefs.capture-release.v1', state='released',
                    run_id=run_id, epoch=epoch, supervisor_pid=os.getpid(),
                    supervisor_start_ticks=start_ticks,
                    collector_pid=active['collector_pid'],
                    collector_start_ticks=active['collector_start_ticks'],
                    capture_token_sha256=token_sha256,
                    capture_token_schema=active['schema'],
                    instance_owner_sha256=owner_sha256,
                    instance=active['instance'], instance_inode=active['instance_inode'],
                    gate_ready_sha256=hashlib.sha256(gate_ready.read_bytes()).hexdigest(),
                    tick=tick, capture_token_published_monotonic_ns=active['published_monotonic_ns'],
                    released_monotonic_ns=released_monotonic_ns)
    _exclusive_json(gate_release, released)

if role and re.fullmatch('[0-9a-f]{32}', epoch or ''):
    if role == 's':
        # Name the main thread only after ROS/DDS initialization. Naming it at
        # interpreter startup makes its native helper threads inherit the same
        # comm and therefore prevents unambiguous kernel-TID correlation.
        previous_profile = sys.getprofile()
        def on_call(frame, event, argument):
            if (event == 'call' and frame.f_code.co_name == 'advance'
                    and frame.f_code.co_filename.replace('\\', '/').endswith('/Simulator/wksim_core/joint.py')):
                sys.setprofile(previous_profile)
                assign_name()
                _first_step_gate(frame)
        sys.setprofile(on_call)
    else:
        assign_name()
